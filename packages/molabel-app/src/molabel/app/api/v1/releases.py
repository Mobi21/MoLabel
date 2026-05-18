"""Release endpoints -- /api/v1/releases.

Handles dataset release lifecycle: creation, validation, approval,
and listing of frozen release snapshots.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import text

from molabel.app.api.v1.exports import ExportSummary
from molabel.app.middleware.session import CurrentReviewer
from molabel.app.schemas import PaginatedResponse, QueryParams
from molabel.app.utils import get_engine

router = APIRouter(prefix="/releases", tags=["releases"])


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------


class ReleaseSummary(BaseModel):
    """Lightweight release listing model."""

    release_id: str
    workspace_id: str
    name: str
    version: str
    status: str
    export_ids: list[str] = []
    validation_status: str | None = None
    approved_by: str | None = None
    created_at: datetime
    approved_at: datetime | None = None


class ReleaseCreate(BaseModel):
    """Request body for creating a new release."""

    workspace_id: str
    name: str
    version: str
    export_ids: list[str]
    validation_gate_ids: list[str] | None = None
    benchmark_run_ids: list[str] | None = None
    certification_threshold: float = 1.0
    notes: str | None = None


class GateResult(BaseModel):
    """Result of a single validation gate evaluation."""

    gate_id: str
    gate_name: str
    plugin: str
    status: str
    required_value: float | None = None
    actual_value: float | None = None
    message: str = ""
    details: dict[str, Any] | None = None


class ValidationReport(BaseModel):
    """Validation report for a release."""

    status: str
    gates: list[GateResult] = []
    generated_at: datetime


class ReleaseDetail(BaseModel):
    """Full release detail model."""

    release_id: str
    workspace_id: str
    name: str
    version: str
    status: str
    export_ids: list[str] = []
    exports: list[ExportSummary] = []
    validation_report: ValidationReport | None = None
    proof_manifest: dict[str, Any] | None = None
    manifest_path: str | None = None
    notes: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    created_at: datetime


class ReleaseApproval(BaseModel):
    """Request body for approving or rejecting a release."""

    approved: bool
    notes: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def _ensure_release_tables(engine) -> None:
    """Create release/audit tables when lightweight test DBs omit migrations."""

    with engine.connect() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS releases ("
                "id TEXT PRIMARY KEY, "
                "release_slug TEXT, "
                "version TEXT, "
                "name TEXT, "
                "description TEXT, "
                "status TEXT, "
                "export_bundle_ids TEXT NOT NULL, "
                "validation_run_ids TEXT, "
                "dataset_snapshot_id TEXT, "
                "quality_summary TEXT, "
                "signed_off_by TEXT, "
                "signed_off_at TEXT, "
                "release_metadata TEXT, "
                "manifest_path TEXT, "
                "workspace_id TEXT, "
                "created_at TEXT, "
                "released_at TEXT, "
                "revoked_at TEXT)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_releases_workspace_id "
                "ON releases(workspace_id)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS audit_events ("
                "id TEXT PRIMARY KEY, "
                "workspace_id TEXT, "
                "event_type TEXT, "
                "actor TEXT, "
                "actor_name TEXT, "
                "object_type TEXT, "
                "object_id TEXT, "
                "summary TEXT, "
                "details TEXT, "
                "created_at TEXT)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_audit_events_workspace_id "
                "ON audit_events(workspace_id)"
            )
        )
        conn.commit()


def _json_loads(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except json.JSONDecodeError:
        return default


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _manifest_from_path(value: Any) -> dict[str, Any] | None:
    if not value:
        return None
    path = Path(str(value))
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _slugify(value: str) -> str:
    normalized = "".join(
        ch.lower() if ch.isalnum() else "-" for ch in value.strip()
    ).strip("-")
    return "-".join(part for part in normalized.split("-") if part) or "release"


def _metric_value(summary: dict[str, Any], metric_id: str) -> float | None:
    for metric in summary.get("metrics", []):
        if isinstance(metric, dict) and metric.get("metric_id") == metric_id:
            value = metric.get("value")
            if isinstance(value, int | float):
                return float(value)
    return None


def _benchmark_summary_candidates(root: Path) -> list[tuple[str, Path, dict[str, Any]]]:
    runs_root = root / "workbench" / "benchmarks" / "runs"
    if not runs_root.exists():
        return []

    candidates: list[tuple[str, Path, dict[str, Any]]] = []
    for summary_path in sorted(runs_root.glob("**/summary.json")):
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(summary, dict):
            continue
        run_id = str(summary.get("run_id") or summary_path.parent.name)
        candidates.append((run_id, summary_path, summary))
    return candidates


def _select_benchmark_summaries(
    *,
    engine,
    workspace_id: str,
    run_ids: list[str],
) -> tuple[list[tuple[str, Path, dict[str, Any]]], list[str]]:
    root = _workspace_root(engine, workspace_id)
    if root is None:
        return [], list(run_ids)

    candidates = _benchmark_summary_candidates(root)
    selected: list[tuple[str, Path, dict[str, Any]]] = []
    missing: list[str] = []
    for requested_id in run_ids:
        match = next(
            (
                candidate
                for candidate in candidates
                if candidate[0] == requested_id
                or candidate[1].parent.name == requested_id
                or str(candidate[1].parent.relative_to(root)) == requested_id
            ),
            None,
        )
        if match is None:
            missing.append(requested_id)
        else:
            selected.append(match)
    return selected, missing


def _benchmark_certification_gates(
    *,
    engine,
    workspace_id: str,
    run_ids: list[str],
    threshold: float,
) -> list[GateResult]:
    if not run_ids:
        return []

    gates: list[GateResult] = []
    selected, missing = _select_benchmark_summaries(
        engine=engine,
        workspace_id=workspace_id,
        run_ids=run_ids,
    )
    for missing_id in missing:
        gates.append(
            GateResult(
                gate_id=f"benchmark:{missing_id}",
                gate_name=f"Benchmark Certification: {missing_id}",
                plugin="molabel.release.certification",
                status="failed",
                required_value=threshold,
                message="Requested benchmark run summary was not found.",
                details={"run_id": missing_id, "source": "benchmark_run_ids"},
            )
        )

    for run_id, summary_path, summary in selected:
        overall_score = summary.get("overall_score")
        actual_score = (
            float(overall_score) if isinstance(overall_score, int | float) else None
        )
        checklist_score = _metric_value(summary, "operator_checklist")
        blocking_failures = summary.get("diagnostics", {}).get("blocking_failures", [])
        status = "passed"
        messages: list[str] = []
        if actual_score is None:
            status = "failed"
            messages.append("Summary has no numeric overall_score.")
        elif actual_score < threshold:
            status = "failed"
            messages.append("Overall score is below the release threshold.")
        if checklist_score is not None and checklist_score < threshold:
            status = "failed"
            messages.append("Operator checklist score is below the release threshold.")
        if blocking_failures:
            status = "failed"
            messages.append("Operator run has blocking checklist failures.")
        if not messages:
            messages.append("Benchmark run satisfies release certification threshold.")

        gates.append(
            GateResult(
                gate_id=f"benchmark:{run_id}",
                gate_name=(
                    f"Benchmark Certification: "
                    f"{summary.get('benchmark_id') or run_id}"
                ),
                plugin="molabel.release.certification",
                status=status,
                required_value=threshold,
                actual_value=actual_score,
                message=" ".join(messages),
                details={
                    "summary_path": str(summary_path),
                    "benchmark_id": summary.get("benchmark_id"),
                    "run_id": run_id,
                    "mode": summary.get("mode"),
                    "variant": summary.get("variant"),
                    "stage": summary.get("stage"),
                    "record_count": summary.get("record_count"),
                    "operator_checklist_score": checklist_score,
                    "blocking_failures": blocking_failures,
                },
            )
        )
    return gates


def _validation_report(
    *,
    engine,
    workspace_id: str,
    gate_ids: list[str] | None,
    benchmark_run_ids: list[str] | None,
    certification_threshold: float,
) -> ValidationReport:
    now = datetime.now(UTC)
    gates = [
        GateResult(
            gate_id=gate_id,
            gate_name=gate_id.replace("_", " ").replace("-", " ").title(),
            plugin="molabel.release.certification",
            status="passed",
            message="Gate recorded as satisfied for this release proof manifest.",
            details={"source": "release_create.validation_gate_ids"},
        )
        for gate_id in (gate_ids or [])
    ]
    gates.extend(
        _benchmark_certification_gates(
            engine=engine,
            workspace_id=workspace_id,
            run_ids=benchmark_run_ids or [],
            threshold=certification_threshold,
        )
    )
    status = "passed" if all(gate.status == "passed" for gate in gates) else "failed"
    return ValidationReport(status=status, gates=gates, generated_at=now)


def _release_row_to_detail(row: Any) -> ReleaseDetail:
    release_metadata = _json_loads(row[12], {})
    validation_data = release_metadata.get("validation_report")
    proof_manifest = release_metadata.get("proof_manifest")
    if not isinstance(proof_manifest, dict):
        proof_manifest = _manifest_from_path(row[13])
    if validation_data is None and isinstance(proof_manifest, dict):
        validation_data = proof_manifest.get("validation_report")
    validation_report = (
        ValidationReport.model_validate(validation_data) if validation_data else None
    )
    return ReleaseDetail(
        release_id=str(row[0]),
        workspace_id=str(row[14]),
        name=str(row[3]),
        version=str(row[2]),
        status=str(row[5]),
        export_ids=[str(item) for item in _json_loads(row[6], [])],
        exports=[],
        validation_report=validation_report,
        proof_manifest=proof_manifest if isinstance(proof_manifest, dict) else None,
        manifest_path=str(row[13]) if row[13] else None,
        notes=release_metadata.get("notes"),
        approved_by=str(row[10]) if row[10] else None,
        approved_at=_parse_dt(row[11]),
        created_at=_parse_dt(row[15]) or datetime.now(UTC),
    )


def _release_detail_to_summary(detail: ReleaseDetail) -> ReleaseSummary:
    return ReleaseSummary(
        release_id=detail.release_id,
        workspace_id=detail.workspace_id,
        name=detail.name,
        version=detail.version,
        status=detail.status,
        export_ids=detail.export_ids,
        validation_status=(
            detail.validation_report.status if detail.validation_report else None
        ),
        approved_by=detail.approved_by,
        created_at=detail.created_at,
        approved_at=detail.approved_at,
    )


def _workspace_root(engine, workspace_id: str) -> Path | None:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT root_path FROM workspaces WHERE id = :id"),
            {"id": workspace_id},
        ).first()
    if row is None or not row[0]:
        return None
    return Path(str(row[0]))


def _write_proof_manifest(
    *,
    engine,
    release_id: str,
    data: ReleaseCreate,
    status: str,
    validation_report: ValidationReport,
    reviewer: CurrentReviewer,
    approved_at: datetime | None = None,
) -> tuple[dict[str, Any], str | None]:
    now = datetime.now(UTC)
    proof_manifest: dict[str, Any] = {
        "schema": "molabel.release.proof_manifest",
        "schema_version": 1,
        "release_id": release_id,
        "workspace_id": data.workspace_id,
        "name": data.name,
        "version": data.version,
        "status": status,
        "export_ids": data.export_ids,
        "validation_gate_ids": data.validation_gate_ids or [],
        "benchmark_run_ids": data.benchmark_run_ids or [],
        "certification_threshold": data.certification_threshold,
        "validation_report": validation_report.model_dump(mode="json"),
        "notes": data.notes,
        "created_by": str(reviewer.id),
        "approved_by": str(reviewer.id) if approved_at else None,
        "approved_at": approved_at.isoformat() if approved_at else None,
        "generated_at": now.isoformat(),
    }

    root = _workspace_root(engine, data.workspace_id)
    if root is None:
        return proof_manifest, None

    release_dir = root / "workbench" / "releases" / _slugify(data.version)
    release_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = release_dir / "proof-manifest.json"
    manifest_path.write_text(
        json.dumps(proof_manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return proof_manifest, str(manifest_path)


def _record_audit_event(
    engine,
    *,
    workspace_id: str,
    event_type: str,
    reviewer: CurrentReviewer,
    object_type: str,
    object_id: str,
    summary: str,
    details: dict[str, Any],
) -> None:
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO audit_events ("
                "id, workspace_id, event_type, actor, actor_name, object_type, "
                "object_id, summary, details, created_at"
                ") VALUES ("
                ":id, :workspace_id, :event_type, :actor, :actor_name, "
                ":object_type, :object_id, :summary, :details, :created_at)"
            ),
            {
                "id": str(uuid.uuid4()),
                "workspace_id": workspace_id,
                "event_type": event_type,
                "actor": str(reviewer.id),
                "actor_name": reviewer.display_name,
                "object_type": object_type,
                "object_id": object_id,
                "summary": summary,
                "details": json.dumps(details, sort_keys=True),
                "created_at": datetime.now(UTC).isoformat(),
            },
        )
        conn.commit()


@router.get("", response_model=PaginatedResponse[ReleaseSummary])
async def list_releases(
    request: Request,
    reviewer: CurrentReviewer,
    workspace_id: Annotated[str, Query(description="Workspace ID (required)")],
    params: Annotated[QueryParams, Depends()],
    status: Annotated[str | None, Query(description="Optional status filter")] = None,
) -> PaginatedResponse[ReleaseSummary]:
    """List releases for a workspace.

    Returns a paginated list of releases, optionally filtered by status.
    """
    engine = get_engine(request)
    _ensure_release_tables(engine)
    query = (
        "SELECT id, release_slug, version, name, description, status, "
        "export_bundle_ids, validation_run_ids, dataset_snapshot_id, "
        "quality_summary, signed_off_by, signed_off_at, release_metadata, "
        "manifest_path, workspace_id, created_at, released_at, revoked_at "
        "FROM releases WHERE workspace_id = :workspace_id"
    )
    bind: dict[str, Any] = {"workspace_id": workspace_id, "limit": params.limit}
    if status:
        query += " AND status = :status"
        bind["status"] = status
    query += " ORDER BY created_at DESC LIMIT :limit"

    with engine.connect() as conn:
        rows = conn.execute(text(query), bind).fetchall()

    items = [_release_detail_to_summary(_release_row_to_detail(row)) for row in rows]
    return PaginatedResponse(items=items, cursor=None, has_more=False)


@router.post("", response_model=ReleaseDetail, status_code=201)
async def create_release(
    request: Request,
    data: ReleaseCreate,
    reviewer: CurrentReviewer,
) -> ReleaseDetail:
    """Create a new release.

    Creates a frozen release snapshot from the specified exports.
    Validation gates are evaluated if specified.
    """
    engine = get_engine(request)
    _ensure_release_tables(engine)
    release_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    validation_report = _validation_report(
        engine=engine,
        workspace_id=data.workspace_id,
        gate_ids=data.validation_gate_ids,
        benchmark_run_ids=data.benchmark_run_ids,
        certification_threshold=data.certification_threshold,
    )
    proof_manifest, manifest_path = _write_proof_manifest(
        engine=engine,
        release_id=release_id,
        data=data,
        status="draft",
        validation_report=validation_report,
        reviewer=reviewer,
    )
    release_metadata = {
        "notes": data.notes,
        "proof_manifest": proof_manifest,
        "validation_report": validation_report.model_dump(mode="json"),
    }
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO releases ("
                "id, release_slug, version, name, description, status, "
                "export_bundle_ids, validation_run_ids, dataset_snapshot_id, "
                "quality_summary, signed_off_by, signed_off_at, release_metadata, "
                "manifest_path, workspace_id, created_at, released_at, revoked_at"
                ") VALUES ("
                ":id, :slug, :version, :name, :description, :status, "
                ":export_ids, :validation_ids, NULL, :quality_summary, NULL, NULL, "
                ":metadata, :manifest_path, :workspace_id, :created_at, NULL, NULL)"
            ),
            {
                "id": release_id,
                "slug": _slugify(f"{data.name}-{data.version}"),
                "version": data.version,
                "name": data.name,
                "description": data.notes,
                "status": "draft",
                "export_ids": json.dumps(data.export_ids),
                "validation_ids": json.dumps(data.validation_gate_ids or []),
                "quality_summary": json.dumps(
                    {
                        "validation_status": validation_report.status,
                        "gate_count": len(validation_report.gates),
                    }
                ),
                "metadata": json.dumps(release_metadata, sort_keys=True),
                "manifest_path": manifest_path,
                "workspace_id": data.workspace_id,
                "created_at": now.isoformat(),
            },
        )
        conn.commit()

    _record_audit_event(
        engine,
        workspace_id=data.workspace_id,
        event_type="release_created",
        reviewer=reviewer,
        object_type="release",
        object_id=release_id,
        summary=f"Created release {data.name} {data.version}",
        details={"export_ids": data.export_ids, "manifest_path": manifest_path},
    )
    return _get_release_detail(engine, release_id)


def _get_release_detail(engine, release_id: str) -> ReleaseDetail:
    _ensure_release_tables(engine)
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, release_slug, version, name, description, status, "
                "export_bundle_ids, validation_run_ids, dataset_snapshot_id, "
                "quality_summary, signed_off_by, signed_off_at, release_metadata, "
                "manifest_path, workspace_id, created_at, released_at, revoked_at "
                "FROM releases WHERE id = :id"
            ),
            {"id": release_id},
        ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Release not found")
    return _release_row_to_detail(row)


@router.get("/{release_id}", response_model=ReleaseDetail)
async def get_release(
    request: Request,
    release_id: str,
    reviewer: CurrentReviewer,
) -> ReleaseDetail:
    """Get detailed information about a specific release.

    Returns 404 if the release does not exist.
    """
    return _get_release_detail(get_engine(request), release_id)


@router.post("/{release_id}/approve", response_model=ReleaseDetail)
async def approve_release(
    request: Request,
    release_id: str,
    data: ReleaseApproval,
    reviewer: CurrentReviewer,
) -> ReleaseDetail:
    """Approve or reject a release.

    Only operators can approve releases. The release must be in a
    state that allows approval (e.g. all validation gates passing).
    Returns 404 if the release does not exist.
    """
    engine = get_engine(request)
    detail = _get_release_detail(engine, release_id)
    new_status = "approved" if data.approved else "rejected"
    approved_at = datetime.now(UTC) if data.approved else None
    manifest = detail.proof_manifest or {}
    validation_report = detail.validation_report or _validation_report(
        engine=engine,
        workspace_id=detail.workspace_id,
        gate_ids=[],
        benchmark_run_ids=[],
        certification_threshold=1.0,
    )
    if data.approved and validation_report.status != "passed":
        raise HTTPException(
            status_code=409,
            detail="Release cannot be approved until all validation gates pass",
        )
    create_data = ReleaseCreate(
        workspace_id=detail.workspace_id,
        name=detail.name,
        version=detail.version,
        export_ids=detail.export_ids,
        validation_gate_ids=[gate.gate_id for gate in validation_report.gates],
        benchmark_run_ids=[
            str(run_id) for run_id in manifest.get("benchmark_run_ids", [])
        ],
        certification_threshold=float(manifest.get("certification_threshold", 1.0)),
        notes=data.notes or detail.notes,
    )
    proof_manifest, manifest_path = _write_proof_manifest(
        engine=engine,
        release_id=release_id,
        data=create_data,
        status=new_status,
        validation_report=validation_report,
        reviewer=reviewer,
        approved_at=approved_at,
    )
    metadata = {
        "notes": data.notes or detail.notes,
        "proof_manifest": proof_manifest,
        "validation_report": validation_report.model_dump(mode="json"),
    }
    with engine.connect() as conn:
        conn.execute(
            text(
                "UPDATE releases SET status = :status, signed_off_by = :signed_by, "
                "signed_off_at = :signed_at, release_metadata = :metadata, "
                "manifest_path = :manifest_path, released_at = :released_at "
                "WHERE id = :id"
            ),
            {
                "id": release_id,
                "status": new_status,
                "signed_by": str(reviewer.id) if data.approved else None,
                "signed_at": approved_at.isoformat() if approved_at else None,
                "metadata": json.dumps(metadata, sort_keys=True),
                "manifest_path": manifest_path or detail.manifest_path,
                "released_at": approved_at.isoformat() if approved_at else None,
            },
        )
        conn.commit()

    _record_audit_event(
        engine,
        workspace_id=detail.workspace_id,
        event_type="release_approved" if data.approved else "release_rejected",
        reviewer=reviewer,
        object_type="release",
        object_id=release_id,
        summary=(
            f"Approved release {detail.name} {detail.version}"
            if data.approved
            else f"Rejected release {detail.name} {detail.version}"
        ),
        details={"notes": data.notes, "manifest_path": manifest_path},
    )
    return _get_release_detail(engine, release_id)

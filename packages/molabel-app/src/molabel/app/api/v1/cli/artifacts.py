"""CLI selector resolution and artifact read/write endpoints."""

from __future__ import annotations

import difflib
import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from molabel.app.api.v1.cli.deps import CurrentCliReviewer
from molabel.app.utils import get_engine
from molabel.core.export.atomic_writer import AtomicWriter

router = APIRouter(prefix="", tags=["cli"])

ArtifactKind = Literal[
    "workspace_manifest",
    "workflow",
    "prompt",
    "task_schema",
]

SelectorKind = Literal[
    "workspace",
    "workspace_manifest",
    "dataset",
    "workflow",
    "prompt",
    "task_schema",
    "snapshot",
]


class SelectorResolveRequest(BaseModel):
    kind: SelectorKind
    selector: str
    workspace_id: str | None = None
    workspace_root: str | None = None


class SelectorResolveResponse(BaseModel):
    kind: SelectorKind
    selector: str
    resolved: bool = False
    resolved_id: str | None = None
    resolved_path: str | None = None
    display_name: str | None = None
    version: str | None = None
    workspace_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactReadRequest(BaseModel):
    kind: ArtifactKind
    selector: str
    workspace_id: str | None = None
    workspace_root: str | None = None


class ArtifactReadResponse(BaseModel):
    kind: ArtifactKind
    selector: str
    resolved_path: str
    exists: bool
    content: str | None = None
    content_hash: str | None = None
    file_size_bytes: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactDiffRequest(BaseModel):
    kind: ArtifactKind
    selector: str
    content: str
    workspace_id: str | None = None
    workspace_root: str | None = None
    expected_hash: str | None = None


class ArtifactDiffResponse(BaseModel):
    kind: ArtifactKind
    selector: str
    resolved_path: str
    current_hash: str | None = None
    new_hash: str
    has_conflict: bool
    diff: str


class ArtifactWriteRequest(BaseModel):
    kind: ArtifactKind
    selector: str
    content: str
    workspace_id: str | None = None
    workspace_root: str | None = None
    expected_hash: str | None = None


class ArtifactWriteResponse(BaseModel):
    kind: ArtifactKind
    selector: str
    resolved_path: str
    success: bool
    content_hash: str
    file_size_bytes: int
    previous_path: str | None = None


class ArtifactProposalCreateRequest(ArtifactDiffRequest):
    """Create a durable semantic diff proposal for later accept/reject."""

    title: str | None = None
    rationale: str | None = None
    run_id: str | None = None


class ArtifactProposalResponse(BaseModel):
    proposal_id: str
    kind: ArtifactKind
    selector: str
    resolved_path: str
    status: Literal["proposed", "accepted", "rejected", "conflicted"]
    current_hash: str | None = None
    new_hash: str
    has_conflict: bool
    diff: str
    proposal_path: str
    title: str | None = None
    rationale: str | None = None
    run_id: str | None = None
    created_by: str | None = None
    created_at: datetime
    decided_by: str | None = None
    decided_at: datetime | None = None
    decision_notes: str | None = None
    write_result: ArtifactWriteResponse | None = None


class ArtifactTraceResponse(BaseModel):
    proposal_id: str
    proposal: dict[str, Any]
    trace: dict[str, Any]


class ArtifactProposalDecisionRequest(BaseModel):
    decision: Literal["accept", "reject"]
    workspace_id: str | None = None
    workspace_root: str | None = None
    notes: str | None = None


def _workspace_root_from_request(workspace_root: str | None) -> Path:
    if workspace_root is not None:
        return Path(workspace_root).expanduser().resolve()
    return Path.cwd().resolve()


def _selector_looks_like_path(selector: str) -> bool:
    return (
        selector.startswith(".")
        or "/" in selector
        or "\\" in selector
        or Path(selector).is_absolute()
    )


def _canonical_artifact_relative_path(
    *,
    kind: ArtifactKind,
    selector: str,
) -> Path | None:
    canonical_roots: dict[ArtifactKind, tuple[str, str]] = {
        "workflow": ("workbench/workflows", ".yaml"),
        "prompt": ("workbench/prompts", ".yaml"),
        "task_schema": ("workbench/config/task-schemas", ".yaml"),
        "workspace_manifest": ("", ""),
    }
    if kind == "workspace_manifest":
        return Path("workbench.project.yaml")

    mapping = canonical_roots.get(kind)
    if mapping is None or _selector_looks_like_path(selector):
        return None

    directory, extension = mapping
    filename = selector if selector.endswith(extension) else f"{selector}{extension}"
    return Path(directory) / filename


def _hash_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _hash_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _proposal_id() -> str:
    return str(uuid.uuid4())


def _ensure_within_root(root: Path, candidate: Path) -> Path:
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise HTTPException(status_code=400, detail="Resolved path escapes workspace")
    return resolved


def _proposal_root(workspace_root: str | None) -> Path:
    root = _workspace_root_from_request(workspace_root)
    proposal_root = root / "workbench" / "proposals" / "artifacts"
    proposal_root.mkdir(parents=True, exist_ok=True)
    return proposal_root


def _proposal_path(workspace_root: str | None, proposal_id: str) -> Path:
    try:
        uuid.UUID(proposal_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid proposal id") from exc
    return _proposal_root(workspace_root) / f"{proposal_id}.json"


def _load_proposal(workspace_root: str | None, proposal_id: str) -> dict[str, Any]:
    path = _proposal_path(workspace_root, proposal_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Artifact proposal not found")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500,
            detail="Artifact proposal is not valid JSON",
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=500, detail="Artifact proposal is malformed")
    return payload


def _write_proposal(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _proposal_response(payload: dict[str, Any]) -> ArtifactProposalResponse:
    return ArtifactProposalResponse.model_validate(payload)


def _audit_events_for_object(
    request: Request,
    *,
    workspace_id: str | None,
    object_id: str,
) -> list[dict[str, Any]]:
    engine = get_engine(request)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT id, workspace_id, event_type, actor, actor_name, "
                    "object_type, object_id, summary, details, created_at "
                    "FROM audit_events "
                    "WHERE object_id = :object_id "
                    "AND (:workspace_id IS NULL OR workspace_id = :workspace_id) "
                    "ORDER BY created_at ASC"
                ),
                {"object_id": object_id, "workspace_id": workspace_id},
            ).mappings()
            events: list[dict[str, Any]] = []
            for row in rows:
                details_raw = row.get("details")
                details: dict[str, Any] = {}
                if isinstance(details_raw, str) and details_raw:
                    try:
                        parsed = json.loads(details_raw)
                        if isinstance(parsed, dict):
                            details = parsed
                    except json.JSONDecodeError:
                        details = {"raw": details_raw}
                events.append(
                    {
                        "id": row.get("id"),
                        "workspace_id": row.get("workspace_id"),
                        "event_type": row.get("event_type"),
                        "actor": row.get("actor"),
                        "actor_name": row.get("actor_name"),
                        "object_type": row.get("object_type"),
                        "object_id": row.get("object_id"),
                        "summary": row.get("summary"),
                        "details": details,
                        "created_at": row.get("created_at"),
                    }
                )
            return events
    except Exception:
        return []


def _release_links_for_proposal(
    *,
    workspace_root: str | None,
    proposal_id: str,
    resolved_path: str | None,
) -> list[dict[str, Any]]:
    root = _workspace_root_from_request(workspace_root)
    releases_root = root / "workbench" / "releases"
    if not releases_root.exists():
        return []

    links: list[dict[str, Any]] = []
    for manifest_path in releases_root.glob("**/proof-manifest.json"):
        try:
            manifest_text = manifest_path.read_text(encoding="utf-8")
            manifest = json.loads(manifest_text)
        except (OSError, json.JSONDecodeError):
            continue
        if proposal_id not in manifest_text and (
            resolved_path is None or resolved_path not in manifest_text
        ):
            continue
        links.append(
            {
                "release_id": manifest.get("release_id"),
                "version": manifest.get("version"),
                "status": manifest.get("status"),
                "manifest_path": str(manifest_path),
            }
        )
    return links


def _build_artifact_trace(
    request: Request,
    *,
    payload: dict[str, Any],
    workspace_root: str | None,
    workspace_id: str | None,
) -> dict[str, Any]:
    resolved_path = str(payload.get("resolved_path") or "")
    current_hash = _hash_file(Path(resolved_path)) if resolved_path else None
    expected_hash = payload.get("expected_hash") or payload.get("current_hash")
    proposal_id = str(payload["proposal_id"])
    audit_events = _audit_events_for_object(
        request,
        workspace_id=workspace_id,
        object_id=proposal_id,
    )
    return {
        "schema": "molabel.artifact.trace",
        "proposal_id": proposal_id,
        "kind": payload.get("kind"),
        "selector": payload.get("selector"),
        "target_path": resolved_path or None,
        "run_id": payload.get("run_id"),
        "created_by": payload.get("created_by"),
        "created_at": payload.get("created_at"),
        "decided_by": payload.get("decided_by"),
        "decided_at": payload.get("decided_at"),
        "decision_notes": payload.get("decision_notes"),
        "status": payload.get("status"),
        "source_hash": payload.get("current_hash"),
        "expected_hash": expected_hash,
        "proposed_hash": payload.get("new_hash"),
        "current_hash": current_hash,
        "hashes_match_original": (
            current_hash == expected_hash if current_hash and expected_hash else None
        ),
        "hashes_match_proposal": (
            current_hash == payload.get("new_hash")
            if current_hash and payload.get("new_hash")
            else None
        ),
        "has_conflict": payload.get("has_conflict"),
        "proposal_path": payload.get("proposal_path"),
        "write_result": payload.get("write_result"),
        "audit_event_ids": [event["id"] for event in audit_events if event.get("id")],
        "audit_events": audit_events,
        "release_links": _release_links_for_proposal(
            workspace_root=workspace_root,
            proposal_id=proposal_id,
            resolved_path=resolved_path or None,
        ),
    }


def _record_audit_event(
    request: Request,
    *,
    reviewer: CurrentCliReviewer,
    workspace_id: str | None,
    event_type: str,
    object_id: str,
    summary: str,
    details: dict[str, Any],
) -> None:
    engine = get_engine(request)
    with engine.connect() as conn:
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
                "INSERT INTO audit_events ("
                "id, workspace_id, event_type, actor, actor_name, object_type, "
                "object_id, summary, details, created_at"
                ") VALUES ("
                ":id, :workspace_id, :event_type, :actor, :actor_name, "
                ":object_type, :object_id, :summary, :details, :created_at)"
            ),
            {
                "id": str(uuid.uuid4()),
                "workspace_id": workspace_id or str(reviewer.workspace_id),
                "event_type": event_type,
                "actor": str(reviewer.id),
                "actor_name": reviewer.display_name,
                "object_type": "artifact_proposal",
                "object_id": object_id,
                "summary": summary,
                "details": json.dumps(details, sort_keys=True),
                "created_at": datetime.now(UTC).isoformat(),
            },
        )
        conn.commit()


def _query_one(engine: Any, sql: str, params: dict[str, Any]) -> Any | None:
    with engine.connect() as conn:
        return conn.execute(text(sql), params).first()


def _resolve_db_artifact(
    request: Request,
    *,
    kind: ArtifactKind,
    selector: str,
    workspace_id: str | None,
) -> tuple[str, Path, dict[str, Any]]:
    engine = get_engine(request)
    if kind == "workspace_manifest":
        if workspace_id is None:
            row = _query_one(
                engine,
                (
                    "SELECT id, workspace_name, root_path, manifest_path "
                    "FROM workspaces "
                    "WHERE root_path = :selector "
                    "OR workspace_name = :selector "
                    "OR id = :selector LIMIT 1"
                ),
                {"selector": selector},
            )
        else:
            row = _query_one(
                engine,
                "SELECT id, workspace_name, root_path, manifest_path "
                "FROM workspaces WHERE id = :wid LIMIT 1",
                {"wid": workspace_id},
            )
        if row is None:
            raise HTTPException(status_code=404, detail="Workspace not found")
        root = Path(str(row[2])).expanduser().resolve()
        manifest = Path(str(row[3] or "workbench.project.yaml"))
        if not manifest.is_absolute():
            manifest = root / manifest
        path = _ensure_within_root(root, manifest)
        return str(row[0]), path, {"workspace_name": str(row[1])}

    if kind == "dataset":
        sql = (
            "SELECT id, dataset_slug, NULL, dataset_name, NULL, NULL "
            "FROM datasets "
            "WHERE (id = :selector "
            "OR dataset_slug = :selector "
            "OR dataset_name = :selector)"
        )
        params: dict[str, Any] = {"selector": selector}
        if workspace_id is not None:
            sql += " AND workspace_id = :workspace_id"
            params["workspace_id"] = workspace_id
        row = _query_one(engine, sql + " LIMIT 1", params)
        if row is None:
            raise HTTPException(status_code=404, detail="dataset not found")
        return str(row[0]), Path("."), {"slug": str(row[1]), "label": str(row[3])}

    if kind == "snapshot":
        sql = (
            "SELECT dataset_snapshots.id, NULL, NULL, dataset_snapshots.name, "
            "workspaces.root_path, NULL "
            "FROM dataset_snapshots "
            "JOIN workspaces ON workspaces.id = dataset_snapshots.workspace_id "
            "WHERE (dataset_snapshots.id = :selector "
            "OR dataset_snapshots.name = :selector)"
        )
        params = {"selector": selector}
        if workspace_id is not None:
            sql += " AND dataset_snapshots.workspace_id = :workspace_id"
            params["workspace_id"] = workspace_id
        row = _query_one(engine, sql + " LIMIT 1", params)
        if row is None:
            raise HTTPException(status_code=404, detail="snapshot not found")
        root = Path(str(row[4])).expanduser().resolve()
        snapshot_path = root / "workbench" / "snapshots" / f"{row[0]}.json"
        return str(row[0]), snapshot_path, {"label": str(row[3])}

    table_map = {
        "workflow": ("workflow_definitions", "workflow_slug", "file_path", "name"),
        "prompt": ("prompt_templates", "prompt_slug", "file_path", "name"),
        "task_schema": ("task_schemas", "task_schema_slug", "file_path", "title"),
    }
    table, slug_column, file_column, label_column = table_map[kind]

    if kind == "workflow" or kind == "prompt":
        sql = (
            f"SELECT {table}.id, {table}.{slug_column}, {table}.{file_column}, "
            f"{table}.{label_column}, workspaces.root_path, {table}.version "
            f"FROM {table} JOIN workspaces ON workspaces.id = {table}.workspace_id "
            f"WHERE ({table}.id = :selector OR {table}.{slug_column} = :selector "
            f"OR {table}.name = :selector OR {table}.{file_column} = :selector)"
        )
        params = {"selector": selector}
        if workspace_id is not None:
            sql += f" AND {table}.workspace_id = :workspace_id"
            params["workspace_id"] = workspace_id
    else:
        sql = (
            f"SELECT {table}.id, {table}.{slug_column}, {table}.{file_column}, "
            f"{table}.{label_column}, workspaces.root_path, NULL "
            f"FROM {table} JOIN workspaces ON workspaces.id = {table}.workspace_id "
            f"WHERE ({table}.id = :selector OR {table}.{slug_column} = :selector "
            f"OR {table}.{file_column} = :selector)"
        )
        params = {"selector": selector}
        if workspace_id is not None:
            sql += f" AND {table}.workspace_id = :workspace_id"
            params["workspace_id"] = workspace_id

    row = _query_one(engine, sql + " LIMIT 1", params)
    if row is None:
        raise HTTPException(status_code=404, detail=f"{kind} not found")

    root = Path(str(row[4])).expanduser().resolve()
    file_path = str(row[2]) if row[2] else None
    if file_path is None:
        raise HTTPException(status_code=404, detail="Artifact file path unavailable")
    path = Path(file_path)
    if not path.is_absolute():
        path = root / path
    path = _ensure_within_root(root, path)
    metadata = {
        "slug": str(row[1]),
        "label": str(row[3]),
        "version": str(row[5]) if row[5] is not None else None,
    }
    return str(row[0]), path, metadata


def _resolve_artifact_path(
    request: Request,
    *,
    kind: ArtifactKind,
    selector: str,
    workspace_root: str | None,
    workspace_id: str | None,
) -> tuple[Path, dict[str, Any]]:
    if kind == "workspace_manifest":
        root = _workspace_root_from_request(workspace_root)
        return root / "workbench.project.yaml", {}

    try:
        _artifact_id, path, metadata = _resolve_db_artifact(
            request,
            kind=kind,
            selector=selector,
            workspace_id=workspace_id,
        )
        return path, metadata
    except HTTPException:
        root = _workspace_root_from_request(workspace_root)
        canonical = _canonical_artifact_relative_path(kind=kind, selector=selector)
        if canonical is not None:
            return _ensure_within_root(root, root / canonical), {}

        candidate = Path(selector)
        if not candidate.is_absolute():
            candidate = root / candidate
        return _ensure_within_root(root, candidate), {}


@router.post("/selectors/resolve", response_model=SelectorResolveResponse)
async def resolve_selector(
    request: Request,
    body: SelectorResolveRequest,
) -> SelectorResolveResponse:
    """Resolve a CLI selector into a concrete path or database id."""
    if body.kind == "workspace":
        engine = get_engine(request)
        row = _query_one(
            engine,
            "SELECT id, workspace_name, root_path, manifest_path "
            "FROM workspaces WHERE id = :selector OR workspace_name = :selector "
            "OR root_path = :selector LIMIT 1",
            {"selector": body.selector},
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Workspace not found")
        return SelectorResolveResponse(
            kind=body.kind,
            selector=body.selector,
            resolved=True,
            resolved_id=str(row[0]),
            resolved_path=str(row[2]),
            display_name=str(row[1]),
            workspace_id=str(row[0]),
            metadata={"manifest_path": str(row[3])},
        )

    if body.kind == "workspace_manifest":
        root = _workspace_root_from_request(body.workspace_root)
        return SelectorResolveResponse(
            kind=body.kind,
            selector=body.selector,
            resolved=True,
            resolved_path=str(root / "workbench.project.yaml"),
            display_name="workspace manifest",
            workspace_id=body.workspace_id,
        )

    if body.kind == "dataset":
        engine = get_engine(request)
        sql = (
            "SELECT id, dataset_slug, dataset_name, workspace_id "
            "FROM datasets "
            "WHERE id = :selector "
            "OR dataset_slug = :selector "
            "OR dataset_name = :selector"
        )
        params: dict[str, Any] = {"selector": body.selector}
        if body.workspace_id is not None:
            sql += " AND workspace_id = :workspace_id"
            params["workspace_id"] = body.workspace_id
        row = _query_one(engine, sql + " LIMIT 1", params)
        if row is None:
            raise HTTPException(status_code=404, detail="dataset not found")
        return SelectorResolveResponse(
            kind=body.kind,
            selector=body.selector,
            resolved=True,
            resolved_id=str(row[0]),
            resolved_path=None,
            display_name=str(row[2]),
            workspace_id=str(row[3]),
            metadata={"slug": str(row[1])},
        )

    artifact_id, path, metadata = _resolve_db_artifact(
        request,
        kind=body.kind,  # type: ignore[arg-type]
        selector=body.selector,
        workspace_id=body.workspace_id,
    )
    return SelectorResolveResponse(
        kind=body.kind,
        selector=body.selector,
        resolved=True,
        resolved_id=artifact_id,
        resolved_path=str(path),
        workspace_id=body.workspace_id,
        display_name=metadata.get("label"),
        version=metadata.get("version"),
        metadata=metadata,
    )


@router.post("/artifacts/read", response_model=ArtifactReadResponse)
async def read_artifact(
    request: Request,
    body: ArtifactReadRequest,
) -> ArtifactReadResponse:
    """Read a canonical artifact as UTF-8 text."""
    path, metadata = _resolve_artifact_path(
        request,
        kind=body.kind,
        selector=body.selector,
        workspace_root=body.workspace_root,
        workspace_id=body.workspace_id,
    )
    if not path.exists():
        return ArtifactReadResponse(
            kind=body.kind,
            selector=body.selector,
            resolved_path=str(path),
            exists=False,
            metadata=metadata,
        )

    content = path.read_text(encoding="utf-8")
    return ArtifactReadResponse(
        kind=body.kind,
        selector=body.selector,
        resolved_path=str(path),
        exists=True,
        content=content,
        content_hash=_hash_file(path),
        file_size_bytes=path.stat().st_size,
        metadata=metadata,
    )


@router.post("/artifacts/diff", response_model=ArtifactDiffResponse)
async def diff_artifact(
    request: Request,
    body: ArtifactDiffRequest,
) -> ArtifactDiffResponse:
    """Diff proposed content against the current canonical artifact."""
    path, _metadata = _resolve_artifact_path(
        request,
        kind=body.kind,
        selector=body.selector,
        workspace_root=body.workspace_root,
        workspace_id=body.workspace_id,
    )
    current_content = path.read_text(encoding="utf-8") if path.exists() else ""
    current_hash = _hash_file(path)
    new_hash = _hash_text(body.content)
    has_conflict = (
        current_hash is not None
        and body.expected_hash is not None
        and current_hash != body.expected_hash
    )
    diff = "".join(
        difflib.unified_diff(
            current_content.splitlines(keepends=True),
            body.content.splitlines(keepends=True),
            fromfile=str(path),
            tofile=f"{path} (proposed)",
        )
    )
    return ArtifactDiffResponse(
        kind=body.kind,
        selector=body.selector,
        resolved_path=str(path),
        current_hash=current_hash,
        new_hash=new_hash,
        has_conflict=has_conflict,
        diff=diff,
    )


@router.post("/artifacts/proposals", response_model=ArtifactProposalResponse)
async def create_artifact_proposal(
    request: Request,
    body: ArtifactProposalCreateRequest,
    reviewer: CurrentCliReviewer,
) -> ArtifactProposalResponse:
    """Create a durable artifact diff proposal without applying it."""
    path, _metadata = _resolve_artifact_path(
        request,
        kind=body.kind,
        selector=body.selector,
        workspace_root=body.workspace_root,
        workspace_id=body.workspace_id,
    )
    current_content = path.read_text(encoding="utf-8") if path.exists() else ""
    current_hash = _hash_file(path)
    new_hash = _hash_text(body.content)
    has_conflict = (
        current_hash is not None
        and body.expected_hash is not None
        and current_hash != body.expected_hash
    )
    proposal_id = _proposal_id()
    proposal_path = _proposal_path(body.workspace_root, proposal_id)
    diff = "".join(
        difflib.unified_diff(
            current_content.splitlines(keepends=True),
            body.content.splitlines(keepends=True),
            fromfile=str(path),
            tofile=f"{path} (proposed)",
        )
    )
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "proposal_id": proposal_id,
        "kind": body.kind,
        "selector": body.selector,
        "resolved_path": str(path),
        "status": "conflicted" if has_conflict else "proposed",
        "current_hash": current_hash,
        "new_hash": new_hash,
        "expected_hash": body.expected_hash,
        "has_conflict": has_conflict,
        "diff": diff,
        "content": body.content,
        "proposal_path": str(proposal_path),
        "title": body.title,
        "rationale": body.rationale,
        "run_id": body.run_id,
        "created_by": str(reviewer.id),
        "created_at": now.isoformat(),
        "decided_by": None,
        "decided_at": None,
        "decision_notes": None,
        "write_result": None,
    }
    _write_proposal(proposal_path, payload)
    _record_audit_event(
        request,
        reviewer=reviewer,
        workspace_id=body.workspace_id,
        event_type="artifact_proposed",
        object_id=proposal_id,
        summary=f"Proposed artifact change for {body.kind}:{body.selector}",
        details={
            "kind": body.kind,
            "selector": body.selector,
            "resolved_path": str(path),
            "run_id": body.run_id,
            "has_conflict": has_conflict,
            "proposal_path": str(proposal_path),
        },
    )
    return _proposal_response(payload)


@router.get(
    "/artifacts/proposals/{proposal_id}/trace",
    response_model=ArtifactTraceResponse,
)
async def trace_artifact_proposal(
    request: Request,
    proposal_id: str,
    workspace_root: str | None = None,
    workspace_id: str | None = None,
) -> ArtifactTraceResponse:
    """Return a chain-of-custody trace for a durable artifact proposal."""
    payload = _load_proposal(workspace_root, proposal_id)
    trace = _build_artifact_trace(
        request,
        payload=payload,
        workspace_root=workspace_root,
        workspace_id=workspace_id,
    )
    safe_payload = dict(payload)
    safe_payload.pop("content", None)
    return ArtifactTraceResponse(
        proposal_id=proposal_id,
        proposal=safe_payload,
        trace=trace,
    )


@router.post(
    "/artifacts/proposals/{proposal_id}/decision",
    response_model=ArtifactProposalResponse,
)
async def decide_artifact_proposal(
    request: Request,
    proposal_id: str,
    body: ArtifactProposalDecisionRequest,
    reviewer: CurrentCliReviewer,
) -> ArtifactProposalResponse:
    """Accept or reject a durable artifact diff proposal."""
    payload = _load_proposal(body.workspace_root, proposal_id)
    if payload.get("status") in {"accepted", "rejected"}:
        raise HTTPException(status_code=409, detail="Artifact proposal is closed")
    if payload.get("status") == "conflicted" and body.decision == "accept":
        raise HTTPException(status_code=409, detail="Artifact proposal has a conflict")

    decided_at = datetime.now(UTC)
    write_result: ArtifactWriteResponse | None = None
    if body.decision == "accept":
        path, _metadata = _resolve_artifact_path(
            request,
            kind=payload["kind"],
            selector=payload["selector"],
            workspace_root=body.workspace_root,
            workspace_id=body.workspace_id,
        )
        current_hash = _hash_file(path)
        expected_hash = payload.get("expected_hash") or payload.get("current_hash")
        if current_hash is not None and expected_hash != current_hash:
            payload["status"] = "conflicted"
            payload["has_conflict"] = True
            payload["decision_notes"] = body.notes
            payload["decided_by"] = str(reviewer.id)
            payload["decided_at"] = decided_at.isoformat()
            _write_proposal(_proposal_path(body.workspace_root, proposal_id), payload)
            raise HTTPException(
                status_code=409,
                detail="Artifact changed since proposal creation",
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        result = AtomicWriter().write_atomic(
            str(payload["content"]).encode("utf-8"),
            path,
            skip_conflict_check=True,
        )
        if not result.success or result.final_path is None:
            raise HTTPException(
                status_code=500,
                detail=result.error or "Artifact proposal write failed",
            )
        write_result = ArtifactWriteResponse(
            kind=payload["kind"],
            selector=payload["selector"],
            resolved_path=str(result.final_path),
            success=True,
            content_hash=result.content_hash,
            file_size_bytes=result.file_size_bytes,
            previous_path=str(result.previous_path) if result.previous_path else None,
        )

    payload["status"] = "accepted" if body.decision == "accept" else "rejected"
    payload["decided_by"] = str(reviewer.id)
    payload["decided_at"] = decided_at.isoformat()
    payload["decision_notes"] = body.notes
    payload["write_result"] = (
        write_result.model_dump(mode="json") if write_result is not None else None
    )
    _write_proposal(_proposal_path(body.workspace_root, proposal_id), payload)
    _record_audit_event(
        request,
        reviewer=reviewer,
        workspace_id=body.workspace_id,
        event_type=(
            "artifact_proposal_accepted"
            if body.decision == "accept"
            else "artifact_proposal_rejected"
        ),
        object_id=proposal_id,
        summary=f"{body.decision.title()}ed artifact proposal {proposal_id}",
        details={
            "decision": body.decision,
            "notes": body.notes,
            "kind": payload.get("kind"),
            "selector": payload.get("selector"),
            "run_id": payload.get("run_id"),
            "write_result": payload.get("write_result"),
        },
    )
    return _proposal_response(payload)


@router.post("/artifacts/write", response_model=ArtifactWriteResponse)
async def write_artifact(
    request: Request,
    body: ArtifactWriteRequest,
    _reviewer: CurrentCliReviewer,
) -> ArtifactWriteResponse:
    """Write canonical artifact content after an expected-hash check."""
    path, _metadata = _resolve_artifact_path(
        request,
        kind=body.kind,
        selector=body.selector,
        workspace_root=body.workspace_root,
        workspace_id=body.workspace_id,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    current_hash = _hash_file(path)
    if path.exists():
        if body.expected_hash is None:
            raise HTTPException(
                status_code=409,
                detail="expected_hash is required when overwriting an existing file",
            )
        if current_hash != body.expected_hash:
            raise HTTPException(
                status_code=409,
                detail="Artifact changed since it was read",
            )

    writer = AtomicWriter()
    result = writer.write_atomic(
        body.content.encode("utf-8"),
        path,
        skip_conflict_check=True,
    )
    if not result.success or result.final_path is None:
        raise HTTPException(
            status_code=500,
            detail=result.error or "Artifact write failed",
        )

    return ArtifactWriteResponse(
        kind=body.kind,
        selector=body.selector,
        resolved_path=str(result.final_path),
        success=True,
        content_hash=result.content_hash,
        file_size_bytes=result.file_size_bytes,
        previous_path=str(result.previous_path) if result.previous_path else None,
    )

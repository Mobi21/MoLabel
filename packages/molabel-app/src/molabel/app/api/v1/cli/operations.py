"""CLI template browsing and snapshot restore endpoints."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import bindparam, text
from sqlmodel import Session, select

from molabel.app.api.v1.cli.deps import CurrentCliReviewer
from molabel.app.utils import get_engine
from molabel.core.agents.queue_binding import deserialize_agent_output_ids
from molabel.core.data.snapshot_service import SnapshotService
from molabel.core.models import Dataset, DatasetSnapshot, Record
from molabel.core.workflow.templates import (
    get_template_path,
    get_template_yaml,
    list_templates,
)

router = APIRouter(prefix="", tags=["cli"])


class WorkflowTemplateSummary(BaseModel):
    template_id: str
    name: str
    description: str
    file_path: str
    version: str
    task_family: str
    capabilities: list[str] = Field(default_factory=list)
    validated_by_benchmarks: list[str] = Field(default_factory=list)


class WorkflowTemplateDetail(WorkflowTemplateSummary):
    absolute_path: str
    yaml: str


class SnapshotRestoreResponse(BaseModel):
    restored_snapshot_id: str
    safety_snapshot_id: str
    records_restored: int = 0
    labels_restored: int = 0
    restored_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SnapshotRestoreRequest(BaseModel):
    dataset_id: str
    snapshot_id: str


class LocksResponse(BaseModel):
    available: bool
    items: list[dict] = Field(default_factory=list)
    message: str


class BenchmarkRunFactsResponse(BaseModel):
    workflow_execution_id: str
    workflow_status: str
    current_step_id: str | None = None
    workspace_id: str
    workspace_root: str | None = None
    queue_id: str | None = None
    run_artifact_dir: str | None = None
    summary_path: str | None = None
    report_path: str | None = None
    artifact_files: list[str] = Field(default_factory=list)
    record_count: int = 0
    available_count: int = 0
    claimed_count: int = 0
    submitted_count: int = 0
    review_event_count: int = 0
    queue_empty: bool = False
    review_completion_rate: float = 0.0
    decision_counts: dict[str, int] = Field(default_factory=dict)
    semantic_decision_counts: dict[str, int] = Field(default_factory=dict)


@router.get("/workflow-templates", response_model=list[WorkflowTemplateSummary])
async def workflow_templates() -> list[WorkflowTemplateSummary]:
    """List built-in workflow templates available to the CLI."""
    return [
        WorkflowTemplateSummary(
            template_id=template["id"],
            name=template["name"],
            description=template["description"],
            file_path=template["file"],
            version=template["version"],
            task_family=template["task_family"],
            capabilities=list(template.get("capabilities", [])),
            validated_by_benchmarks=list(template.get("validated_by_benchmarks", [])),
        )
        for template in list_templates()
    ]


@router.get("/workflow-templates/{template_id}", response_model=WorkflowTemplateDetail)
async def get_workflow_template(template_id: str) -> WorkflowTemplateDetail:
    """Return a built-in workflow template with its YAML content."""
    try:
        template_path = get_template_path(template_id)
        yaml_text = get_template_yaml(template_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    template = next(
        (item for item in list_templates() if item["id"] == template_id), None
    )
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")

    return WorkflowTemplateDetail(
        template_id=template["id"],
        name=template["name"],
        description=template["description"],
        file_path=template["file"],
        version=template["version"],
        task_family=template["task_family"],
        capabilities=list(template.get("capabilities", [])),
        validated_by_benchmarks=list(template.get("validated_by_benchmarks", [])),
        absolute_path=str(template_path),
        yaml=yaml_text,
    )


@router.post(
    "/datasets/{dataset_id}/snapshots/{snapshot_id}/restore",
    response_model=SnapshotRestoreResponse,
)
async def restore_snapshot(
    request: Request,
    dataset_id: uuid.UUID,
    snapshot_id: uuid.UUID,
    _reviewer: CurrentCliReviewer,
) -> SnapshotRestoreResponse:
    """Restore a dataset snapshot using the core snapshot service."""
    engine = get_engine(request)
    with Session(engine) as session:
        dataset = session.get(Dataset, dataset_id)
        if dataset is None:
            raise HTTPException(status_code=404, detail="Dataset not found")
        snapshot = session.get(DatasetSnapshot, snapshot_id)
        if snapshot is None or snapshot.dataset_id != dataset_id:
            raise HTTPException(
                status_code=404, detail=f"Snapshot {snapshot_id} not found"
            )
        workspace_id = dataset.workspace_id

    service = SnapshotService()
    safety = service.create_snapshot(
        engine,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        name="Pre-restore safety snapshot",
        description=f"Auto-created before restoring snapshot '{snapshot_id}'",
    )

    membership_data = snapshot.dataset_membership or {}
    if isinstance(membership_data, str):
        membership_data = json.loads(membership_data)
    restored_record_states = membership_data.get("record_states", {})
    health_status = membership_data.get("health_status")

    with Session(engine) as session:
        dataset = session.get(Dataset, dataset_id)
        if dataset is None:
            raise HTTPException(status_code=404, detail="Dataset not found")
        dataset.record_count = snapshot.record_count
        dataset.labeled_count = snapshot.labeled_count
        dataset.updated_at = datetime.now(UTC)
        if health_status is not None:
            dataset.health_status = health_status  # type: ignore[assignment]
        session.add(dataset)

        records = list(
            session.exec(select(Record).where(Record.dataset_id == dataset_id)).all()
        )
        record_lookup = {str(record.id): record for record in records}
        for record_key, state in restored_record_states.items():
            record = record_lookup.get(str(record_key))
            if record is None:
                continue
            record.latest_label = state.get("latest_label")
            record.composite_confidence = state.get("composite_confidence")
            record.export_eligible = bool(state.get("export_eligible"))
            record.flags = state.get("flags")
            record.label_count = int(state.get("label_count", 0))
            record.updated_at = datetime.now(UTC)
            session.add(record)
        session.commit()

    return SnapshotRestoreResponse(
        restored_snapshot_id=str(snapshot_id),
        safety_snapshot_id=str(safety.snapshot_id),
        records_restored=len(restored_record_states),
        labels_restored=sum(
            1
            for state in restored_record_states.values()
            if int(state.get("label_count", 0)) > 0
        ),
    )


@router.post("/snapshots/restore", response_model=SnapshotRestoreResponse)
async def restore_snapshot_from_body(
    request: Request,
    body: SnapshotRestoreRequest,
    reviewer: CurrentCliReviewer,
) -> SnapshotRestoreResponse:
    """Restore a snapshot using a request body convenient for CLI clients."""

    return await restore_snapshot(
        request,
        dataset_id=uuid.UUID(body.dataset_id),
        snapshot_id=uuid.UUID(body.snapshot_id),
        _reviewer=reviewer,
    )


@router.get("/locks", response_model=LocksResponse)
async def get_locks() -> LocksResponse:
    """Expose lock state when the backend has a lock registry.

    The current backend does not yet surface one, so the CLI gets a structured
    empty response instead of a guessed state.
    """

    return LocksResponse(
        available=False,
        items=[],
        message="No lock registry is configured in the current backend",
    )


@router.get(
    "/benchmark-run-facts/{workflow_execution_id}",
    response_model=BenchmarkRunFactsResponse,
)
async def get_benchmark_run_facts(
    request: Request,
    workflow_execution_id: uuid.UUID,
    _reviewer: CurrentCliReviewer,
) -> BenchmarkRunFactsResponse:
    """Return persisted review/queue facts for a benchmark workflow execution."""
    engine = get_engine(request)
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT we.id,
                       we.status,
                       we.current_step_id,
                       we.context,
                       we.workspace_id,
                       ws.root_path
                FROM workflow_executions AS we
                JOIN workspaces AS ws ON ws.id = we.workspace_id
                WHERE we.id = :workflow_execution_id
                LIMIT 1
                """
            ),
            {"workflow_execution_id": str(workflow_execution_id)},
        ).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Workflow execution not found")

        context_raw = row[3]
        if isinstance(context_raw, str):
            try:
                context_raw = json.loads(context_raw)
            except json.JSONDecodeError:
                context_raw = {}
        context = context_raw if isinstance(context_raw, dict) else {}

        queue_id = None
        review_queue_ids = context.get("review_queue_ids")
        if isinstance(review_queue_ids, list) and review_queue_ids:
            last_queue = review_queue_ids[-1]
            if isinstance(last_queue, str) and last_queue.strip():
                queue_id = last_queue
        if not queue_id:
            step_outputs = context.get("step_outputs")
            if isinstance(step_outputs, dict):
                for value in step_outputs.values():
                    if not isinstance(value, dict):
                        continue
                    summary = value.get("summary")
                    if not isinstance(summary, dict):
                        continue
                    candidate = summary.get("queue_id")
                    if isinstance(candidate, str) and candidate.strip():
                        queue_id = candidate
                        break

        record_count = 0
        available_count = 0
        claimed_count = 0
        submitted_count = 0
        review_event_count = 0
        decision_counts: dict[str, int] = {}
        semantic_decision_counts: dict[str, int] = {}
        if queue_id:
            task_counts = conn.execute(
                text(
                    """
                    SELECT status, COUNT(*)
                    FROM review_tasks
                    WHERE queue_id = :queue_id
                    GROUP BY status
                    """
                ),
                {"queue_id": queue_id},
            ).all()
            for status, count in task_counts:
                count_int = int(count or 0)
                record_count += count_int
                normalized = str(status or "").strip().lower()
                if normalized == "available":
                    available_count = count_int
                elif normalized == "claimed":
                    claimed_count = count_int
                elif normalized == "submitted":
                    submitted_count = count_int

            review_event_count = int(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM review_events AS re
                        JOIN review_tasks AS rt ON rt.id = re.review_task_id
                        WHERE rt.queue_id = :queue_id
                        """
                    ),
                    {"queue_id": queue_id},
                ).scalar_one()
                or 0
            )
            for decision, count in conn.execute(
                text(
                    """
                    SELECT COALESCE(decision, ''), COUNT(*)
                    FROM review_events AS re
                    JOIN review_tasks AS rt ON rt.id = re.review_task_id
                    WHERE rt.queue_id = :queue_id
                    GROUP BY COALESCE(decision, '')
                    """
                ),
                {"queue_id": queue_id},
            ):
                key = str(decision or "").strip() or "unspecified"
                decision_counts[key] = int(count or 0)

            latest_event_rows = conn.execute(
                text(
                    """
                    SELECT
                        rt.id,
                        rt.agent_output_ids,
                        COALESCE(re.decision, ''),
                        re.labels
                    FROM review_tasks AS rt
                    JOIN review_events AS re ON re.review_task_id = rt.id
                    WHERE rt.queue_id = :queue_id
                      AND re.created_at = (
                          SELECT MAX(re2.created_at)
                          FROM review_events AS re2
                          WHERE re2.review_task_id = rt.id
                      )
                    """
                ),
                {"queue_id": queue_id},
            ).all()

            task_rows: list[tuple[list[str], str, dict[str, Any]]] = []
            output_id_set: set[str] = set()
            for _task_id, raw_output_ids, raw_decision, raw_labels in latest_event_rows:
                output_ids = [
                    str(output_id)
                    for output_id in deserialize_agent_output_ids(raw_output_ids)
                ]
                labels = raw_labels
                if isinstance(labels, str):
                    try:
                        labels = json.loads(labels)
                    except json.JSONDecodeError:
                        labels = {}
                if not isinstance(labels, dict):
                    labels = {}
                task_rows.append(
                    (output_ids, str(raw_decision or "").strip().lower(), labels)
                )
                output_id_set.update(output_ids)

            proposal_by_output_id: dict[str, dict[str, Any]] = {}
            if output_id_set:
                query = text(
                    """
                    SELECT id, labels
                    FROM agent_outputs
                    WHERE id IN :output_ids
                    """
                ).bindparams(bindparam("output_ids", expanding=True))
                for output_id, raw_labels in conn.execute(
                    query,
                    {"output_ids": sorted(output_id_set)},
                ):
                    labels = raw_labels
                    if isinstance(labels, str):
                        try:
                            labels = json.loads(labels)
                        except json.JSONDecodeError:
                            labels = {}
                    if isinstance(labels, dict):
                        proposal_by_output_id[str(output_id)] = labels

            for output_ids, raw_decision, review_labels in task_rows:
                proposal_labels = next(
                    (
                        proposal_by_output_id[output_id]
                        for output_id in output_ids
                        if output_id in proposal_by_output_id
                    ),
                    None,
                )
                semantic = raw_decision or "unspecified"
                if semantic in {"accept", "accept_ai", "edit", "edit_ai"}:
                    semantic = (
                        "edit_ai"
                        if (
                            proposal_labels is not None
                            and proposal_labels != review_labels
                        )
                        else "accept_ai"
                    )
                elif semantic == "reject":
                    semantic = "reject_ai"
                semantic_decision_counts[semantic] = (
                    semantic_decision_counts.get(semantic, 0) + 1
                )

    workspace_root = str(row[5]) if row[5] is not None else None
    artifact_dir: Path | None = None
    artifact_files: list[str] = []
    summary_path: str | None = None
    report_path: str | None = None
    if workspace_root:
        artifact_dir = (
            Path(workspace_root) / "workbench" / "benchmarks" / "runs" / "live-operator"
        )
        if artifact_dir.exists():
            artifact_files = sorted(
                str(path.relative_to(artifact_dir))
                for path in artifact_dir.rglob("*")
                if path.is_file()
            )
            summary_candidate = artifact_dir / "summary.json"
            report_candidate = artifact_dir / "report.md"
            if summary_candidate.exists():
                summary_path = str(summary_candidate)
            if report_candidate.exists():
                report_path = str(report_candidate)

    return BenchmarkRunFactsResponse(
        workflow_execution_id=str(row[0]),
        workflow_status=str(row[1]),
        current_step_id=str(row[2]) if row[2] is not None else None,
        workspace_id=str(row[4]),
        workspace_root=workspace_root,
        queue_id=queue_id,
        run_artifact_dir=str(artifact_dir) if artifact_dir is not None else None,
        summary_path=summary_path,
        report_path=report_path,
        artifact_files=artifact_files,
        record_count=record_count,
        available_count=available_count,
        claimed_count=claimed_count,
        submitted_count=submitted_count,
        review_event_count=review_event_count,
        queue_empty=record_count > 0 and available_count == 0 and claimed_count == 0,
        review_completion_rate=(
            submitted_count / record_count if record_count else 0.0
        ),
        decision_counts=decision_counts,
        semantic_decision_counts=semantic_decision_counts,
    )

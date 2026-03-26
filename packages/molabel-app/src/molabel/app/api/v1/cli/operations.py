"""CLI template browsing and snapshot restore endpoints."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from molabel.app.api.v1.cli.deps import CurrentCliReviewer
from molabel.app.utils import get_engine
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


@router.get("/workflow-templates", response_model=list[WorkflowTemplateSummary])
async def workflow_templates() -> list[WorkflowTemplateSummary]:
    """List built-in workflow templates available to the CLI."""
    return [
        WorkflowTemplateSummary(
            template_id=template["id"],
            name=template["name"],
            description=template["description"],
            file_path=template["file"],
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

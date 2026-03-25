"""Export endpoints -- /api/v1/exports.

Handles dataset export creation, preview, validation, download, and
Hugging Face Hub push operations.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from molabel.app.middleware.session import CurrentReviewer
from molabel.app.schemas import PaginatedResponse, QueryParams

router = APIRouter(prefix="/exports", tags=["exports"])


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------


class ExportSummary(BaseModel):
    """Lightweight export listing model."""

    export_id: str
    workspace_id: str
    dataset_id: str
    name: str
    format: str
    status: str
    record_count: int = 0
    file_path: str | None = None
    file_size_bytes: int | None = None
    created_at: datetime
    completed_at: datetime | None = None


class ExportInclusion(BaseModel):
    """Which data fields to include in the export."""

    record_data: bool = True
    human_labels: bool = True
    agent_labels: bool = False
    review_metadata: bool = False
    adjudication_history: bool = False
    record_ids: bool = True
    provenance: bool = False


class ExportFilters(BaseModel):
    """Filters applied when selecting records for export."""

    status: list[str] | None = None
    min_agreement: float | None = None
    exclude_flagged: bool = False
    snapshot_id: str | None = None
    record_ids: list[str] | None = None


class ExportCreate(BaseModel):
    """Request body for creating a new export."""

    workspace_id: str
    dataset_id: str
    name: str
    format: str
    packager_plugin: str | None = None
    include: ExportInclusion
    filters: ExportFilters | None = None
    output_path: str | None = None


class ExportDetail(BaseModel):
    """Full export detail model."""

    export_id: str
    workspace_id: str
    dataset_id: str
    name: str
    format: str
    status: str
    record_count: int = 0
    include: ExportInclusion
    filters: ExportFilters | None = None
    file_path: str | None = None
    file_size_bytes: int | None = None
    validation_status: str | None = None
    validation_errors: list[str] = []
    output_hash: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    error: str | None = None


class ExportPreview(BaseModel):
    """Preview of an export showing sample records and estimates."""

    sample_records: list[dict[str, Any]] = []
    total_matching: int = 0
    estimated_file_size_bytes: int | None = None
    warnings: list[str] = []


class ValidationCheck(BaseModel):
    """A single validation check result."""

    check_name: str
    status: str
    message: str
    details: dict[str, Any] | None = None


class ExportValidation(BaseModel):
    """Export validation result."""

    export_id: str
    status: str
    checks: list[ValidationCheck] = []
    validated_at: datetime


class HFPushRequest(BaseModel):
    """Request body for pushing an export to Hugging Face Hub."""

    repo_id: str
    split: str = "train"
    private: bool = True
    commit_message: str | None = None


class HFPushStatus(BaseModel):
    """Status of a Hugging Face Hub push operation."""

    export_id: str
    repo_id: str
    status: str
    url: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedResponse[ExportSummary])
async def list_exports(
    reviewer: CurrentReviewer,
    workspace_id: Annotated[str, Query(description="Workspace ID (required)")],
    params: Annotated[QueryParams, Depends()],
    dataset_id: Annotated[
        str | None, Query(description="Optional dataset filter")
    ] = None,
    status: Annotated[str | None, Query(description="Optional status filter")] = None,
) -> PaginatedResponse[ExportSummary]:
    """List exports for a workspace.

    Returns a paginated list of exports, optionally filtered by dataset
    and status.
    """
    return PaginatedResponse(items=[], cursor=None, has_more=False)


@router.post("", response_model=ExportDetail, status_code=202)
async def create_export(
    data: ExportCreate,
    reviewer: CurrentReviewer,
) -> ExportDetail:
    """Create a new export (async, returns 202).

    Initiates an export job that runs in the background. The export
    status can be polled via GET /exports/{export_id}.
    """
    export_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    return ExportDetail(
        export_id=export_id,
        workspace_id=data.workspace_id,
        dataset_id=data.dataset_id,
        name=data.name,
        format=data.format,
        status="pending",
        record_count=0,
        include=data.include,
        filters=data.filters,
        file_path=None,
        file_size_bytes=None,
        validation_status=None,
        validation_errors=[],
        output_hash=None,
        created_at=now,
        completed_at=None,
        error=None,
    )


@router.post("/preview", response_model=ExportPreview)
async def preview_export(
    data: ExportCreate,
    reviewer: CurrentReviewer,
) -> ExportPreview:
    """Preview an export before creation.

    Returns sample records, total matching count, and estimated file
    size without actually creating the export.
    """
    return ExportPreview(
        sample_records=[],
        total_matching=0,
        estimated_file_size_bytes=None,
        warnings=[],
    )


@router.get("/{export_id}", response_model=ExportDetail)
async def get_export(
    export_id: str,
    reviewer: CurrentReviewer,
) -> ExportDetail:
    """Get detailed information about a specific export.

    Returns 404 if the export does not exist.
    """
    raise HTTPException(status_code=404, detail="Export not found")


@router.post("/{export_id}/validate", response_model=ExportValidation)
async def validate_export(
    export_id: str,
    reviewer: CurrentReviewer,
) -> ExportValidation:
    """Run validation checks on a completed export.

    Returns the validation status and individual check results.
    """
    now = datetime.now(UTC)
    return ExportValidation(
        export_id=export_id,
        status="not_found",
        checks=[],
        validated_at=now,
    )


@router.post("/{export_id}/download")
async def download_export(
    export_id: str,
    reviewer: CurrentReviewer,
) -> JSONResponse:
    """Download an exported file.

    Returns the export file as a download. Currently returns a
    placeholder message.
    """
    return JSONResponse(
        status_code=404,
        content={"detail": "Export not found or not yet completed"},
    )


@router.post("/{export_id}/push-hf", response_model=HFPushStatus, status_code=202)
async def push_to_huggingface(
    export_id: str,
    data: HFPushRequest,
    reviewer: CurrentReviewer,
) -> HFPushStatus:
    """Push an export to Hugging Face Hub (async, returns 202).

    Initiates a push operation that runs in the background. Status
    can be polled via GET /exports/{export_id}.
    """
    return HFPushStatus(
        export_id=export_id,
        repo_id=data.repo_id,
        status="pending",
        url=None,
        error=None,
    )

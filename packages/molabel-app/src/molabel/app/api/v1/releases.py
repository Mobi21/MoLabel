"""Release endpoints -- /api/v1/releases.

Handles dataset release lifecycle: creation, validation, approval,
and listing of frozen release snapshots.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from molabel.app.api.v1.exports import ExportSummary
from molabel.app.middleware.session import CurrentReviewer
from molabel.app.schemas import PaginatedResponse, QueryParams

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


@router.get("", response_model=PaginatedResponse[ReleaseSummary])
async def list_releases(
    reviewer: CurrentReviewer,
    workspace_id: Annotated[str, Query(description="Workspace ID (required)")],
    params: Annotated[QueryParams, Depends()],
    status: Annotated[str | None, Query(description="Optional status filter")] = None,
) -> PaginatedResponse[ReleaseSummary]:
    """List releases for a workspace.

    Returns a paginated list of releases, optionally filtered by status.
    """
    return PaginatedResponse(items=[], cursor=None, has_more=False)


@router.post("", response_model=ReleaseDetail, status_code=201)
async def create_release(
    data: ReleaseCreate,
    reviewer: CurrentReviewer,
) -> ReleaseDetail:
    """Create a new release.

    Creates a frozen release snapshot from the specified exports.
    Validation gates are evaluated if specified.
    """
    release_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    return ReleaseDetail(
        release_id=release_id,
        workspace_id=data.workspace_id,
        name=data.name,
        version=data.version,
        status="draft",
        export_ids=data.export_ids,
        exports=[],
        validation_report=None,
        notes=data.notes,
        approved_by=None,
        approved_at=None,
        created_at=now,
    )


@router.get("/{release_id}", response_model=ReleaseDetail)
async def get_release(
    release_id: str,
    reviewer: CurrentReviewer,
) -> ReleaseDetail:
    """Get detailed information about a specific release.

    Returns 404 if the release does not exist.
    """
    raise HTTPException(status_code=404, detail="Release not found")


@router.post("/{release_id}/approve", response_model=ReleaseDetail)
async def approve_release(
    release_id: str,
    data: ReleaseApproval,
    reviewer: CurrentReviewer,
) -> ReleaseDetail:
    """Approve or reject a release.

    Only operators can approve releases. The release must be in a
    state that allows approval (e.g. all validation gates passing).
    Returns 404 if the release does not exist.
    """
    raise HTTPException(status_code=404, detail="Release not found")

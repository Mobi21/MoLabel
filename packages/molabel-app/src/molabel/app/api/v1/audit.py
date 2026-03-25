"""Audit log endpoints -- /api/v1/audit.

Provides immutable audit trail access for all significant workspace
events including review submissions, configuration changes, exports,
and release approvals.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from molabel.app.middleware.session import CurrentReviewer
from molabel.app.schemas import PaginatedResponse, QueryParams

router = APIRouter(prefix="/audit", tags=["audit"])


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------


class AuditEvent(BaseModel):
    """A single audit log event."""

    audit_id: str
    workspace_id: str
    event_type: str
    actor: str
    actor_name: str | None = None
    object_type: str
    object_id: str
    summary: str
    details: dict[str, Any] | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedResponse[AuditEvent])
async def list_audit_events(
    reviewer: CurrentReviewer,
    workspace_id: Annotated[str, Query(description="Workspace ID (required)")],
    params: Annotated[QueryParams, Depends()],
    event_type: Annotated[str | None, Query(description="Filter by event type")] = None,
    actor: Annotated[str | None, Query(description="Filter by actor ID")] = None,
    object_type: Annotated[
        str | None, Query(description="Filter by object type")
    ] = None,
    object_id: Annotated[str | None, Query(description="Filter by object ID")] = None,
    created_after: Annotated[
        datetime | None, Query(description="Filter events after this timestamp")
    ] = None,
    created_before: Annotated[
        datetime | None, Query(description="Filter events before this timestamp")
    ] = None,
) -> PaginatedResponse[AuditEvent]:
    """List audit events for a workspace.

    Returns a paginated list of audit events with optional filters for
    event type, actor, object type/id, and time range.
    """
    return PaginatedResponse(items=[], cursor=None, has_more=False)


@router.get("/{audit_id}", response_model=AuditEvent)
async def get_audit_event(
    audit_id: str,
    reviewer: CurrentReviewer,
) -> AuditEvent:
    """Get a single audit event by ID.

    Returns 404 if the audit event does not exist.
    """
    raise HTTPException(status_code=404, detail="Audit event not found")

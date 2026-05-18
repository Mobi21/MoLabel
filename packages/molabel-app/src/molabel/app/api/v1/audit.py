"""Audit log endpoints -- /api/v1/audit.

Provides immutable audit trail access for all significant workspace
events including review submissions, configuration changes, exports,
and release approvals.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import text

from molabel.app.middleware.session import CurrentReviewer
from molabel.app.schemas import PaginatedResponse, QueryParams
from molabel.app.utils import get_engine

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


def _ensure_audit_table(engine) -> None:
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
                "CREATE INDEX IF NOT EXISTS idx_audit_events_workspace_id "
                "ON audit_events(workspace_id)"
            )
        )
        conn.commit()


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _parse_details(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return {"raw": str(value)}
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def _row_to_audit_event(row: Any) -> AuditEvent:
    return AuditEvent(
        audit_id=str(row[0]),
        workspace_id=str(row[1]),
        event_type=str(row[2]),
        actor=str(row[3]),
        actor_name=str(row[4]) if row[4] else None,
        object_type=str(row[5]),
        object_id=str(row[6]),
        summary=str(row[7]),
        details=_parse_details(row[8]),
        created_at=_parse_datetime(row[9]),
    )


@router.get("", response_model=PaginatedResponse[AuditEvent])
async def list_audit_events(
    request: Request,
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
    engine = get_engine(request)
    _ensure_audit_table(engine)
    query = (
        "SELECT id, workspace_id, event_type, actor, actor_name, object_type, "
        "object_id, summary, details, created_at "
        "FROM audit_events WHERE workspace_id = :workspace_id"
    )
    bind: dict[str, Any] = {"workspace_id": workspace_id, "limit": params.limit}
    if event_type:
        query += " AND event_type = :event_type"
        bind["event_type"] = event_type
    if actor:
        query += " AND actor = :actor"
        bind["actor"] = actor
    if object_type:
        query += " AND object_type = :object_type"
        bind["object_type"] = object_type
    if object_id:
        query += " AND object_id = :object_id"
        bind["object_id"] = object_id
    if created_after:
        query += " AND created_at >= :created_after"
        bind["created_after"] = created_after.isoformat()
    if created_before:
        query += " AND created_at <= :created_before"
        bind["created_before"] = created_before.isoformat()
    query += " ORDER BY created_at DESC LIMIT :limit"

    with engine.connect() as conn:
        rows = conn.execute(text(query), bind).fetchall()
    return PaginatedResponse(
        items=[_row_to_audit_event(row) for row in rows],
        cursor=None,
        has_more=False,
    )


@router.get("/{audit_id}", response_model=AuditEvent)
async def get_audit_event(
    request: Request,
    audit_id: str,
    reviewer: CurrentReviewer,
) -> AuditEvent:
    """Get a single audit event by ID.

    Returns 404 if the audit event does not exist.
    """
    engine = get_engine(request)
    _ensure_audit_table(engine)
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, workspace_id, event_type, actor, actor_name, "
                "object_type, object_id, summary, details, created_at "
                "FROM audit_events WHERE id = :id"
            ),
            {"id": audit_id},
        ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Audit event not found")
    return _row_to_audit_event(row)

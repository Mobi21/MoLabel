"""Review event endpoints — /api/v1/review.

Lists review events with filtering (API-063). Only a session's workspace is
visible to it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import text

from molabel.app.middleware.session import CurrentReviewer
from molabel.app.schemas import PaginatedResponse, QueryParams
from molabel.app.utils import get_engine
from molabel.core.database import hyphenated_id

router = APIRouter(prefix="/review", tags=["review"])


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------


class ReviewEvent(BaseModel):
    """Response model for a single review event."""

    review_event_id: str
    reviewer_id: str
    reviewer_name: str
    record_id: str
    dataset_id: str
    task_schema_id: str
    task_schema_version: int
    decision: str
    labels: dict[str, Any]
    rationale: str | None = None
    ai_was_revealed: bool
    is_draft: bool
    review_duration_ms: int | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/events", response_model=PaginatedResponse[ReviewEvent])
async def list_review_events(
    request: Request,
    params: Annotated[QueryParams, Depends()],
    reviewer: CurrentReviewer,
    record_id: str | None = Query(None),
    reviewer_id: str | None = Query(None),
    task_schema_id: str | None = Query(None),
    is_draft: bool | None = Query(None),
    dataset_id: str | None = Query(None),
) -> PaginatedResponse[ReviewEvent]:
    """List review events with filtering (API-063). It lists none yet.

    It needs a session, and a filter that names a row of another workspace
    answers 404, as every review endpoint does for a queue or task of
    another workspace.
    """
    named_rows = (
        (record_id, "records", "Record"),
        (reviewer_id, "reviewer_profiles", "Reviewer profile"),
        (task_schema_id, "task_schemas", "Task schema"),
        (dataset_id, "datasets", "Dataset"),
    )
    with get_engine(request).connect() as conn:
        for row_id, table, noun in named_rows:
            if row_id is None:
                continue
            found = conn.execute(
                text(f"SELECT 1 FROM {table} WHERE id = :id AND workspace_id = :wid"),
                {"id": hyphenated_id(row_id), "wid": str(reviewer.workspace_id)},
            ).first()
            if found is None:
                raise HTTPException(status_code=404, detail=f"{noun} not found")
    return PaginatedResponse(items=[], cursor=None, has_more=False)

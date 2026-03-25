"""Review event endpoints — /api/v1/review.

Lists review events with filtering (API-063).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from molabel.app.schemas import PaginatedResponse, QueryParams

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
    params: Annotated[QueryParams, Depends()],
    record_id: str | None = Query(None),
    reviewer_id: str | None = Query(None),
    task_schema_id: str | None = Query(None),
    is_draft: bool | None = Query(None),
    dataset_id: str | None = Query(None),
) -> PaginatedResponse[ReviewEvent]:
    """List review events with filtering (API-063)."""
    return PaginatedResponse(items=[], cursor=None, has_more=False)

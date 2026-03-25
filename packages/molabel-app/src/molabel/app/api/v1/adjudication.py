"""Adjudication endpoints — /api/v1/adjudication.

Extended adjudication queue endpoints (API-064 through API-066).

Note: Basic adjudication (AJ-001 through AJ-007) is handled in queue.py.
This module adds the typed adjudication queue listing with filters,
detail view, and per-item resolution endpoint using path parameters.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from molabel.app.middleware.session import CurrentReviewer
from molabel.app.schemas import PaginatedResponse, QueryParams

router = APIRouter(prefix="/adjudication", tags=["adjudication"])


# ---------------------------------------------------------------------------
# Pydantic response / request models
# ---------------------------------------------------------------------------


class AdjudicationQueueItem(BaseModel):
    """Summary model for an adjudication queue item."""

    adjudication_id: str
    record_id: str
    dataset_id: str
    task_schema_id: str
    status: str
    disagreement_type: str
    disagreement_severity: str
    disagreeing_fields: list[str]
    reviewer_count: int
    agent_output_count: int
    created_at: datetime


class ReviewerLabelSet(BaseModel):
    """Labels submitted by a single human reviewer."""

    reviewer_id: str
    reviewer_name: str
    review_event_id: str
    decision: str
    labels: dict[str, Any]
    rationale: str | None = None
    ai_was_revealed: bool
    created_at: datetime


class AgentLabelSet(BaseModel):
    """Labels produced by an agent run."""

    agent_run_id: str
    agent_role: str
    model_profile_id: str
    model_identifier: str
    labels: dict[str, Any]
    confidence: float | None = None
    created_at: datetime


class FieldDisagreement(BaseModel):
    """Disagreement detail for a single field."""

    field_name: str
    values: dict[str, Any]
    spread: float | None = None


class AdjudicationHistoryEntry(BaseModel):
    """A single entry in the adjudication history log."""

    action: str
    actor: str
    details: dict[str, Any] | None = None
    timestamp: datetime


class AdjudicationDetail(BaseModel):
    """Detailed model for a single adjudication item."""

    adjudication_id: str
    record_id: str
    dataset_id: str
    task_schema_id: str
    status: str
    record_data: dict[str, Any]
    reviewer_labels: list[ReviewerLabelSet]
    agent_labels: list[AgentLabelSet]
    disagreeing_fields: list[FieldDisagreement]
    policy_excerpt: str | None = None
    history: list[AdjudicationHistoryEntry]
    created_at: datetime
    resolved_at: datetime | None = None


class AdjudicationResolve(BaseModel):
    """Request body for resolving an adjudication item."""

    resolution_type: str
    resolved_labels: dict[str, Any] | None = None
    reasoning: str
    tier: str | None = None


class AdjudicationResult(BaseModel):
    """Response model for a resolved adjudication item."""

    adjudication_id: str
    record_id: str
    resolution_type: str
    resolved_labels: dict[str, Any] | None = None
    reasoning: str
    resolved_by: str
    tier: str | None = None
    resolved_at: datetime


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/queue", response_model=PaginatedResponse[AdjudicationQueueItem])
async def list_adjudication_queue(
    params: Annotated[QueryParams, Depends()],
    task_schema_id: str | None = Query(None),
    dataset_id: str | None = Query(None),
    severity: str | None = Query(None),
) -> PaginatedResponse[AdjudicationQueueItem]:
    """List adjudication queue items with filtering (API-064).

    This endpoint provides a paginated, filterable view of the
    adjudication queue, complementing the basic queue endpoint in
    the queue router.
    """
    return PaginatedResponse(items=[], cursor=None, has_more=False)


@router.get("/{adjudication_id}", response_model=AdjudicationDetail)
async def get_adjudication_detail(
    adjudication_id: str,
) -> AdjudicationDetail:
    """Get adjudication detail with all reviewer and agent labels (API-065)."""
    raise HTTPException(status_code=404, detail="Adjudication item not found")


@router.post(
    "/{adjudication_id}/resolve",
    response_model=AdjudicationResult,
)
async def resolve_adjudication(
    adjudication_id: str,
    body: AdjudicationResolve,
    reviewer: CurrentReviewer,
) -> AdjudicationResult:
    """Resolve an adjudication item (API-066)."""
    raise HTTPException(status_code=404, detail="Adjudication item not found")

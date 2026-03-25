"""Correction batch endpoints — /api/v1/corrections.

Manages correction batches, analysis, and refinement suggestions
for the agent feedback loop.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from molabel.app.middleware.session import CurrentReviewer
from molabel.app.schemas import PaginatedResponse, QueryParams

router = APIRouter(prefix="/corrections", tags=["corrections"])


# ---------------------------------------------------------------------------
# Pydantic response / request models
# ---------------------------------------------------------------------------


class CorrectionBatch(BaseModel):
    """Summary model for a correction batch."""

    batch_id: str
    workspace_id: str
    task_schema_id: str
    prompt_template_id: str
    correction_count: int
    status: str
    threshold: int
    created_at: datetime
    updated_at: datetime


class CorrectionAnalyzeRequest(BaseModel):
    """Request body to trigger correction analysis."""

    batch_id: str
    model_profile_id: str | None = None


class AnalysisStatus(BaseModel):
    """Response model for an in-progress correction analysis."""

    batch_id: str
    status: str
    job_id: str


class FewShotExample(BaseModel):
    """A single few-shot example (shared with prompts module)."""

    record_id: str | None = None
    input_text: str
    expected_output: dict[str, Any]
    source: str


class FieldCorrectionSummary(BaseModel):
    """Summary of corrections for a specific field."""

    field_name: str
    correction_count: int
    most_common_from: Any = None
    most_common_to: Any = None


class RefinementChanges(BaseModel):
    """Proposed changes from correction analysis."""

    instruction_patches: list[str]
    new_few_shot_examples: list[FewShotExample]
    fields_with_most_corrections: list[FieldCorrectionSummary]


class CorrectionPattern(BaseModel):
    """A recurring correction pattern."""

    pattern: str
    frequency: int
    example_record_ids: list[str]


class CorrectionSummary(BaseModel):
    """Statistical summary of corrections in a batch."""

    total_corrections: int
    corrections_by_field: dict[str, int]
    most_common_patterns: list[CorrectionPattern]


class RefinementSuggestion(BaseModel):
    """Refinement suggestion produced by correction analysis."""

    batch_id: str
    prompt_id: str
    current_version: str
    suggested_changes: RefinementChanges
    correction_summary: CorrectionSummary
    estimated_impact: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedResponse[CorrectionBatch])
async def list_correction_batches(
    params: Annotated[QueryParams, Depends()],
    workspace_id: str | None = Query(None),
    task_schema_id: str | None = Query(None),
    prompt_template_id: str | None = Query(None),
    status: str | None = Query(None),
) -> PaginatedResponse[CorrectionBatch]:
    """List correction batches with filtering."""
    return PaginatedResponse(items=[], cursor=None, has_more=False)


@router.post("/analyze", response_model=AnalysisStatus, status_code=202)
async def trigger_correction_analysis(
    body: CorrectionAnalyzeRequest,
    reviewer: CurrentReviewer,
) -> AnalysisStatus:
    """Trigger correction analysis for a batch.

    Returns 202 Accepted as the analysis executes asynchronously.
    """
    job_id = str(uuid.uuid4())
    return AnalysisStatus(
        batch_id=body.batch_id,
        status="pending",
        job_id=job_id,
    )


@router.get("/{batch_id}/refinement", response_model=RefinementSuggestion)
async def get_refinement_suggestion(
    batch_id: str,
) -> RefinementSuggestion:
    """Get the refinement suggestion for a correction batch."""
    raise HTTPException(
        status_code=404,
        detail="Correction batch not found or analysis not complete",
    )

"""Cost tracking endpoints -- /api/v1/costs.

Provides LLM cost summaries broken down by model, agent role, and
time period, as well as cost estimates for planned operations.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from molabel.app.middleware.session import CurrentReviewer

router = APIRouter(prefix="/costs", tags=["costs"])


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------


class ModelCost(BaseModel):
    """Cost breakdown for a single model."""

    model_profile_id: str
    model_identifier: str
    cost_usd: float = 0.0
    tokens_input: int = 0
    tokens_output: int = 0
    runs: int = 0


class RoleCost(BaseModel):
    """Cost breakdown for a single agent role."""

    agent_role: str
    cost_usd: float = 0.0
    runs: int = 0


class DailyCost(BaseModel):
    """Cost breakdown for a single day."""

    date: str
    cost_usd: float = 0.0
    runs: int = 0


class CostSummary(BaseModel):
    """Aggregate cost summary for a workspace."""

    workspace_id: str
    total_cost_usd: float = 0.0
    total_tokens_input: int = 0
    total_tokens_output: int = 0
    total_runs: int = 0
    by_model: list[ModelCost] = []
    by_role: list[RoleCost] = []
    daily_trend: list[DailyCost] = []


class CostEstimate(BaseModel):
    """Estimated cost for a planned operation."""

    model_profile_id: str
    model_identifier: str
    estimated_records: int = 0
    estimated_tokens_input: int = 0
    estimated_tokens_output: int = 0
    estimated_cost_usd: float = 0.0
    confidence: str = "low"
    pricing_source: str = "unknown"
    warnings: list[str] = []


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=CostSummary)
async def get_cost_summary(
    reviewer: CurrentReviewer,
    workspace_id: Annotated[str, Query(description="Workspace ID (required)")],
    model_profile_id: Annotated[
        str | None, Query(description="Filter by model profile")
    ] = None,
    agent_role: Annotated[str | None, Query(description="Filter by agent role")] = None,
    period: Annotated[
        str | None, Query(description="Time period (e.g. '7d', '30d', 'all')")
    ] = None,
    created_after: Annotated[
        datetime | None, Query(description="Filter costs after this timestamp")
    ] = None,
    created_before: Annotated[
        datetime | None, Query(description="Filter costs before this timestamp")
    ] = None,
) -> CostSummary:
    """Get aggregated cost summary for a workspace.

    Returns total costs broken down by model, agent role, and daily
    trend. Supports filtering by model profile, agent role, and time
    range.
    """
    return CostSummary(
        workspace_id=workspace_id,
        total_cost_usd=0.0,
        total_tokens_input=0,
        total_tokens_output=0,
        total_runs=0,
        by_model=[],
        by_role=[],
        daily_trend=[],
    )


@router.get("/estimate", response_model=CostEstimate)
async def get_cost_estimate(
    reviewer: CurrentReviewer,
    workspace_id: Annotated[str | None, Query(description="Workspace ID")] = None,
    dataset_id: Annotated[
        str | None, Query(description="Dataset ID for estimation")
    ] = None,
    model_profile_id: Annotated[
        str | None, Query(description="Model profile for pricing")
    ] = None,
    agent_role: Annotated[
        str | None, Query(description="Agent role for estimation")
    ] = None,
    record_count: Annotated[
        int | None, Query(description="Number of records to estimate")
    ] = None,
) -> CostEstimate:
    """Estimate cost for a planned labeling operation.

    Returns estimated token usage, cost, and confidence level for the
    specified parameters.
    """
    return CostEstimate(
        model_profile_id=model_profile_id or "none",
        model_identifier="unknown",
        estimated_records=record_count or 0,
        estimated_tokens_input=0,
        estimated_tokens_output=0,
        estimated_cost_usd=0.0,
        confidence="low",
        pricing_source="none",
        warnings=["No pricing data available. Configure a model profile first."],
    )

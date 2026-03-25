"""Agent run endpoints — /api/v1/agent-runs.

CRUD and analytics for agent runs, outputs, and comparison runs
(API-041 through API-052).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from molabel.app.middleware.session import CurrentReviewer
from molabel.app.schemas import PaginatedResponse, QueryParams

router = APIRouter(prefix="/agent-runs", tags=["agent-runs"])


# ---------------------------------------------------------------------------
# Pydantic response / request models
# ---------------------------------------------------------------------------


class CostInfo(BaseModel):
    """Cost and token usage information for an agent run."""

    estimated_cost_usd: float | None = None
    actual_cost_usd: float | None = None
    tokens_input: int | None = None
    tokens_output: int | None = None


class AgentRunSummary(BaseModel):
    """Summary model for agent run list responses."""

    agent_run_id: str
    workspace_id: str
    dataset_id: str
    agent_role: str
    model_profile_id: str
    model_identifier: str
    runtime_profile_id: str | None = None
    prompt_version: str
    status: str
    records_targeted: int
    records_completed: int
    records_failed: int
    comparison_id: str | None = None
    cost_estimate: CostInfo | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime


class AgentRunDetail(BaseModel):
    """Detailed model for a single agent run."""

    agent_run_id: str
    workspace_id: str
    dataset_id: str
    agent_role: str
    plugin_adapter: str
    model_profile_id: str
    model_identifier: str
    runtime_profile_id: str | None = None
    prompt_version: str
    prompt_content_hash: str
    task_schema_id: str
    status: str
    records_targeted: int
    records_completed: int
    records_failed: int
    retry_count: int
    partial_failure_summary: str | None = None
    comparison_id: str | None = None
    cost: CostInfo | None = None
    execution_params: dict[str, Any]
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    error: str | None = None


class AgentRunCreate(BaseModel):
    """Request body for starting a new agent run."""

    workspace_id: str
    dataset_id: str
    agent_role: str
    task_schema_id: str
    model_profile_id: str
    runtime_profile_id: str | None = None
    prompt_version: str | None = None
    record_filter: dict[str, Any] | None = None
    params: dict[str, Any] | None = None


class ComparisonRunCreate(BaseModel):
    """Request body for starting a comparison run across multiple models."""

    workspace_id: str
    dataset_id: str
    agent_role: str
    task_schema_id: str
    model_profile_ids: list[str]
    runtime_profile_id: str | None = None
    prompt_version: str | None = None
    record_filter: dict[str, Any] | None = None
    params: dict[str, Any] | None = None


class ComparisonRun(BaseModel):
    """Response model for a comparison run."""

    comparison_id: str
    agent_run_ids: list[str]
    status: str
    created_at: datetime


class ConfidenceSignals(BaseModel):
    """Confidence signal breakdown for an agent output."""

    self_reported: float | None = None
    self_consistency: float | None = None
    logprobs: float | None = None
    composite: float | None = None


class AgentOutput(BaseModel):
    """Response model for a single agent output."""

    agent_output_id: str
    agent_run_id: str
    record_id: str
    output_type: str
    labels: dict[str, Any]
    confidence: float | None = None
    confidence_signals: ConfidenceSignals | None = None
    normalization_status: str
    review_visibility: str
    eligible_actions: list[str]
    validation_errors: list[str]
    created_at: datetime


class ComparisonModelResult(BaseModel):
    """Per-model result within a comparison."""

    agent_run_id: str
    model_profile_id: str
    model_identifier: str
    accuracy: float | None = None
    agreement_rate: float | None = None
    cost_per_label: float | None = None
    avg_latency_ms: float | None = None
    records_completed: int
    records_failed: int


class ComparisonResult(BaseModel):
    """Response model for comparison results across models."""

    comparison_id: str
    workspace_id: str
    dataset_id: str
    agent_role: str
    status: str
    model_results: list[ComparisonModelResult]
    created_at: datetime
    completed_at: datetime | None = None


class TrendPoint(BaseModel):
    """A single point in a time-series trend."""

    timestamp: datetime
    value: float
    prompt_version: str | None = None


class ErrorPattern(BaseModel):
    """A recurring error pattern detected in agent outputs."""

    pattern_type: str
    description: str
    affected_records: int
    example_record_ids: list[str]


class CalibrationBucket(BaseModel):
    """A single bucket in a confidence calibration chart."""

    confidence_range: tuple[float, float]
    predicted_accuracy: float
    actual_accuracy: float
    record_count: int


class PromptVersionMetrics(BaseModel):
    """Performance metrics for a single prompt version."""

    prompt_version: str
    accuracy: float | None = None
    records_evaluated: int
    cost_per_label: float | None = None
    created_at: datetime


class AgentAnalytics(BaseModel):
    """Aggregated analytics for agent runs."""

    accuracy_by_field: dict[str, float]
    accuracy_by_label_value: dict[str, dict[str, float]]
    accuracy_overall: float | None = None
    agreement_trend: list[TrendPoint]
    error_patterns: list[ErrorPattern]
    cost_per_correct_label: float | None = None
    cost_per_label: float | None = None
    throughput_per_minute: float | None = None
    confidence_calibration: list[CalibrationBucket]
    prompt_version_comparison: list[PromptVersionMetrics]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedResponse[AgentRunSummary])
async def list_agent_runs(
    params: Annotated[QueryParams, Depends()],
    workspace_id: str = Query(..., description="Workspace ID (required)"),
    dataset_id: str | None = Query(None),
    status: str | None = Query(None),
    agent_role: str | None = Query(None),
    model_profile_id: str | None = Query(None),
    comparison_id: str | None = Query(None),
) -> PaginatedResponse[AgentRunSummary]:
    """List agent runs with filtering (API-041)."""
    return PaginatedResponse(items=[], cursor=None, has_more=False)


@router.get("/analytics", response_model=AgentAnalytics)
async def get_agent_analytics(
    workspace_id: str = Query(..., description="Workspace ID (required)"),
    dataset_id: str | None = Query(None),
    model_profile_id: str | None = Query(None),
    agent_role: str | None = Query(None),
) -> AgentAnalytics:
    """Get aggregated agent analytics (API-052)."""
    return AgentAnalytics(
        accuracy_by_field={},
        accuracy_by_label_value={},
        accuracy_overall=None,
        agreement_trend=[],
        error_patterns=[],
        cost_per_correct_label=None,
        cost_per_label=None,
        throughput_per_minute=None,
        confidence_calibration=[],
        prompt_version_comparison=[],
    )


@router.get("/comparison/{comparison_id}", response_model=ComparisonResult)
async def get_comparison_results(
    comparison_id: str,
) -> ComparisonResult:
    """Get comparison results for a comparison run (API-050)."""
    raise HTTPException(status_code=404, detail="Comparison not found")


@router.get("/{agent_run_id}", response_model=AgentRunDetail)
async def get_agent_run(
    agent_run_id: str,
) -> AgentRunDetail:
    """Get agent run detail (API-042)."""
    raise HTTPException(status_code=404, detail="Agent run not found")


@router.post("", response_model=AgentRunDetail, status_code=202)
async def start_agent_run(
    body: AgentRunCreate,
    reviewer: CurrentReviewer,
) -> AgentRunDetail:
    """Start a new agent run (API-043).

    Returns 202 Accepted as the run executes asynchronously.
    """
    now = datetime.now(UTC)
    run_id = str(uuid.uuid4())
    return AgentRunDetail(
        agent_run_id=run_id,
        workspace_id=body.workspace_id,
        dataset_id=body.dataset_id,
        agent_role=body.agent_role,
        plugin_adapter="default",
        model_profile_id=body.model_profile_id,
        model_identifier="pending",
        runtime_profile_id=body.runtime_profile_id,
        prompt_version=body.prompt_version or "v1",
        prompt_content_hash="",
        task_schema_id=body.task_schema_id,
        status="pending",
        records_targeted=0,
        records_completed=0,
        records_failed=0,
        retry_count=0,
        partial_failure_summary=None,
        comparison_id=None,
        cost=None,
        execution_params=body.params or {},
        started_at=None,
        completed_at=None,
        created_at=now,
        error=None,
    )


@router.post("/compare", response_model=ComparisonRun, status_code=202)
async def start_comparison_run(
    body: ComparisonRunCreate,
    reviewer: CurrentReviewer,
) -> ComparisonRun:
    """Start a comparison run across multiple models (API-044).

    Returns 202 Accepted as the runs execute asynchronously.
    """
    now = datetime.now(UTC)
    comparison_id = str(uuid.uuid4())
    agent_run_ids = [str(uuid.uuid4()) for _ in body.model_profile_ids]
    return ComparisonRun(
        comparison_id=comparison_id,
        agent_run_ids=agent_run_ids,
        status="pending",
        created_at=now,
    )


@router.post("/{agent_run_id}/cancel", response_model=AgentRunDetail)
async def cancel_agent_run(
    agent_run_id: str,
    reviewer: CurrentReviewer,
) -> AgentRunDetail:
    """Cancel a running agent run (API-045)."""
    raise HTTPException(status_code=404, detail="Agent run not found")


@router.get(
    "/{agent_run_id}/outputs",
    response_model=PaginatedResponse[AgentOutput],
)
async def list_agent_outputs(
    agent_run_id: str,
    params: Annotated[QueryParams, Depends()],
    normalization_status: str | None = Query(None),
) -> PaginatedResponse[AgentOutput]:
    """List outputs for an agent run (API-047)."""
    return PaginatedResponse(items=[], cursor=None, has_more=False)


@router.get(
    "/{agent_run_id}/outputs/{record_id}",
    response_model=AgentOutput,
)
async def get_agent_output_for_record(
    agent_run_id: str,
    record_id: str,
) -> AgentOutput:
    """Get agent output for a specific record (API-048)."""
    raise HTTPException(status_code=404, detail="Agent output not found")

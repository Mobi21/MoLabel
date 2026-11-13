"""Agent run endpoints — /api/v1/agent-runs.

CRUD and analytics for agent runs, outputs, and comparison runs
(API-041 through API-052).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import text

from molabel.app.middleware.session import CurrentReviewer
from molabel.app.schemas import PaginatedResponse, QueryParams
from molabel.app.utils import get_engine

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
    failure_envelope: dict[str, Any] | None = None


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


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _failure_envelope(
    *,
    run_id: str,
    status: str,
    error_summary: str | None,
    failed_records: int,
    completed_records: int,
    total_records: int,
    retry_count: int,
) -> dict[str, Any] | None:
    if not error_summary and failed_records <= 0 and status not in {"failed", "error"}:
        return None

    message = error_summary or f"Run ended with status {status}"
    lower = message.lower()
    category = (
        "partial_failure" if failed_records and completed_records else "runtime_error"
    )
    retryable = failed_records > 0
    repair_command = f"molabel run retry {run_id} --failed-only"

    auth_tokens = (
        "api key",
        "x-api-key",
        "unauthorized",
        "401",
        "login failure",
        "auth",
    )
    if any(token in lower for token in auth_tokens):
        category = "provider_auth"
        retryable = False
        repair_command = (
            "molabel provider health --provider anthropic "
            "--model-id MiniMax-M2.7-highspeed"
        )
    elif "timeout" in lower or "timed out" in lower:
        category = "provider_timeout"
        retryable = True
    elif any(token in lower for token in ("json", "malformed", "parse")):
        category = "malformed_output"
        retryable = True
    elif any(token in lower for token in ("validation", "schema")):
        category = "schema_validation"
        retryable = True
    elif any(
        token in lower for token in ("empty output", "no output", "empty response")
    ):
        category = "empty_output"
        retryable = True
    elif any(
        token in lower for token in ("retry exhausted", "max retries", "retry limit")
    ):
        category = "retry_exhausted"
        retryable = False

    return {
        "schema": "molabel.run.failure_envelope",
        "run_id": run_id,
        "category": category,
        "message": message,
        "retryable": retryable,
        "terminal": status in {"failed", "error"} and not retryable,
        "affected_records": failed_records,
        "completed_records": completed_records,
        "total_records": total_records,
        "partial_outputs": completed_records > 0,
        "canonical_state_changed": False,
        "retry_count": retry_count,
        "recommended_repair_commands": [
            f"molabel run failures {run_id}",
            repair_command,
        ],
    }


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
    request: Request,
    agent_run_id: str,
) -> AgentRunDetail:
    """Get agent run detail (API-042)."""
    engine = get_engine(request)
    with engine.connect() as conn:
        row = (
            conn.execute(
                text(
                    """
                SELECT
                    agent_runs.id,
                    agent_runs.workspace_id,
                    agent_runs.dataset_id,
                    agent_runs.agent_role,
                    agent_runs.adapter_plugin,
                    agent_runs.model_profile_id,
                    COALESCE(
                        model_profiles.model_identifier,
                        'unknown'
                    ) AS model_identifier,
                    agent_runs.runtime_profile_id,
                    agent_runs.prompt_version,
                    agent_runs.task_schema_id,
                    agent_runs.status,
                    agent_runs.total_records,
                    agent_runs.completed_records,
                    agent_runs.failed_records,
                    agent_runs.retry_count,
                    agent_runs.error_summary,
                    agent_runs.cost_estimate,
                    agent_runs.cost_actual,
                    agent_runs.comparison_id,
                    agent_runs.config,
                    agent_runs.started_at,
                    agent_runs.completed_at,
                    agent_runs.created_at
                FROM agent_runs
                LEFT JOIN model_profiles
                    ON model_profiles.id = agent_runs.model_profile_id
                WHERE agent_runs.id = :agent_run_id
                LIMIT 1
                """
                ),
                {"agent_run_id": agent_run_id},
            )
            .mappings()
            .first()
        )

    if row is None:
        raise HTTPException(status_code=404, detail="Agent run not found")

    total_records = int(row["total_records"] or 0)
    completed_records = int(row["completed_records"] or 0)
    failed_records = int(row["failed_records"] or 0)
    retry_count = int(row["retry_count"] or 0)
    status = str(row["status"])
    error_summary = (
        str(row["error_summary"]) if row["error_summary"] is not None else None
    )
    cost_data = _json_object(row["cost_actual"]) or _json_object(row["cost_estimate"])

    return AgentRunDetail(
        agent_run_id=str(row["id"]),
        workspace_id=str(row["workspace_id"]),
        dataset_id=str(row["dataset_id"]),
        agent_role=str(row["agent_role"]),
        plugin_adapter=str(row["adapter_plugin"] or "default"),
        model_profile_id=str(row["model_profile_id"]),
        model_identifier=str(row["model_identifier"]),
        runtime_profile_id=(
            str(row["runtime_profile_id"]) if row["runtime_profile_id"] else None
        ),
        prompt_version=str(row["prompt_version"] or "v1"),
        prompt_content_hash="",
        task_schema_id=str(row["task_schema_id"]),
        status=status,
        records_targeted=total_records,
        records_completed=completed_records,
        records_failed=failed_records,
        retry_count=retry_count,
        partial_failure_summary=error_summary if failed_records else None,
        comparison_id=str(row["comparison_id"]) if row["comparison_id"] else None,
        cost=CostInfo(**cost_data) if cost_data else None,
        execution_params=_json_object(row["config"]),
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        created_at=row["created_at"],
        error=error_summary if status in {"failed", "error"} else None,
        failure_envelope=_failure_envelope(
            run_id=str(row["id"]),
            status=status,
            error_summary=error_summary,
            failed_records=failed_records,
            completed_records=completed_records,
            total_records=total_records,
            retry_count=retry_count,
        ),
    )


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

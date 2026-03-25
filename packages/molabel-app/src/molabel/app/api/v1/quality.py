"""Quality endpoints -- /api/v1/quality.

Provides quality dashboard, inter-annotator agreement metrics, and
drift detection reports for monitoring labeling quality over time.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from molabel.app.middleware.session import CurrentReviewer

router = APIRouter(prefix="/quality", tags=["quality"])


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------


class ReadinessGate(BaseModel):
    """A single readiness gate evaluation result."""

    gate_id: str
    name: str
    status: str  # "passing" | "failing" | "not_evaluated"
    required_value: float | None = None
    current_value: float | None = None
    last_evaluated_at: datetime | None = None


class QualityTrendPoint(BaseModel):
    """A single point in a quality trend timeseries."""

    date: str
    agreement: float | None = None
    review_count: int = 0
    adjudication_count: int = 0


class QualityDashboard(BaseModel):
    """Aggregate quality dashboard for a workspace."""

    workspace_id: str
    overall_agreement: float | None = None
    human_agent_agreement: float | None = None
    inter_annotator_agreement: float | None = None
    review_coverage: float = 0.0
    adjudication_rate: float | None = None
    readiness_gates: list[ReadinessGate] = []
    recent_quality_trend: list[QualityTrendPoint] = []


class AgreementDetail(BaseModel):
    """Detailed agreement metrics for a single scope."""

    cohens_kappa: float | None = None
    percent_agreement: float | None = None
    krippendorffs_alpha: float | None = None
    sample_size: int = 0


class ReviewerAgreement(BaseModel):
    """Per-reviewer agreement metrics."""

    reviewer_id: str
    reviewer_name: str
    agreement_with_consensus: float | None = None
    agreement_with_agent: float | None = None
    records_reviewed: int = 0
    avg_review_time: float | None = None


class AgreementMetrics(BaseModel):
    """Full agreement metrics report."""

    overall: AgreementDetail
    per_field: dict[str, AgreementDetail] = {}
    per_reviewer: dict[str, ReviewerAgreement] = {}
    per_label_value: dict[str, dict[str, float]] = {}
    confusion_matrices: dict[str, list[list[int]]] = {}


class DriftIndicator(BaseModel):
    """A single drift detection indicator."""

    metric: str
    baseline_value: float
    current_value: float
    drift_magnitude: float
    detected_at: datetime


class DriftReport(BaseModel):
    """Drift detection report for a workspace/dataset."""

    dataset_id: str | None = None
    indicators: list[DriftIndicator] = []
    last_analyzed_at: datetime | None = None
    baseline_snapshot_id: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/dashboard", response_model=QualityDashboard)
async def get_quality_dashboard(
    reviewer: CurrentReviewer,
    workspace_id: Annotated[str, Query(description="Workspace ID (required)")],
    dataset_id: Annotated[
        str | None, Query(description="Optional dataset filter")
    ] = None,
    task_schema_id: Annotated[
        str | None, Query(description="Optional task schema filter")
    ] = None,
) -> QualityDashboard:
    """Get the quality dashboard for a workspace.

    Returns aggregate quality metrics including agreement scores,
    review coverage, adjudication rates, readiness gates, and
    recent quality trend data.
    """
    return QualityDashboard(
        workspace_id=workspace_id,
        overall_agreement=None,
        human_agent_agreement=None,
        inter_annotator_agreement=None,
        review_coverage=0.0,
        adjudication_rate=None,
        readiness_gates=[],
        recent_quality_trend=[],
    )


@router.get("/agreement", response_model=AgreementMetrics)
async def get_agreement_metrics(
    reviewer: CurrentReviewer,
    workspace_id: Annotated[str, Query(description="Workspace ID (required)")],
    dataset_id: Annotated[
        str | None, Query(description="Optional dataset filter")
    ] = None,
    task_schema_id: Annotated[
        str | None, Query(description="Optional task schema filter")
    ] = None,
) -> AgreementMetrics:
    """Get detailed inter-annotator agreement metrics.

    Returns overall, per-field, per-reviewer, and per-label agreement
    metrics including Cohen's kappa, Krippendorff's alpha, and
    confusion matrices.
    """
    return AgreementMetrics(
        overall=AgreementDetail(
            cohens_kappa=None,
            percent_agreement=None,
            krippendorffs_alpha=None,
            sample_size=0,
        ),
        per_field={},
        per_reviewer={},
        per_label_value={},
        confusion_matrices={},
    )


@router.get("/drift", response_model=DriftReport)
async def get_drift_report(
    reviewer: CurrentReviewer,
    workspace_id: Annotated[str, Query(description="Workspace ID (required)")],
    dataset_id: Annotated[
        str | None, Query(description="Optional dataset filter")
    ] = None,
) -> DriftReport:
    """Get the drift detection report for a workspace/dataset.

    Identifies statistical drift in labeling patterns compared to a
    baseline snapshot.
    """
    return DriftReport(
        dataset_id=dataset_id,
        indicators=[],
        last_analyzed_at=None,
        baseline_snapshot_id=None,
    )

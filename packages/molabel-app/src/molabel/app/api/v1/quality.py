"""Quality endpoints -- /api/v1/quality.

Provides the quality dashboard, agreement measured from review events, and
drift detection reports. The dashboard and drift report are not computed yet.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import text

from molabel.app.middleware.session import CurrentReviewer
from molabel.app.services.review_events import (
    queue_agent_proposals,
    queue_review_events,
)
from molabel.app.utils import get_engine
from molabel.core.quality.agreement_metrics import (
    AgreementAnalysisResult,
    AgreementMetricsService,
    AgreementMetricSummary,
)
from molabel.core.quality.review_agreement import agreement_records_from_reviews

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


class AgreementScope(BaseModel):
    """Agreement among one set of raters.

    ``pooled`` pools every field into one variable, so it is not an average
    of ``fields``. ``skipped_fields`` maps each field whose Krippendorff's
    alpha is undefined to the reason.
    """

    pooled: AgreementMetricSummary
    fields: dict[str, AgreementMetricSummary] = {}
    skipped_fields: dict[str, str | None] = {}


class AgreementReport(BaseModel):
    """Agreement measured from the review events of the queues in scope.

    ``inter_annotator`` rates reviewers against each other, and
    ``human_agent`` pairs each reviewer's value with each agent proposal.
    """

    workspace_id: str
    queue_id: str | None = None
    dataset_id: str | None = None
    task_schema_id: str | None = None
    record_count: int = 0
    reviewer_count: int = 0
    inter_annotator: AgreementScope
    human_agent: AgreementScope
    warnings: list[str] = []


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


def _scope(result: AgreementAnalysisResult) -> AgreementScope:
    return AgreementScope(
        pooled=result.overall,
        fields=result.fields,
        skipped_fields={
            field: summary.null_reasons.get("krippendorff_alpha")
            for field, summary in result.fields.items()
            if summary.krippendorff_alpha is None
        },
    )


def _label_field_names(conn: Any, task_schema_id: str) -> list[str] | None:
    raw = conn.execute(
        text("SELECT label_fields FROM task_schemas WHERE id = :id"),
        {"id": task_schema_id},
    ).scalar()
    fields = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(fields, list):
        return None
    return [field["name"] for field in fields if isinstance(field, dict)]


@router.get("/agreement", response_model=AgreementReport)
async def get_agreement_metrics(
    request: Request,
    reviewer: CurrentReviewer,
    workspace_id: Annotated[str, Query(description="Workspace ID (required)")],
    queue_id: Annotated[str | None, Query(description="Optional queue filter")] = None,
    dataset_id: Annotated[
        str | None, Query(description="Optional dataset filter")
    ] = None,
    task_schema_id: Annotated[
        str | None, Query(description="Optional task schema filter")
    ] = None,
) -> AgreementReport:
    """Measure agreement over the review tasks in scope.

    Each reviewer and each agent run is one rater, and a reviewer's value is
    the labels their counted review event stores. With one task schema in
    scope, every label field of the schema is reported, measured or skipped.
    ``docs/guides/agreement-metrics.md`` gives the formulas and the rules.
    It measures only the caller's workspace, and answers 404 for any other.
    """
    if workspace_id != str(reviewer.workspace_id):
        raise HTTPException(status_code=404, detail="Workspace not found")
    with get_engine(request).connect() as conn:
        tasks = conn.execute(
            text(
                "SELECT DISTINCT queue_id, record_id, task_schema_id "
                "FROM review_tasks WHERE workspace_id = :workspace_id "
                "AND (:queue_id IS NULL OR queue_id = :queue_id) "
                "AND (:dataset_id IS NULL OR dataset_id = :dataset_id) "
                "AND (:task_schema_id IS NULL OR task_schema_id = :task_schema_id)"
            ),
            {
                "workspace_id": workspace_id,
                "queue_id": queue_id,
                "dataset_id": dataset_id,
                "task_schema_id": task_schema_id,
            },
        ).fetchall()
        queue_ids = sorted({str(row[0]) for row in tasks})
        schema_ids = {str(row[2]) for row in tasks}
        records = agreement_records_from_reviews(
            queue_review_events(conn, queue_ids),
            queue_agent_proposals(conn, queue_ids),
            record_ids=[str(row[1]) for row in tasks],
        )
        fields = (
            _label_field_names(conn, next(iter(schema_ids)))
            if len(schema_ids) == 1
            else None
        )

    service = AgreementMetricsService()
    inter_annotator = service.analyze(
        records, analysis_type="inter_annotator", fields=fields
    )
    human_agent = service.analyze(records, analysis_type="human_agent", fields=fields)
    return AgreementReport(
        workspace_id=workspace_id,
        queue_id=queue_id,
        dataset_id=dataset_id,
        task_schema_id=task_schema_id,
        record_count=len(records),
        reviewer_count=len(
            {
                annotation.rater
                for record in records
                for annotation in record.annotations
                if annotation.source == "human"
            }
        ),
        inter_annotator=_scope(inter_annotator),
        human_agent=_scope(human_agent),
        warnings=[*inter_annotator.warnings, *human_agent.warnings],
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

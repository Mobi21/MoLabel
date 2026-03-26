"""Focused tests for AgreementAnalysisExecutor wiring."""

from __future__ import annotations

import pytest

from molabel.core.quality.agreement_metrics import AgreementMetricsService
from molabel.core.workflow.context import RecordSet, WorkflowContext
from molabel.core.workflow.steps.quality_steps import AgreementAnalysisExecutor


class _RecordingAgreementDataSource:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def load_agreement_records(
        self,
        *,
        record_ids: list[str],
        review_queue_ids: list[str],
        agent_run_ids: list[str],
        analysis_type: str,
        config: dict[str, object],
    ) -> list[dict[str, object]]:
        self.calls.append(
            {
                "record_ids": list(record_ids),
                "review_queue_ids": list(review_queue_ids),
                "agent_run_ids": list(agent_run_ids),
                "analysis_type": analysis_type,
                "config": dict(config),
            }
        )
        return [
            {
                "record_id": "r1",
                "annotations": [
                    {"source": "human", "labels": {"sentiment": "positive"}},
                    {"source": "agent", "labels": {"sentiment": "positive"}},
                ],
            },
            {
                "record_id": "r2",
                "annotations": [
                    {"source": "human", "labels": {"sentiment": "positive"}},
                    {"source": "agent", "labels": {"sentiment": "negative"}},
                ],
            },
            {
                "record_id": "r3",
                "annotations": [
                    {"source": "human", "labels": {"sentiment": "negative"}},
                    {"source": "agent", "labels": {"sentiment": "negative"}},
                ],
            },
        ]


class _HumanHeavyAgreementDataSource:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def load_agreement_records(
        self,
        *,
        record_ids: list[str],
        review_queue_ids: list[str],
        agent_run_ids: list[str],
        analysis_type: str,
        config: dict[str, object],
    ) -> list[dict[str, object]]:
        self.calls.append(
            {
                "record_ids": list(record_ids),
                "review_queue_ids": list(review_queue_ids),
                "agent_run_ids": list(agent_run_ids),
                "analysis_type": analysis_type,
                "config": dict(config),
            }
        )
        return [
            {
                "record_id": "r1",
                "annotations": [
                    {"source": "human", "labels": {"sentiment": "positive"}},
                    {"source": "human", "labels": {"sentiment": "positive"}},
                    {"source": "agent", "labels": {"sentiment": "negative"}},
                ],
            }
        ]


def _context() -> WorkflowContext:
    ctx = WorkflowContext(
        workspace_id="ws-1",
        workflow_execution_id="exec-1",
        workflow_version=1,
    )
    ctx.record_sets["_init"] = RecordSet(record_ids=["r1", "r2", "r3"], record_count=3)
    ctx.active_record_set_id = "_init"
    ctx.review_queue_ids = ["review-1"]
    ctx.agent_run_ids = ["agent-1"]
    return ctx


def test_executor_uses_metrics_service_and_writes_flat_metrics() -> None:
    executor = AgreementAnalysisExecutor()
    ctx = _context()
    data_source = _RecordingAgreementDataSource()
    metrics_service = AgreementMetricsService()

    result = executor.execute(
        "agreement",
        {"analysis_type": "both"},
        ctx,
        services={
            "agreement_data_source": data_source,
            "agreement_metrics_service": metrics_service,
        },
    )

    assert result.success
    assert len(data_source.calls) == 1
    assert data_source.calls[0]["record_ids"] == ["r1", "r2", "r3"]
    assert data_source.calls[0]["analysis_type"] == "both"

    assert ctx.metrics["agreement.kappa"] == pytest.approx(1 / 3)
    assert ctx.metrics["agreement.percent_agreement"] == pytest.approx(2 / 3)
    assert ctx.metrics["agreement.fleiss_kappa"] == pytest.approx(1 / 3)
    assert ctx.metrics["agreement.krippendorff_alpha"] == pytest.approx(1 / 3)
    assert ctx.metrics["agreement.human_agent_agreement"] == pytest.approx(2 / 3)
    assert ctx.metrics["agreement.human_agent.by_field.sentiment.agreement_rate"] == (
        pytest.approx(2 / 3)
    )
    assert ctx.metrics[
        "agreement.human_agent.by_field.sentiment.label_value.positive.agreement_rate"
    ] == pytest.approx(1 / 2)

    assert result.output is not None
    assert result.output.summary["overall"]["cohen_kappa"] == pytest.approx(1 / 3)
    assert result.output.summary["human_agent_by_field"]["sentiment"][
        "agreement_rate"
    ] == pytest.approx(2 / 3)


def test_validate_rejects_invalid_analysis_type() -> None:
    executor = AgreementAnalysisExecutor()
    ctx = _context()

    errors = executor.validate("agreement", {"analysis_type": "invalid"}, ctx)

    assert errors


def test_executor_human_agent_ignores_human_human_pairs() -> None:
    executor = AgreementAnalysisExecutor()
    ctx = _context()
    data_source = _HumanHeavyAgreementDataSource()

    result = executor.execute(
        "agreement",
        {"analysis_type": "human_agent"},
        ctx,
        services={
            "agreement_data_source": data_source,
            "agreement_metrics_service": AgreementMetricsService(),
        },
    )

    assert result.success
    assert len(data_source.calls) == 1
    assert ctx.metrics["agreement.percent_agreement"] == pytest.approx(0.0)
    assert ctx.metrics["agreement.kappa"] == pytest.approx(-1.0)
    assert result.output is not None
    assert result.output.summary["overall"]["comparisons"] == 2
    assert result.output.summary["overall"]["percent_agreement"] == pytest.approx(0.0)

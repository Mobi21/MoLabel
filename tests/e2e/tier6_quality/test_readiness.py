"""Readiness dashboard test (T6-10).

Gate evaluation: passing/failing/not_evaluated, overall readiness.
Uses ReadinessDashboardService (QA-008) with configurable ReadinessGate objects.
"""

from __future__ import annotations

import pytest

from molabel.core.quality.readiness import (
    ReadinessDashboardService,
    ReadinessGate,
)
from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SHARED_WORKSPACE


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier6
async def test_readiness_gate_evaluation(
    ctx: TestContext,
    client: InstrumentedClient,
) -> None:
    """T6-10: Gate evaluation: passing/failing/not_evaluated, overall readiness."""
    service = ReadinessDashboardService()

    with checkpoint(ctx, "all_gates_pass_dataset_ready"):
        metrics = {
            "agreement_rate": 0.92,
            "coverage": 0.95,
            "avg_confidence": 0.88,
        }
        gates = [
            ReadinessGate(
                gate_name="min_agreement",
                metric_key="agreement_rate",
                threshold=0.85,
                comparison="gte",
            ),
            ReadinessGate(
                gate_name="min_coverage",
                metric_key="coverage",
                threshold=0.90,
                comparison="gte",
            ),
            ReadinessGate(
                gate_name="min_confidence",
                metric_key="avg_confidence",
                threshold=0.80,
                comparison="gte",
            ),
        ]

        result = service.assess(metrics, gates=gates)
        assert result.ready is True
        assert result.gates_passed == 3
        assert result.gates_total == 3
        assert "All 3 gates passed" in result.summary

        for gate_status in result.gates:
            assert gate_status.passed is True

    with checkpoint(ctx, "single_gate_failure_not_ready"):
        metrics_fail = {
            "agreement_rate": 0.80,  # below 0.85 threshold
            "coverage": 0.95,
            "avg_confidence": 0.88,
        }
        gates_same = [
            ReadinessGate(
                gate_name="min_agreement",
                metric_key="agreement_rate",
                threshold=0.85,
                comparison="gte",
            ),
            ReadinessGate(
                gate_name="min_coverage",
                metric_key="coverage",
                threshold=0.90,
                comparison="gte",
            ),
            ReadinessGate(
                gate_name="min_confidence",
                metric_key="avg_confidence",
                threshold=0.80,
                comparison="gte",
            ),
        ]

        result_fail = service.assess(metrics_fail, gates=gates_same)
        assert result_fail.ready is False
        assert result_fail.gates_passed == 2
        assert result_fail.gates_total == 3

        failed_gate = next(
            g for g in result_fail.gates if g.gate_name == "min_agreement"
        )
        assert failed_gate.passed is False
        assert failed_gate.current_value == pytest.approx(0.80)
        assert failed_gate.threshold == pytest.approx(0.85)
        assert "min_agreement" in result_fail.summary

    with checkpoint(ctx, "lte_comparison_passes_when_below_threshold"):
        # Error rate must be below threshold
        metrics_lte = {"error_rate": 0.03}
        gate_lte = [
            ReadinessGate(
                gate_name="max_error_rate",
                metric_key="error_rate",
                threshold=0.05,
                comparison="lte",
            ),
        ]

        result_lte = service.assess(metrics_lte, gates=gate_lte)
        assert result_lte.ready is True
        error_gate = result_lte.gates[0]
        assert error_gate.passed is True

    with checkpoint(ctx, "lte_comparison_fails_when_above_threshold"):
        metrics_lte_fail = {"error_rate": 0.08}
        gate_lte_fail = [
            ReadinessGate(
                gate_name="max_error_rate",
                metric_key="error_rate",
                threshold=0.05,
                comparison="lte",
            ),
        ]

        result_lte_fail = service.assess(metrics_lte_fail, gates=gate_lte_fail)
        assert result_lte_fail.ready is False
        error_gate_fail = result_lte_fail.gates[0]
        assert error_gate_fail.passed is False

    with checkpoint(ctx, "gt_and_lt_comparisons"):
        metrics_strict = {
            "kappa": 0.75,
            "drift_score": 0.04,
        }
        gates_strict = [
            ReadinessGate(
                gate_name="kappa_gt",
                metric_key="kappa",
                threshold=0.70,
                comparison="gt",
            ),
            ReadinessGate(
                gate_name="drift_lt",
                metric_key="drift_score",
                threshold=0.05,
                comparison="lt",
            ),
        ]

        result_strict = service.assess(metrics_strict, gates=gates_strict)
        assert result_strict.ready is True
        assert result_strict.gates_passed == 2

    with checkpoint(ctx, "eq_comparison"):
        metrics_eq = {"label_version": 2.0}
        gate_eq = [
            ReadinessGate(
                gate_name="version_check",
                metric_key="label_version",
                threshold=2.0,
                comparison="eq",
            ),
        ]

        result_eq = service.assess(metrics_eq, gates=gate_eq)
        assert result_eq.ready is True
        assert result_eq.gates[0].passed is True

    with checkpoint(ctx, "missing_metric_key_treated_as_zero"):
        metrics_missing = {"coverage": 0.95}
        gates_missing = [
            ReadinessGate(
                gate_name="min_agreement",
                metric_key="agreement_rate",
                threshold=0.85,
                comparison="gte",
            ),
            ReadinessGate(
                gate_name="min_coverage",
                metric_key="coverage",
                threshold=0.90,
                comparison="gte",
            ),
        ]

        result_missing = service.assess(metrics_missing, gates=gates_missing)
        # agreement_rate missing → treated as 0.0 → fails
        assert result_missing.ready is False
        assert any("agreement_rate" in w for w in result_missing.warnings)

        agreement_gate = next(
            g for g in result_missing.gates if g.gate_name == "min_agreement"
        )
        assert agreement_gate.current_value == pytest.approx(0.0)
        assert agreement_gate.passed is False

    with checkpoint(ctx, "no_gates_configured_ready_by_default"):
        empty_service = ReadinessDashboardService()
        result_empty = empty_service.assess({"coverage": 0.9})
        assert result_empty.ready is True
        assert result_empty.gates_total == 0
        assert any("No readiness gates" in w for w in result_empty.warnings)

    with checkpoint(ctx, "default_gates_used_when_none_passed"):
        default_gate_service = ReadinessDashboardService(
            default_gates=[
                ReadinessGate(
                    gate_name="default_coverage",
                    metric_key="coverage",
                    threshold=0.85,
                    comparison="gte",
                ),
            ]
        )

        # assess() with no gates= argument uses default_gates
        result_default = default_gate_service.assess({"coverage": 0.90})
        assert result_default.ready is True
        assert result_default.gates_total == 1
        assert result_default.gates[0].gate_name == "default_coverage"

    with checkpoint(ctx, "per_gate_current_value_recorded"):
        metrics_vals = {
            "agreement_rate": 0.87,
            "coverage": 0.91,
        }
        gates_vals = [
            ReadinessGate(
                gate_name="agreement",
                metric_key="agreement_rate",
                threshold=0.85,
                comparison="gte",
            ),
            ReadinessGate(
                gate_name="coverage",
                metric_key="coverage",
                threshold=0.90,
                comparison="gte",
            ),
        ]

        result_vals = service.assess(metrics_vals, gates=gates_vals)
        gate_map = {g.gate_name: g for g in result_vals.gates}

        assert gate_map["agreement"].current_value == pytest.approx(0.87)
        assert gate_map["coverage"].current_value == pytest.approx(0.91)
        assert gate_map["agreement"].threshold == pytest.approx(0.85)
        assert gate_map["coverage"].threshold == pytest.approx(0.90)

    with checkpoint(ctx, "all_gates_failed_summary_lists_them"):
        metrics_all_fail = {
            "agreement_rate": 0.50,
            "coverage": 0.60,
        }
        gates_all_fail = [
            ReadinessGate(
                gate_name="min_agreement",
                metric_key="agreement_rate",
                threshold=0.85,
                comparison="gte",
            ),
            ReadinessGate(
                gate_name="min_coverage",
                metric_key="coverage",
                threshold=0.90,
                comparison="gte",
            ),
        ]

        result_all_fail = service.assess(metrics_all_fail, gates=gates_all_fail)
        assert result_all_fail.ready is False
        assert result_all_fail.gates_passed == 0
        assert "min_agreement" in result_all_fail.summary
        assert "min_coverage" in result_all_fail.summary

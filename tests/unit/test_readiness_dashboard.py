"""Tests for the readiness dashboard service (QA-008)."""

from __future__ import annotations

import pytest

from molabel.core.quality.readiness import (
    ReadinessDashboardService,
    ReadinessGate,
)


def test_all_gates_passed() -> None:
    service = ReadinessDashboardService()
    result = service.assess(
        metrics={
            "agreement.kappa": 0.85,
            "review.coverage": 0.95,
            "drift.max_shift": 0.02,
        },
        gates=[
            ReadinessGate(
                gate_name="Min Agreement",
                metric_key="agreement.kappa",
                threshold=0.8,
                comparison="gte",
            ),
            ReadinessGate(
                gate_name="Min Coverage",
                metric_key="review.coverage",
                threshold=0.9,
                comparison="gte",
            ),
            ReadinessGate(
                gate_name="Max Drift",
                metric_key="drift.max_shift",
                threshold=0.1,
                comparison="lte",
            ),
        ],
    )

    assert result.ready is True
    assert result.gates_passed == 3
    assert result.gates_total == 3
    assert all(g.passed for g in result.gates)
    assert "ready" in result.summary.lower()


def test_one_gate_failed() -> None:
    service = ReadinessDashboardService()
    result = service.assess(
        metrics={
            "agreement.kappa": 0.65,
            "review.coverage": 0.95,
        },
        gates=[
            ReadinessGate(
                gate_name="Min Agreement",
                metric_key="agreement.kappa",
                threshold=0.8,
                comparison="gte",
            ),
            ReadinessGate(
                gate_name="Min Coverage",
                metric_key="review.coverage",
                threshold=0.9,
                comparison="gte",
            ),
        ],
    )

    assert result.ready is False
    assert result.gates_passed == 1
    assert result.gates_total == 2
    failed_gates = [g for g in result.gates if not g.passed]
    assert len(failed_gates) == 1
    assert failed_gates[0].gate_name == "Min Agreement"
    assert "Min Agreement" in result.summary


def test_missing_metric_treated_as_zero() -> None:
    service = ReadinessDashboardService()
    result = service.assess(
        metrics={},
        gates=[
            ReadinessGate(
                gate_name="Min Agreement",
                metric_key="agreement.kappa",
                threshold=0.8,
                comparison="gte",
            ),
        ],
    )

    assert result.ready is False
    assert result.gates[0].current_value == pytest.approx(0.0)
    assert len(result.warnings) > 0
    assert any("not found" in w.lower() for w in result.warnings)


def test_no_gates_configured() -> None:
    service = ReadinessDashboardService()
    result = service.assess(metrics={"agreement.kappa": 0.9})

    assert result.ready is True
    assert result.gates_total == 0
    assert len(result.warnings) > 0


def test_lte_comparison() -> None:
    service = ReadinessDashboardService()
    result = service.assess(
        metrics={"drift.max_shift": 0.15},
        gates=[
            ReadinessGate(
                gate_name="Max Drift",
                metric_key="drift.max_shift",
                threshold=0.1,
                comparison="lte",
            ),
        ],
    )

    assert result.ready is False
    assert result.gates[0].passed is False


def test_gt_comparison() -> None:
    service = ReadinessDashboardService()
    result = service.assess(
        metrics={"review.count": 100},
        gates=[
            ReadinessGate(
                gate_name="Min Reviews",
                metric_key="review.count",
                threshold=100,
                comparison="gt",
                description="Must have more than 100 reviews.",
            ),
        ],
    )

    # 100 is not > 100
    assert result.ready is False
    assert result.gates[0].passed is False


def test_lt_comparison() -> None:
    service = ReadinessDashboardService()
    result = service.assess(
        metrics={"error.rate": 0.01},
        gates=[
            ReadinessGate(
                gate_name="Low Error Rate",
                metric_key="error.rate",
                threshold=0.05,
                comparison="lt",
            ),
        ],
    )

    assert result.ready is True
    assert result.gates[0].passed is True


def test_eq_comparison() -> None:
    service = ReadinessDashboardService()
    result = service.assess(
        metrics={"version": 2.0},
        gates=[
            ReadinessGate(
                gate_name="Schema Version",
                metric_key="version",
                threshold=2.0,
                comparison="eq",
            ),
        ],
    )

    assert result.ready is True
    assert result.gates[0].passed is True


def test_default_gates() -> None:
    service = ReadinessDashboardService(
        default_gates=[
            ReadinessGate(
                gate_name="Min Agreement",
                metric_key="agreement.kappa",
                threshold=0.7,
            ),
        ]
    )
    result = service.assess(metrics={"agreement.kappa": 0.85})

    assert result.ready is True
    assert result.gates_total == 1
    assert result.gates[0].gate_name == "Min Agreement"


def test_override_default_gates() -> None:
    service = ReadinessDashboardService(
        default_gates=[
            ReadinessGate(
                gate_name="Default Gate",
                metric_key="agreement.kappa",
                threshold=0.7,
            ),
        ]
    )
    result = service.assess(
        metrics={"review.count": 50.0},
        gates=[
            ReadinessGate(
                gate_name="Custom Gate",
                metric_key="review.count",
                threshold=10.0,
            ),
        ],
    )

    assert result.gates_total == 1
    assert result.gates[0].gate_name == "Custom Gate"


def test_dict_gate_input() -> None:
    service = ReadinessDashboardService()
    result = service.assess(
        metrics={"agreement.kappa": 0.9},
        gates=[
            {
                "gate_name": "Min Agreement",
                "metric_key": "agreement.kappa",
                "threshold": 0.8,
            },
        ],
    )

    assert result.ready is True
    assert result.gates_total == 1


def test_gate_status_captures_current_value() -> None:
    service = ReadinessDashboardService()
    result = service.assess(
        metrics={"agreement.kappa": 0.75},
        gates=[
            ReadinessGate(
                gate_name="Min Agreement",
                metric_key="agreement.kappa",
                threshold=0.8,
                description="Agreement must be at least 80%.",
            ),
        ],
    )

    gate = result.gates[0]
    assert gate.gate_name == "Min Agreement"
    assert gate.threshold == pytest.approx(0.8)
    assert gate.current_value == pytest.approx(0.75)
    assert gate.passed is False
    assert gate.description == "Agreement must be at least 80%."
    assert gate.comparison == "gte"

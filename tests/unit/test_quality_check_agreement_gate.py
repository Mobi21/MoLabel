"""quality_check's min_agreement gate on the output of agreement_analysis."""

from __future__ import annotations

from typing import Any

import pytest

from molabel.core.workflow.context import WorkflowContext
from molabel.core.workflow.steps.quality_steps import (
    AgreementAnalysisExecutor,
    QualityCheckExecutor,
)


def _records(units: list[dict[str, tuple[str, ...]]]) -> list[dict[str, Any]]:
    """One record per unit. A unit maps each field to the values of r0, r1, ..."""
    return [
        {
            "record_id": f"u{index}",
            "annotations": [
                {
                    "source": "human",
                    "rater_id": f"r{rater}",
                    "labels": dict(zip(unit, values, strict=True)),
                }
                for rater, values in enumerate(zip(*unit.values(), strict=True))
            ],
        }
        for index, unit in enumerate(units)
    ]


class _ReportingChecker:
    def __init__(self, agreement: float) -> None:
        self.agreement = agreement

    def check(self, **_: Any) -> dict[str, float]:
        return {"agreement": self.agreement}


def _run_gate(
    records: list[dict[str, Any]],
    min_agreement: float,
    services: dict[str, Any] | None = None,
) -> tuple[WorkflowContext, dict[str, Any]]:
    ctx = WorkflowContext(
        workspace_id="ws-1", workflow_execution_id="exec-1", workflow_version=1
    )
    analysis = AgreementAnalysisExecutor().execute(
        "agreement",
        {"analysis_type": "inter_annotator", "agreement_records": records},
        ctx,
    )
    assert analysis.success
    check = QualityCheckExecutor().execute(
        "quality", {"min_agreement": min_agreement}, ctx, services
    )
    assert check.success
    assert check.output is not None
    return ctx, check.output.summary["details"][0]


THREE_RATERS = [
    {"code": ("a", "a", "a")},
    {"code": ("b", "b", "b")},
    {"code": ("a", "a", "a")},
    {"code": ("b", "b", "b")},
    {"code": ("a", "a", "b")},
]


@pytest.mark.parametrize(("min_agreement", "passed"), [(0.7, True), (0.8, False)])
def test_min_agreement_gates_on_alpha_for_three_raters(
    min_agreement: float, passed: bool
) -> None:
    ctx, detail = _run_gate(_records(THREE_RATERS), min_agreement)

    assert "agreement.kappa" not in ctx.metrics
    assert ctx.variables["quality.passed"] is passed
    # n = 15 with a = 8, b = 7. Only the last unit mismatches, 2 coincidences:
    # alpha = 1 - 14 * 2 / (225 - 64 - 49) = 0.75.
    assert detail["actual"] == pytest.approx(0.75)
    assert detail["passed"] is passed
    assert detail["metric"] == "krippendorff_alpha"


def test_min_agreement_fails_on_one_field_while_the_pooled_alpha_passes() -> None:
    units = [
        {"sentiment": ("pos", "pos"), "topic": ("x", "x")},
        {"sentiment": ("neg", "neg"), "topic": ("y", "x")},
        {"sentiment": ("pos", "pos"), "topic": ("x", "y")},
        {"sentiment": ("neg", "neg"), "topic": ("y", "y")},
    ]

    ctx, detail = _run_gate(_records(units), 0.6)

    # Pooled: n = 16 over four labels of 4 each, 4 mismatching coincidences:
    # alpha = 1 - 15 * 4 / (256 - 64) = 0.6875.
    assert ctx.metrics["agreement.krippendorff_alpha"] == pytest.approx(0.6875)
    assert ctx.variables["quality.passed"] is False
    # topic: n = 8 with x = y = 4, 4 mismatching coincidences: 1 - 7 * 4 / 32.
    assert detail["failing_fields"] == pytest.approx({"topic": 0.125})
    assert detail["fields"] == pytest.approx({"sentiment": 1.0, "topic": 0.125})
    assert detail["actual"] == pytest.approx(0.125)


def test_min_agreement_fails_on_a_field_whose_alpha_is_null() -> None:
    units = [
        {"sentiment": ("pos", "pos"), "flag": ("no", "no")},
        {"sentiment": ("neg", "neg"), "flag": ("no", "no")},
    ]

    ctx, detail = _run_gate(_records(units), 0.8)

    assert ctx.metrics["agreement.krippendorff_alpha"] == pytest.approx(1.0)
    assert ctx.variables["quality.passed"] is False
    assert detail["failing_fields"] == {"flag": None}


PER_FIELD_SPLIT = [
    {"sentiment": ("pos", "pos"), "topic": ("x", "x")},
    {"sentiment": ("neg", "neg"), "topic": ("y", "x")},
    {"sentiment": ("pos", "pos"), "topic": ("x", "y")},
    {"sentiment": ("neg", "neg"), "topic": ("y", "y")},
]


@pytest.mark.parametrize("reported", [0.99, 0.1])
def test_an_injected_checker_cannot_override_the_field_minimum(
    reported: float,
) -> None:
    ctx, detail = _run_gate(
        _records(PER_FIELD_SPLIT),
        0.6,
        {"quality_checker": _ReportingChecker(reported)},
    )

    assert detail["actual"] == pytest.approx(0.125)
    assert ctx.metrics["quality.agreement"] == pytest.approx(0.125)
    assert ctx.variables["quality.passed"] is False


def test_an_injected_checker_cannot_fail_fields_that_all_agree() -> None:
    units = [{"code": ("a", "a")}, {"code": ("b", "b")}]

    ctx, detail = _run_gate(
        _records(units), 0.6, {"quality_checker": _ReportingChecker(0.1)}
    )

    assert detail["actual"] == pytest.approx(1.0)
    assert ctx.variables["quality.passed"] is True

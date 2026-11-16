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
    """One record per unit. A unit maps each field to rater r1, r2, r3's values."""
    return [
        {
            "record_id": f"u{index}",
            "annotations": [
                {
                    "source": "human",
                    "rater_id": f"r{rater}",
                    "labels": {field: values[rater] for field, values in unit.items()},
                }
                for rater in range(3)
            ],
        }
        for index, unit in enumerate(units)
    ]


def _run_gate(
    records: list[dict[str, Any]], min_agreement: float
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
        "quality", {"min_agreement": min_agreement}, ctx
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

"""quality_check's min_agreement gate on the output of agreement_analysis."""

from __future__ import annotations

from typing import Any

import pytest

from molabel.core.quality.agreement_metrics import (
    NO_PAIRABLE_VALUES,
    SINGLE_CATEGORY,
)
from molabel.core.workflow.context import WorkflowContext
from molabel.core.workflow.steps.quality_steps import (
    AgreementAnalysisExecutor,
    QualityCheckExecutor,
)


def _records(
    units: list[dict[str, tuple[str | None, ...]]],
) -> list[dict[str, Any]]:
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
    required: list[str] | None = None,
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
    config: dict[str, Any] = {"min_agreement": min_agreement}
    if required is not None:
        config["fields"] = required
    check = QualityCheckExecutor().execute("quality", config, ctx, services)
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


SENTIMENT_SPLIT = [("pos", "pos"), ("neg", "neg"), ("pos", "neg"), ("neg", "neg")]
# n = 8 with pos = 3, neg = 5, and one mismatching unit, 2 coincidences:
# alpha = 1 - 7 * 2 / (64 - 9 - 25) = 8 / 15.
SENTIMENT_ALPHA = 8 / 15


@pytest.mark.parametrize(
    ("other", "reason"),
    [
        (("x", None), NO_PAIRABLE_VALUES),
        (("no", "no"), SINGLE_CATEGORY),
    ],
    ids=["one-rater", "one-label"],
)
def test_a_null_field_is_skipped_and_the_measured_fields_decide(
    other: tuple[str | None, str | None], reason: str
) -> None:
    units = [{"sentiment": pair, "other": other} for pair in SENTIMENT_SPLIT]

    ctx, detail = _run_gate(_records(units), 0.5)

    assert detail["skipped_fields"] == {"other": reason}
    assert detail["fields"] == pytest.approx(
        {"sentiment": SENTIMENT_ALPHA, "other": None}
    )
    assert detail["failing_fields"] == {}
    assert (detail["passed"], detail["code"]) == (True, None)
    assert detail["actual"] == pytest.approx(SENTIMENT_ALPHA)
    assert ctx.metrics["quality.agreement"] == pytest.approx(SENTIMENT_ALPHA)
    assert ctx.variables["quality.passed"] is True
    summary = ctx.variables["agreement.fields"]["other"]
    assert summary["null_reasons"]["krippendorff_alpha"] == reason


@pytest.mark.parametrize("required", [["flag"], ["sentiment", "absent"]])
def test_a_required_field_that_is_null_fails_the_gate(required: list[str]) -> None:
    units = [{"sentiment": pair, "flag": ("no", "no")} for pair in SENTIMENT_SPLIT]

    ctx, detail = _run_gate(_records(units), 0.5, required=required)

    null_field = required[-1]
    assert detail["failing_fields"] == {null_field: None}
    assert null_field not in detail["skipped_fields"]
    assert (detail["passed"], detail["actual"], detail["code"]) == (False, None, None)
    assert "quality.agreement" not in ctx.metrics
    assert ctx.variables["quality.passed"] is False


def test_a_required_field_below_the_threshold_fails_the_gate() -> None:
    units = [{"sentiment": pair, "flag": ("no", "no")} for pair in SENTIMENT_SPLIT]

    ctx, detail = _run_gate(_records(units), 0.6, required=["sentiment"])

    assert detail["failing_fields"] == pytest.approx({"sentiment": SENTIMENT_ALPHA})
    assert detail["skipped_fields"] == {"flag": SINGLE_CATEGORY}
    assert detail["actual"] == pytest.approx(SENTIMENT_ALPHA)
    assert ctx.variables["quality.passed"] is False


def test_the_gate_fails_when_every_field_is_skipped() -> None:
    units = [
        {"flag": ("no", "no"), "note": ("x", None)},
        {"flag": ("no", "no"), "note": ("y", None)},
    ]

    ctx, detail = _run_gate(_records(units), 0.5)

    assert detail["skipped_fields"] == {
        "flag": SINGLE_CATEGORY,
        "note": NO_PAIRABLE_VALUES,
    }
    assert (detail["passed"], detail["actual"], detail["code"]) == (
        False,
        None,
        "NO_MEASURED_FIELDS",
    )
    assert "quality.agreement" not in ctx.metrics
    assert ctx.variables["quality.passed"] is False


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


@pytest.mark.parametrize("analyzed", [False, True], ids=["no-analysis", "no-records"])
def test_min_agreement_fails_when_no_agreement_records_were_analyzed(
    analyzed: bool,
) -> None:
    ctx = WorkflowContext(
        workspace_id="ws-1", workflow_execution_id="exec-1", workflow_version=1
    )
    ctx.metrics["quality.agreement"] = 0.9
    if analyzed:
        AgreementAnalysisExecutor().execute(
            "agreement", {"agreement_records": [], "fields": ["code"]}, ctx
        )

    check = QualityCheckExecutor().execute("quality", {"min_agreement": 0.8}, ctx)

    assert check.output is not None
    detail = check.output.summary["details"][0]
    assert (detail["passed"], detail["actual"], detail["code"]) == (
        False,
        None,
        "NO_AGREEMENT_RECORDS",
    )
    assert check.output.warnings == [f"NO_AGREEMENT_RECORDS: {detail['reason']}"]
    assert ctx.variables["quality.passed"] is False
    assert "quality.agreement" not in ctx.metrics

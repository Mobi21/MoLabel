"""Macro F1 through the grounded scorer matches its per-label definition.

Per label, precision is tp / (tp + fp), recall is tp / (tp + fn), and F1 is
their harmonic mean, each 0 when its denominator is 0. Macro F1 is the mean
of F1 over the labels seen in the gold or in a prediction that carries the
field. A record with no prediction predicts null, which counts as a false
negative for its gold label.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import pytest
import yaml

from molabel.core.quality.grounded_benchmarks import (
    GroundedBaselines,
    GroundedBenchmarkBundle,
    GroundedBenchmarkScenario,
    GroundedLabelMap,
    GroundedMetricsConfig,
    GroundedPaperMetadata,
    score_grounded_stage,
)
from molabel.core.utils.canonical import canonical_label_value

AUTHORITY = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "benchmarks-grounded"
    / "banking77"
    / "authority"
)
FIELD = "intent_label"


def _banking77_bundle() -> GroundedBenchmarkBundle:
    """The checked-in banking77 authority pack, whose metrics include macro F1."""

    def load(name: str, model: Any) -> Any:
        text = (AUTHORITY / name).read_text(encoding="utf-8")
        return model.model_validate(yaml.safe_load(text) or {})

    return GroundedBenchmarkBundle(
        workspace_root=AUTHORITY.parent,
        authority=None,
        scenario=load("scenario.yaml", GroundedBenchmarkScenario),
        paper=load("paper.yaml", GroundedPaperMetadata),
        label_map=load("label-map.yaml", GroundedLabelMap),
        metrics=load("metrics.yaml", GroundedMetricsConfig),
        baselines=load("baselines.yaml", GroundedBaselines),
    )


def _macro_f1(
    gold_rows: list[dict[str, Any]], predictions: list[dict[str, Any]]
) -> tuple[float, dict[str, float]]:
    summary = score_grounded_stage(
        bundle=_banking77_bundle(),
        predictions=predictions,
        gold_rows=gold_rows,
        run_id="macro-f1-test",
        stage="molabel_model",
        variant="molabel_operated",
    )
    (metric,) = [m for m in summary.metrics if m.metric_type == "macro_f1"]
    return metric.value, metric.details["per_label_f1"]


def _reference(
    gold_rows: list[dict[str, Any]], predictions: list[dict[str, Any]]
) -> tuple[float, dict[str, float]]:
    gold = {
        row["record_id"]: canonical_label_value(row["labels"].get(FIELD))
        for row in gold_rows
    }
    predicted_rows = {row["record_id"]: row["labels"] for row in predictions}
    predicted = {
        record_id: canonical_label_value(predicted_rows.get(record_id, {}).get(FIELD))
        for record_id in gold
    }
    labels = set(gold.values()) | {
        canonical_label_value(labels[FIELD])
        for labels in predicted_rows.values()
        if FIELD in labels
    }
    scores: dict[str, float] = {}
    for label in labels:
        tp = sum(1 for r in gold if gold[r] == label and predicted[r] == label)
        fp = sum(1 for r in gold if gold[r] != label and predicted[r] == label)
        fn = sum(1 for r in gold if gold[r] == label and predicted[r] != label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        harmonic = precision + recall
        scores[label] = 2 * precision * recall / harmonic if harmonic else 0.0
    return sum(scores.values()) / len(scores), scores


def test_macro_f1_on_a_worked_example() -> None:
    """Gold a a b b c against a b b c c.

    a: tp 1, fp 0, fn 1, F1 2/3. b: tp 1, fp 1, fn 1, F1 1/2. c: tp 1, fp 1,
    fn 0, F1 2/3. Macro F1 is their mean, 11/18.
    """
    gold_rows = [
        {"record_id": f"r{i}", "labels": {FIELD: value}}
        for i, value in enumerate("aabbc")
    ]
    predictions = [
        {"record_id": f"r{i}", "labels": {FIELD: value}}
        for i, value in enumerate("abbcc")
    ]

    value, per_label = _macro_f1(gold_rows, predictions)

    assert value == pytest.approx(11 / 18)
    assert per_label == pytest.approx({"a": 2 / 3, "b": 1 / 2, "c": 2 / 3})


def test_macro_f1_matches_the_definition_with_missing_and_null_values() -> None:
    rng = random.Random(11)
    intents = [f"intent_{i}" for i in range(9)]
    gold_rows: list[dict[str, Any]] = []
    predictions: list[dict[str, Any]] = []
    for index in range(400):
        record_id = f"r{index}"
        intent = rng.choice(intents)
        gold_rows.append({"record_id": record_id, "labels": {FIELD: intent}})
        roll = rng.random()
        if roll < 0.7:
            predictions.append({"record_id": record_id, "labels": {FIELD: intent}})
        elif roll < 0.9:
            other = rng.choice([i for i in intents if i != intent])
            predictions.append({"record_id": record_id, "labels": {FIELD: other}})
        elif roll < 0.95:
            predictions.append({"record_id": record_id, "labels": {}})
    gold_rows[0]["labels"][FIELD] = None
    predictions.append({"record_id": "unknown", "labels": {FIELD: "intent_0"}})

    value, per_label = _macro_f1(gold_rows, predictions)
    expected_value, expected_per_label = _reference(gold_rows, predictions)

    assert value == pytest.approx(expected_value)
    assert per_label == pytest.approx(expected_per_label)

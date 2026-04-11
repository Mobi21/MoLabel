from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from molabel.core.quality.grounded_benchmarks import (
    load_grounded_benchmark,
    load_jsonl,
)

ROOT = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "benchmarks-grounded"
    / "banking77"
)


def _score_predictions(
    predictions: dict[str, dict[str, Any]],
    gold_rows: list[dict[str, Any]],
) -> dict[str, float]:
    total = len(gold_rows)
    correct = 0
    for row in gold_rows:
        record_id = row["record_id"]
        expected = row["labels"]
        actual = predictions[record_id]
        if actual["intent_label"] == expected["intent_label"]:
            correct += 1
    return {"intent_accuracy": correct / max(total, 1)}


def _macro_f1(
    predictions: dict[str, dict[str, Any]],
    gold_rows: list[dict[str, Any]],
) -> float:
    labels: set[str] = set()
    predicted_per_label: dict[str, int] = {}
    gold_per_label: dict[str, int] = {}
    correct_per_label: dict[str, int] = {}

    for row in gold_rows:
        record_id = row["record_id"]
        gold_label = row["labels"]["intent_label"]
        predicted_label = predictions[record_id]["intent_label"]
        labels.add(gold_label)
        labels.add(predicted_label)
        gold_per_label[gold_label] = gold_per_label.get(gold_label, 0) + 1
        predicted_per_label[predicted_label] = (
            predicted_per_label.get(predicted_label, 0) + 1
        )
        if predicted_label == gold_label:
            correct_per_label[gold_label] = correct_per_label.get(gold_label, 0) + 1

    f1_sum = 0.0
    for label in labels:
        tp = correct_per_label.get(label, 0)
        pred_total = predicted_per_label.get(label, 0)
        gold_total = gold_per_label.get(label, 0)
        precision = tp / pred_total if pred_total else 0.0
        recall = tp / gold_total if gold_total else 0.0
        denom = precision + recall
        f1 = 2 * precision * recall / denom if denom else 0.0
        f1_sum += f1
    return f1_sum / len(labels) if labels else 0.0


def test_banking77_grounded_fixture_contract() -> None:
    bundle = load_grounded_benchmark(ROOT)
    scenario = bundle.scenario

    assert scenario.benchmark_id == "banking77"
    assert scenario.track == "grounded"
    assert scenario.paper_metadata_path.endswith("paper.yaml")
    assert (
        scenario.paper_gold_path == "workbench/benchmarks/gold/paper-direct/test.jsonl"
    )
    assert (
        scenario.molabel_gold_path
        == "workbench/benchmarks/gold/molabel-operated/test.jsonl"
    )
    assert set(scenario.evaluation_modes) == {"model", "workflow", "operator"}
    assert set(scenario.scoring_variants) == {"paper_direct", "molabel_operated"}
    assert scenario.subset_policy["subset_size"] == 16

    assert bundle.paper.dataset_name == "BANKING77"
    assert bundle.paper.dataset_license == "MIT"
    assert bundle.paper.redistribution_status == "allowed"

    assert bundle.label_map.record_id_field == "record_id"
    assert bundle.metrics.primary_metric_id == "intent_accuracy"
    assert bundle.operator is not None
    assert {check.check_id for check in bundle.operator.checks} >= {
        "uses_public_cli_and_skill_only",
        "configures_minimax_2_7_profile",
        "preserves_artifact_integrity",
    }
    assert {metric.metric_id for metric in bundle.metrics.metrics} >= {
        "intent_accuracy",
        "intent_macro_f1",
        "intent_exact_match",
    }
    assert {tax.tax_id for tax in bundle.metrics.tax_definitions} == {
        "model_tax",
        "workflow_tax",
        "operator_tax",
    }

    assert len(bundle.baselines.baselines) == 2
    floor = next(
        baseline
        for baseline in bundle.baselines.baselines
        if baseline.baseline_id == "majority_class_card_arrival"
    )
    assert floor.metrics["intent_accuracy"] == pytest.approx(0.0625)


def test_banking77_grounded_files_align() -> None:
    split_rows = load_jsonl(ROOT / "workbench" / "benchmarks" / "splits" / "test.jsonl")
    paper_gold_rows = load_jsonl(
        ROOT / "workbench" / "benchmarks" / "gold" / "paper-direct" / "test.jsonl"
    )
    molabel_gold_rows = load_jsonl(
        ROOT / "workbench" / "benchmarks" / "gold" / "molabel-operated" / "test.jsonl"
    )
    human_rows = load_jsonl(
        ROOT / "workbench" / "benchmarks" / "human-labels" / "reviewer-nina.jsonl"
    )
    review_rows = load_jsonl(
        ROOT / "workbench" / "benchmarks" / "reviews" / "reviewer-owen.jsonl"
    )

    assert len(split_rows) == 16
    assert len(paper_gold_rows) == len(molabel_gold_rows) == 16

    raw_ids = {row["record_id"] for row in split_rows}
    assert raw_ids == {row["record_id"] for row in paper_gold_rows}
    assert raw_ids == {row["record_id"] for row in molabel_gold_rows}

    # Every gold label should be a declared BANKING77 intent.
    bundle = load_grounded_benchmark(ROOT)
    allowed_labels = set(bundle.label_map.field_mappings[0].mapping.values())
    for row in paper_gold_rows + molabel_gold_rows:
        assert row["labels"]["intent_label"] in allowed_labels

    # Confusion-heavy slice: every record has a unique gold label.
    label_counts = Counter(row["labels"]["intent_label"] for row in paper_gold_rows)
    assert all(count == 1 for count in label_counts.values())

    # Every split record has a source_label that matches the paper-direct gold
    # label (since both sides are in the canonical BANKING77 vocabulary).
    paper_gold_by_id = {row["record_id"]: row for row in paper_gold_rows}
    for split_row in split_rows:
        assert (
            split_row["source_label"]
            == paper_gold_by_id[split_row["record_id"]]["labels"]["intent_label"]
        )

    human_wrong = sum(1 for row in human_rows if row.get("is_intentionally_wrong"))
    review_wrong = sum(1 for row in review_rows if row.get("is_intentionally_wrong"))
    assert human_wrong >= 2
    assert review_wrong >= 1

    assert all(row["record_id"] in raw_ids for row in human_rows)
    assert all(row["record_id"] in raw_ids for row in review_rows)


def test_banking77_reference_runs_bound_the_slice() -> None:
    gold_rows = load_jsonl(
        ROOT / "workbench" / "benchmarks" / "gold" / "paper-direct" / "test.jsonl"
    )
    oracle_predictions = {row["record_id"]: dict(row["labels"]) for row in gold_rows}
    floor_predictions = {
        row["record_id"]: {"intent_label": "card_arrival"} for row in gold_rows
    }

    oracle = _score_predictions(oracle_predictions, gold_rows)
    floor = _score_predictions(floor_predictions, gold_rows)

    assert oracle["intent_accuracy"] == pytest.approx(1.0)
    assert floor["intent_accuracy"] == pytest.approx(1 / 16)

    assert _macro_f1(oracle_predictions, gold_rows) == pytest.approx(1.0)
    # Floor baseline macro_f1: the single correct label has f1=2/17, all
    # other labels f1=0. Average over 16 labels = 2/(17*16) = 0.007352941...
    assert _macro_f1(floor_predictions, gold_rows) == pytest.approx(2 / (17 * 16))

    paper_run = json.loads(
        (
            ROOT
            / "workbench"
            / "benchmarks"
            / "runs"
            / "reference-paper-direct"
            / "summary.json"
        ).read_text(encoding="utf-8")
    )
    floor_run = json.loads(
        (
            ROOT
            / "workbench"
            / "benchmarks"
            / "runs"
            / "reference-model-floor"
            / "summary.json"
        ).read_text(encoding="utf-8")
    )

    assert paper_run["benchmark_id"] == "banking77"
    assert floor_run["benchmark_id"] == "banking77"
    assert paper_run["overall_score"] == pytest.approx(1.0)

from __future__ import annotations

import json
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
    / "goemotions"
)


GOEMOTIONS_VOCAB = {
    "admiration",
    "amusement",
    "anger",
    "annoyance",
    "approval",
    "caring",
    "confusion",
    "curiosity",
    "desire",
    "disappointment",
    "disapproval",
    "disgust",
    "embarrassment",
    "excitement",
    "fear",
    "gratitude",
    "grief",
    "joy",
    "love",
    "nervousness",
    "optimism",
    "pride",
    "realization",
    "relief",
    "remorse",
    "sadness",
    "surprise",
    "neutral",
}


def _score_set_f1(
    predictions: dict[str, set[str]],
    gold_rows: list[dict[str, Any]],
) -> dict[str, float]:
    overlap_total = 0
    predicted_total = 0
    gold_total = 0
    jaccard_sum = 0.0
    for row in gold_rows:
        gold_set = set(row["labels"]["emotion_labels"])
        pred_set = predictions.get(row["record_id"], set())
        overlap_total += len(gold_set & pred_set)
        predicted_total += len(pred_set)
        gold_total += len(gold_set)
        union = gold_set | pred_set
        jaccard_sum += len(gold_set & pred_set) / len(union) if union else 0.0
    precision = overlap_total / predicted_total if predicted_total else 0.0
    recall = overlap_total / gold_total if gold_total else 0.0
    denom = precision + recall
    f1 = 2 * precision * recall / denom if denom else 0.0
    jaccard = jaccard_sum / len(gold_rows) if gold_rows else 0.0
    return {
        "set_f1": f1,
        "set_precision": precision,
        "set_recall": recall,
        "jaccard": jaccard,
    }


def test_goemotions_grounded_fixture_contract() -> None:
    bundle = load_grounded_benchmark(ROOT)
    scenario = bundle.scenario

    assert scenario.benchmark_id == "goemotions"
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
    assert scenario.subset_policy["subset_size"] == 12

    assert bundle.paper.dataset_name == "GoEmotions"
    assert bundle.paper.dataset_license == "Apache-2.0"
    assert bundle.paper.redistribution_status == "allowed"

    assert bundle.label_map.record_id_field == "record_id"
    assert bundle.metrics.primary_metric_id == "emotion_set_f1"
    assert bundle.operator is not None
    assert {check.check_id for check in bundle.operator.checks} >= {
        "uses_public_cli_and_skill_only",
        "configures_minimax_2_7_profile",
        "preserves_artifact_integrity",
    }
    assert {metric.metric_id for metric in bundle.metrics.metrics} >= {
        "emotion_set_f1",
        "emotion_jaccard",
        "emotion_set_precision",
        "emotion_set_recall",
        "emotion_exact_match",
    }
    assert {tax.tax_id for tax in bundle.metrics.tax_definitions} == {
        "model_tax",
        "autorun_tax",
        "review_tax",
        "operator_tax",
    }

    assert len(bundle.baselines.baselines) == 2


def test_goemotions_grounded_files_align() -> None:
    split_rows = load_jsonl(ROOT / "workbench" / "benchmarks" / "splits" / "test.jsonl")
    paper_gold_rows = load_jsonl(
        ROOT / "workbench" / "benchmarks" / "gold" / "paper-direct" / "test.jsonl"
    )
    operational_gold_rows = load_jsonl(
        ROOT / "workbench" / "benchmarks" / "gold" / "molabel-operated" / "test.jsonl"
    )
    human_rows = load_jsonl(
        ROOT / "workbench" / "benchmarks" / "human-labels" / "reviewer-priya.jsonl"
    )
    review_rows = load_jsonl(
        ROOT / "workbench" / "benchmarks" / "reviews" / "reviewer-quinn.jsonl"
    )

    assert len(split_rows) == 12
    assert len(paper_gold_rows) == 12
    assert len(operational_gold_rows) == 12

    raw_ids = {row["record_id"] for row in split_rows}
    assert raw_ids == {row["record_id"] for row in paper_gold_rows}
    assert raw_ids == {row["record_id"] for row in operational_gold_rows}

    # Every predicted label must belong to the authority vocabulary, with no
    # duplicates inside a single set.
    for row in paper_gold_rows + operational_gold_rows:
        label_list = row["labels"]["emotion_labels"]
        assert isinstance(label_list, list)
        assert len(label_list) == len(set(label_list)), (
            f"Duplicate labels in {row['record_id']}: {label_list}"
        )
        assert set(label_list) <= GOEMOTIONS_VOCAB
        # Paper-direct and molabel-operated views hold the same label set.
    paper_sets = {
        row["record_id"]: set(row["labels"]["emotion_labels"])
        for row in paper_gold_rows
    }
    op_sets = {
        row["record_id"]: set(row["labels"]["emotion_labels"])
        for row in operational_gold_rows
    }
    assert paper_sets == op_sets

    # MoLabel-operated view preserves disagreement only where the split marked
    # annotator_agreement as "majority".
    split_by_id = {row["record_id"]: row for row in split_rows}
    for row in operational_gold_rows:
        expected_disagreement = (
            split_by_id[row["record_id"]]["annotator_agreement"] == "majority"
        )
        assert row["workflow"]["should_preserve_disagreement"] == expected_disagreement

    # Slice must include at least one single-label case, one multi-label case,
    # one neutral-only case, and one disagreement case.
    label_sizes = [len(row["labels"]["emotion_labels"]) for row in paper_gold_rows]
    assert any(size == 1 for size in label_sizes)
    assert any(size >= 2 for size in label_sizes)
    assert any(
        set(row["labels"]["emotion_labels"]) == {"neutral"} for row in paper_gold_rows
    )
    assert any(
        row["workflow"]["should_preserve_disagreement"] for row in operational_gold_rows
    )

    human_wrong = sum(1 for row in human_rows if row.get("is_intentionally_wrong"))
    review_wrong = sum(1 for row in review_rows if row.get("is_intentionally_wrong"))
    assert human_wrong >= 2
    assert review_wrong >= 1

    # Human and review reviewer labels must also be inside the vocabulary and
    # carry no duplicate labels.
    for row in human_rows + review_rows:
        assert row["record_id"] in raw_ids
        labels = row["labels"]["emotion_labels"]
        assert len(labels) == len(set(labels))
        assert set(labels) <= GOEMOTIONS_VOCAB


def test_goemotions_reference_runs_bound_the_slice() -> None:
    gold_rows = load_jsonl(
        ROOT / "workbench" / "benchmarks" / "gold" / "paper-direct" / "test.jsonl"
    )
    oracle_predictions = {
        row["record_id"]: set(row["labels"]["emotion_labels"]) for row in gold_rows
    }
    floor_predictions = {row["record_id"]: {"neutral"} for row in gold_rows}

    oracle = _score_set_f1(oracle_predictions, gold_rows)
    floor = _score_set_f1(floor_predictions, gold_rows)

    assert oracle["set_f1"] == pytest.approx(1.0)
    assert oracle["jaccard"] == pytest.approx(1.0)

    # 2 of the 12 records have neutral in their gold set.
    # overlap=2, predicted=12 (one per record), gold=21 (sum of set sizes)
    assert floor["set_precision"] == pytest.approx(2 / 12)
    assert floor["set_recall"] == pytest.approx(2 / 21)
    expected_f1 = 2 * (2 / 12) * (2 / 21) / ((2 / 12) + (2 / 21))
    assert floor["set_f1"] == pytest.approx(expected_f1)
    assert floor["jaccard"] == pytest.approx(2 / 12)

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

    assert paper_run["benchmark_id"] == "goemotions"
    assert floor_run["benchmark_id"] == "goemotions"
    assert paper_run["overall_score"] == pytest.approx(1.0)
    expected_overall = expected_f1 * 1.0 / 1.5 + (2 / 12) * 0.5 / 1.5
    assert floor_run["overall_score"] == pytest.approx(expected_overall)

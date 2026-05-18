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
    / "clinc150"
)


def _score_predictions(
    predictions: dict[str, dict[str, Any]],
    gold_rows: list[dict[str, Any]],
) -> dict[str, float]:
    total = len(gold_rows)
    correct = 0
    oos_total = 0
    oos_correct = 0

    for row in gold_rows:
        record_id = row["record_id"]
        expected = row["labels"]
        actual = predictions[record_id]

        if actual["intent_label"] == expected["intent_label"]:
            correct += 1
        if expected["is_out_of_scope"]:
            oos_total += 1
            if actual["is_out_of_scope"]:
                oos_correct += 1

    return {
        "intent_accuracy": correct / max(total, 1),
        "oos_recall": oos_correct / max(oos_total, 1),
    }


def test_clinc150_grounded_fixture_contract() -> None:
    bundle = load_grounded_benchmark(ROOT)
    scenario = bundle.scenario

    assert scenario.benchmark_id == "clinc150"
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

    assert bundle.paper.dataset_name == "CLINC150"
    assert bundle.paper.dataset_license == "CC BY 3.0"
    assert bundle.paper.redistribution_status == "subset_allowed"

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
        "oos_recall",
        "intent_exact_match",
    }
    assert {tax.tax_id for tax in bundle.metrics.tax_definitions} == {
        "model_tax",
        "autorun_tax",
        "review_tax",
        "operator_tax",
    }

    assert len(bundle.baselines.baselines) == 2
    heuristic = next(
        baseline
        for baseline in bundle.baselines.baselines
        if baseline.baseline_id == "always_oos"
    )
    assert heuristic.metrics["intent_accuracy"] == pytest.approx(0.25)


def test_clinc150_grounded_files_align() -> None:
    train_rows = load_jsonl(
        ROOT / "workbench" / "benchmarks" / "splits" / "train.jsonl"
    )
    val_rows = load_jsonl(ROOT / "workbench" / "benchmarks" / "splits" / "val.jsonl")
    test_rows = load_jsonl(ROOT / "workbench" / "benchmarks" / "splits" / "test.jsonl")
    paper_gold_rows = load_jsonl(
        ROOT / "workbench" / "benchmarks" / "gold" / "paper-direct" / "test.jsonl"
    )
    molabel_gold_rows = load_jsonl(
        ROOT / "workbench" / "benchmarks" / "gold" / "molabel-operated" / "test.jsonl"
    )
    human_rows = load_jsonl(
        ROOT / "workbench" / "benchmarks" / "human-labels" / "reviewer-mira.jsonl"
    )
    review_rows = load_jsonl(
        ROOT / "workbench" / "benchmarks" / "reviews" / "reviewer-otto.jsonl"
    )

    assert len(train_rows) == 4
    assert len(val_rows) == 4
    assert len(test_rows) == 16
    assert len(paper_gold_rows) == len(molabel_gold_rows) == 16

    raw_ids = {row["record_id"] for row in test_rows}
    assert raw_ids == {row["record_id"] for row in paper_gold_rows}
    assert raw_ids == {row["record_id"] for row in molabel_gold_rows}
    assert sum(1 for row in test_rows if row["source_label"] == "oos") == 4

    human_wrong = sum(1 for row in human_rows if row.get("is_intentionally_wrong"))
    review_wrong = sum(1 for row in review_rows if row.get("is_intentionally_wrong"))
    assert human_wrong >= 2
    assert review_wrong >= 1

    assert all(row["record_id"] in raw_ids for row in human_rows)
    assert all(row["record_id"] in raw_ids for row in review_rows)


def test_clinc150_reference_runs_bound_the_slice() -> None:
    gold_rows = load_jsonl(
        ROOT / "workbench" / "benchmarks" / "gold" / "paper-direct" / "test.jsonl"
    )
    oracle_predictions = {row["record_id"]: dict(row["labels"]) for row in gold_rows}
    always_oos_predictions = {
        row["record_id"]: {"intent_label": "oos", "is_out_of_scope": True}
        for row in gold_rows
    }

    oracle = _score_predictions(oracle_predictions, gold_rows)
    floor = _score_predictions(always_oos_predictions, gold_rows)

    assert oracle["intent_accuracy"] == pytest.approx(1.0)
    assert oracle["oos_recall"] == pytest.approx(1.0)
    assert floor["intent_accuracy"] == pytest.approx(0.25)
    assert floor["oos_recall"] == pytest.approx(1.0)

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

    assert paper_run["benchmark_id"] == "clinc150"
    assert floor_run["benchmark_id"] == "clinc150"

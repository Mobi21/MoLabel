from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from molabel.core.quality.grounded_benchmarks import (
    load_grounded_benchmark,
    load_jsonl,
    score_grounded_stage,
)

ROOT = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "benchmarks-grounded"
    / "beir"
)


def test_beir_fixture_scores_graded_rankings_with_ndcg() -> None:
    bundle = load_grounded_benchmark(ROOT)
    assert bundle.scenario.benchmark_id == "beir"
    assert bundle.metrics.primary_metric_id == "ndcg_at_5"
    assert {metric.metric_id for metric in bundle.metrics.metrics} >= {
        "ndcg_at_5",
        "map",
        "mrr",
        "recall_at_5",
        "precision_at_5",
    }

    gold_rows = load_jsonl(
        ROOT / "workbench" / "benchmarks" / "gold" / "paper-direct" / "dev.jsonl"
    )
    oracle = score_grounded_stage(
        bundle=bundle,
        predictions=gold_rows,
        gold_rows=gold_rows,
        run_id="oracle",
        stage="paper_model",
        variant="paper_direct",
    )
    assert oracle.overall_score == pytest.approx(1.0)
    assert any(
        max(row["labels"]["qrels"].values()) > 1 for row in gold_rows
    ), "BEIR slice should preserve graded qrels, not binary set overlap"

    degraded_predictions = deepcopy(gold_rows)
    degraded_predictions[0]["labels"]["ranking"]["results"][0]["result_id"] = "d1"
    degraded_predictions[0]["labels"]["ranking"]["results"][1]["result_id"] = "d2"
    degraded = score_grounded_stage(
        bundle=bundle,
        predictions=degraded_predictions,
        gold_rows=gold_rows,
        run_id="degraded",
        stage="paper_model",
        variant="paper_direct",
    )
    assert degraded.overall_score < oracle.overall_score
    assert degraded.overall_score > 0.0


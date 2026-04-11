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
    / "msmarco"
)


def test_msmarco_fixture_scores_reciprocal_rank_at_five() -> None:
    bundle = load_grounded_benchmark(ROOT)
    assert bundle.scenario.benchmark_id == "msmarco"
    assert bundle.metrics.primary_metric_id == "mrr_at_5"
    assert {metric.metric_id for metric in bundle.metrics.metrics} >= {
        "mrr_at_5",
        "map",
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
    assert all(
        set(row["labels"]["qrels"].values()) == {1} for row in gold_rows
    ), "MS MARCO slice should keep passage-ranking binary qrels"

    degraded_predictions = deepcopy(gold_rows)
    degraded_predictions[0]["labels"]["ranking"]["results"] = [
        {"result_id": "p1", "rank": 1},
        {"result_id": "p3", "rank": 2},
        {"result_id": "p2", "rank": 3},
        {"result_id": "p4", "rank": 4},
        {"result_id": "p5", "rank": 5},
    ]
    degraded_predictions[0]["labels"]["ranking"]["expected_depth"] = 5
    degraded_predictions[0]["labels"]["ranking"]["corpus_snapshot_id"] = "snapshot-v1"
    degraded_predictions[0]["labels"]["ranking"]["corpus_hash"] = "hash-v1"
    degraded = score_grounded_stage(
        bundle=bundle,
        predictions=degraded_predictions,
        gold_rows=gold_rows,
        run_id="degraded",
        stage="paper_model",
        variant="paper_direct",
    )
    assert degraded.overall_score == pytest.approx((1 / 3 + 1 + 1 + 1) / 4)

from __future__ import annotations

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
    / "hotpotqa"
)


def test_hotpotqa_fixture_scores_joint_answer_and_support() -> None:
    bundle = load_grounded_benchmark(ROOT)
    assert bundle.scenario.benchmark_id == "hotpotqa"
    assert bundle.metrics.primary_metric_id == "joint_answer_support"

    gold_rows = load_jsonl(
        ROOT / "workbench" / "benchmarks" / "gold" / "paper-direct" / "dev.jsonl"
    )
    summary = score_grounded_stage(
        bundle=bundle,
        predictions=gold_rows,
        gold_rows=gold_rows,
        run_id="oracle",
        stage="paper_model",
        variant="paper_direct",
    )
    assert summary.overall_score == pytest.approx(1.0)
    assert all(
        len(row["labels"]["qa_bundle"]["supporting_facts"]) == 2 for row in gold_rows
    )

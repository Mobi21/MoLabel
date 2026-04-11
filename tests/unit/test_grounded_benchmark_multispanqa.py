from __future__ import annotations

from pathlib import Path

import pytest

from molabel.core.quality.grounded_benchmark_primitives import validate_span_annotation
from molabel.core.quality.grounded_benchmarks import (
    load_grounded_benchmark,
    load_jsonl,
    score_grounded_stage,
)

ROOT = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "benchmarks-grounded"
    / "multispanqa"
)


def test_multispanqa_fixture_preserves_discontiguous_answer_segments() -> None:
    bundle = load_grounded_benchmark(ROOT)
    assert bundle.scenario.benchmark_id == "multispanqa"
    assert bundle.metrics.primary_metric_id == "span_overlap_f1"

    gold_rows = load_jsonl(
        ROOT / "workbench" / "benchmarks" / "gold" / "paper-direct" / "dev.jsonl"
    )
    assert any(
        len(row["labels"]["spans"]["spans"][0]["segments"]) > 1 for row in gold_rows
    )
    assert all(
        validate_span_annotation(row["labels"]["spans"]).is_valid for row in gold_rows
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


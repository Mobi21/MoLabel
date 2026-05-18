from __future__ import annotations

from pathlib import Path

import pytest

from molabel.core.quality.grounded_benchmark_primitives import validate_span_annotation
from molabel.core.quality.grounded_benchmarks import (
    load_grounded_benchmark,
    load_jsonl,
    score_grounded_stage,
)

ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "benchmarks-grounded" / "cuad"


def test_cuad_fixture_preserves_grounded_clause_offsets() -> None:
    bundle = load_grounded_benchmark(ROOT)
    assert bundle.scenario.benchmark_id == "cuad"
    assert bundle.metrics.primary_metric_id == "span_overlap_f1"

    gold_rows = load_jsonl(
        ROOT / "workbench" / "benchmarks" / "gold" / "paper-direct" / "dev.jsonl"
    )
    for row in gold_rows:
        annotation = row["labels"]["spans"]
        assert validate_span_annotation(annotation).is_valid is True
        assert annotation["spans"][0]["normalized_value"]

    summary = score_grounded_stage(
        bundle=bundle,
        predictions=gold_rows,
        gold_rows=gold_rows,
        run_id="oracle",
        stage="paper_model",
        variant="paper_direct",
    )
    assert summary.overall_score == pytest.approx(1.0)

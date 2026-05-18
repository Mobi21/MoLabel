from __future__ import annotations

from pathlib import Path

import pytest

from molabel.core.quality.grounded_benchmark_primitives import validate_grounded_anchor
from molabel.core.quality.grounded_benchmarks import (
    load_grounded_benchmark,
    load_jsonl,
    score_grounded_stage,
)

ROOT = (
    Path(__file__).resolve().parents[2] / "fixtures" / "benchmarks-grounded" / "tabfact"
)


def test_tabfact_fixture_keeps_paper_and_grounded_views_distinct() -> None:
    bundle = load_grounded_benchmark(ROOT)
    assert bundle.scenario.benchmark_id == "tabfact"
    assert bundle.metrics.primary_metric_id == "decision_accuracy"

    split_rows = load_jsonl(ROOT / "workbench" / "benchmarks" / "splits" / "dev.jsonl")
    for row in split_rows:
        assert all(
            validate_grounded_anchor(anchor).is_valid
            for anchor in row["available_anchors"]
        )

    paper_gold = load_jsonl(
        ROOT / "workbench" / "benchmarks" / "gold" / "paper-direct" / "dev.jsonl"
    )
    molabel_gold = load_jsonl(
        ROOT / "workbench" / "benchmarks" / "gold" / "molabel-operated" / "dev.jsonl"
    )
    assert all("evidence_bundle" not in row["labels"] for row in paper_gold)
    assert all("evidence_bundle" in row["labels"] for row in molabel_gold)

    paper_summary = score_grounded_stage(
        bundle=bundle,
        predictions=paper_gold,
        gold_rows=paper_gold,
        run_id="oracle-paper",
        stage="paper_model",
        variant="paper_direct",
    )
    molabel_summary = score_grounded_stage(
        bundle=bundle,
        predictions=molabel_gold,
        gold_rows=molabel_gold,
        run_id="oracle-molabel",
        stage="workflow_reviewed",
        variant="molabel_operated",
    )
    assert paper_summary.overall_score == pytest.approx(1.0)
    assert molabel_summary.overall_score == pytest.approx(1.0)

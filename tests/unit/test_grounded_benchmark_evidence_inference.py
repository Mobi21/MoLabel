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
    / "evidence-inference"
)


def test_evidence_inference_fixture_uses_grouped_evidence_primitives() -> None:
    bundle = load_grounded_benchmark(ROOT)
    assert bundle.scenario.benchmark_id == "evidence-inference"
    assert bundle.metrics.primary_metric_id == "joint_effect_evidence"
    assert {metric.metric_id for metric in bundle.metrics.metrics} >= {
        "joint_effect_evidence",
        "decision_accuracy",
        "evidence_group_f1",
    }

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
    assert any(len(row["labels"]["evidence_bundle"]["groups"]) > 1 for row in gold_rows)

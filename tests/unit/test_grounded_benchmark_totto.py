from __future__ import annotations

from pathlib import Path

import pytest

from molabel.core.quality.grounded_benchmark_primitives import (
    validate_grounded_generation_artifact,
)
from molabel.core.quality.grounded_benchmarks import (
    load_grounded_benchmark,
    load_jsonl,
    score_grounded_stage,
)

ROOT = (
    Path(__file__).resolve().parents[2] / "fixtures" / "benchmarks-grounded" / "totto"
)


def test_totto_fixture_preserves_cell_grounded_generation() -> None:
    bundle = load_grounded_benchmark(ROOT)
    assert bundle.scenario.benchmark_id == "totto"
    assert bundle.metrics.primary_metric_id == "grounded_generation_score"

    gold_rows = load_jsonl(
        ROOT / "workbench" / "benchmarks" / "gold" / "paper-direct" / "dev.jsonl"
    )
    for row in gold_rows:
        artifact = row["labels"]["generation"]
        assert (
            validate_grounded_generation_artifact(
                artifact, required_fields=["summary"]
            ).is_valid
            is True
        )
        assert all(
            anchor_id.startswith("cell_")
            for claim in artifact["claims"]
            for anchor_id in claim["anchor_ids"]
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

"""Tests for multi-model comparison service (AG-006, AG-007)."""

from __future__ import annotations

import pytest

from molabel.core.agents.comparison import (
    ComparisonRecord,
    ComparisonResult,
    ComparisonRun,
    ModelConfig,
    MultiModelComparisonService,
)


@pytest.fixture()
def service() -> MultiModelComparisonService:
    return MultiModelComparisonService()


@pytest.fixture()
def two_models() -> list[ModelConfig]:
    return [
        ModelConfig(
            model_id="gpt-4",
            model_name="GPT-4",
            provider_type="openai_compatible",
            cost_per_input_token=0.00003,
            cost_per_output_token=0.00006,
        ),
        ModelConfig(
            model_id="claude-3",
            model_name="Claude 3",
            provider_type="anthropic",
            cost_per_input_token=0.000015,
            cost_per_output_token=0.000075,
        ),
    ]


@pytest.fixture()
def record_ids() -> list[str]:
    return ["rec-1", "rec-2", "rec-3"]


# ---------------------------------------------------------------------------
# AG-006: Multi-model comparison runs
# ---------------------------------------------------------------------------


def test_run_comparison_without_processor(
    service: MultiModelComparisonService,
    two_models: list[ModelConfig],
    record_ids: list[str],
) -> None:
    """Running without a processor produces empty records for all combinations."""
    run = service.run_comparison(
        model_configs=two_models,
        record_ids=record_ids,
    )
    assert run.status == "completed"
    assert run.result is not None
    assert len(run.result.records) == 6  # 2 models x 3 records
    assert run.result.model_ids == ["gpt-4", "claude-3"]
    assert run.result.record_ids == record_ids
    assert run.started_at is not None
    assert run.completed_at is not None


def test_run_comparison_with_processor(
    service: MultiModelComparisonService,
    two_models: list[ModelConfig],
    record_ids: list[str],
) -> None:
    """A processor can return dicts or ComparisonRecord instances."""

    def processor(record_id: str, model_config: ModelConfig) -> ComparisonRecord:
        label = "positive" if model_config.model_id == "gpt-4" else "negative"
        return ComparisonRecord(
            record_id=record_id,
            model_id=model_config.model_id,
            labels={"sentiment": label},
            tokens_input=100,
            tokens_output=20,
            latency_ms=150,
        )

    run = service.run_comparison(
        model_configs=two_models,
        record_ids=record_ids,
        processor=processor,
    )
    assert run.status == "completed"
    assert run.result is not None

    gpt4_records = run.result.records_for_model("gpt-4")
    assert len(gpt4_records) == 3
    assert all(r.labels["sentiment"] == "positive" for r in gpt4_records)

    claude_records = run.result.records_for_model("claude-3")
    assert all(r.labels["sentiment"] == "negative" for r in claude_records)


def test_run_comparison_handles_processor_error(
    service: MultiModelComparisonService,
    two_models: list[ModelConfig],
) -> None:
    """A failing processor records the error on the comparison record."""

    def failing_processor(record_id: str, model_config: ModelConfig) -> dict:
        if record_id == "rec-2":
            raise RuntimeError("model timeout")
        return {"labels": {"sentiment": "positive"}}

    run = service.run_comparison(
        model_configs=two_models,
        record_ids=["rec-1", "rec-2"],
        processor=failing_processor,
    )
    assert run.status == "completed"
    assert run.result is not None

    errors = [r for r in run.result.records if r.error is not None]
    assert len(errors) == 2  # Both models fail on rec-2
    assert "model timeout" in errors[0].error


def test_comparison_result_query_helpers(
    service: MultiModelComparisonService,
    two_models: list[ModelConfig],
    record_ids: list[str],
) -> None:
    """ComparisonResult provides convenience query methods."""

    def processor(record_id: str, model_config: ModelConfig) -> ComparisonRecord:
        return ComparisonRecord(
            record_id=record_id,
            model_id=model_config.model_id,
            labels={"sentiment": "positive"},
        )

    run = service.run_comparison(
        model_configs=two_models,
        record_ids=record_ids,
        processor=processor,
    )
    result = run.result
    assert result is not None

    assert len(result.records_for_model("gpt-4")) == 3
    assert len(result.records_for_record("rec-1")) == 2


def test_run_comparison_tracks_model_ids(service: MultiModelComparisonService) -> None:
    """ComparisonRun tracks model configs and record IDs."""
    configs = [
        ModelConfig(model_id="m1", model_name="Model 1"),
        ModelConfig(model_id="m2", model_name="Model 2"),
        ModelConfig(model_id="m3", model_name="Model 3"),
    ]
    run = service.run_comparison(
        model_configs=configs,
        record_ids=["r1"],
    )
    assert len(run.model_configs) == 3
    assert run.result is not None
    assert run.result.model_ids == ["m1", "m2", "m3"]


# ---------------------------------------------------------------------------
# AG-007: Comparison aggregate views
# ---------------------------------------------------------------------------


def _make_result(
    model_labels: dict[str, dict[str, dict[str, str]]],
    latencies: dict[str, int] | None = None,
    tokens: dict[str, tuple[int, int]] | None = None,
) -> ComparisonResult:
    """Build a ComparisonResult from model -> record_id -> labels mapping."""
    records: list[ComparisonRecord] = []
    model_ids = sorted(model_labels.keys())
    record_ids: set[str] = set()

    for model_id, per_record in model_labels.items():
        for record_id, labels in per_record.items():
            record_ids.add(record_id)
            lat = latencies.get(model_id, 100) if latencies else 100
            tok = tokens.get(model_id, (100, 20)) if tokens else (100, 20)
            records.append(
                ComparisonRecord(
                    record_id=record_id,
                    model_id=model_id,
                    labels=labels,
                    tokens_input=tok[0],
                    tokens_output=tok[1],
                    latency_ms=lat,
                )
            )

    return ComparisonResult(
        records=records,
        model_ids=model_ids,
        record_ids=sorted(record_ids),
    )


def test_agreement_matrix_perfect_agreement(
    service: MultiModelComparisonService,
) -> None:
    """Two models with identical labels produce 100% agreement."""
    result = _make_result(
        {
            "m1": {"r1": {"s": "pos"}, "r2": {"s": "neg"}},
            "m2": {"r1": {"s": "pos"}, "r2": {"s": "neg"}},
        }
    )
    agg = service.compute_aggregate(result)
    matrix = agg.agreement_matrix
    assert matrix.matrix["m1"]["m2"] == 1.0
    assert matrix.matrix["m2"]["m1"] == 1.0


def test_agreement_matrix_complete_disagreement(
    service: MultiModelComparisonService,
) -> None:
    """Two models that always disagree produce 0% agreement."""
    result = _make_result(
        {
            "m1": {"r1": {"s": "pos"}, "r2": {"s": "neg"}},
            "m2": {"r1": {"s": "neg"}, "r2": {"s": "pos"}},
        }
    )
    agg = service.compute_aggregate(result)
    assert agg.agreement_matrix.matrix["m1"]["m2"] == 0.0


def test_agreement_matrix_partial_agreement(
    service: MultiModelComparisonService,
) -> None:
    """Mixed agreement produces a rate between 0 and 1."""
    result = _make_result(
        {
            "m1": {"r1": {"s": "pos"}, "r2": {"s": "neg"}, "r3": {"s": "pos"}},
            "m2": {"r1": {"s": "pos"}, "r2": {"s": "pos"}, "r3": {"s": "pos"}},
        }
    )
    agg = service.compute_aggregate(result)
    rate = agg.agreement_matrix.matrix["m1"]["m2"]
    assert 0.0 < rate < 1.0
    assert rate == pytest.approx(2 / 3)


def test_distributions_per_model(service: MultiModelComparisonService) -> None:
    """Label distribution is computed per model per field."""
    result = _make_result(
        {
            "m1": {"r1": {"s": "pos"}, "r2": {"s": "pos"}, "r3": {"s": "neg"}},
            "m2": {"r1": {"s": "neg"}, "r2": {"s": "neg"}, "r3": {"s": "neg"}},
        }
    )
    agg = service.compute_aggregate(result)
    dists = {d.model_id: d for d in agg.distributions}

    assert dists["m1"].field_distributions["s"]["pos"] == 2
    assert dists["m1"].field_distributions["s"]["neg"] == 1
    assert dists["m2"].field_distributions["s"]["neg"] == 3


def test_cost_comparison(service: MultiModelComparisonService) -> None:
    """Cost comparison uses model config pricing."""
    configs = [
        ModelConfig(
            model_id="cheap",
            model_name="Cheap",
            cost_per_input_token=0.00001,
            cost_per_output_token=0.00002,
        ),
        ModelConfig(
            model_id="expensive",
            model_name="Expensive",
            cost_per_input_token=0.0001,
            cost_per_output_token=0.0002,
        ),
    ]
    result = _make_result(
        {
            "cheap": {"r1": {"s": "pos"}},
            "expensive": {"r1": {"s": "pos"}},
        },
        tokens={"cheap": (100, 20), "expensive": (100, 20)},
    )
    agg = service.compute_aggregate(result, configs)
    assert agg.cost_comparison.cheapest_model == "cheap"
    assert agg.cost_comparison.most_expensive_model == "expensive"
    assert (
        agg.cost_comparison.model_costs["cheap"]
        < agg.cost_comparison.model_costs["expensive"]
    )


def test_latency_comparison(service: MultiModelComparisonService) -> None:
    """Latency comparison computes avg/p50/p95 per model."""
    result = _make_result(
        {
            "fast": {"r1": {"s": "a"}, "r2": {"s": "b"}},
            "slow": {"r1": {"s": "a"}, "r2": {"s": "b"}},
        },
        latencies={"fast": 50, "slow": 300},
    )
    agg = service.compute_aggregate(result)
    assert agg.latency_comparison.fastest_model == "fast"
    assert agg.latency_comparison.slowest_model == "slow"
    assert agg.latency_comparison.model_avg_ms["fast"] == 50.0
    assert agg.latency_comparison.model_avg_ms["slow"] == 300.0


def test_per_record_agreement(service: MultiModelComparisonService) -> None:
    """Per-record agreement is 1.0 when all models agree on that record."""
    result = _make_result(
        {
            "m1": {"r1": {"s": "pos"}, "r2": {"s": "neg"}},
            "m2": {"r1": {"s": "pos"}, "r2": {"s": "pos"}},
        }
    )
    agg = service.compute_aggregate(result)
    assert agg.per_record_agreement["r1"] == 1.0
    assert agg.per_record_agreement["r2"] == 0.0


def test_export_comparison_data(
    service: MultiModelComparisonService,
    two_models: list[ModelConfig],
    record_ids: list[str],
) -> None:
    """Export produces a serializable dict structure."""
    run = service.run_comparison(
        model_configs=two_models,
        record_ids=record_ids,
    )
    data = service.export_comparison_data(run)
    assert data["status"] == "completed"
    assert len(data["model_configs"]) == 2
    assert len(data["records"]) == 6
    assert data["aggregate"] is not None
    assert "agreement_matrix" in data["aggregate"]


def test_export_comparison_data_empty_run(
    service: MultiModelComparisonService,
) -> None:
    """Export handles an incomplete run gracefully."""
    run = ComparisonRun(status="pending")
    data = service.export_comparison_data(run)
    assert data["status"] == "pending"
    assert data["aggregate"] is None

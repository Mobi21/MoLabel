"""Comparison run tests (T5-03, T5-04).

T5-03: 2-model comparison run — separate agent runs, per-model metrics.
T5-04: 3-model comparison run — 3 agent runs all appear in comparison result.
"""

from __future__ import annotations

import pytest

from molabel.core.agents.comparison import (
    ComparisonRecord,
    ModelConfig,
    MultiModelComparisonService,
)
from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SHARED_WORKSPACE

# ---------------------------------------------------------------------------
# T5-03: 2-model comparison run
# ---------------------------------------------------------------------------


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier5
async def test_two_model_comparison_run(
    ctx: TestContext,
    client: InstrumentedClient,
) -> None:
    """T5-03: 2-model comparison — separate runs, per-model accuracy + agreement_rate.
    """
    with checkpoint(ctx, "session_setup"):
        await client.login("reviewer-t5-03")

    with checkpoint(ctx, "create_comparison_run_via_api"):
        compare_resp = await client.post(
            "/agent-runs/compare",
            json={
                "workspace_id": "00000000-0000-0000-0000-000000000001",
                "dataset_id": "00000000-0000-0000-0000-000000000002",
                "agent_role": "proposer",
                "task_schema_id": "00000000-0000-0000-0000-000000000003",
                "model_profile_ids": ["model-profile-a", "model-profile-b"],
                "prompt_version": "v1",
            },
        )
        assert compare_resp.status_code == 202
        compare_body = compare_resp.json()
        assert "comparison_id" in compare_body
        assert "agent_run_ids" in compare_body
        assert len(compare_body["agent_run_ids"]) == 2
        assert compare_body["status"] == "pending"

    with checkpoint(ctx, "core_service_two_model_comparison"):
        service = MultiModelComparisonService()
        model_a = ModelConfig(
            model_id="model-a", model_name="ModelA", cost_per_output_token=0.002
        )
        model_b = ModelConfig(
            model_id="model-b", model_name="ModelB", cost_per_output_token=0.001
        )

        record_ids = ["rec-1", "rec-2", "rec-3"]

        def processor(*, record_id: str, model_config: ModelConfig) -> ComparisonRecord:
            # Model A always says "positive", Model B always says "negative"
            label = "positive" if model_config.model_id == "model-a" else "negative"
            return ComparisonRecord(
                record_id=record_id,
                model_id=model_config.model_id,
                labels={"sentiment": label},
                confidence=0.8,
                tokens_input=100,
                tokens_output=20,
                latency_ms=500,
            )

        run = service.run_comparison(
            model_configs=[model_a, model_b],
            record_ids=record_ids,
            processor=processor,
        )

        assert run.status == "completed"
        assert run.result is not None
        assert len(run.result.records) == 6  # 3 records × 2 models

    with checkpoint(ctx, "aggregate_metrics_two_model"):
        agg = service.compute_aggregate(run.result, [model_a, model_b])

        assert agg.total_models == 2
        assert agg.total_records == 3

        # Agreement matrix: model-a vs model-b should be 0.0 (they always disagree)
        matrix = agg.agreement_matrix.matrix
        assert "model-a" in matrix
        assert "model-b" in matrix
        # Self-agreement is 1.0
        assert matrix["model-a"]["model-a"] == 1.0
        assert matrix["model-b"]["model-b"] == 1.0
        # Cross-agreement: both disagree on all records → 0.0
        assert matrix["model-a"]["model-b"] == 0.0

        # Cost: model-b is cheaper
        cost = agg.cost_comparison
        assert cost.cheapest_model == "model-b"

    with checkpoint(ctx, "per_record_agreement_computed"):
        # All records: model-a says positive, model-b says negative → 0.0 agreement
        for rec_id in record_ids:
            assert agg.per_record_agreement.get(rec_id) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# T5-04: 3-model comparison run
# ---------------------------------------------------------------------------


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier5
async def test_three_model_comparison_run(
    ctx: TestContext,
    client: InstrumentedClient,
) -> None:
    """T5-04: 3-model comparison — 3 agent runs, all appear in comparison result."""
    with checkpoint(ctx, "session_setup"):
        await client.login("reviewer-t5-04")

    with checkpoint(ctx, "create_three_model_comparison_via_api"):
        compare_resp = await client.post(
            "/agent-runs/compare",
            json={
                "workspace_id": "00000000-0000-0000-0000-000000000001",
                "dataset_id": "00000000-0000-0000-0000-000000000002",
                "agent_role": "proposer",
                "task_schema_id": "00000000-0000-0000-0000-000000000003",
                "model_profile_ids": [
                    "model-profile-a",
                    "model-profile-b",
                    "model-profile-c",
                ],
            },
        )
        assert compare_resp.status_code == 202
        body = compare_resp.json()
        assert len(body["agent_run_ids"]) == 3

    with checkpoint(ctx, "core_service_three_model_comparison"):
        service = MultiModelComparisonService()
        models = [
            ModelConfig(model_id=f"model-{i}", model_name=f"Model{i.upper()}")
            for i in ("a", "b", "c")
        ]

        record_ids = ["r1", "r2", "r3", "r4", "r5"]

        # Models A and B agree; C disagrees
        labels_by_model = {
            "model-a": "positive",
            "model-b": "positive",
            "model-c": "negative",
        }

        def processor3(
            *, record_id: str, model_config: ModelConfig
        ) -> ComparisonRecord:
            return ComparisonRecord(
                record_id=record_id,
                model_id=model_config.model_id,
                labels={"sentiment": labels_by_model[model_config.model_id]},
                confidence=0.85,
                tokens_input=120,
                tokens_output=25,
                latency_ms=400,
            )

        run3 = service.run_comparison(
            model_configs=models,
            record_ids=record_ids,
            processor=processor3,
        )

        assert run3.status == "completed"
        assert run3.result is not None
        assert len(run3.result.records) == 15  # 5 records × 3 models
        assert set(run3.result.model_ids) == {"model-a", "model-b", "model-c"}

    with checkpoint(ctx, "aggregate_three_model"):
        agg3 = service.compute_aggregate(run3.result, models)

        assert agg3.total_models == 3
        assert agg3.total_records == 5

        matrix3 = agg3.agreement_matrix.matrix
        # A and B agree fully → 1.0
        assert matrix3["model-a"]["model-b"] == pytest.approx(1.0)
        assert matrix3["model-b"]["model-a"] == pytest.approx(1.0)
        # A/B vs C always disagree → 0.0
        assert matrix3["model-a"]["model-c"] == pytest.approx(0.0)
        assert matrix3["model-b"]["model-c"] == pytest.approx(0.0)

    with checkpoint(ctx, "export_comparison_data"):
        export_data = service.export_comparison_data(run3)
        assert export_data["status"] == "completed"
        assert len(export_data["records"]) == 15
        assert export_data["aggregate"]["total_models"] == 3

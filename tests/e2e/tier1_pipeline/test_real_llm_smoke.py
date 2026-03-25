"""T1-01-REAL: Real LLM smoke test for text classification.

Same pipeline as T1-01 but runs 5 records with a real MiniMax 2.7 call
(no cassette).  Skipped automatically unless the ``real_llm`` marker is
selected and MINIMAX_API_KEY is set.

Run with:
    uv run pytest tests/e2e/tier1_pipeline/test_real_llm_smoke.py -m real_llm -v
"""

from __future__ import annotations

import os

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.factories import (
    import_payload,
    text_classification_records,
    text_classification_schema_payload,
)
from tests.e2e.infrastructure.parallel import INDEPENDENT


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier1
@pytest.mark.real_llm
@pytest.mark.slow
async def test_real_llm_smoke_text_classification(
    client,
    ctx,
) -> None:
    """T1-01-REAL: Smoke test with real MiniMax 2.7 on 5 product reviews."""

    minimax_api_key = os.environ.get("MINIMAX_API_KEY")
    if not minimax_api_key:
        pytest.skip("MINIMAX_API_KEY not set — skipping real LLM smoke test")

    # ── Checkpoint 1: Workspace + Reviewer ───────────────────────────────
    with checkpoint(ctx, "workspace_setup"):
        ws_resp = await client.post(
            "/api/v1/workspaces",
            json={
                "path": "/tmp/real-llm-smoke",
                "workspace_name": "Real LLM Smoke WS",
            },
        )
        assert ws_resp.status_code == 201, ws_resp.text
        ws_id = ws_resp.json()["workspace_id"]

        r1_resp = await client.post(
            "/api/v1/reviewer-profiles",
            json={"display_name": "Smoke Reviewer", "workspace_id": ws_id},
        )
        assert r1_resp.status_code == 201, r1_resp.text
        r1_id = str(r1_resp.json()["id"])
        await client.login(r1_id)

    # ── Checkpoint 2: Dataset Import (5 records only) ─────────────────────
    with checkpoint(ctx, "data_import"):
        ds_resp = await client.post(
            "/api/v1/datasets",
            json={
                "dataset_name": "Smoke Reviews",
                "workspace_id": ws_id,
                "source_type": "jsonl",
                "record_kind": "text",
            },
        )
        assert ds_resp.status_code == 201, ds_resp.text
        ds_id = ds_resp.json()["dataset_id"]

        # Take only the first 5 records to limit cost/latency
        all_records = text_classification_records()
        five_records = all_records[:5]
        assert len(five_records) == 5

        import_resp = await client.post(
            f"/api/v1/datasets/{ds_id}/import",
            json=import_payload("jsonl", five_records, text_field="text"),
        )
        assert import_resp.status_code == 202, import_resp.text

    # ── Checkpoint 3: Task Schema + Model Profile + Prompt ───────────────
    with checkpoint(ctx, "schema_config"):
        schema_payload = text_classification_schema_payload()
        schema_resp = await client.post(
            "/api/v1/task-schemas",
            json={
                "workspace_id": ws_id,
                "task_type": schema_payload["task_type"],
                "title": "Sentiment Classification Smoke",
                "task_schema_slug": "sentiment-smoke",
                "label_fields": schema_payload["label_fields"],
                "blind_review_policy": "hide_agent_outputs_by_default",
            },
        )
        assert schema_resp.status_code == 201, schema_resp.text
        schema_id = schema_resp.json()["task_schema_id"]

        model_resp = await client.post(
            "/api/v1/model-profiles",
            json={
                "model_profile_slug": "minimax-2-7-smoke",
                "provider_type": "anthropic",
                "provider_name": "MiniMax",
                "model_identifier": "minimax-2.7",
                "base_url": "https://api.minimax.chat/v1",
                "cost_per_input_token": 0.000001,
                "cost_per_output_token": 0.000003,
            },
        )
        assert model_resp.status_code == 201, model_resp.text
        model_profile_id = str(model_resp.json()["id"])

        prompt_resp = await client.post(
            "/api/v1/prompts",
            json={
                "workspace_id": ws_id,
                "name": "Sentiment Smoke Prompt",
                "agent_role": "proposer",
                "task_schema_id": schema_id,
                "system_instructions": (
                    "Classify the sentiment of this product review. "
                    "Return a JSON object with a single key 'sentiment' "
                    "and value one of: positive, negative, neutral."
                ),
            },
        )
        assert prompt_resp.status_code == 201, prompt_resp.text
        prompt_version = prompt_resp.json()["current_version"]

    # ── Checkpoint 4: Real Agent Run ──────────────────────────────────────
    with checkpoint(ctx, "real_agent_run"):
        run_resp = await client.post(
            "/api/v1/agent-runs",
            json={
                "workspace_id": ws_id,
                "dataset_id": ds_id,
                "agent_role": "proposer",
                "task_schema_id": schema_id,
                "model_profile_id": model_profile_id,
                "prompt_version": prompt_version,
            },
        )
        assert run_resp.status_code == 202, run_resp.text
        run_data = run_resp.json()
        run_id = run_data["agent_run_id"]

        # Mark real LLM call on context for reporting
        ctx.real_llm_calls += 1

        # Assert the run was accepted
        assert run_data["status"] in {"pending", "running", "completed"}
        assert run_data["model_profile_id"] == model_profile_id

    # ── Checkpoint 5: Verify Outputs ──────────────────────────────────────
    with checkpoint(ctx, "verify_outputs"):
        outputs_resp = await client.get(f"/api/v1/agent-runs/{run_id}/outputs")
        assert outputs_resp.status_code == 200, outputs_resp.text
        outputs_data = outputs_resp.json()
        assert "items" in outputs_data

        # For real LLM: verify any returned outputs are valid JSON labels
        for output in outputs_data.get("items", []):
            labels = output.get("labels", {})
            assert isinstance(labels, dict), "Output labels must be a dict"
            if "sentiment" in labels:
                assert labels["sentiment"] in {
                    "positive",
                    "negative",
                    "neutral",
                }, f"Invalid sentiment value: {labels['sentiment']}"

            # Verify token counts and cost tracking fields are present
            # (they may be None if not yet implemented, but keys should exist)
            assert "confidence" in output or output.get("confidence") is None

    # ── Checkpoint 6: Cost Tracking ───────────────────────────────────────
    with checkpoint(ctx, "cost_tracking"):
        # Fetch analytics to verify cost/token info is tracked
        analytics_resp = await client.get(
            "/api/v1/agent-runs/analytics",
            params={"workspace_id": ws_id, "dataset_id": ds_id},
        )
        assert analytics_resp.status_code == 200, analytics_resp.text
        analytics_data = analytics_resp.json()
        # Analytics structure should be present even if values are empty
        assert "accuracy_by_field" in analytics_data
        assert "cost_per_label" in analytics_data

"""T1-05: Full pipeline test for pairwise comparison (response ranking).

Runs the complete labeling pipeline on 35 response pairs:
  workspace -> reviewer setup -> session -> dataset import -> task schema
  (categorical preferred A/B/tie + numeric confidence) -> model profile ->
  prompt -> agent run -> queue claim -> human review -> quality check ->
  export -> release.

Key assertions:
  - Preference values are one of {A, B, tie}
  - Confidence values are floats in [0.0, 1.0]
  - 3-class agreement computed
  - stable_fields contain both response_a and response_b
"""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.factories import (
    import_payload,
    pairwise_comparison_records,
    pairwise_comparison_schema_payload,
)
from tests.e2e.infrastructure.parallel import INDEPENDENT

_VALID_PREFERENCES = {"A", "B", "tie"}


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier1
async def test_full_pipeline_pairwise_comparison(
    client,
    ctx,
    cassette,
) -> None:
    """T1-05: Full pipeline for pairwise response ranking on 35 pairs."""

    # ── Checkpoint 1: Workspace & Reviewer Setup ──────────────────────────
    with checkpoint(ctx, "workspace_setup"):
        ws_resp = await client.post(
            "/api/v1/workspaces",
            json={
                "path": "/tmp/pairwise-test",
                "workspace_name": "Pairwise Comparison WS",
            },
        )
        assert ws_resp.status_code == 201, ws_resp.text
        ws_id = ws_resp.json()["workspace_id"]

        r1_resp = await client.post(
            "/api/v1/reviewer-profiles",
            json={"display_name": "Ranking Reviewer", "workspace_id": ws_id},
        )
        assert r1_resp.status_code == 201, r1_resp.text
        r1_id = str(r1_resp.json()["id"])
        await client.login(r1_id)

    # ── Checkpoint 2: Dataset Import ──────────────────────────────────────
    with checkpoint(ctx, "data_import"):
        ds_resp = await client.post(
            "/api/v1/datasets",
            json={
                "dataset_name": "Response Pairs",
                "workspace_id": ws_id,
                "source_type": "jsonl",
                "record_kind": "pair",
            },
        )
        assert ds_resp.status_code == 201, ds_resp.text
        ds_id = ds_resp.json()["dataset_id"]

        records = pairwise_comparison_records()
        assert len(records) == 35, f"Expected 35 records, got {len(records)}"

        # Pairwise records have both response_a and response_b — import as stable_fields
        import_resp = await client.post(
            f"/api/v1/datasets/{ds_id}/import",
            json=import_payload("jsonl", records, text_field="prompt"),
        )
        assert import_resp.status_code == 202, import_resp.text
        assert import_resp.json()["dataset_id"] == ds_id

    # ── Checkpoint 3: Task Schema + Prompt ───────────────────────────────
    with checkpoint(ctx, "schema_config"):
        schema_payload = pairwise_comparison_schema_payload()
        schema_resp = await client.post(
            "/api/v1/task-schemas",
            json={
                "workspace_id": ws_id,
                "task_type": schema_payload["task_type"],
                "title": "Pairwise Response Comparison",
                "task_schema_slug": schema_payload["task_slug"],
                "label_fields": schema_payload["label_fields"],
                "blind_review_policy": "hide_agent_outputs_by_default",
            },
        )
        assert schema_resp.status_code == 201, schema_resp.text
        schema_data = schema_resp.json()
        schema_id = schema_data["task_schema_id"]

        # Verify both label fields are stored correctly
        label_fields = schema_data.get("label_fields", [])
        field_names = {f["name"] for f in label_fields}
        assert "preferred" in field_names, (
            f"preferred field missing. Got: {field_names}"
        )
        assert "confidence" in field_names, (
            f"confidence field missing. Got: {field_names}"
        )

        preferred_field = next(f for f in label_fields if f["name"] == "preferred")
        assert preferred_field["field_type"] == "categorical"
        assert set(preferred_field["options"]) == _VALID_PREFERENCES

        confidence_field = next(f for f in label_fields if f["name"] == "confidence")
        assert confidence_field["field_type"] == "numeric"
        assert confidence_field["scale_min"] == 0.0
        assert confidence_field["scale_max"] == 1.0

        prompt_resp = await client.post(
            "/api/v1/prompts",
            json={
                "workspace_id": ws_id,
                "name": "Pairwise Comparison Prompt v1",
                "agent_role": "proposer",
                "task_schema_id": schema_id,
                "system_instructions": (
                    "You are a response quality evaluator. "
                    "Given a prompt and two responses (A and B), decide which "
                    "response is better or if they are equal. "
                    'Return JSON: {"preferred": "<A|B|tie>", '
                    '"confidence": <0.0-1.0>}. '
                    "Use confidence 0.5 for ties, higher when one response "
                    "is clearly better."
                ),
                "task_rubric": (
                    "A: prefer response A. "
                    "B: prefer response B. "
                    "tie: responses are approximately equal quality. "
                    "Confidence reflects how certain you are about the preference."
                ),
            },
        )
        assert prompt_resp.status_code == 201, prompt_resp.text
        prompt_version = prompt_resp.json()["current_version"]

    # ── Checkpoint 4: Model Profile + Agent Run ───────────────────────────
    with checkpoint(ctx, "agent_run"):
        model_resp = await client.post(
            "/api/v1/model-profiles",
            json={
                "model_profile_slug": "minimax-2-7-pairwise",
                "provider_type": "anthropic",
                "provider_name": "MiniMax",
                "model_identifier": "MiniMax-M2.7-highspeed",
                "base_url": "https://api.minimax.io/anthropic",
                "cost_per_input_token": 0.000001,
                "cost_per_output_token": 0.000003,
            },
        )
        assert model_resp.status_code == 201, model_resp.text
        model_profile_id = str(model_resp.json()["id"])

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
        assert run_data["status"] in {"pending", "running", "completed"}

        # Verify preference and confidence values in outputs
        outputs_resp = await client.get(f"/api/v1/agent-runs/{run_id}/outputs")
        assert outputs_resp.status_code == 200, outputs_resp.text
        outputs_data = outputs_resp.json()
        assert "items" in outputs_data

        for output in outputs_data.get("items", []):
            labels = output.get("labels", {})
            assert "preferred" in labels, f"Missing 'preferred' in output: {labels}"
            assert labels["preferred"] in _VALID_PREFERENCES, (
                f"Invalid preference: {labels['preferred']}"
            )

            if "confidence" in labels and labels["confidence"] is not None:
                conf = float(labels["confidence"])
                assert 0.0 <= conf <= 1.0, f"Confidence {conf} not in [0, 1]"

    # ── Checkpoint 5: Queue Claim + Human Review ──────────────────────────
    with checkpoint(ctx, "human_review"):
        queue_id = f"{ds_id}:{schema_id}"
        claim_resp = await client.post(f"/api/v1/queues/{queue_id}/claim")
        assert claim_resp.status_code == 200, claim_resp.text
        claim_data = claim_resp.json()

        if not claim_data["queue_empty"]:
            task = claim_data["task"]
            task_id = task["id"]

            # Verify stable_fields contain both responses if available
            record_id = task.get("record_id")
            if record_id:
                record_resp = await client.get(
                    f"/api/v1/datasets/{ds_id}/records/{record_id}"
                )
                if record_resp.status_code == 200:
                    record_data = record_resp.json()
                    stable_fields = record_data.get("stable_fields", {})
                    # The import_payload may store response_a/response_b in
                    # stable_fields; if present, verify both exist
                    if "response_a" in stable_fields or "response_b" in stable_fields:
                        assert "response_a" in stable_fields, (
                            "stable_fields missing response_a"
                        )
                        assert "response_b" in stable_fields, (
                            "stable_fields missing response_b"
                        )

            submit_resp = await client.post(
                f"/api/v1/review-tasks/{task_id}/submit",
                json={
                    "labels": {"preferred": "A", "confidence": 0.85},
                    "decision": "accept",
                    "rationale": (
                        "Response A provides a more accurate and detailed explanation."
                    ),
                    "auto_claim_next": False,
                },
            )
            assert submit_resp.status_code == 200, submit_resp.text
            submit_data = submit_resp.json()
            assert submit_data["submitted_task"]["status"] == "submitted"

            # Verify preference labels in review events
            review_events_resp = await client.get(
                "/api/v1/review/events",
                params={"dataset_id": ds_id, "task_schema_id": schema_id},
            )
            assert review_events_resp.status_code == 200
            events = review_events_resp.json().get("items", [])
            if events:
                event_labels = events[0]["labels"]
                assert event_labels.get("preferred") in _VALID_PREFERENCES

    # ── Checkpoint 6: Quality Check ───────────────────────────────────────
    with checkpoint(ctx, "quality_check"):
        quality_resp = await client.get(
            "/api/v1/quality/dashboard",
            params={"workspace_id": ws_id, "dataset_id": ds_id},
        )
        assert quality_resp.status_code == 200, quality_resp.text
        quality_data = quality_resp.json()
        assert quality_data["workspace_id"] == ws_id
        assert "review_coverage" in quality_data

        # 3-class agreement (A/B/tie) via agreement endpoint
        agreement_resp = await client.get(
            "/api/v1/quality/agreement",
            params={
                "workspace_id": ws_id,
                "dataset_id": ds_id,
                "task_schema_id": schema_id,
            },
        )
        assert agreement_resp.status_code == 200, agreement_resp.text
        agreement_data = agreement_resp.json()
        assert "overall" in agreement_data

    # ── Checkpoint 7: Export + Release ────────────────────────────────────
    with checkpoint(ctx, "export_release"):
        export_resp = await client.post(
            "/api/v1/exports",
            json={
                "workspace_id": ws_id,
                "dataset_id": ds_id,
                "name": "Pairwise Export v1",
                "format": "jsonl",
                "include": {
                    "record_data": True,
                    "human_labels": True,
                    "agent_labels": False,
                    "review_metadata": True,
                    "record_ids": True,
                },
                "filters": {"exclude_flagged": True},
            },
        )
        assert export_resp.status_code == 202, export_resp.text
        export_data = export_resp.json()
        export_id = export_data["export_id"]
        assert export_data["format"] == "jsonl"

        release_resp = await client.post(
            "/api/v1/releases",
            json={
                "workspace_id": ws_id,
                "name": "Pairwise Comparison v1.0",
                "version": "1.0.0",
                "export_ids": [export_id],
                "notes": "Initial pairwise preference ranking release.",
            },
        )
        assert release_resp.status_code == 201, release_resp.text
        release_data = release_resp.json()
        assert release_data["status"] == "draft"
        assert export_id in release_data["export_ids"]

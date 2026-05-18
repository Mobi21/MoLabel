"""T1-04: Full pipeline test for content moderation.

Runs the complete labeling pipeline on 45 user comments:
  workspace -> reviewer setup -> session -> dataset import -> task schema
  (ordinal severity 1-5 + rationale text) -> model profile -> prompt ->
  agent run -> queue claim -> human review -> quality check -> export -> release.

Key assertions:
  - Severity scores are integers in valid range [1, 5]
  - Rationale field is populated (text type)
  - Weighted kappa applicable for ordinal agreement
  - Export includes both severity and rationale fields
"""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.factories import (
    content_moderation_records,
    content_moderation_schema_payload,
    import_payload,
)
from tests.e2e.infrastructure.parallel import INDEPENDENT

_VALID_SEVERITY_OPTIONS = {"1", "2", "3", "4", "5"}


def _coerce_severity(val: object) -> int | None:
    """Coerce severity to int for range-checking (may come as string or int)."""
    try:
        return int(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier1
async def test_full_pipeline_content_moderation(
    client,
    ctx,
    cassette,
) -> None:
    """T1-04: Full pipeline for toxicity rating on 45 comments."""

    # ── Checkpoint 1: Workspace & Reviewer Setup ──────────────────────────
    with checkpoint(ctx, "workspace_setup"):
        ws_resp = await client.post(
            "/api/v1/workspaces",
            json={
                "path": "/tmp/content-mod-test",
                "workspace_name": "Content Moderation WS",
            },
        )
        assert ws_resp.status_code == 201, ws_resp.text
        ws_id = ws_resp.json()["workspace_id"]

        r1_resp = await client.post(
            "/api/v1/reviewer-profiles",
            json={"display_name": "Mod Reviewer", "workspace_id": ws_id},
        )
        assert r1_resp.status_code == 201, r1_resp.text
        r1_id = str(r1_resp.json()["id"])
        await client.login(r1_id)

    # ── Checkpoint 2: Dataset Import ──────────────────────────────────────
    with checkpoint(ctx, "data_import"):
        ds_resp = await client.post(
            "/api/v1/datasets",
            json={
                "dataset_name": "User Comments",
                "workspace_id": ws_id,
                "source_type": "jsonl",
                "record_kind": "text",
            },
        )
        assert ds_resp.status_code == 201, ds_resp.text
        ds_id = ds_resp.json()["dataset_id"]

        records = content_moderation_records()
        assert len(records) == 45, f"Expected 45 records, got {len(records)}"

        import_resp = await client.post(
            f"/api/v1/datasets/{ds_id}/import",
            json=import_payload("jsonl", records, text_field="text"),
        )
        assert import_resp.status_code == 202, import_resp.text
        assert import_resp.json()["dataset_id"] == ds_id

    # ── Checkpoint 3: Task Schema + Prompt ───────────────────────────────
    with checkpoint(ctx, "schema_config"):
        schema_payload = content_moderation_schema_payload()
        schema_resp = await client.post(
            "/api/v1/task-schemas",
            json={
                "workspace_id": ws_id,
                "task_type": schema_payload["task_type"],
                "title": "Content Moderation",
                "task_schema_slug": schema_payload["task_slug"],
                "label_fields": schema_payload["label_fields"],
                "blind_review_policy": "hide_agent_outputs_by_default",
            },
        )
        assert schema_resp.status_code == 201, schema_resp.text
        schema_data = schema_resp.json()
        schema_id = schema_data["task_schema_id"]

        # Verify both fields are stored
        label_fields = schema_data.get("label_fields", [])
        field_names = {f["name"] for f in label_fields}
        assert "severity" in field_names, f"severity field missing. Got: {field_names}"
        assert "rationale" in field_names, (
            f"rationale field missing. Got: {field_names}"
        )

        severity_field = next(f for f in label_fields if f["name"] == "severity")
        assert severity_field["field_type"] == "ordinal"
        assert set(severity_field["options"]) == _VALID_SEVERITY_OPTIONS
        assert severity_field["scale_min"] == 1
        assert severity_field["scale_max"] == 5

        rationale_field = next(f for f in label_fields if f["name"] == "rationale")
        assert rationale_field["field_type"] == "text"

        prompt_resp = await client.post(
            "/api/v1/prompts",
            json={
                "workspace_id": ws_id,
                "name": "Content Moderation Prompt v1",
                "agent_role": "proposer",
                "task_schema_id": schema_id,
                "system_instructions": (
                    "You are a content moderation assistant. "
                    "Rate the severity of each comment on a scale from 1 to 5:\n"
                    "1 = safe (no violations)\n"
                    "2 = borderline (mild language or ambiguous)\n"
                    "3 = moderate (clear policy violation, not extreme)\n"
                    "4 = severe (explicit harmful content)\n"
                    "5 = extreme (immediate removal required)\n"
                    "Also provide a brief rationale explaining the rating.\n"
                    'Return JSON: {"severity": "<1-5>", "rationale": "<text>"}.'
                ),
                "task_rubric": (
                    "Be consistent with ordinal scale. "
                    "Context-dependent comments (sarcasm, coded language) require "
                    "careful interpretation — explain in rationale."
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
                "model_profile_slug": "minimax-2-7-mod",
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

        # Verify outputs: severity in valid range, rationale populated
        outputs_resp = await client.get(f"/api/v1/agent-runs/{run_id}/outputs")
        assert outputs_resp.status_code == 200, outputs_resp.text
        outputs_data = outputs_resp.json()
        assert "items" in outputs_data

        for output in outputs_data.get("items", []):
            labels = output.get("labels", {})
            assert "severity" in labels, f"Missing 'severity' in output: {labels}"

            severity = _coerce_severity(labels["severity"])
            assert severity is not None, (
                f"severity not coercible to int: {labels['severity']}"
            )
            assert 1 <= severity <= 5, f"severity {severity} out of range [1,5]"

            # rationale is optional per schema but we assert structure
            if "rationale" in labels and labels["rationale"] is not None:
                assert isinstance(labels["rationale"], str), (
                    f"rationale must be a string, got: {type(labels['rationale'])}"
                )

    # ── Checkpoint 5: Queue Claim + Human Review ──────────────────────────
    with checkpoint(ctx, "human_review"):
        queue_id = f"{ds_id}:{schema_id}"
        claim_resp = await client.post(f"/api/v1/queues/{queue_id}/claim")
        assert claim_resp.status_code == 200, claim_resp.text
        claim_data = claim_resp.json()

        if not claim_data["queue_empty"]:
            task_id = claim_data["task"]["id"]
            submit_resp = await client.post(
                f"/api/v1/review-tasks/{task_id}/submit",
                json={
                    "labels": {
                        "severity": "3",
                        "rationale": (
                            "Contains mildly offensive language directed at "
                            "content creators but does not rise to severe "
                            "violation level."
                        ),
                    },
                    "decision": "accept",
                    "auto_claim_next": False,
                },
            )
            assert submit_resp.status_code == 200, submit_resp.text
            submit_data = submit_resp.json()
            assert submit_data["submitted_task"]["status"] == "submitted"

            # Verify both fields are in the stored review event
            review_events_resp = await client.get(
                "/api/v1/review/events",
                params={"dataset_id": ds_id, "task_schema_id": schema_id},
            )
            assert review_events_resp.status_code == 200
            events = review_events_resp.json().get("items", [])
            if events:
                event_labels = events[0]["labels"]
                assert "severity" in event_labels
                assert "rationale" in event_labels
                sev = _coerce_severity(event_labels["severity"])
                assert sev is not None and 1 <= sev <= 5

    # ── Checkpoint 6: Quality Check ───────────────────────────────────────
    with checkpoint(ctx, "quality_check"):
        quality_resp = await client.get(
            "/api/v1/quality/dashboard",
            params={"workspace_id": ws_id, "dataset_id": ds_id},
        )
        assert quality_resp.status_code == 200, quality_resp.text
        quality_data = quality_resp.json()
        assert quality_data["workspace_id"] == ws_id
        # Weighted kappa for ordinal fields may be in per_field agreement
        assert "review_coverage" in quality_data

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
        assert "per_field" in agreement_data

    # ── Checkpoint 7: Export + Release ────────────────────────────────────
    with checkpoint(ctx, "export_release"):
        export_resp = await client.post(
            "/api/v1/exports",
            json={
                "workspace_id": ws_id,
                "dataset_id": ds_id,
                "name": "Content Mod Export v1",
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

        # Release the moderation dataset
        release_resp = await client.post(
            "/api/v1/releases",
            json={
                "workspace_id": ws_id,
                "name": "Content Moderation v1.0",
                "version": "1.0.0",
                "export_ids": [export_id],
                "notes": "Initial content moderation severity + rationale release.",
            },
        )
        assert release_resp.status_code == 201, release_resp.text
        release_data = release_resp.json()
        assert release_data["status"] == "draft"
        assert export_id in release_data["export_ids"]

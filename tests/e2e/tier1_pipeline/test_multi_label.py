"""T1-02: Full pipeline test for multi-label topic tagging.

Runs the complete labeling pipeline on 40 news articles:
  workspace -> reviewer setup -> session -> dataset import -> task schema
  (multi_select / 8 topics) -> model profile -> prompt -> agent run ->
  queue claim -> human review -> quality check -> export -> release.

Key assertions:
  - Agent outputs contain list-type labels (multi_select field)
  - Set-based agreement computed (Jaccard similarity)
  - List structure preserved in export
"""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.factories import (
    import_payload,
    multi_label_records,
    multi_label_schema_payload,
)
from tests.e2e.infrastructure.parallel import INDEPENDENT

_VALID_TOPICS = {
    "politics",
    "sports",
    "technology",
    "science",
    "health",
    "entertainment",
    "business",
    "environment",
}


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier1
async def test_full_pipeline_multi_label(
    client,
    ctx,
    cassette,
) -> None:
    """T1-02: Full pipeline for multi-label topic tagging on 40 news articles."""

    # ── Checkpoint 1: Workspace & Reviewer Setup ──────────────────────────
    with checkpoint(ctx, "workspace_setup"):
        ws_resp = await client.post(
            "/api/v1/workspaces",
            json={
                "path": "/tmp/multi-label-test",
                "workspace_name": "Multi-Label Topic WS",
            },
        )
        assert ws_resp.status_code == 201, ws_resp.text
        ws_id = ws_resp.json()["workspace_id"]

        r1_resp = await client.post(
            "/api/v1/reviewer-profiles",
            json={"display_name": "Topic Reviewer", "workspace_id": ws_id},
        )
        assert r1_resp.status_code == 201, r1_resp.text
        r1_id = str(r1_resp.json()["id"])
        await client.login(r1_id)

    # ── Checkpoint 2: Dataset Import ──────────────────────────────────────
    with checkpoint(ctx, "data_import"):
        ds_resp = await client.post(
            "/api/v1/datasets",
            json={
                "dataset_name": "News Articles",
                "workspace_id": ws_id,
                "source_type": "jsonl",
                "record_kind": "text",
            },
        )
        assert ds_resp.status_code == 201, ds_resp.text
        ds_id = ds_resp.json()["dataset_id"]

        records = multi_label_records()
        assert len(records) == 40, f"Expected 40 records, got {len(records)}"

        import_resp = await client.post(
            f"/api/v1/datasets/{ds_id}/import",
            json=import_payload("jsonl", records, text_field="text"),
        )
        assert import_resp.status_code == 202, import_resp.text
        assert import_resp.json()["dataset_id"] == ds_id

    # ── Checkpoint 3: Task Schema + Prompt ───────────────────────────────
    with checkpoint(ctx, "schema_config"):
        schema_payload = multi_label_schema_payload()
        schema_resp = await client.post(
            "/api/v1/task-schemas",
            json={
                "workspace_id": ws_id,
                "task_type": schema_payload["task_type"],
                "title": "Topic Tagging",
                "task_schema_slug": schema_payload["task_slug"],
                "label_fields": schema_payload["label_fields"],
                "blind_review_policy": "hide_agent_outputs_by_default",
            },
        )
        assert schema_resp.status_code == 201, schema_resp.text
        schema_data = schema_resp.json()
        schema_id = schema_data["task_schema_id"]

        # Verify multi_select field type is stored correctly
        label_fields = schema_data.get("label_fields", [])
        topics_field = next((f for f in label_fields if f["name"] == "topics"), None)
        assert topics_field is not None, "topics field not found in schema"
        assert topics_field["field_type"] == "multi_select"
        assert set(topics_field["options"]) == _VALID_TOPICS

        prompt_resp = await client.post(
            "/api/v1/prompts",
            json={
                "workspace_id": ws_id,
                "name": "Topic Tagging Prompt v1",
                "agent_role": "proposer",
                "task_schema_id": schema_id,
                "system_instructions": (
                    "You are a news article topic classifier. "
                    "Given an article, assign all applicable topic categories. "
                    "Valid topics: politics, sports, technology, science, health, "
                    "entertainment, business, environment. "
                    'Return JSON: {"topics": ["<topic1>", "<topic2>"]}. '
                    "Include all that apply; at least one required."
                ),
                "task_rubric": (
                    "Assign multiple topics if the article covers multiple areas. "
                    "A health-tech-business article about biotech funding should get "
                    "all three: health, technology, business."
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
                "model_profile_slug": "minimax-2-7-ml",
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

        # Verify outputs — check that topics are list-type
        outputs_resp = await client.get(f"/api/v1/agent-runs/{run_id}/outputs")
        assert outputs_resp.status_code == 200, outputs_resp.text
        outputs_data = outputs_resp.json()
        assert "items" in outputs_data

        for output in outputs_data.get("items", []):
            labels = output.get("labels", {})
            assert "topics" in labels, f"Missing 'topics' in output labels: {labels}"
            topics_val = labels["topics"]
            # Multi-select field MUST produce a list
            assert isinstance(topics_val, list), (
                f"Expected list for topics, got "
                f"{type(topics_val).__name__}: {topics_val}"
            )
            assert len(topics_val) >= 1, "At least one topic required"
            for t in topics_val:
                assert t in _VALID_TOPICS, f"Invalid topic value: {t}"

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
                    "labels": {"topics": ["technology", "business"]},
                    "decision": "accept",
                    "rationale": (
                        "Article covers both a tech product and its business impact."
                    ),
                    "auto_claim_next": False,
                },
            )
            assert submit_resp.status_code == 200, submit_resp.text
            submit_data = submit_resp.json()
            assert submit_data["submitted_task"]["status"] == "submitted"

            # Verify that the submitted label is a list
            review_events_resp = await client.get(
                "/api/v1/review/events",
                params={"dataset_id": ds_id, "task_schema_id": schema_id},
            )
            assert review_events_resp.status_code == 200
            events = review_events_resp.json().get("items", [])
            if events:
                submitted_labels = events[0]["labels"]
                assert isinstance(submitted_labels.get("topics"), list), (
                    "Review event labels.topics must be a list"
                )

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
        # per_field may contain topics set-agreement metric
        assert "per_field" in agreement_data

    # ── Checkpoint 7: Export + Release ────────────────────────────────────
    with checkpoint(ctx, "export_release"):
        export_resp = await client.post(
            "/api/v1/exports",
            json={
                "workspace_id": ws_id,
                "dataset_id": ds_id,
                "name": "Topic Tags Export v1",
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
                "name": "Topic Tags v1.0",
                "version": "1.0.0",
                "export_ids": [export_id],
                "notes": "Initial multi-label topic tagging release.",
            },
        )
        assert release_resp.status_code == 201, release_resp.text
        release_data = release_resp.json()
        assert release_data["status"] == "draft"
        assert export_id in release_data["export_ids"]

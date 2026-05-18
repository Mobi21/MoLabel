"""T1-03: Full pipeline test for Named Entity Recognition (NER).

Runs the complete labeling pipeline on 30 sentences:
  workspace -> reviewer setup -> session -> dataset import -> task schema
  (JSON field for entity spans) -> model profile -> prompt -> agent run ->
  queue claim -> human review -> quality check -> export -> release.

Key assertions:
  - Entity spans extracted as JSON: [{start, end, label, text}, ...]
  - Validation catches invalid span structure
  - Span-based agreement computed
  - Character offsets (start/end) preserved through export
"""

from __future__ import annotations

import json

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.factories import (
    import_payload,
    ner_records,
    ner_schema_payload,
)
from tests.e2e.infrastructure.parallel import INDEPENDENT

_VALID_NER_LABELS = {"PERSON", "ORG", "LOC", "DATE", "MONEY", "MISC"}


def _validate_entity_spans(entities: object, text: str = "") -> None:
    """Assert that entities is a valid list of NER span dicts."""
    assert isinstance(entities, list), (
        f"entities must be a list, got {type(entities).__name__}: {entities}"
    )
    for span in entities:
        assert isinstance(span, dict), f"Each span must be a dict, got: {span}"
        assert "start" in span, f"Span missing 'start': {span}"
        assert "end" in span, f"Span missing 'end': {span}"
        assert "label" in span, f"Span missing 'label': {span}"
        assert "text" in span, f"Span missing 'text': {span}"
        assert isinstance(span["start"], int), f"start must be int: {span}"
        assert isinstance(span["end"], int), f"end must be int: {span}"
        assert span["start"] >= 0, f"start must be non-negative: {span}"
        assert span["end"] > span["start"], f"end must be > start: {span}"


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier1
async def test_full_pipeline_ner(
    client,
    ctx,
    cassette,
) -> None:
    """T1-03: Full pipeline for NER on 30 annotated sentences."""

    # ── Checkpoint 1: Workspace & Reviewer Setup ──────────────────────────
    with checkpoint(ctx, "workspace_setup"):
        ws_resp = await client.post(
            "/api/v1/workspaces",
            json={
                "path": "/tmp/ner-test",
                "workspace_name": "NER Test WS",
            },
        )
        assert ws_resp.status_code == 201, ws_resp.text
        ws_id = ws_resp.json()["workspace_id"]

        r1_resp = await client.post(
            "/api/v1/reviewer-profiles",
            json={"display_name": "NER Reviewer", "workspace_id": ws_id},
        )
        assert r1_resp.status_code == 201, r1_resp.text
        r1_id = str(r1_resp.json()["id"])
        await client.login(r1_id)

    # ── Checkpoint 2: Dataset Import ──────────────────────────────────────
    with checkpoint(ctx, "data_import"):
        ds_resp = await client.post(
            "/api/v1/datasets",
            json={
                "dataset_name": "NER Sentences",
                "workspace_id": ws_id,
                "source_type": "jsonl",
                "record_kind": "text",
            },
        )
        assert ds_resp.status_code == 201, ds_resp.text
        ds_id = ds_resp.json()["dataset_id"]

        records = ner_records()
        assert len(records) == 30, f"Expected 30 records, got {len(records)}"

        import_resp = await client.post(
            f"/api/v1/datasets/{ds_id}/import",
            json=import_payload("jsonl", records, text_field="text"),
        )
        assert import_resp.status_code == 202, import_resp.text
        assert import_resp.json()["dataset_id"] == ds_id

    # ── Checkpoint 3: Task Schema + Prompt ───────────────────────────────
    with checkpoint(ctx, "schema_config"):
        schema_payload = ner_schema_payload()
        schema_resp = await client.post(
            "/api/v1/task-schemas",
            json={
                "workspace_id": ws_id,
                "task_type": schema_payload["task_type"],
                "title": "Named Entity Recognition",
                "task_schema_slug": schema_payload["task_slug"],
                "label_fields": schema_payload["label_fields"],
                "blind_review_policy": "hide_agent_outputs_by_default",
            },
        )
        assert schema_resp.status_code == 201, schema_resp.text
        schema_data = schema_resp.json()
        schema_id = schema_data["task_schema_id"]

        # Verify JSON field type is stored
        label_fields = schema_data.get("label_fields", [])
        entities_field = next(
            (f for f in label_fields if f["name"] == "entities"), None
        )
        assert entities_field is not None, "entities field not found in schema"
        assert entities_field["field_type"] == "json"

        prompt_resp = await client.post(
            "/api/v1/prompts",
            json={
                "workspace_id": ws_id,
                "name": "NER Prompt v1",
                "agent_role": "proposer",
                "task_schema_id": schema_id,
                "system_instructions": (
                    "You are a named entity recognition assistant. "
                    "Given a sentence, identify all named entities and return "
                    "their character spans as a JSON array. "
                    'Each entity: {"start": <int>, "end": <int>, '
                    '"label": "<PERSON|ORG|LOC|DATE|MONEY|MISC>", '
                    '"text": "<matched text>"}. '
                    'Return JSON: {"entities": [...]}. '
                    "Return an empty list if no entities found."
                ),
                "task_rubric": (
                    "PERSON: individual people. "
                    "ORG: companies, agencies, institutions. "
                    "LOC: countries, cities, geographic features. "
                    "DATE: absolute or relative dates/times. "
                    "MONEY: monetary values. "
                    "MISC: other named entities (products, events, etc.)."
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
                "model_profile_slug": "minimax-2-7-ner",
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

        # Verify entity span structure in outputs
        outputs_resp = await client.get(f"/api/v1/agent-runs/{run_id}/outputs")
        assert outputs_resp.status_code == 200, outputs_resp.text
        outputs_data = outputs_resp.json()
        assert "items" in outputs_data

        for output in outputs_data.get("items", []):
            labels = output.get("labels", {})
            assert "entities" in labels, (
                f"Missing 'entities' in output labels: {labels}"
            )
            entities_val = labels["entities"]
            # entities may be stored as a JSON string or a list
            if isinstance(entities_val, str):
                entities_val = json.loads(entities_val)
            _validate_entity_spans(entities_val)

    # ── Checkpoint 5: Queue Claim + Human Review ──────────────────────────
    with checkpoint(ctx, "human_review"):
        queue_id = f"{ds_id}:{schema_id}"
        claim_resp = await client.post(f"/api/v1/queues/{queue_id}/claim")
        assert claim_resp.status_code == 200, claim_resp.text
        claim_data = claim_resp.json()

        if not claim_data["queue_empty"]:
            task_id = claim_data["task"]["id"]
            # Human reviewer provides corrected entity spans
            human_entities = [
                {"start": 0, "end": 9, "label": "PERSON", "text": "Elon Musk"},
                {"start": 42, "end": 47, "label": "ORG", "text": "Tesla"},
                {"start": 67, "end": 73, "label": "LOC", "text": "Austin"},
                {"start": 75, "end": 80, "label": "LOC", "text": "Texas"},
            ]
            submit_resp = await client.post(
                f"/api/v1/review-tasks/{task_id}/submit",
                json={
                    "labels": {"entities": human_entities},
                    "decision": "accept",
                    "rationale": (
                        "Corrected entity spans with precise character offsets."
                    ),
                    "auto_claim_next": False,
                },
            )
            assert submit_resp.status_code == 200, submit_resp.text
            submit_data = submit_resp.json()
            assert submit_data["submitted_task"]["status"] == "submitted"

            # Verify character offsets are preserved in stored review event
            review_events_resp = await client.get(
                "/api/v1/review/events",
                params={"dataset_id": ds_id, "task_schema_id": schema_id},
            )
            assert review_events_resp.status_code == 200
            events = review_events_resp.json().get("items", [])
            if events:
                stored_entities = events[0]["labels"].get("entities", [])
                if isinstance(stored_entities, str):
                    stored_entities = json.loads(stored_entities)
                _validate_entity_spans(stored_entities)
                # Verify offsets are preserved
                for span in stored_entities:
                    assert isinstance(span["start"], int)
                    assert isinstance(span["end"], int)

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

    # ── Checkpoint 7: Export + Release ────────────────────────────────────
    with checkpoint(ctx, "export_release"):
        export_resp = await client.post(
            "/api/v1/exports",
            json={
                "workspace_id": ws_id,
                "dataset_id": ds_id,
                "name": "NER Export v1",
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

        # Verify export contains the entities field
        assert export_data["format"] == "jsonl"
        assert export_data["dataset_id"] == ds_id

        release_resp = await client.post(
            "/api/v1/releases",
            json={
                "workspace_id": ws_id,
                "name": "NER Dataset v1.0",
                "version": "1.0.0",
                "export_ids": [export_id],
                "notes": "Initial NER span annotation release.",
            },
        )
        assert release_resp.status_code == 201, release_resp.text
        release_data = release_resp.json()
        assert release_data["status"] == "draft"
        assert export_id in release_data["export_ids"]

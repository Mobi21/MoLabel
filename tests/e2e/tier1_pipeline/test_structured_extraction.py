"""T1-06: Full pipeline test for structured extraction (invoice parsing).

Runs the complete labeling pipeline on 25 invoice texts:
  workspace -> reviewer setup -> session -> dataset import -> task schema
  (multi-field: vendor_name, total_amount, date, currency, line_items JSON) ->
  model profile -> prompt -> agent run -> queue claim -> human review ->
  quality check -> export -> release.

Key assertions:
  - All extraction fields present in outputs (vendor_name, total_amount, date)
  - total_amount is numeric (float/int), not a string
  - date is parseable as ISO 8601 (YYYY-MM-DD)
  - currency is a 3-letter string when present
  - line_items is a list of {description, quantity, price} when present
  - Nested structure preserved through export
"""

from __future__ import annotations

import re

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.factories import (
    import_payload,
    structured_extraction_records,
    structured_extraction_schema_payload,
)
from tests.e2e.infrastructure.parallel import INDEPENDENT

_ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")


def _validate_extraction_output(labels: dict) -> None:
    """Assert that an extraction output has the required fields and types."""
    # Required fields
    assert "vendor_name" in labels, f"Missing vendor_name in labels: {labels}"
    assert "total_amount" in labels, f"Missing total_amount in labels: {labels}"
    assert "date" in labels, f"Missing date in labels: {labels}"

    assert isinstance(labels["vendor_name"], str), (
        f"vendor_name must be str: {labels['vendor_name']}"
    )
    assert len(labels["vendor_name"]) > 0, "vendor_name must not be empty"

    # total_amount must be numeric
    total = labels["total_amount"]
    assert isinstance(total, (int, float)), (
        f"total_amount must be numeric, got {type(total).__name__}: {total}"
    )
    assert total >= 0, f"total_amount must be non-negative: {total}"

    # date must be ISO format
    date_val = labels["date"]
    assert isinstance(date_val, str), f"date must be str: {date_val}"
    assert _ISO_DATE_PATTERN.match(date_val), (
        f"date must be YYYY-MM-DD format, got: {date_val}"
    )

    # currency is optional but if present must be 3 letters
    if "currency" in labels and labels["currency"] is not None:
        currency = labels["currency"]
        assert isinstance(currency, str), f"currency must be str: {currency}"
        assert _CURRENCY_PATTERN.match(currency), (
            f"currency must be 3-letter ISO code, got: {currency}"
        )

    # line_items is optional but if present must be a list
    if "line_items" in labels and labels["line_items"] is not None:
        import json as _json

        line_items = labels["line_items"]
        if isinstance(line_items, str):
            line_items = _json.loads(line_items)
        assert isinstance(line_items, list), (
            f"line_items must be list, got {type(line_items).__name__}"
        )
        for item in line_items:
            assert isinstance(item, dict), f"Each line_item must be a dict: {item}"
            # Should have at minimum a description
            assert "description" in item, f"line_item missing description: {item}"


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier1
async def test_full_pipeline_structured_extraction(
    client,
    ctx,
    cassette,
) -> None:
    """T1-06: Full pipeline for invoice extraction on 25 invoice texts."""

    # ── Checkpoint 1: Workspace & Reviewer Setup ──────────────────────────
    with checkpoint(ctx, "workspace_setup"):
        ws_resp = await client.post(
            "/api/v1/workspaces",
            json={
                "path": "/tmp/extraction-test",
                "workspace_name": "Invoice Extraction WS",
            },
        )
        assert ws_resp.status_code == 201, ws_resp.text
        ws_id = ws_resp.json()["workspace_id"]

        r1_resp = await client.post(
            "/api/v1/reviewer-profiles",
            json={"display_name": "Extraction Reviewer", "workspace_id": ws_id},
        )
        assert r1_resp.status_code == 201, r1_resp.text
        r1_id = str(r1_resp.json()["id"])
        await client.login(r1_id)

    # ── Checkpoint 2: Dataset Import ──────────────────────────────────────
    with checkpoint(ctx, "data_import"):
        ds_resp = await client.post(
            "/api/v1/datasets",
            json={
                "dataset_name": "Invoices",
                "workspace_id": ws_id,
                "source_type": "jsonl",
                "record_kind": "document",
            },
        )
        assert ds_resp.status_code == 201, ds_resp.text
        ds_id = ds_resp.json()["dataset_id"]

        records = structured_extraction_records()
        assert len(records) == 25, f"Expected 25 records, got {len(records)}"

        import_resp = await client.post(
            f"/api/v1/datasets/{ds_id}/import",
            json=import_payload("jsonl", records, text_field="text"),
        )
        assert import_resp.status_code == 202, import_resp.text
        assert import_resp.json()["dataset_id"] == ds_id

    # ── Checkpoint 3: Task Schema + Prompt ───────────────────────────────
    with checkpoint(ctx, "schema_config"):
        schema_payload = structured_extraction_schema_payload()
        schema_resp = await client.post(
            "/api/v1/task-schemas",
            json={
                "workspace_id": ws_id,
                "task_type": schema_payload["task_type"],
                "title": "Invoice Field Extraction",
                "task_schema_slug": schema_payload["task_slug"],
                "label_fields": schema_payload["label_fields"],
                "blind_review_policy": "hide_agent_outputs_by_default",
            },
        )
        assert schema_resp.status_code == 201, schema_resp.text
        schema_data = schema_resp.json()
        schema_id = schema_data["task_schema_id"]

        # Verify all 5 label fields are stored
        label_fields = schema_data.get("label_fields", [])
        field_names = {f["name"] for f in label_fields}
        expected_fields = {
            "vendor_name",
            "total_amount",
            "date",
            "currency",
            "line_items",
        }
        assert expected_fields <= field_names, (
            f"Missing fields: {expected_fields - field_names}"
        )

        # Verify types
        total_field = next(f for f in label_fields if f["name"] == "total_amount")
        assert total_field["field_type"] == "numeric"

        line_items_field = next(f for f in label_fields if f["name"] == "line_items")
        assert line_items_field["field_type"] == "json"

        prompt_resp = await client.post(
            "/api/v1/prompts",
            json={
                "workspace_id": ws_id,
                "name": "Invoice Extraction Prompt v1",
                "agent_role": "proposer",
                "task_schema_id": schema_id,
                "system_instructions": (
                    "You are an invoice data extraction assistant. "
                    "Extract structured fields from the invoice or receipt text. "
                    "Return JSON with these fields:\n"
                    "  - vendor_name: string (required)\n"
                    "  - total_amount: number, no currency symbol (required)\n"
                    "  - date: YYYY-MM-DD format (required)\n"
                    "  - currency: 3-letter ISO code e.g. USD, EUR (optional)\n"
                    "  - line_items: array of {description, quantity, price}"
                    " (optional)\n"
                    'Example: {"vendor_name": "Acme Corp", '
                    '"total_amount": 465.93, "date": "2024-03-15", '
                    '"currency": "USD", "line_items": ['
                    '{"description": "Widget", "quantity": 5, "price": 9.99}]}'
                ),
                "task_rubric": (
                    "Always include required fields. "
                    "total_amount should be the final total (after tax). "
                    "Use null for optional fields if not found."
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
                "model_profile_slug": "minimax-2-7-extraction",
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

        # Verify structured extraction outputs
        outputs_resp = await client.get(f"/api/v1/agent-runs/{run_id}/outputs")
        assert outputs_resp.status_code == 200, outputs_resp.text
        outputs_data = outputs_resp.json()
        assert "items" in outputs_data

        for output in outputs_data.get("items", []):
            labels = output.get("labels", {})
            _validate_extraction_output(labels)

    # ── Checkpoint 5: Queue Claim + Human Review ──────────────────────────
    with checkpoint(ctx, "human_review"):
        queue_id = f"{ds_id}:{schema_id}"
        claim_resp = await client.post(f"/api/v1/queues/{queue_id}/claim")
        assert claim_resp.status_code == 200, claim_resp.text
        claim_data = claim_resp.json()

        if not claim_data["queue_empty"]:
            task_id = claim_data["task"]["id"]
            # Human reviewer provides corrected extraction
            human_labels = {
                "vendor_name": "Acme Office Supplies Ltd.",
                "total_amount": 465.93,
                "date": "2024-03-15",
                "currency": "USD",
                "line_items": [
                    {
                        "description": "Printer Paper (Case)",
                        "quantity": 5,
                        "price": 42.99,
                    },
                    {
                        "description": "Black Ink Cartridges (Pack 4)",
                        "quantity": 2,
                        "price": 89.99,
                    },
                    {
                        "description": "Stapler, heavy-duty",
                        "quantity": 1,
                        "price": 34.50,
                    },
                ],
            }
            submit_resp = await client.post(
                f"/api/v1/review-tasks/{task_id}/submit",
                json={
                    "labels": human_labels,
                    "decision": "accept",
                    "rationale": "Corrected line items from invoice INV-2024-00847.",
                    "auto_claim_next": False,
                },
            )
            assert submit_resp.status_code == 200, submit_resp.text
            assert submit_resp.json()["submitted_task"]["status"] == "submitted"

            # Verify nested structure preserved in review events
            review_events_resp = await client.get(
                "/api/v1/review/events",
                params={"dataset_id": ds_id, "task_schema_id": schema_id},
            )
            assert review_events_resp.status_code == 200
            events = review_events_resp.json().get("items", [])
            if events:
                event_labels = events[0]["labels"]
                _validate_extraction_output(event_labels)
                # Verify nested line_items are preserved
                if event_labels.get("line_items"):
                    import json as _json

                    line_items = event_labels["line_items"]
                    if isinstance(line_items, str):
                        line_items = _json.loads(line_items)
                    assert len(line_items) == 3

    # ── Checkpoint 6: Quality Check (per-field accuracy) ─────────────────
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
        # per_field should contain per-field accuracy for extraction fields
        assert "per_field" in agreement_data

    # ── Checkpoint 7: Export + Release ────────────────────────────────────
    with checkpoint(ctx, "export_release"):
        export_resp = await client.post(
            "/api/v1/exports",
            json={
                "workspace_id": ws_id,
                "dataset_id": ds_id,
                "name": "Invoice Extraction Export v1",
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
        assert export_data["dataset_id"] == ds_id

        release_resp = await client.post(
            "/api/v1/releases",
            json={
                "workspace_id": ws_id,
                "name": "Invoice Extraction v1.0",
                "version": "1.0.0",
                "export_ids": [export_id],
                "notes": "Initial structured invoice extraction release.",
            },
        )
        assert release_resp.status_code == 201, release_resp.text
        release_data = release_resp.json()
        assert release_data["status"] == "draft"
        assert export_id in release_data["export_ids"]

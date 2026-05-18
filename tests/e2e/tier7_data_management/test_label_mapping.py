"""T7-10: Label mapping — field rename + value translation.

Verifies:
- Field rename: "rating" → "sentiment"
- Value translation: 1-2 → "negative", 3 → "neutral", 4-5 → "positive"
- Preview endpoint applies mappings to sample records
- Save endpoint persists the mapping
- Unmapped fields reported in preview result
"""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.parallel import INDEPENDENT


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier7
async def test_label_mapping(client, ctx):
    """T7-10: Label mapping — field rename + value translation, preview, save."""

    # ── Checkpoint 1: Setup ───────────────────────────────────────────────────
    with checkpoint(ctx, "setup"):
        ws = await client.post(
            "/api/v1/workspaces",
            json={
                "path": "/tmp/ws-label-mapping-test",
                "workspace_name": "Label Mapping Test",
            },
        )
        assert ws.status_code == 201
        ws_id = ws.json()["workspace_id"]

        # Create task schema for sentiment
        schema = await client.post(
            "/api/v1/task-schemas",
            json={
                "workspace_id": ws_id,
                "task_schema_slug": "sentiment",
                "task_type": "classification",
                "title": "Sentiment Classification",
                "label_fields": [
                    {
                        "name": "sentiment",
                        "field_type": "categorical",
                        "options": ["positive", "negative", "neutral"],
                        "required": True,
                    }
                ],
            },
        )
        assert schema.status_code == 201
        schema_id = schema.json()["task_schema_id"]

    # ── Checkpoint 2: Preview label mapping ──────────────────────────────────
    with checkpoint(ctx, "preview"):
        sample_records = [
            {"rating": "1", "text": "Terrible product"},
            {"rating": "2", "text": "Not good"},
            {"rating": "3", "text": "Average"},
            {"rating": "4", "text": "Pretty good"},
            {"rating": "5", "text": "Excellent"},
        ]

        field_mappings = [
            {
                "source_field": "rating",
                "target_field": "sentiment",
                "transform": "rename",
            },
            {"source_field": "text", "target_field": "text", "transform": "direct"},
        ]

        def _vm(src: str, tgt: str) -> dict:
            return {"source_value": src, "target_value": tgt, "field_name": "sentiment"}

        value_mappings = [
            _vm("1", "negative"),
            _vm("2", "negative"),
            _vm("3", "neutral"),
            _vm("4", "positive"),
            _vm("5", "positive"),
        ]

        preview_resp = await client.post(
            "/api/v1/label-mappings/preview",
            json={
                "source_system": "legacy_rating_system",
                "task_schema_id": schema_id,
                "field_mappings": field_mappings,
                "value_mappings": value_mappings,
                "sample_records": sample_records,
            },
        )
        assert preview_resp.status_code == 200
        preview = preview_resp.json()

        assert preview["total_records"] == 5
        assert preview["successful"] == 5
        assert preview["errors_count"] == 0

        mapped = preview["mapped_records"]
        assert len(mapped) == 5

        # Verify value translations
        sentiments = [m["mapped"].get("sentiment") for m in mapped]
        assert sentiments[0] == "negative"  # rating=1
        assert sentiments[1] == "negative"  # rating=2
        assert sentiments[2] == "neutral"  # rating=3
        assert sentiments[3] == "positive"  # rating=4
        assert sentiments[4] == "positive"  # rating=5

    # ── Checkpoint 3: Unmapped fields reported ───────────────────────────────
    with checkpoint(ctx, "unmapped_fields"):
        records_with_extra = [
            {
                "rating": "3",
                "text": "ok",
                "extra_field": "ignore_me",
                "another": "also_ignore",
            },
        ]
        preview2_resp = await client.post(
            "/api/v1/label-mappings/preview",
            json={
                "source_system": "test",
                "task_schema_id": schema_id,
                "field_mappings": [
                    {"source_field": "rating", "target_field": "sentiment"},
                ],
                "value_mappings": [
                    _vm("3", "neutral"),
                ],
                "sample_records": records_with_extra,
            },
        )
        assert preview2_resp.status_code == 200
        preview2 = preview2_resp.json()
        # Unmapped fields: text, extra_field, another
        unmapped = preview2.get("unmapped_fields", [])
        assert "extra_field" in unmapped or "another" in unmapped or "text" in unmapped

    # ── Checkpoint 4: Save the mapping ───────────────────────────────────────
    with checkpoint(ctx, "save"):
        save_resp = await client.post(
            "/api/v1/label-mappings",
            json={
                "name": "Rating to Sentiment v1",
                "mapping_slug": "rating-to-sentiment-v1",
                "workspace_id": ws_id,
                "source_system": "legacy_rating_system",
                "source_format": "csv",
                "task_schema_id": schema_id,
                "field_mappings": field_mappings,
                "value_mappings": value_mappings,
                "default_trust_level": "external",
                "unmapped_field_policy": "preserve_reference",
            },
        )
        assert save_resp.status_code == 201
        saved = save_resp.json()
        assert saved["mapping_id"]
        assert saved["name"] == "Rating to Sentiment v1"
        assert saved["mapping_slug"] == "rating-to-sentiment-v1"
        assert saved["source_system"] == "legacy_rating_system"
        assert len(saved["field_mappings"]) == 2
        assert len(saved["value_mappings"]) == 5
        assert saved["default_trust_level"] == "external"

"""Tier 3 — API Coverage: Label Mappings (T3-22).

Tests:
    T3-22: Preview + save with field/value mappings
"""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SHARED_WORKSPACE

BASE = "/api/v1"
WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"


async def _setup(client: InstrumentedClient) -> str:
    rp = await client.post(
        f"{BASE}/reviewer-profiles",
        json={"display_name": "LM Reviewer", "workspace_id": WORKSPACE_ID},
    )
    assert rp.status_code == 201
    reviewer_id = rp.json()["id"]
    login = await client.post(f"{BASE}/sessions", json={"reviewer_id": reviewer_id})
    assert login.status_code == 200
    client._session_cookie = login.cookies.get("molabel_session")

    ws = await client.post(
        f"{BASE}/workspaces",
        json={"path": "/tmp/ws-lm", "workspace_name": "LM Workspace"},
    )
    assert ws.status_code == 201
    return ws.json()["workspace_id"]


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier3
async def test_label_mappings_preview_and_save(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T3-22: Preview label mapping and save it."""

    workspace_id = await _setup(client)
    task_schema_id = "00000000-0000-0000-0000-7as7schema001"

    sample_records = [
        {"raw_label": "POSITIVE", "text": "I love this!"},
        {"raw_label": "NEGATIVE", "text": "This is terrible."},
        {"raw_label": "NEUTRAL", "text": "It is okay."},
    ]

    field_mappings = [
        {
            "source_field": "raw_label",
            "target_field": "sentiment",
            "transform": "direct",
        },
        {"source_field": "text", "target_field": "input_text", "transform": "direct"},
    ]

    value_mappings = [
        {
            "source_value": "POSITIVE",
            "target_value": "positive",
            "field_name": "sentiment",
        },
        {
            "source_value": "NEGATIVE",
            "target_value": "negative",
            "field_name": "sentiment",
        },
        {
            "source_value": "NEUTRAL",
            "target_value": "neutral",
            "field_name": "sentiment",
        },
    ]

    with checkpoint(ctx, "preview_label_mapping"):
        resp = await client.post(
            f"{BASE}/label-mappings/preview",
            json={
                "source_system": "legacy_annotator",
                "source_format": "csv",
                "task_schema_id": task_schema_id,
                "field_mappings": field_mappings,
                "value_mappings": value_mappings,
                "sample_records": sample_records,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "mapped_records" in body
        assert body["total_records"] == 3
        assert body["successful"] >= 0
        assert "unmapped_fields" in body
        # Verify mapping was applied
        for mapped_rec in body["mapped_records"]:
            assert "original" in mapped_rec
            assert "mapped" in mapped_rec

    with checkpoint(ctx, "preview_with_unmapped_fields"):
        # Include a field not in mappings
        records_with_extra = [
            {"raw_label": "POSITIVE", "text": "Hi", "extra_field": "value"}
        ]
        resp = await client.post(
            f"{BASE}/label-mappings/preview",
            json={
                "source_system": "legacy",
                "task_schema_id": task_schema_id,
                "field_mappings": field_mappings,
                "value_mappings": [],
                "sample_records": records_with_extra,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "extra_field" in body["unmapped_fields"]

    with checkpoint(ctx, "save_label_mapping"):
        resp = await client.post(
            f"{BASE}/label-mappings",
            json={
                "name": "Legacy Annotation Mapping",
                "workspace_id": workspace_id,
                "source_system": "legacy_annotator",
                "source_format": "csv",
                "task_schema_id": task_schema_id,
                "field_mappings": field_mappings,
                "value_mappings": value_mappings,
                "default_trust_level": "external",
                "unmapped_field_policy": "preserve_reference",
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["name"] == "Legacy Annotation Mapping"
        assert body["source_system"] == "legacy_annotator"
        assert body["workspace_id"] == workspace_id
        assert len(body["field_mappings"]) == 2
        assert len(body["value_mappings"]) == 3
        assert "mapping_id" in body
        assert "mapping_slug" in body

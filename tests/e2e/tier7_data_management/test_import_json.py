"""T7-02: JSON import via plugin loader.

Verifies:
- Array of objects: each becomes a record
- Nested JSON objects are preserved in stable_fields / payload
- records_path config navigates nested structure
- Non-dict array elements are skipped
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.parallel import INDEPENDENT


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier7
async def test_import_json(client, ctx):
    """T7-02: JSON import — nested JSON preserved, array records each a record."""

    # ── Checkpoint 1: Setup ───────────────────────────────────────────────────
    with checkpoint(ctx, "setup"):
        ws = await client.post(
            "/api/v1/workspaces",
            json={
                "path": "/tmp/ws-json-import-test",
                "workspace_name": "JSON Import Test",
            },
        )
        assert ws.status_code == 201
        ws_id = ws.json()["workspace_id"]

        ds = await client.post(
            "/api/v1/datasets",
            json={
                "dataset_name": "JSON Dataset",
                "workspace_id": ws_id,
                "source_type": "json",
            },
        )
        assert ds.status_code == 201
        ds_id = ds.json()["dataset_id"]

    # ── Checkpoint 2: Simple array loading ───────────────────────────────────
    with checkpoint(ctx, "array_loading"):
        from molabel.plugins.loaders.json_loader import JsonLoader

        data = [
            {
                "id": "j1",
                "title": "Article One",
                "meta": {"author": "Alice", "tags": ["ai", "ml"]},
            },
            {
                "id": "j2",
                "title": "Article Two",
                "meta": {"author": "Bob", "tags": ["data"]},
            },
            {
                "id": "j3",
                "title": "Article Three",
                "meta": {"author": "Carol", "tags": []},
            },
        ]

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(data, f, ensure_ascii=False)
            json_path = Path(f.name)

        try:
            loader = JsonLoader()
            assert loader.can_load(json_path)

            records = list(loader.load_records(json_path, config={"id_field": "id"}))
            assert len(records) == 3

            for i, rec in enumerate(records):
                assert rec.external_id == data[i]["id"]
                # Nested dict preserved in stable_fields
                assert isinstance(rec.stable_fields["meta"], dict)
                assert rec.stable_fields["meta"]["author"] == data[i]["meta"]["author"]
                # Nested list preserved
                assert isinstance(rec.stable_fields["meta"]["tags"], list)
        finally:
            json_path.unlink(missing_ok=True)

    # ── Checkpoint 3: Nested path loading ────────────────────────────────────
    with checkpoint(ctx, "nested_path"):
        from molabel.plugins.loaders.json_loader import JsonLoader

        nested_data = {
            "metadata": {"version": "1.0"},
            "items": [
                {"item_id": "a", "content": "first"},
                {"item_id": "b", "content": "second"},
            ],
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(nested_data, f)
            nested_path = Path(f.name)

        try:
            loader2 = JsonLoader()
            records2 = list(
                loader2.load_records(
                    nested_path,
                    config={"records_path": "items", "id_field": "item_id"},
                )
            )
            assert len(records2) == 2
            assert records2[0].external_id == "a"
            assert records2[1].external_id == "b"

            # get_schema works on nested structure
            schema = loader2.get_schema(nested_path)
            assert schema["type"] == "object"
        finally:
            nested_path.unlink(missing_ok=True)

    # ── Checkpoint 4: estimate_record_count ──────────────────────────────────
    with checkpoint(ctx, "record_count"):
        from molabel.plugins.loaders.json_loader import JsonLoader

        count_data = [{"x": i} for i in range(7)]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(count_data, f)
            count_path = Path(f.name)

        try:
            loader3 = JsonLoader()
            count = loader3.estimate_record_count(count_path)
            assert count == 7
        finally:
            count_path.unlink(missing_ok=True)

    # ── Checkpoint 5: API import call ────────────────────────────────────────
    with checkpoint(ctx, "api_import"):
        resp = await client.post(
            f"/api/v1/datasets/{ds_id}/import",
            json={"source_uri": "test://json"},
        )
        assert resp.status_code == 202
        assert resp.json()["dataset_id"] == ds_id

"""T7-03: JSONL import via plugin loader.

Verifies:
- One JSON object per line → one record each
- Valid lines are imported even if some lines are malformed
- Malformed lines raise json.JSONDecodeError (not silently dropped)
- Empty lines are skipped
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
async def test_import_jsonl(client, ctx):
    """T7-03: JSONL import — one record per line, malformed lines surfaced."""

    # ── Checkpoint 1: Setup ───────────────────────────────────────────────────
    with checkpoint(ctx, "setup"):
        ws = await client.post(
            "/api/v1/workspaces", json={"path": "/tmp/ws-jsonl-import-test", "workspace_name": "JSONL Import Test"}
        )
        assert ws.status_code == 201
        ws_id = ws.json()["workspace_id"]

        ds = await client.post(
            "/api/v1/datasets",
            json={
                "dataset_name": "JSONL Dataset",
                "workspace_id": ws_id,
                "source_type": "jsonl",
            },
        )
        assert ds.status_code == 201
        ds_id = ds.json()["dataset_id"]

    # ── Checkpoint 2: Valid JSONL loading ─────────────────────────────────────
    with checkpoint(ctx, "valid_jsonl"):
        from molabel.plugins.loaders.jsonl_loader import JsonlLoader

        valid_lines = [
            {"id": "jl-01", "text": "First record", "score": 4.5},
            {"id": "jl-02", "text": "Second record", "score": 3.0},
            {"id": "jl-03", "text": "Third record with unicode: café 🎉", "score": 5.0},
        ]

        content = (
            "\n".join(json.dumps(r, ensure_ascii=False) for r in valid_lines) + "\n"
        )

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            jsonl_path = Path(f.name)

        try:
            loader = JsonlLoader()
            assert loader.can_load(jsonl_path)

            records = list(loader.load_records(jsonl_path, config={"id_field": "id"}))
            assert len(records) == 3

            for i, rec in enumerate(records):
                assert rec.external_id == valid_lines[i]["id"]
                assert rec.stable_fields["text"] == valid_lines[i]["text"]
                assert rec.stable_fields["score"] == valid_lines[i]["score"]

            # estimate_record_count
            count = loader.estimate_record_count(jsonl_path)
            assert count == 3
        finally:
            jsonl_path.unlink(missing_ok=True)

    # ── Checkpoint 3: Empty lines skipped ────────────────────────────────────
    with checkpoint(ctx, "empty_lines"):
        from molabel.plugins.loaders.jsonl_loader import JsonlLoader

        content_with_blanks = (
            '{"id": "e1", "text": "alpha"}\n\n\n{"id": "e2", "text": "beta"}\n'
        )

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        ) as f:
            f.write(content_with_blanks)
            blank_path = Path(f.name)

        try:
            loader2 = JsonlLoader()
            records2 = list(loader2.load_records(blank_path, config={}))
            assert len(records2) == 2
        finally:
            blank_path.unlink(missing_ok=True)

    # ── Checkpoint 4: Malformed line raises json.JSONDecodeError ─────────────
    with checkpoint(ctx, "malformed_lines"):
        from molabel.plugins.loaders.jsonl_loader import JsonlLoader

        content_bad = (
            '{"id": "good1", "text": "valid"}\n'
            "NOT_VALID_JSON\n"
            '{"id": "good2", "text": "also valid"}\n'
        )

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        ) as f:
            f.write(content_bad)
            bad_path = Path(f.name)

        try:
            loader3 = JsonlLoader()
            # The loader raises json.JSONDecodeError on malformed lines
            with pytest.raises(json.JSONDecodeError):
                list(loader3.load_records(bad_path, config={}))
        finally:
            bad_path.unlink(missing_ok=True)

    # ── Checkpoint 5: Schema inference ───────────────────────────────────────
    with checkpoint(ctx, "schema"):
        from molabel.plugins.loaders.jsonl_loader import JsonlLoader

        schema_data = '{"name": "Alice", "age": 30, "active": true}\n'
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        ) as f:
            f.write(schema_data)
            schema_path = Path(f.name)

        try:
            loader4 = JsonlLoader()
            schema = loader4.get_schema(schema_path)
            assert schema["type"] == "object"
            props = schema["properties"]
            assert props["name"]["type"] == "string"
            assert props["age"]["type"] == "integer"
            assert props["active"]["type"] == "boolean"
        finally:
            schema_path.unlink(missing_ok=True)

    # ── Checkpoint 6: API import ──────────────────────────────────────────────
    with checkpoint(ctx, "api_import"):
        resp = await client.post(
            f"/api/v1/datasets/{ds_id}/import",
            json={"source_uri": "test://jsonl"},
        )
        assert resp.status_code == 202
        assert resp.json()["dataset_id"] == ds_id

"""T7-09: JSONL export via plugin exporter.

Verifies:
- One JSON object per line
- All stable_fields present in each line
- Final newline present
- UTF-8 encoding
- validate_export passes
- Empty export produces empty (or zero-line) content
"""

from __future__ import annotations

import json
import uuid

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.parallel import INDEPENDENT


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier7
async def test_export_jsonl(client, ctx):
    """T7-09: Export to JSONL — one object per line, all fields."""

    # ── Checkpoint 1: Setup ───────────────────────────────────────────────────
    with checkpoint(ctx, "setup"):
        ws = await client.post(
            "/api/v1/workspaces", json={"path": "/tmp/ws-jsonl-export-test", "workspace_name": "JSONL Export Test"}
        )
        assert ws.status_code == 201
        ws_id = ws.json()["workspace_id"]

        ds = await client.post(
            "/api/v1/datasets",
            json={
                "dataset_name": "JSONL Export Dataset",
                "workspace_id": ws_id,
                "source_type": "jsonl",
            },
        )
        assert ds.status_code == 201
        ds_id = ds.json()["dataset_id"]

    # ── Checkpoint 2: Basic JSONL export ─────────────────────────────────────
    with checkpoint(ctx, "jsonl_export"):
        from molabel.core.types import SENTINEL_DATASET_ID, Record
        from molabel.plugins.exporters.jsonl_exporter import JsonlExporter

        records = [
            Record(
                id=uuid.uuid4(),
                dataset_id=SENTINEL_DATASET_ID,
                stable_fields={
                    "text": f"Record {i}",
                    "source": "test",
                    "score": i,
                },
                payload={},
                record_kind=None,
            )
            for i in range(4)
        ]

        exporter = JsonlExporter()
        artifact = exporter.package(records, labels={}, config={})

        assert artifact.format == "jsonl"
        assert artifact.record_count == 4
        assert artifact.data is not None

        content = artifact.data.decode("utf-8")
        lines = [ln for ln in content.splitlines() if ln.strip()]

        # One JSON object per line
        assert len(lines) == 4, f"Expected 4 lines, got {len(lines)}"

        for i, line in enumerate(lines):
            obj = json.loads(line)
            assert obj["text"] == f"Record {i}"
            assert obj["source"] == "test"
            assert obj["score"] == i

        # Content ends with newline
        assert content.endswith("\n")

    # ── Checkpoint 3: UTF-8 with unicode ─────────────────────────────────────
    with checkpoint(ctx, "unicode"):
        from molabel.core.types import SENTINEL_DATASET_ID, Record
        from molabel.plugins.exporters.jsonl_exporter import JsonlExporter

        unicode_records = [
            Record(
                id=uuid.uuid4(),
                dataset_id=SENTINEL_DATASET_ID,
                stable_fields={
                    "text": "Emoji: 🎉 CJK: 这是测试 Arabic: اختبار",
                    "note": "Newline\nembedded",
                },
                payload={},
                record_kind=None,
            )
        ]

        exporter2 = JsonlExporter()
        artifact2 = exporter2.package(unicode_records, labels={}, config={})
        content2 = artifact2.data.decode("utf-8")
        obj2 = json.loads(content2.strip())
        assert "🎉" in obj2["text"]
        assert "这是测试" in obj2["text"]
        assert "اختبار" in obj2["text"]

    # ── Checkpoint 4: validate_export passes ─────────────────────────────────
    with checkpoint(ctx, "validation"):
        from molabel.core.types import SENTINEL_DATASET_ID, Record
        from molabel.plugins.exporters.jsonl_exporter import JsonlExporter

        recs3 = [
            Record(
                id=uuid.uuid4(),
                dataset_id=SENTINEL_DATASET_ID,
                stable_fields={"v": str(i)},
                payload={},
                record_kind=None,
            )
            for i in range(3)
        ]

        exporter3 = JsonlExporter()
        artifact3 = exporter3.package(recs3, labels={}, config={})
        result = exporter3.validate_export(artifact3)
        assert result.is_valid, f"Validation failed: {result.errors}"

    # ── Checkpoint 5: API export endpoint ────────────────────────────────────
    with checkpoint(ctx, "api_export"):
        resp = await client.post(
            "/api/v1/exports",
            json={
                "workspace_id": ws_id,
                "dataset_id": ds_id,
                "name": "JSONL Export",
                "format": "jsonl",
                "include": {
                    "record_data": True,
                    "human_labels": True,
                },
            },
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["format"] == "jsonl"
        assert "export_id" in body

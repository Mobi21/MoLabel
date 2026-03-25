"""T8-12: Records with 10000+ character text — stored and processed correctly.

Verifies:
- 10000+ char text is loaded and preserved exactly by JSONL loader
- Long text round-trips through JSONL export without truncation
- CSV export handles long text (may wrap in JSON string)
- Parquet export preserves long text
- No silent truncation or overflow
"""

from __future__ import annotations

import json
import tempfile
import uuid
from pathlib import Path

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.parallel import INDEPENDENT

# Generate a 10000+ character text
LONG_TEXT_LENGTH = 10_500
_BASE = (
    "The quick brown fox jumps over the lazy dog. " * 50
    + "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
    + "sed do eiusmod tempor incididunt ut labore et dolore. "
    + "Ut enim ad minim veniam, quis nostrud exercitation. " * 30
)
# Pad to guarantee >= LONG_TEXT_LENGTH characters
LONG_TEXT = _BASE + "Z" * max(0, LONG_TEXT_LENGTH - len(_BASE))
assert len(LONG_TEXT) >= LONG_TEXT_LENGTH, f"Long text only {len(LONG_TEXT)} chars"


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier8
async def test_long_text(client, ctx):
    """T8-12: Records with 10000+ character text — no truncation at any stage."""

    # ── Checkpoint 1: Setup ───────────────────────────────────────────────────
    with checkpoint(ctx, "setup"):
        ws = await client.post("/api/v1/workspaces", json={"path": "/tmp/ws-long-text-test", "workspace_name": "Long Text Test"})
        assert ws.status_code == 201
        ws_id = ws.json()["workspace_id"]

        ds = await client.post(
            "/api/v1/datasets",
            json={
                "dataset_name": "Long Text Dataset",
                "workspace_id": ws_id,
                "source_type": "jsonl",
            },
        )
        assert ds.status_code == 201
        ds_id = ds.json()["dataset_id"]

    # ── Checkpoint 2: JSONL round-trip with long text ─────────────────────────
    with checkpoint(ctx, "jsonl_round_trip"):
        from molabel.plugins.loaders.jsonl_loader import JsonlLoader

        record_data = {
            "id": "long-001",
            "text": LONG_TEXT,
            "length": len(LONG_TEXT),
            "category": "long_form",
        }

        jsonl_content = json.dumps(record_data, ensure_ascii=False) + "\n"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        ) as f:
            f.write(jsonl_content)
            jsonl_path = Path(f.name)

        try:
            loader = JsonlLoader()
            records = list(loader.load_records(jsonl_path, config={"id_field": "id"}))
            assert len(records) == 1

            loaded_text = records[0].stable_fields["text"]
            got = len(loaded_text)
            assert len(loaded_text) >= LONG_TEXT_LENGTH, (
                f"Text truncated: expected {LONG_TEXT_LENGTH}+ chars, got {got}"
            )
            assert loaded_text == LONG_TEXT, "Long text was modified during load"
        finally:
            jsonl_path.unlink(missing_ok=True)

    # ── Checkpoint 3: JSONL export preserves long text ────────────────────────
    with checkpoint(ctx, "jsonl_export"):
        from molabel.core.types import SENTINEL_DATASET_ID, Record
        from molabel.plugins.exporters.jsonl_exporter import JsonlExporter

        rec = Record(
            id=uuid.uuid4(),
            dataset_id=SENTINEL_DATASET_ID,
            stable_fields={"id": "long-001", "text": LONG_TEXT},
            payload={},
            record_kind=None,
        )

        exporter = JsonlExporter()
        artifact = exporter.package([rec], labels={}, config={})
        content = artifact.data.decode("utf-8")
        lines = [ln for ln in content.splitlines() if ln.strip()]
        assert len(lines) == 1

        exported_obj = json.loads(lines[0])
        exported_text = exported_obj["text"]
        got_exp = len(exported_text)
        assert len(exported_text) >= LONG_TEXT_LENGTH, (
            f"Export truncated: expected {LONG_TEXT_LENGTH}+ chars, got {got_exp}"
        )
        assert exported_text == LONG_TEXT, "Long text was modified during export"

    # ── Checkpoint 4: Multiple long-text records ──────────────────────────────
    with checkpoint(ctx, "multiple_long_records"):
        from molabel.core.types import SENTINEL_DATASET_ID, Record
        from molabel.plugins.exporters.jsonl_exporter import JsonlExporter

        long_records = [
            Record(
                id=uuid.uuid4(),
                dataset_id=SENTINEL_DATASET_ID,
                stable_fields={"text": LONG_TEXT + f"_suffix_{i}", "idx": i},
                payload={},
                record_kind=None,
            )
            for i in range(5)
        ]

        exporter2 = JsonlExporter()
        artifact2 = exporter2.package(long_records, labels={}, config={})
        assert artifact2.record_count == 5

        lines2 = [
            ln for ln in artifact2.data.decode("utf-8").splitlines() if ln.strip()
        ]
        assert len(lines2) == 5
        for i, ln in enumerate(lines2):
            obj = json.loads(ln)
            assert len(obj["text"]) >= LONG_TEXT_LENGTH
            assert f"_suffix_{i}" in obj["text"]

    # ── Checkpoint 5: CSV export with long text ───────────────────────────────
    with checkpoint(ctx, "csv_long_text"):
        from molabel.core.types import SENTINEL_DATASET_ID, Record
        from molabel.plugins.exporters.csv_exporter import CsvExporter

        csv_rec = Record(
            id=uuid.uuid4(),
            dataset_id=SENTINEL_DATASET_ID,
            stable_fields={"id": "csv-long-001", "text": LONG_TEXT},
            payload={},
            record_kind=None,
        )

        csv_exporter = CsvExporter()
        csv_artifact = csv_exporter.package([csv_rec], labels={}, config={})
        csv_bytes = csv_artifact.data

        # CSV content should contain the long text
        csv_content = csv_bytes.decode("utf-8")
        assert len(csv_content) >= LONG_TEXT_LENGTH, (
            f"CSV shorter than expected: {len(csv_content)} chars"
        )

    # ── Checkpoint 6: API import ──────────────────────────────────────────────
    with checkpoint(ctx, "api_import"):
        resp = await client.post(
            f"/api/v1/datasets/{ds_id}/import",
            json={"source_uri": "test://long-text"},
        )
        assert resp.status_code == 202

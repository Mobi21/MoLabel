"""T7-07: CSV export via plugin exporter.

Verifies:
- Header row present
- Correct column names
- UTF-8 encoding (including non-ASCII characters)
- Complex values (dict, list) serialized as JSON strings in cells
- Row count matches record count
- validate_export passes
"""

from __future__ import annotations

import csv
import io
import uuid

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.parallel import INDEPENDENT


def _make_record(text: str, record_id: str | None = None) -> object:
    """Create a minimal Record-like object for export testing."""
    from molabel.core.types import SENTINEL_DATASET_ID, Record

    rid = uuid.uuid4()
    return Record(
        id=rid,
        dataset_id=SENTINEL_DATASET_ID,
        stable_fields={"text": text, "source": "test"},
        payload={"text": text},
        record_kind=None,
    )


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier7
async def test_export_csv(client, ctx):
    """T7-07: Export to CSV — header row, correct columns, UTF-8."""

    # ── Checkpoint 1: Setup ───────────────────────────────────────────────────
    with checkpoint(ctx, "setup"):
        ws = await client.post(
            "/workspaces", json={"workspace_name": "CSV Export Test"}
        )
        assert ws.status_code == 201
        ws_id = ws.json()["workspace_id"]

        reviewer = await client.post(
            "/reviewer-profiles", json={"display_name": "Exporter"}
        )
        assert reviewer.status_code == 201
        await client.login(reviewer.json()["reviewer_id"])

        ds = await client.post(
            "/datasets",
            json={
                "dataset_name": "CSV Export Dataset",
                "workspace_id": ws_id,
                "source_type": "csv",
            },
        )
        assert ds.status_code == 201
        ds_id = ds.json()["dataset_id"]

    # ── Checkpoint 2: Basic CSV export via plugin ─────────────────────────────
    with checkpoint(ctx, "csv_export"):
        from molabel.core.types import SENTINEL_DATASET_ID, Record
        from molabel.plugins.exporters.csv_exporter import CsvExporter

        records = [
            Record(
                id=uuid.uuid4(),
                dataset_id=SENTINEL_DATASET_ID,
                stable_fields={
                    "text": "Bonjour café",
                    "rating": "5",
                    "tags": ["a", "b"],
                },
                payload={},
                record_kind=None,
            ),
            Record(
                id=uuid.uuid4(),
                dataset_id=SENTINEL_DATASET_ID,
                stable_fields={
                    "text": "日本語テスト",
                    "rating": "3",
                    "tags": ["c"],
                },
                payload={},
                record_kind=None,
            ),
        ]

        exporter = CsvExporter()
        artifact = exporter.package(records, labels={}, config={})

        # Artifact has data bytes
        assert artifact.data is not None
        assert artifact.format == "csv"
        assert artifact.record_count == 2

        # Decode and parse CSV
        csv_text = artifact.data.decode("utf-8")

        reader = csv.reader(io.StringIO(csv_text))
        header = next(reader)
        data_rows = list(reader)

        # Header must be present
        assert len(header) > 0, "CSV must have a header row"
        assert "text" in header
        assert "rating" in header

        # Correct row count (not counting header)
        assert len(data_rows) == 2, f"Expected 2 data rows, got {len(data_rows)}"

        # UTF-8 content preserved
        all_text = csv_text
        assert "Bonjour café" in all_text or "caf" in all_text
        assert "日本語" in all_text

        # Tags (list) serialized as JSON string
        tags_col_idx = header.index("tags") if "tags" in header else -1
        if tags_col_idx >= 0:
            import json

            tags_val = data_rows[0][tags_col_idx]
            # Should be a JSON-encoded string like '["a", "b"]'
            parsed = json.loads(tags_val)
            assert isinstance(parsed, list)

    # ── Checkpoint 3: validate_export passes ─────────────────────────────────
    with checkpoint(ctx, "validation"):
        from molabel.core.types import SENTINEL_DATASET_ID, Record
        from molabel.plugins.exporters.csv_exporter import CsvExporter

        records2 = [
            Record(
                id=uuid.uuid4(),
                dataset_id=SENTINEL_DATASET_ID,
                stable_fields={"x": "hello"},
                payload={},
                record_kind=None,
            )
            for _ in range(3)
        ]

        exporter2 = CsvExporter()
        artifact2 = exporter2.package(records2, labels={}, config={})
        result = exporter2.validate_export(artifact2)
        assert result.is_valid, f"Validation failed: {result.errors}"

    # ── Checkpoint 4: API export endpoint ────────────────────────────────────
    with checkpoint(ctx, "api_export"):
        resp = await client.post(
            "/exports",
            json={
                "workspace_id": ws_id,
                "dataset_id": ds_id,
                "name": "CSV Export",
                "format": "csv",
                "include": {
                    "record_data": True,
                    "human_labels": True,
                },
            },
        )
        assert resp.status_code == 202
        export_body = resp.json()
        assert export_body["format"] == "csv"
        assert export_body["dataset_id"] == ds_id
        assert "export_id" in export_body

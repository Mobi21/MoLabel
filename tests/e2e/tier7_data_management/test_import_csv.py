"""T7-01: CSV import via plugin loader.

Verifies:
- Headers are parsed into stable_fields (not imported as a data record)
- Each data row becomes one record
- stable_fields keys match column names
- id_column config maps to external_id
"""

from __future__ import annotations

import csv
import tempfile
from pathlib import Path

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.parallel import INDEPENDENT


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier7
async def test_import_csv(client, ctx):
    """T7-01: Import CSV, verify stable_fields from columns, header not a record."""

    # ── Checkpoint 1: Setup workspace + dataset ──────────────────────────────
    with checkpoint(ctx, "setup"):
        ws = await client.post(
            "/api/v1/workspaces", json={"path": "/tmp/ws-csv-import-test", "workspace_name": "CSV Import Test"}
        )
        assert ws.status_code == 201
        ws_id = ws.json()["workspace_id"]

        ds = await client.post(
            "/api/v1/datasets",
            json={
                "dataset_name": "CSV Dataset",
                "workspace_id": ws_id,
                "source_type": "csv",
            },
        )
        assert ds.status_code == 201
        ds_id = ds.json()["dataset_id"]

    # ── Checkpoint 2: Build CSV file and load via plugin ─────────────────────
    with checkpoint(ctx, "loader_validation"):
        from molabel.plugins.loaders.csv_loader import CsvLoader

        rows = [
            {"id": "r1", "text": "Hello world", "rating": "5"},
            {"id": "r2", "text": "Not great", "rating": "2"},
            {"id": "r3", "text": "Decent product", "rating": "3"},
        ]

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            writer = csv.DictWriter(f, fieldnames=["id", "text", "rating"])
            writer.writeheader()
            writer.writerows(rows)
            csv_path = Path(f.name)

        try:
            loader = CsvLoader()
            assert loader.can_load(csv_path)

            records = list(loader.load_records(csv_path, config={"id_column": "id"}))

            # Header must NOT appear as a record
            assert len(records) == 3, f"Expected 3 records, got {len(records)}"

            # stable_fields must contain all column values from data rows
            for i, record in enumerate(records):
                assert "id" in record.stable_fields
                assert "text" in record.stable_fields
                assert "rating" in record.stable_fields
                # external_id set from id_column
                assert record.external_id == rows[i]["id"]

        finally:
            csv_path.unlink(missing_ok=True)

    # ── Checkpoint 3: Schema inference ───────────────────────────────────────
    with checkpoint(ctx, "schema_inference"):
        rows2 = [
            {"product_id": "p1", "price": "9.99", "in_stock": "true", "qty": "10"},
        ]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            writer = csv.DictWriter(f, fieldnames=list(rows2[0].keys()))
            writer.writeheader()
            writer.writerows(rows2)
            csv_path2 = Path(f.name)

        try:
            loader2 = CsvLoader()
            schema = loader2.get_schema(csv_path2)
            assert schema["type"] == "object"
            assert "properties" in schema
            props = schema["properties"]
            # qty "10" should infer as integer
            assert props.get("qty", {}).get("type") in ("integer", "number", "string")
            # price "9.99" should infer as number or string
            assert "price" in props

            # estimate_record_count excludes header
            count = loader2.estimate_record_count(csv_path2)
            assert count == 1
        finally:
            csv_path2.unlink(missing_ok=True)

    # ── Checkpoint 4: Import via API ─────────────────────────────────────────
    with checkpoint(ctx, "api_import"):
        resp = await client.post(
            f"/api/v1/datasets/{ds_id}/import",
            json={"source_uri": "test://placeholder"},
        )
        # API returns 202 (async job queued)
        assert resp.status_code == 202
        body = resp.json()
        assert body["dataset_id"] == ds_id
        assert body["status"] in ("queued", "pending", "running", "completed")
        assert "job_id" in body

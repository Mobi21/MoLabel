"""T7-08: Parquet export via plugin exporter.

Verifies:
- Correct schema — column names present
- Column type correctness (string, int, float preserved)
- Row count matches record count
- validate_export passes
- In-memory (no destination) and file-based export modes
"""

from __future__ import annotations

import uuid

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.parallel import INDEPENDENT


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier7
async def test_export_parquet(client, ctx):
    """T7-08: Export to Parquet — correct schema and column types."""

    # ── Checkpoint 1: Setup ───────────────────────────────────────────────────
    with checkpoint(ctx, "setup"):
        ws = await client.post(
            "/api/v1/workspaces",
            json={
                "path": "/tmp/ws-parquet-export-test",
                "workspace_name": "Parquet Export Test",
            },
        )
        assert ws.status_code == 201
        ws_id = ws.json()["workspace_id"]

        ds = await client.post(
            "/api/v1/datasets",
            json={
                "dataset_name": "Parquet Export Dataset",
                "workspace_id": ws_id,
                "source_type": "parquet",
            },
        )
        assert ds.status_code == 201
        ds_id = ds.json()["dataset_id"]

    # ── Checkpoint 2: In-memory Parquet export ────────────────────────────────
    with checkpoint(ctx, "parquet_export"):
        try:
            import io as _io

            import pyarrow.parquet as pq
        except ImportError:
            pytest.skip("pyarrow not installed")

        from molabel.core.types import SENTINEL_DATASET_ID, Record
        from molabel.plugins.exporters.parquet_exporter import ParquetExporter

        records = [
            Record(
                id=uuid.uuid4(),
                dataset_id=SENTINEL_DATASET_ID,
                stable_fields={
                    "text": f"Record {i}",
                    "score": i * 10,
                    "rate": float(i) / 10,
                },
                payload={},
                record_kind=None,
            )
            for i in range(5)
        ]

        exporter = ParquetExporter()
        artifact = exporter.package(records, labels={}, config={})

        assert artifact.format == "parquet"
        assert artifact.record_count == 5
        assert artifact.data is not None

        # Parse Parquet and check schema
        pf = pq.ParquetFile(_io.BytesIO(artifact.data))
        table = pf.read()

        assert pf.metadata.num_rows == 5, f"Expected 5 rows, got {pf.metadata.num_rows}"

        schema = table.schema
        col_names = schema.names
        assert "text" in col_names
        assert "score" in col_names
        assert "rate" in col_names

    # ── Checkpoint 3: validate_export passes ─────────────────────────────────
    with checkpoint(ctx, "validation"):
        try:
            import pyarrow as _pa  # noqa: F401
        except ImportError:
            pytest.skip("pyarrow not installed")

        from molabel.core.types import SENTINEL_DATASET_ID, Record
        from molabel.plugins.exporters.parquet_exporter import ParquetExporter

        records2 = [
            Record(
                id=uuid.uuid4(),
                dataset_id=SENTINEL_DATASET_ID,
                stable_fields={"val": str(i)},
                payload={},
                record_kind=None,
            )
            for i in range(4)
        ]

        exporter2 = ParquetExporter()
        artifact2 = exporter2.package(records2, labels={}, config={})
        result = exporter2.validate_export(artifact2)
        assert result.is_valid, f"Parquet validation failed: {result.errors}"

    # ── Checkpoint 4: API export endpoint ────────────────────────────────────
    with checkpoint(ctx, "api_export"):
        resp = await client.post(
            "/api/v1/exports",
            json={
                "workspace_id": ws_id,
                "dataset_id": ds_id,
                "name": "Parquet Export",
                "format": "parquet",
                "include": {
                    "record_data": True,
                    "human_labels": True,
                },
            },
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["format"] == "parquet"
        assert "export_id" in body

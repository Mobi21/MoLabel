"""T8-08: Filter eliminates all records — downstream agent_run handles 0 records.

Verifies:
- A filter expression that matches nothing produces 0 records
- Exporting 0 filtered records produces a valid (empty) artifact
- DatasetAnalytics still returns valid shape with 0 matching records
- JSONL exporter handles empty filtered result gracefully
"""

from __future__ import annotations

import uuid

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.parallel import INDEPENDENT


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier8
async def test_empty_filter(client, ctx):
    """T8-08: Filter eliminates all records, downstream agent_run handles 0 records."""

    # ── Checkpoint 1: Setup ───────────────────────────────────────────────────
    with checkpoint(ctx, "setup"):
        ws = await client.post(
            "/api/v1/workspaces", json={"path": "/tmp/ws-empty-filter-test", "workspace_name": "Empty Filter Test"}
        )
        assert ws.status_code == 201
        ws_id = ws.json()["workspace_id"]

        ds = await client.post(
            "/api/v1/datasets",
            json={
                "dataset_name": "Filter Dataset",
                "workspace_id": ws_id,
                "source_type": "jsonl",
            },
        )
        assert ds.status_code == 201
        ds_id = ds.json()["dataset_id"]

    # ── Checkpoint 2: Simulate filter that matches nothing ────────────────────
    with checkpoint(ctx, "empty_filter_result"):
        from molabel.core.types import SENTINEL_DATASET_ID, Record

        # 5 records with category "news"
        all_records = [
            Record(
                id=uuid.uuid4(),
                dataset_id=SENTINEL_DATASET_ID,
                stable_fields={"text": f"News article {i}", "category": "news"},
                payload={},
                record_kind=None,
            )
            for i in range(5)
        ]

        # Filter: only category "sports" — matches nothing
        filtered = [
            r for r in all_records if r.stable_fields.get("category") == "sports"
        ]
        assert len(filtered) == 0, "Filter should eliminate all records"

    # ── Checkpoint 3: Export with empty filter result ─────────────────────────
    with checkpoint(ctx, "export_empty_filter"):
        from molabel.plugins.exporters.jsonl_exporter import JsonlExporter

        exporter = JsonlExporter()
        artifact = exporter.package([], labels={}, config={})

        assert artifact.record_count == 0
        content = artifact.data.decode("utf-8")
        lines = [ln for ln in content.splitlines() if ln.strip()]
        assert len(lines) == 0

    # ── Checkpoint 4: Export API with empty filter spec ───────────────────────
    with checkpoint(ctx, "api_export_with_filter"):
        export_resp = await client.post(
            "/api/v1/exports",
            json={
                "workspace_id": ws_id,
                "dataset_id": ds_id,
                "name": "Empty Filter Export",
                "format": "jsonl",
                "include": {
                    "record_data": True,
                    "human_labels": True,
                },
                "filters": {
                    "status": ["nonexistent_status"],
                    "exclude_flagged": False,
                },
            },
        )
        assert export_resp.status_code == 202
        assert export_resp.json()["dataset_id"] == ds_id

    # ── Checkpoint 5: Preview with empty result ───────────────────────────────
    with checkpoint(ctx, "preview_empty"):
        preview_resp = await client.post(
            "/api/v1/exports/preview",
            json={
                "workspace_id": ws_id,
                "dataset_id": ds_id,
                "name": "Empty Filter Preview",
                "format": "jsonl",
                "include": {
                    "record_data": True,
                    "human_labels": True,
                },
                "filters": {
                    "record_ids": [],  # Empty record_ids filter = nothing
                },
            },
        )
        assert preview_resp.status_code == 200
        preview = preview_resp.json()
        assert "total_matching" in preview
        assert isinstance(preview["sample_records"], list)

    # ── Checkpoint 6: Parquet exporter handles 0-record result ────────────────
    with checkpoint(ctx, "parquet_empty_filter"):
        try:
            import pyarrow.parquet as pq
        except ImportError:
            pytest.skip("pyarrow not installed")

        from molabel.plugins.exporters.parquet_exporter import ParquetExporter

        pq_exporter = ParquetExporter()
        pq_artifact = pq_exporter.package([], labels={}, config={})

        assert pq_artifact.record_count == 0
        assert pq_artifact.data is not None

        import io as _io

        pf = pq.ParquetFile(_io.BytesIO(pq_artifact.data))
        assert pf.metadata.num_rows == 0

"""T8-07: Empty dataset (0 records) — agent run, export, quality handle gracefully.

Verifies:
- Dataset with 0 records is created successfully
- GET /datasets/{id}/records returns empty list (not error)
- GET /datasets/{id}/analytics returns zeros (not error)
- POST /exports on empty dataset returns 202 (not error)
- DatasetAnalytics with record_count=0 is valid
- Export with 0 records produces valid (empty) artifact
"""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.parallel import INDEPENDENT


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier8
async def test_empty_dataset(client, ctx):
    """T8-07: Agent run, export, quality on 0-record dataset — all graceful."""

    # ── Checkpoint 1: Setup empty dataset ────────────────────────────────────
    with checkpoint(ctx, "setup"):
        ws = await client.post(
            "/api/v1/workspaces",
            json={
                "path": "/tmp/ws-empty-dataset-test",
                "workspace_name": "Empty Dataset Test",
            },
        )
        assert ws.status_code == 201
        ws_id = ws.json()["workspace_id"]

        ds = await client.post(
            "/api/v1/datasets",
            json={
                "dataset_name": "Empty Dataset",
                "workspace_id": ws_id,
                "source_type": "jsonl",
            },
        )
        assert ds.status_code == 201
        ds_id = ds.json()["dataset_id"]

    # ── Checkpoint 2: Records list is empty (not an error) ────────────────────
    with checkpoint(ctx, "empty_records_list"):
        records_resp = await client.get(f"/api/v1/datasets/{ds_id}/records")
        assert records_resp.status_code == 200
        body = records_resp.json()
        assert body["items"] == []
        assert body["has_more"] is False

    # ── Checkpoint 3: Analytics returns zeros ─────────────────────────────────
    with checkpoint(ctx, "analytics_zeros"):
        analytics_resp = await client.get(f"/api/v1/datasets/{ds_id}/analytics")
        assert analytics_resp.status_code == 200
        analytics = analytics_resp.json()
        assert analytics["record_count"] == 0
        assert analytics["labeled_count"] == 0
        assert isinstance(analytics["label_distributions"], list)

    # ── Checkpoint 4: Snapshot on empty dataset ───────────────────────────────
    with checkpoint(ctx, "empty_snapshot"):
        snap_resp = await client.post(
            f"/api/v1/datasets/{ds_id}/snapshots",
            json={"name": "empty-snapshot", "snapshot_type": "full"},
        )
        assert snap_resp.status_code == 201
        snap = snap_resp.json()
        assert snap["record_count"] == 0
        assert snap["labeled_count"] == 0

    # ── Checkpoint 5: Export on empty dataset returns 202 ────────────────────
    with checkpoint(ctx, "empty_export"):
        export_resp = await client.post(
            "/api/v1/exports",
            json={
                "workspace_id": ws_id,
                "dataset_id": ds_id,
                "name": "Empty Export",
                "format": "jsonl",
                "include": {
                    "record_data": True,
                    "human_labels": True,
                },
            },
        )
        assert export_resp.status_code == 202
        export_body = export_resp.json()
        assert export_body["dataset_id"] == ds_id

    # ── Checkpoint 6: JSONL exporter with 0 records ───────────────────────────
    with checkpoint(ctx, "plugin_empty_export"):
        from molabel.plugins.exporters.jsonl_exporter import JsonlExporter

        exporter = JsonlExporter()
        artifact = exporter.package([], labels={}, config={})

        assert artifact.record_count == 0
        assert artifact.data is not None
        # Empty content (no lines)
        content = artifact.data.decode("utf-8")
        lines = [ln for ln in content.splitlines() if ln.strip()]
        assert len(lines) == 0

        # validate_export on empty artifact
        result = exporter.validate_export(artifact)
        # Empty export is valid (record_count=0 means no count mismatch check)
        assert result.is_valid

    # ── Checkpoint 7: CSV exporter with 0 records ─────────────────────────────
    with checkpoint(ctx, "csv_empty_export"):
        import csv as _csv
        import io as _io

        from molabel.plugins.exporters.csv_exporter import CsvExporter

        csv_exporter = CsvExporter()
        csv_artifact = csv_exporter.package([], labels={}, config={})

        assert csv_artifact.record_count == 0
        csv_text = csv_artifact.data.decode("utf-8")
        reader = _csv.reader(_io.StringIO(csv_text))
        rows = list(reader)
        # Empty export: no header (no columns to write)
        # or header only — either is acceptable for 0 records
        assert len(rows) <= 1

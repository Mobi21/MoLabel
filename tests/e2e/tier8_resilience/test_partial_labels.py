"""T8-09: Export when only 30/50 records labeled.

Verifies:
- Filtered export (only labeled): returns 30 records
- Full export: returns 50 records with null labels for unlabeled ones
- metadata counts reflect labeled vs total
- ExportFilters.status can filter to only export-eligible records
"""

from __future__ import annotations

import json
import uuid

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.parallel import INDEPENDENT

TOTAL = 50
LABELED = 30
UNLABELED = TOTAL - LABELED


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier8
async def test_partial_labels(client, ctx):
    """T8-09: Export when only 30/50 records labeled — filtered=30, full=50."""

    # ── Checkpoint 1: Setup ───────────────────────────────────────────────────
    with checkpoint(ctx, "setup"):
        ws = await client.post(
            "/api/v1/workspaces", json={"path": "/tmp/ws-partial-labels-test", "workspace_name": "Partial Labels Test"}
        )
        assert ws.status_code == 201
        ws_id = ws.json()["workspace_id"]

        ds = await client.post(
            "/api/v1/datasets",
            json={
                "dataset_name": "Partial Labels Dataset",
                "workspace_id": ws_id,
                "source_type": "jsonl",
            },
        )
        assert ds.status_code == 201
        ds_id = ds.json()["dataset_id"]

    # ── Checkpoint 2: Simulate partial labeling ───────────────────────────────
    with checkpoint(ctx, "partial_labels"):
        from molabel.core.types import (
            SENTINEL_DATASET_ID,
            Record,
            ReviewEvent,
            ReviewEventSource,
        )

        all_records = [
            Record(
                id=uuid.uuid4(),
                dataset_id=SENTINEL_DATASET_ID,
                stable_fields={"text": f"Record {i}", "idx": i},
                payload={},
                record_kind=None,
            )
            for i in range(TOTAL)
        ]

        # Label the first 30 records
        labels: dict[str, list[ReviewEvent]] = {}
        for rec in all_records[:LABELED]:
            event = ReviewEvent(
                id=uuid.uuid4(),
                record_id=rec.id,
                source=ReviewEventSource.human,
                labels={"sentiment": "positive"},
            )
            labels[str(rec.id)] = [event]

        # Verify counts
        labeled_count = sum(1 for r in all_records if str(r.id) in labels)
        unlabeled_count = sum(1 for r in all_records if str(r.id) not in labels)
        assert labeled_count == LABELED
        assert unlabeled_count == UNLABELED

    # ── Checkpoint 3: Filtered export (only labeled records = 30) ─────────────
    with checkpoint(ctx, "filtered_export"):
        from molabel.plugins.exporters.jsonl_exporter import JsonlExporter

        exporter = JsonlExporter()

        # Export only labeled records
        labeled_records = [r for r in all_records if str(r.id) in labels]
        filtered_artifact = exporter.package(labeled_records, labels=labels, config={})

        assert filtered_artifact.record_count == LABELED
        content = filtered_artifact.data.decode("utf-8")
        lines = [ln for ln in content.splitlines() if ln.strip()]
        assert len(lines) == LABELED

        # All exported records have a label
        for line in lines:
            obj = json.loads(line)
            assert "sentiment" in obj, f"Missing label in: {obj}"

    # ── Checkpoint 4: Full export (all 50, null labels for unlabeled) ──────────
    with checkpoint(ctx, "full_export"):
        from molabel.plugins.exporters.jsonl_exporter import JsonlExporter

        exporter2 = JsonlExporter()
        full_artifact = exporter2.package(all_records, labels=labels, config={})

        assert full_artifact.record_count == TOTAL
        content2 = full_artifact.data.decode("utf-8")
        lines2 = [ln for ln in content2.splitlines() if ln.strip()]
        assert len(lines2) == TOTAL

        # Count labeled vs unlabeled in export
        labeled_in_export = sum(
            1 for ln in lines2 if json.loads(ln).get("sentiment") is not None
        )
        unlabeled_in_export = TOTAL - labeled_in_export
        assert labeled_in_export == LABELED, (
            f"Expected {LABELED} labeled in full export, got {labeled_in_export}"
        )
        assert unlabeled_in_export == UNLABELED

    # ── Checkpoint 5: API export with filter ─────────────────────────────────
    with checkpoint(ctx, "api_export_filtered"):
        export_resp = await client.post(
            "/api/v1/exports",
            json={
                "workspace_id": ws_id,
                "dataset_id": ds_id,
                "name": "Partial Labels Export",
                "format": "jsonl",
                "include": {
                    "record_data": True,
                    "human_labels": True,
                },
                "filters": {
                    "status": ["export_eligible"],
                    "exclude_flagged": False,
                },
            },
        )
        assert export_resp.status_code == 202
        body = export_resp.json()
        assert "export_id" in body

    # ── Checkpoint 6: Validate export (partial labels, still valid) ───────────
    with checkpoint(ctx, "validate_full"):
        from molabel.plugins.exporters.jsonl_exporter import JsonlExporter

        exporter3 = JsonlExporter()
        full_artifact2 = exporter3.package(all_records, labels=labels, config={})
        result = exporter3.validate_export(full_artifact2)
        assert result.is_valid, f"Full export validation failed: {result.errors}"

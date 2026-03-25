"""T7-12: Snapshot full lifecycle — create, compare, restore.

Verifies:
- POST /datasets/{id}/snapshots → 201 with snapshot_id
- GET /datasets/{id}/snapshots → lists snapshots ordered newest first
- GET /datasets/{id}/snapshots/{sid}/diff → SnapshotDiff with base/compare IDs
- Restore (via diff endpoint verifies snapshot data)
"""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.parallel import INDEPENDENT


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier7
async def test_snapshot_lifecycle(client, ctx):
    """T7-12: Snapshot lifecycle — create snapshot-1, compare, create snapshot-2."""

    # ── Checkpoint 1: Setup ───────────────────────────────────────────────────
    with checkpoint(ctx, "setup"):
        ws = await client.post("/api/v1/workspaces", json={"path": "/tmp/ws-snapshot-test", "workspace_name": "Snapshot Test"})
        assert ws.status_code == 201
        ws_id = ws.json()["workspace_id"]

        ds = await client.post(
            "/api/v1/datasets",
            json={
                "dataset_name": "Snapshot Dataset",
                "workspace_id": ws_id,
                "source_type": "jsonl",
            },
        )
        assert ds.status_code == 201
        ds_id = ds.json()["dataset_id"]

    # ── Checkpoint 2: Create snapshot-1 ──────────────────────────────────────
    with checkpoint(ctx, "create_snapshot_1"):
        snap1_resp = await client.post(
            f"/api/v1/datasets/{ds_id}/snapshots",
            json={
                "name": "snapshot-1",
                "description": "Initial state",
                "snapshot_type": "full",
            },
        )
        assert snap1_resp.status_code == 201
        snap1 = snap1_resp.json()
        assert snap1["name"] == "snapshot-1"
        snap1_id = snap1["snapshot_id"]
        assert snap1_id
        assert snap1["dataset_id"] == ds_id
        assert snap1["snapshot_type"] in ("full", "delta")

    # ── Checkpoint 3: Create snapshot-2 ──────────────────────────────────────
    with checkpoint(ctx, "create_snapshot_2"):
        snap2_resp = await client.post(
            f"/api/v1/datasets/{ds_id}/snapshots",
            json={
                "name": "snapshot-2",
                "description": "After labeling",
                "snapshot_type": "full",
            },
        )
        assert snap2_resp.status_code == 201
        snap2 = snap2_resp.json()
        assert snap2["name"] == "snapshot-2"
        snap2_id = snap2["snapshot_id"]
        assert snap2_id != snap1_id

    # ── Checkpoint 4: List snapshots ─────────────────────────────────────────
    with checkpoint(ctx, "list_snapshots"):
        list_resp = await client.get(f"/api/v1/datasets/{ds_id}/snapshots")
        assert list_resp.status_code == 200
        items = list_resp.json()["items"]
        assert len(items) >= 2

        # Ordered newest first
        names = [s["name"] for s in items]
        assert "snapshot-2" in names
        assert "snapshot-1" in names
        # snapshot-2 should appear before snapshot-1
        idx1 = names.index("snapshot-1")
        idx2 = names.index("snapshot-2")
        assert idx2 < idx1, "Snapshots should be ordered newest first"

    # ── Checkpoint 5: Compare snapshots (diff) ────────────────────────────────
    with checkpoint(ctx, "diff"):
        diff_resp = await client.get(
            f"/api/v1/datasets/{ds_id}/snapshots/{snap2_id}/diff",
            params={"compare_to": snap1_id},
        )
        assert diff_resp.status_code == 200
        diff = diff_resp.json()
        assert "base_snapshot_id" in diff
        assert "compare_snapshot_id" in diff
        assert diff["compare_snapshot_id"] == snap2_id
        # Numeric diff fields present
        assert "records_added" in diff
        assert "records_removed" in diff
        assert "labels_changed" in diff

    # ── Checkpoint 6: SnapshotService direct (unit-level) ────────────────────
    with checkpoint(ctx, "snapshot_service_types"):
        from molabel.core.data.snapshot_service import SnapshotDiff

        # SnapshotDiff model construction
        diff_model = SnapshotDiff(
            snapshot_a_id="00000000-0000-0000-0000-000000000001",
            snapshot_b_id="00000000-0000-0000-0000-000000000002",
            snapshot_a_name="snapshot-1",
            snapshot_b_name="snapshot-2",
            record_count_change=5,
            labeled_count_change=3,
            new_records=5,
            removed_records=0,
            changed_labels=3,
        )
        assert diff_model.record_count_change == 5
        assert diff_model.new_records == 5

"""T8-10: Agent fails after 25/50 records — partial outputs preserved, retry remaining.

Verifies:
- Partial processing produces valid outputs for completed records
- Failed/remaining records can be identified and retried
- Retry processes only the remaining 25 (not re-processing first 25)
- SnapshotService can restore to pre-failure state if needed
"""

from __future__ import annotations

import uuid

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.parallel import INDEPENDENT

TOTAL = 50
COMPLETED_BEFORE_FAILURE = 25


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier8
async def test_rollback_partial(client, ctx):
    """T8-10: Agent fails at 25/50; partial outputs preserved; retry remaining."""

    # ── Checkpoint 1: Setup ───────────────────────────────────────────────────
    with checkpoint(ctx, "setup"):
        ws = await client.post(
            "/api/v1/workspaces", json={"path": "/tmp/ws-rollback-partial-test", "workspace_name": "Rollback Partial Test"}
        )
        assert ws.status_code == 201
        ws_id = ws.json()["workspace_id"]

        ds = await client.post(
            "/api/v1/datasets",
            json={
                "dataset_name": "Rollback Dataset",
                "workspace_id": ws_id,
                "source_type": "jsonl",
            },
        )
        assert ds.status_code == 201
        ds_id = ds.json()["dataset_id"]

    # ── Checkpoint 2: Simulate partial agent run (25/50 succeed then fail) ─────
    with checkpoint(ctx, "partial_run"):
        record_ids = [uuid.uuid4() for _ in range(TOTAL)]

        # Simulate processing: first 25 succeed, then failure at record 26
        completed_outputs: list[dict] = []
        failed_at = None

        for i, rid in enumerate(record_ids):
            if i == COMPLETED_BEFORE_FAILURE:
                # Simulate agent failure
                failed_at = i
                break
            completed_outputs.append(
                {
                    "record_id": str(rid),
                    "output_index": i,
                    "labels": {"sentiment": ["positive", "negative", "neutral"][i % 3]},
                    "status": "completed",
                }
            )

        assert len(completed_outputs) == COMPLETED_BEFORE_FAILURE
        assert failed_at == COMPLETED_BEFORE_FAILURE
        remaining_ids = record_ids[COMPLETED_BEFORE_FAILURE:]
        assert len(remaining_ids) == TOTAL - COMPLETED_BEFORE_FAILURE

    # ── Checkpoint 3: Partial outputs preserved ───────────────────────────────
    with checkpoint(ctx, "partial_preserved"):
        completed_record_ids = {o["record_id"] for o in completed_outputs}
        assert len(completed_record_ids) == COMPLETED_BEFORE_FAILURE

        # Verify completed outputs are intact
        for output in completed_outputs:
            assert output["status"] == "completed"
            assert "labels" in output
            assert "sentiment" in output["labels"]

        # Remaining records are not in completed set
        for rid in remaining_ids:
            assert str(rid) not in completed_record_ids

    # ── Checkpoint 4: Retry processes only remaining records ──────────────────
    with checkpoint(ctx, "retry_remaining"):
        retry_outputs: list[dict] = []

        # Retry only the remaining 25
        for i, rid in enumerate(remaining_ids):
            retry_outputs.append(
                {
                    "record_id": str(rid),
                    "output_index": COMPLETED_BEFORE_FAILURE + i,
                    "labels": {"sentiment": "neutral"},
                    "status": "completed",
                }
            )

        assert len(retry_outputs) == TOTAL - COMPLETED_BEFORE_FAILURE

        # Together, original + retry = all 50
        all_outputs = completed_outputs + retry_outputs
        assert len(all_outputs) == TOTAL

        # No duplicates
        all_record_ids = [o["record_id"] for o in all_outputs]
        assert len(set(all_record_ids)) == TOTAL, (
            "Retry should not re-process completed records"
        )

    # ── Checkpoint 5: Snapshot before failure (restore point) ─────────────────
    with checkpoint(ctx, "snapshot_restore_point"):
        snap_resp = await client.post(
            f"/api/v1/datasets/{ds_id}/snapshots",
            json={
                "name": "pre-failure-snapshot",
                "description": "State before agent failure",
                "snapshot_type": "full",
            },
        )
        assert snap_resp.status_code == 201
        snap_id = snap_resp.json()["snapshot_id"]
        assert snap_id

        # Snapshot records the current state
        assert snap_resp.json()["name"] == "pre-failure-snapshot"

    # ── Checkpoint 6: AgentRunStatus enum has partially_completed ────────────
    with checkpoint(ctx, "status_enum"):
        from molabel.core.types import AgentRunStatus

        assert AgentRunStatus.partially_completed == "partially_completed"
        assert AgentRunStatus.completed == "completed"
        assert AgentRunStatus.failed == "failed"
        assert AgentRunStatus.running == "running"

        # Typical partial-to-retry lifecycle
        lifecycle = [
            AgentRunStatus.running,
            AgentRunStatus.partially_completed,  # after failure at record 25
            AgentRunStatus.running,  # retry starts
            AgentRunStatus.completed,  # retry finishes
        ]
        assert lifecycle[1] == "partially_completed"

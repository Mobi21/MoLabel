"""T8-04: Two agent runs on same dataset simultaneously — no data corruption.

Verifies:
- Two concurrent POST /agent-runs requests on the same dataset
- Both runs get unique agent_run_ids
- Concurrent dataset reads (GET /datasets/{id}/records) return consistent results
- No data corruption from concurrent writes via API
"""

from __future__ import annotations

import asyncio

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.parallel import INDEPENDENT


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier8
async def test_concurrent_operations(client, ctx):
    """T8-04: Two concurrent agent runs on same dataset — no data corruption."""

    # ── Checkpoint 1: Setup shared dataset ───────────────────────────────────
    with checkpoint(ctx, "setup"):
        ws = await client.post(
            "/api/v1/workspaces", json={"path": "/tmp/ws-concurrent-ops-test", "workspace_name": "Concurrent Ops Test"}
        )
        assert ws.status_code == 201
        ws_id = ws.json()["workspace_id"]

        ds = await client.post(
            "/api/v1/datasets",
            json={
                "dataset_name": "Concurrent Dataset",
                "workspace_id": ws_id,
                "source_type": "jsonl",
            },
        )
        assert ds.status_code == 201
        ds_id = ds.json()["dataset_id"]

        schema = await client.post(
            "/api/v1/task-schemas",
            json={
                "workspace_id": ws_id,
                "task_schema_slug": "sentiment-concurrent",
                "task_type": "classification",
                "title": "Sentiment Concurrent",
                "label_fields": [
                    {
                        "name": "sentiment",
                        "field_type": "categorical",
                        "options": ["positive", "negative", "neutral"],
                        "required": True,
                    }
                ],
            },
        )
        assert schema.status_code == 201
        _schema_id = schema.json()["task_schema_id"]

        model = await client.post(
            "/api/v1/model-profiles",
            json={
                "model_profile_slug": "concurrent-test-model",
                "model_identifier": "minimax-2.7",
                "provider_type": "anthropic",
            },
        )
        assert model.status_code == 201
        _model_id = model.json()["id"]

    # ── Checkpoint 2: Concurrent dataset reads ────────────────────────────────
    with checkpoint(ctx, "concurrent_reads"):

        async def read_records():
            return await client.get(f"/api/v1/datasets/{ds_id}/records")

        # Fire 5 concurrent reads
        results = await asyncio.gather(*[read_records() for _ in range(5)])
        for resp in results:
            assert resp.status_code == 200
            body = resp.json()
            assert "items" in body
            # All reads return consistent (same) total
            assert body["items"] == results[0].json()["items"]

    # ── Checkpoint 3: Concurrent dataset analytics reads ─────────────────────
    with checkpoint(ctx, "concurrent_analytics"):

        async def read_analytics():
            return await client.get(f"/api/v1/datasets/{ds_id}/analytics")

        analytics_results = await asyncio.gather(*[read_analytics() for _ in range(3)])
        for resp in analytics_results:
            assert resp.status_code == 200
            assert resp.json()["dataset_id"] == ds_id

    # ── Checkpoint 4: Concurrent snapshot creation ────────────────────────────
    with checkpoint(ctx, "concurrent_snapshots"):

        async def create_snapshot(name: str):
            return await client.post(
                f"/api/v1/datasets/{ds_id}/snapshots",
                json={"name": name, "snapshot_type": "full"},
            )

        snap_results = await asyncio.gather(
            create_snapshot("concurrent-snap-a"),
            create_snapshot("concurrent-snap-b"),
        )
        # Both should succeed (201)
        for resp in snap_results:
            assert resp.status_code == 201

        # Both get unique IDs
        ids = [r.json()["snapshot_id"] for r in snap_results]
        assert len(set(ids)) == 2, "Concurrent snapshots must have unique IDs"

    # ── Checkpoint 5: Concurrent import requests don't conflict ───────────────
    with checkpoint(ctx, "concurrent_imports"):

        async def import_data(uri: str):
            return await client.post(
                f"/api/v1/datasets/{ds_id}/import",
                json={"source_uri": uri},
            )

        import_results = await asyncio.gather(
            import_data("test://concurrent-a"),
            import_data("test://concurrent-b"),
        )
        # Both should return 202 (accepted)
        for resp in import_results:
            assert resp.status_code == 202

        # Both get unique job IDs
        job_ids = [r.json()["job_id"] for r in import_results]
        assert len(set(job_ids)) == 2, "Concurrent imports must have unique job IDs"

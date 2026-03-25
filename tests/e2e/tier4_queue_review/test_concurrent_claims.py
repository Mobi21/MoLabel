"""Concurrent claims atomicity test (T4-07).

Two reviewers claim from the same queue simultaneously.
Only one should succeed due to atomic UPDATE...WHERE SELECT LIMIT 1.
"""

from __future__ import annotations

import asyncio

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SEQUENTIAL


@SEQUENTIAL
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier4
async def test_concurrent_claims_only_one_succeeds(
    ctx: TestContext,
    client: InstrumentedClient,
) -> None:
    """T4-07: Two reviewers claim simultaneously; only one gets the task.

    Uses asyncio.gather() to fire both claim requests concurrently.
    Exactly one response should have queue_empty=False; the other sees
    queue_empty=True (since there is only 1 task in the queue).
    """
    with checkpoint(ctx, "workspace_and_single_task_setup"):
        ws_resp = await client.post(
            "/workspaces", json={"workspace_name": "concurrent-claims-ws"}
        )
        assert ws_resp.status_code == 201
        ws_id = ws_resp.json()["workspace_id"]

        ds_resp = await client.post(
            "/datasets",
            json={
                "workspace_id": ws_id,
                "dataset_name": "concurrent-ds",
                "text_field": "text",
            },
        )
        assert ds_resp.status_code == 201
        ds_id = ds_resp.json()["dataset_id"]

        # Import exactly ONE record so only one claim can win
        import_resp = await client.post(
            f"/datasets/{ds_id}/import",
            json={
                "source_type": "jsonl",
                "records": [{"text": "The sole record for concurrent claim testing."}],
                "text_field": "text",
            },
        )
        assert import_resp.status_code in (200, 201, 202)

        schema_resp = await client.post(
            "/task-schemas",
            json={
                "workspace_id": ws_id,
                "task_slug": "concurrent-claim",
                "task_type": "classification",
                "label_fields": [
                    {
                        "name": "label",
                        "field_type": "categorical",
                        "options": ["yes", "no"],
                        "required": True,
                    }
                ],
            },
        )
        assert schema_resp.status_code == 201
        schema_id = schema_resp.json()["task_schema_id"]

        queue_resp = await client.post(
            "/queues",
            json={
                "workspace_id": ws_id,
                "dataset_id": ds_id,
                "task_schema_id": schema_id,
                "queue_name": "concurrent-queue",
            },
        )
        assert queue_resp.status_code == 201
        queue_id = queue_resp.json()["queue_id"]

    with checkpoint(ctx, "simultaneous_claims"):
        # Both reviewers claim at the same time
        resp_a, resp_b = await asyncio.gather(
            client.post(f"/queues/{queue_id}/claim"),
            client.post(f"/queues/{queue_id}/claim"),
        )
        assert resp_a.status_code == 200
        assert resp_b.status_code == 200

        body_a = resp_a.json()
        body_b = resp_b.json()

    with checkpoint(ctx, "only_one_winner"):
        claimed_count = sum(
            1 for body in (body_a, body_b) if not body.get("queue_empty")
        )
        empty_count = sum(1 for body in (body_a, body_b) if body.get("queue_empty"))
        # Exactly one should have claimed, one should see empty queue
        assert claimed_count == 1, (
            f"Expected exactly 1 winner but got {claimed_count}. "
            f"body_a={body_a}, body_b={body_b}"
        )
        assert empty_count == 1, (
            f"Expected exactly 1 queue_empty but got {empty_count}."
        )

    with checkpoint(ctx, "cleanup_winner_task"):
        # Clean up the winning claim
        winner_body = body_a if not body_a.get("queue_empty") else body_b
        task_id = winner_body["task"]["id"]
        cleanup = await client.post(
            f"/review-tasks/{task_id}/submit",
            json={
                "labels": {"label": "yes"},
                "decision": "accept",
                "auto_claim_next": False,
            },
        )
        assert cleanup.status_code in (200, 409)

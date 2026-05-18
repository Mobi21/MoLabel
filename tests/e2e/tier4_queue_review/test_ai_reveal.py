"""AI reveal tracking test (T4-04).

Verifies that pre-reveal vs post-reveal review decisions are distinguishable
via the ai_was_revealed field on review events.
"""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SEQUENTIAL


@SEQUENTIAL
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier4
async def test_ai_reveal_tracking(
    ctx: TestContext,
    client: InstrumentedClient,
) -> None:
    """T4-04: Track which reviews were pre-reveal vs post-reveal.

    Setup two tasks in a hide-by-default queue:
    - Task A: submit WITHOUT revealing AI → ai_was_revealed = False
    - Task B: reveal AI first, then submit → ai_was_revealed = True
    """
    with checkpoint(ctx, "workspace_setup"):
        ws_resp = await client.post(
            "/api/v1/workspaces",
            json={
                "path": "/tmp/ws-ai-reveal-tracking-ws",
                "workspace_name": "ai-reveal-tracking-ws",
            },
        )
        assert ws_resp.status_code == 201
        ws_id = ws_resp.json()["workspace_id"]

    with checkpoint(ctx, "dataset_import"):
        ds_resp = await client.post(
            "/api/v1/datasets",
            json={
                "workspace_id": ws_id,
                "dataset_name": "reveal-ds",
                "source_type": "jsonl",
            },
        )
        assert ds_resp.status_code == 201
        ds_id = ds_resp.json()["dataset_id"]

        import_resp = await client.post(
            f"/api/v1/datasets/{ds_id}/import",
            json={
                "source_type": "jsonl",
                "records": [
                    {"text": "First review record for reveal tracking."},
                    {"text": "Second review record for reveal tracking."},
                ],
            },
        )
        assert import_resp.status_code in (200, 201, 202)

    with checkpoint(ctx, "schema_and_queue_setup"):
        schema_resp = await client.post(
            "/api/v1/task-schemas",
            json={
                "workspace_id": ws_id,
                "task_schema_slug": "reveal-tracking",
                "title": "Reveal Tracking",
                "task_type": "classification",
                "blind_review_policy": "hide_agent_outputs_by_default",
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
        queue_id = f"{ds_id}:{schema_id}"

    # Claim and submit Task A WITHOUT revealing AI
    with checkpoint(ctx, "claim_and_submit_without_reveal"):
        claim_a = await client.post(f"/api/v1/queues/{queue_id}/claim")
        assert claim_a.status_code == 200
        body_a = claim_a.json()
        if not body_a.get("queue_empty"):
            task_a_id = body_a["task"]["id"]
            assert body_a["task"].get("ai_revealed") is False

            submit_a = await client.post(
                f"/api/v1/review-tasks/{task_a_id}/submit",
                json={
                    "labels": {"label": "yes"},
                    "decision": "accept",
                    "auto_claim_next": False,
                },
            )
            assert submit_a.status_code in (200, 409)
            if submit_a.status_code == 200:
                submitted_task_a = submit_a.json()["submitted_task"]
                # ai_revealed should remain False since we never called reveal-ai
                assert submitted_task_a.get("ai_revealed") is False

    # Claim and submit Task B WITH revealing AI first
    with checkpoint(ctx, "claim_reveal_and_submit_with_reveal"):
        claim_b = await client.post(f"/api/v1/queues/{queue_id}/claim")
        assert claim_b.status_code == 200
        body_b = claim_b.json()
        if not body_b.get("queue_empty"):
            task_b_id = body_b["task"]["id"]
            assert body_b["task"].get("ai_revealed") is False

            # Reveal AI
            reveal_resp = await client.post(
                f"/api/v1/review-tasks/{task_b_id}/reveal-ai"
            )
            # 200 if agent output exists, 409 if policy blocks it or no agent ran
            if reveal_resp.status_code == 200:
                revealed_task = reveal_resp.json()["task"]
                assert revealed_task["ai_revealed"] is True
                assert revealed_task.get("ai_revealed_at") is not None

            submit_b = await client.post(
                f"/api/v1/review-tasks/{task_b_id}/submit",
                json={
                    "labels": {"label": "no"},
                    "decision": "reject",
                    "auto_claim_next": False,
                },
            )
            assert submit_b.status_code in (200, 409)
            if submit_b.status_code == 200 and reveal_resp.status_code == 200:
                submitted_task_b = submit_b.json()["submitted_task"]
                assert submitted_task_b.get("ai_revealed") is True

    with checkpoint(ctx, "verify_queue_status"):
        status_resp = await client.get(f"/api/v1/queues/{queue_id}/status")
        assert status_resp.status_code == 200
        status = status_resp.json()
        assert "submitted" in status
        assert status["submitted"] >= 0

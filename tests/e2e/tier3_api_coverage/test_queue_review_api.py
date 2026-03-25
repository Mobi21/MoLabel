"""Tier 3 — API Coverage: Queue & Review (T3-10).

Tests:
    T3-10: claim, submit, skip, draft, reveal-ai, release, correct,
           status, mission-control
"""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SHARED_WORKSPACE

BASE = "/api/v1"


async def _setup(client: InstrumentedClient) -> tuple[str, str]:
    """Return (reviewer_id, queue_id) after login and DB seeding."""
    rp = await client.post(
        f"{BASE}/reviewer-profiles",
        json={
            "display_name": "Queue Reviewer",
            "workspace_id": "00000000-0000-0000-0000-000000000001",
        },
    )
    assert rp.status_code == 201
    reviewer_id = rp.json()["id"]
    login = await client.post(f"{BASE}/sessions", json={"reviewer_id": reviewer_id})
    assert login.status_code == 200
    client._session_cookie = login.cookies.get("molabel_session")

    # Use a synthetic queue_id — the endpoints work on whatever queue_id is given
    queue_id = "00000000-0000-0000-0000-000000000001"
    return reviewer_id, queue_id


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier3
async def test_queue_all_claim_operations(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T3-10: All queue claim operations (claim returns queue_empty when no tasks)."""

    reviewer_id, queue_id = await _setup(client)

    with checkpoint(ctx, "claim_empty_queue"):
        resp = await client.post(f"{BASE}/queues/{queue_id}/claim")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # Queue is empty since we haven't seeded any tasks
        assert body["queue_empty"] is True or body.get("message") in (
            "queue_empty",
            "claimed",
        )

    with checkpoint(ctx, "queue_status"):
        resp = await client.get(f"{BASE}/queues/{queue_id}/status")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["queue_id"] == queue_id
        assert "total" in body
        assert "available" in body
        assert "active_reviewers" in body

    with checkpoint(ctx, "mission_control"):
        resp = await client.get(f"{BASE}/mission-control/reviewers")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "reviewers" in body

    # Simulate claim operations on a non-existent task — expect 409
    fake_task_id = "00000000-0000-0000-0000-aabbccdd0001"

    with checkpoint(ctx, "submit_nonexistent"):
        resp = await client.post(
            f"{BASE}/review-tasks/{fake_task_id}/submit",
            json={"labels": {"sentiment": "positive"}, "decision": "accept"},
        )
        assert resp.status_code == 409, resp.text

    with checkpoint(ctx, "skip_nonexistent"):
        resp = await client.post(f"{BASE}/review-tasks/{fake_task_id}/skip")
        assert resp.status_code == 409, resp.text

    with checkpoint(ctx, "release_nonexistent"):
        resp = await client.post(f"{BASE}/review-tasks/{fake_task_id}/release")
        assert resp.status_code == 409, resp.text

    with checkpoint(ctx, "draft_nonexistent"):
        resp = await client.post(
            f"{BASE}/review-tasks/{fake_task_id}/draft",
            json={"draft_labels": {"sentiment": "neutral"}},
        )
        assert resp.status_code == 409, resp.text

    with checkpoint(ctx, "reveal_ai_nonexistent"):
        resp = await client.post(f"{BASE}/review-tasks/{fake_task_id}/reveal-ai")
        assert resp.status_code == 409, resp.text

    with checkpoint(ctx, "correct_nonexistent"):
        resp = await client.post(
            f"{BASE}/review-tasks/{fake_task_id}/correct",
            json={"labels": {"sentiment": "negative"}, "rationale": "Correcting label"},
        )
        assert resp.status_code == 409, resp.text

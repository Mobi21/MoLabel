"""Adjudication flow test (T4-10).

Two conflicting reviews → detect disagreements → build adjudication queue
→ resolve with canonical label.
"""

from __future__ import annotations

import uuid

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SEQUENTIAL


@SEQUENTIAL
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier4
async def test_adjudication_flow_detect_build_resolve(
    ctx: TestContext,
    client: InstrumentedClient,
) -> None:
    """T4-10: Two conflicting reviews → detect → build queue → resolve.

    Uses the adjudication endpoints in queue.py:
    - POST /adjudication/detect
    - POST /adjudication/queue/build
    - POST /adjudication/resolve
    """
    with checkpoint(ctx, "session_setup"):
        await client.login("adjudicator-t4-10")

    # Prepare two conflicting review events for the same record
    record_id = str(uuid.uuid4())
    task_schema_id = str(uuid.uuid4())

    conflicting_events = [
        {
            "review_event_id": str(uuid.uuid4()),
            "reviewer_id": str(uuid.uuid4()),
            "labels": {"sentiment": "positive"},
            "decision": "accept",
            "source": "human",
        },
        {
            "review_event_id": str(uuid.uuid4()),
            "reviewer_id": str(uuid.uuid4()),
            "labels": {"sentiment": "negative"},
            "decision": "accept",
            "source": "human",
        },
    ]

    with checkpoint(ctx, "detect_disagreements"):
        detect_resp = await client.post(
            "/adjudication/detect",
            json={
                "review_events_by_record": {record_id: conflicting_events},
                "task_schema_id": task_schema_id,
            },
        )
        assert detect_resp.status_code == 200
        detect_body = detect_resp.json()
        assert "disagreements" in detect_body
        assert "total" in detect_body
        assert detect_body["total"] >= 1

        disagreements = detect_body["disagreements"]
        assert len(disagreements) >= 1
        first_disagreement = disagreements[0]
        assert first_disagreement["record_id"] == record_id
        assert "disagreement_type" in first_disagreement
        assert "fields_in_conflict" in first_disagreement

    with checkpoint(ctx, "build_adjudication_queue"):
        build_resp = await client.post(
            "/adjudication/queue/build",
            json={
                "review_events_by_record": {record_id: conflicting_events},
                "task_schema_id": task_schema_id,
            },
        )
        assert build_resp.status_code == 200
        build_body = build_resp.json()
        assert "items" in build_body
        assert build_body["total"] >= 1
        assert build_body["unresolved"] >= 1

        queue_items = build_body["items"]
        assert len(queue_items) >= 1
        queue_item = queue_items[0]
        assert "id" in queue_item
        assert "severity" in queue_item
        queue_item_id = queue_item["id"]

    with checkpoint(ctx, "get_adjudication_queue"):
        get_queue_resp = await client.get("/adjudication/queue")
        assert get_queue_resp.status_code == 200
        queue_body = get_queue_resp.json()
        assert "items" in queue_body
        assert "total" in queue_body

    with checkpoint(ctx, "resolve_adjudication"):
        resolve_resp = await client.post(
            "/adjudication/resolve",
            json={
                "queue_item_id": queue_item_id,
                "resolution": "resolve",
                "resolved_labels": {"sentiment": "positive"},
                "rationale": "Reviewer A's label matches the context better.",
            },
        )
        assert resolve_resp.status_code == 200
        resolve_body = resolve_resp.json()
        assert resolve_body["message"] == "resolved"
        assert resolve_body["resolution"] == "resolve"
        assert resolve_body["record_id"] == record_id
        assert resolve_body["resolved_labels"] == {"sentiment": "positive"}
        assert resolve_body["rationale"] is not None

    with checkpoint(ctx, "verify_queue_after_resolution"):
        after_resp = await client.get("/adjudication/queue")
        assert after_resp.status_code == 200
        after_body = after_resp.json()
        # Resolved item should not appear in unresolved count
        assert (
            after_body["unresolved"] == 0
            or after_body["unresolved"] < build_body["unresolved"]
        )

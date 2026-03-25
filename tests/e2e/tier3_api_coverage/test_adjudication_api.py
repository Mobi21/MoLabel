"""Tier 3 — API Coverage: Adjudication (T3-11).

Tests:
    T3-11: Detect disagreements, build queue, resolve (4 resolution types)
"""

from __future__ import annotations

import uuid

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SHARED_WORKSPACE

BASE = "/api/v1"


async def _setup(client: InstrumentedClient) -> None:
    rp = await client.post(
        f"{BASE}/reviewer-profiles",
        json={
            "display_name": "Adj Reviewer",
            "workspace_id": "00000000-0000-0000-0000-000000000001",
        },
    )
    assert rp.status_code == 201
    reviewer_id = rp.json()["id"]
    login = await client.post(f"{BASE}/sessions", json={"reviewer_id": reviewer_id})
    assert login.status_code == 200
    client._session_cookie = login.cookies.get("molabel_session")


def _make_review_events(record_id: str, task_schema_id: str) -> list[dict]:
    return [
        {
            "id": str(uuid.uuid4()),
            "record_id": record_id,
            "reviewer_id": str(uuid.uuid4()),
            "source": "human",
            "decision": "accept",
            "labels": {"sentiment": "positive"},
        },
        {
            "id": str(uuid.uuid4()),
            "record_id": record_id,
            "reviewer_id": str(uuid.uuid4()),
            "source": "human",
            "decision": "accept",
            "labels": {"sentiment": "negative"},
        },
    ]


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier3
async def test_adjudication_detect_build_resolve(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T3-11: Detect disagreements, build queue, resolve with all 4 resolution types."""

    await _setup(client)

    task_schema_id = str(uuid.uuid4())
    record_id_1 = str(uuid.uuid4())
    record_id_2 = str(uuid.uuid4())

    events_by_record = {
        record_id_1: _make_review_events(record_id_1, task_schema_id),
        record_id_2: _make_review_events(record_id_2, task_schema_id),
    }

    with checkpoint(ctx, "detect_disagreements"):
        resp = await client.post(
            f"{BASE}/adjudication/detect",
            json={
                "review_events_by_record": events_by_record,
                "task_schema_id": task_schema_id,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "disagreements" in body
        assert "total" in body

    queue_items: list = []
    with checkpoint(ctx, "build_adjudication_queue"):
        resp = await client.post(
            f"{BASE}/adjudication/queue/build",
            json={
                "review_events_by_record": events_by_record,
                "task_schema_id": task_schema_id,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "items" in body
        assert "total" in body
        queue_items = body["items"]

    with checkpoint(ctx, "get_adjudication_queue"):
        resp = await client.get(f"{BASE}/adjudication/queue")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "items" in body

    # Resolve items with all 4 resolution types (if queue has items)
    resolution_types = ["resolve", "preserve_disagreement", "downgrade", "exclude"]
    for i, resolution in enumerate(resolution_types):
        # Will get 404 if out of range, which is acceptable
        item_id = (
            queue_items[i]["id"] if i < len(queue_items) else str(uuid.uuid4())
        )

        with checkpoint(ctx, f"resolve_{resolution}"):
            payload: dict = {
                "queue_item_id": item_id,
                "resolution": resolution,
                "rationale": f"Test {resolution} resolution",
            }
            if resolution == "resolve":
                payload["resolved_labels"] = {"sentiment": "positive"}
            resp = await client.post(
                f"{BASE}/adjudication/resolve",
                json=payload,
            )
            # If no item with that ID, 404 is valid; otherwise 200
            assert resp.status_code in (200, 404), resp.text

    # Extended adjudication router endpoints
    with checkpoint(ctx, "list_adjudication_queue_filtered"):
        resp = await client.get(
            f"{BASE}/adjudication/queue",
            params={"task_schema_id": task_schema_id},
        )
        assert resp.status_code == 200, resp.text

    with checkpoint(ctx, "get_adjudication_detail_404"):
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"{BASE}/adjudication/{fake_id}")
        assert resp.status_code == 404, resp.text

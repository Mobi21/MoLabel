"""Tier 3 — API Coverage: Review Events (T3-28).

Tests:
    T3-28: List at /api/v1/review/events with record_id, reviewer_id,
           is_draft filters
"""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SHARED_WORKSPACE

BASE = "/api/v1"


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier3
async def test_review_events_list_with_filters(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T3-28: List review events with all filter params."""

    # review/events does not require auth (no CurrentReviewer dep in list)
    with checkpoint(ctx, "list_review_events_unfiltered"):
        resp = await client.get(f"{BASE}/review/events")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "items" in body
        assert "has_more" in body
        # Empty initially
        assert isinstance(body["items"], list)

    with checkpoint(ctx, "filter_by_record_id"):
        resp = await client.get(
            f"{BASE}/review/events",
            params={"record_id": "00000000-0000-0000-0000-000000000001"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "items" in body

    with checkpoint(ctx, "filter_by_reviewer_id"):
        resp = await client.get(
            f"{BASE}/review/events",
            params={"reviewer_id": "00000000-0000-0000-0000-000000000001"},
        )
        assert resp.status_code == 200, resp.text

    with checkpoint(ctx, "filter_is_draft_true"):
        resp = await client.get(
            f"{BASE}/review/events",
            params={"is_draft": True},
        )
        assert resp.status_code == 200, resp.text

    with checkpoint(ctx, "filter_is_draft_false"):
        resp = await client.get(
            f"{BASE}/review/events",
            params={"is_draft": False},
        )
        assert resp.status_code == 200, resp.text

    with checkpoint(ctx, "filter_by_task_schema_id"):
        resp = await client.get(
            f"{BASE}/review/events",
            params={"task_schema_id": "00000000-0000-0000-0000-000000000001"},
        )
        assert resp.status_code == 200, resp.text

    with checkpoint(ctx, "filter_by_dataset_id"):
        resp = await client.get(
            f"{BASE}/review/events",
            params={"dataset_id": "00000000-0000-0000-0000-000000000001"},
        )
        assert resp.status_code == 200, resp.text

    with checkpoint(ctx, "combined_filters"):
        resp = await client.get(
            f"{BASE}/review/events",
            params={
                "record_id": "00000000-0000-0000-0000-000000000001",
                "reviewer_id": "00000000-0000-0000-0000-000000000001",
                "is_draft": False,
                "limit": 10,
            },
        )
        assert resp.status_code == 200, resp.text

    with checkpoint(ctx, "pagination"):
        resp = await client.get(f"{BASE}/review/events", params={"limit": 5})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["items"]) <= 5

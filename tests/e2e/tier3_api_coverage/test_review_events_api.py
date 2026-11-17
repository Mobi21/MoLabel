"""Tier 3 — API Coverage: Review Events (T3-28).

Tests:
    T3-28: List at /api/v1/review/events with record_id, reviewer_id,
           is_draft filters, in the session's workspace only
"""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SHARED_WORKSPACE

BASE = "/api/v1"
WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"
NO_ROW_ID = "00000000-0000-0000-0000-0000000000ff"


async def _login(client: InstrumentedClient) -> str:
    rp = await client.post(
        f"{BASE}/reviewer-profiles",
        json={"display_name": "Review Events Reviewer", "workspace_id": WORKSPACE_ID},
    )
    assert rp.status_code == 201, rp.text
    reviewer_id = rp.json()["id"]
    login = await client.post(f"{BASE}/sessions", json={"reviewer_id": reviewer_id})
    assert login.status_code == 200, login.text
    client._session_cookie = login.cookies.get("molabel_session")
    return reviewer_id


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier3
async def test_review_events_list_with_filters(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T3-28: List review events with all filter params."""

    with checkpoint(ctx, "list_review_events_needs_a_session"):
        resp = await client.get(f"{BASE}/review/events")
        assert resp.status_code == 401, resp.text

    reviewer_id = await _login(client)

    with checkpoint(ctx, "list_review_events_unfiltered"):
        resp = await client.get(f"{BASE}/review/events")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "items" in body
        assert "has_more" in body
        assert isinstance(body["items"], list)

    with checkpoint(ctx, "filter_by_reviewer_id"):
        resp = await client.get(
            f"{BASE}/review/events", params={"reviewer_id": reviewer_id}
        )
        assert resp.status_code == 200, resp.text

    with checkpoint(ctx, "filter_is_draft_true"):
        resp = await client.get(f"{BASE}/review/events", params={"is_draft": True})
        assert resp.status_code == 200, resp.text

    with checkpoint(ctx, "filter_is_draft_false"):
        resp = await client.get(f"{BASE}/review/events", params={"is_draft": False})
        assert resp.status_code == 200, resp.text

    for name in ("record_id", "task_schema_id", "dataset_id", "reviewer_id"):
        with checkpoint(ctx, f"filter_by_{name}_of_no_row_in_the_workspace"):
            resp = await client.get(f"{BASE}/review/events", params={name: NO_ROW_ID})
            assert resp.status_code == 404, resp.text

    with checkpoint(ctx, "combined_filters"):
        resp = await client.get(
            f"{BASE}/review/events",
            params={"reviewer_id": reviewer_id, "is_draft": False, "limit": 10},
        )
        assert resp.status_code == 200, resp.text

    with checkpoint(ctx, "pagination"):
        resp = await client.get(f"{BASE}/review/events", params={"limit": 5})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["items"]) <= 5

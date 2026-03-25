"""Tier 9 — Cross-Cutting: Pagination (T9-07).

Tests:
    T9-07: Paginate all list endpoints that return PaginatedResponse;
           verify schema consistency (items, cursor, has_more) and
           that limit parameter is respected.
"""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import INDEPENDENT

BASE = "/api/v1"
WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"


async def _setup(client: InstrumentedClient) -> str:
    rp = await client.post(
        f"{BASE}/reviewer-profiles",
        json={"display_name": "Pagination Reviewer", "workspace_id": WORKSPACE_ID},
    )
    assert rp.status_code == 201
    reviewer_id = rp.json()["id"]
    login = await client.post(f"{BASE}/sessions", json={"reviewer_id": reviewer_id})
    assert login.status_code == 200
    client._session_cookie = login.cookies.get("molabel_session")

    ws = await client.post(
        f"{BASE}/workspaces",
        json={"path": "/tmp/ws-pagination", "workspace_name": "Pagination WS"},
    )
    assert ws.status_code == 201
    return ws.json()["workspace_id"]


def _assert_paginated(body: dict, limit: int | None = None) -> None:
    """Assert PaginatedResponse schema and optional limit enforcement."""
    assert "items" in body, f"Missing 'items' in response: {body}"
    assert "has_more" in body, f"Missing 'has_more' in response: {body}"
    assert "cursor" in body, f"Missing 'cursor' in response: {body}"
    assert isinstance(body["items"], list), (
        f"'items' must be a list, got: {type(body['items'])}"
    )
    assert isinstance(body["has_more"], bool), (
        f"'has_more' must be bool, got: {type(body['has_more'])}"
    )
    if limit is not None:
        assert len(body["items"]) <= limit, (
            f"Expected at most {limit} items, got {len(body['items'])}"
        )


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier9
async def test_pagination(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T9-07: All paginated list endpoints return consistent PaginatedResponse schema.
    """

    workspace_id = await _setup(client)

    with checkpoint(ctx, "workspaces_pagination_schema"):
        resp = await client.get(f"{BASE}/workspaces", params={"limit": 5})
        assert resp.status_code == 200, resp.text
        _assert_paginated(resp.json(), limit=5)

    with checkpoint(ctx, "datasets_pagination_schema"):
        resp = await client.get(
            f"{BASE}/datasets",
            params={"workspace_id": workspace_id, "limit": 5},
        )
        assert resp.status_code == 200, resp.text
        _assert_paginated(resp.json(), limit=5)

    with checkpoint(ctx, "agent_runs_pagination_schema"):
        resp = await client.get(
            f"{BASE}/agent-runs",
            params={"workspace_id": workspace_id, "limit": 5},
        )
        assert resp.status_code == 200, resp.text
        _assert_paginated(resp.json(), limit=5)

    with checkpoint(ctx, "audit_pagination_schema"):
        resp = await client.get(
            f"{BASE}/audit",
            params={"workspace_id": workspace_id, "limit": 5},
        )
        assert resp.status_code == 200, resp.text
        _assert_paginated(resp.json(), limit=5)

    with checkpoint(ctx, "review_events_pagination_schema"):
        resp = await client.get(
            f"{BASE}/review/events",
            params={"limit": 5},
        )
        assert resp.status_code == 200, resp.text
        _assert_paginated(resp.json(), limit=5)

    with checkpoint(ctx, "exports_pagination_schema"):
        resp = await client.get(
            f"{BASE}/exports",
            params={"workspace_id": workspace_id, "limit": 5},
        )
        assert resp.status_code == 200, resp.text
        _assert_paginated(resp.json(), limit=5)

    with checkpoint(ctx, "corrections_pagination_schema"):
        resp = await client.get(
            f"{BASE}/corrections",
            params={"workspace_id": workspace_id, "limit": 5},
        )
        assert resp.status_code == 200, resp.text
        _assert_paginated(resp.json(), limit=5)

    with checkpoint(ctx, "releases_pagination_schema"):
        resp = await client.get(
            f"{BASE}/releases",
            params={"workspace_id": workspace_id, "limit": 5},
        )
        assert resp.status_code == 200, resp.text
        _assert_paginated(resp.json(), limit=5)

    with checkpoint(ctx, "adjudication_queue_pagination_schema"):
        resp = await client.get(
            f"{BASE}/adjudication/queue",
            params={"workspace_id": workspace_id, "limit": 5},
        )
        assert resp.status_code == 200, resp.text
        _assert_paginated(resp.json(), limit=5)

    with checkpoint(ctx, "pagination_default_limit_respected"):
        # Default limit (no explicit limit) — should still return paginated schema
        resp = await client.get(f"{BASE}/workspaces")
        assert resp.status_code == 200, resp.text
        _assert_paginated(resp.json())

    with checkpoint(ctx, "pagination_limit_one"):
        resp = await client.get(f"{BASE}/workspaces", params={"limit": 1})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        _assert_paginated(body, limit=1)
        # At most 1 item
        assert len(body["items"]) <= 1

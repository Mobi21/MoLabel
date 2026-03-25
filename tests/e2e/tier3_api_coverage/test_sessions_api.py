"""Tier 3 — API Coverage: Sessions (T3-21).

Tests:
    T3-21: Create, /me, switch, delete, verify 401 after logout
"""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SHARED_WORKSPACE

BASE = "/api/v1"
WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier3
async def test_sessions_create_me_switch_delete_logout(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T3-21: Full session lifecycle."""

    # Create two reviewer profiles
    rp1_resp = await client.post(
        f"{BASE}/reviewer-profiles",
        json={"display_name": "Session User 1", "workspace_id": WORKSPACE_ID},
    )
    assert rp1_resp.status_code == 201
    reviewer_id_1 = rp1_resp.json()["id"]

    rp2_resp = await client.post(
        f"{BASE}/reviewer-profiles",
        json={"display_name": "Session User 2", "workspace_id": WORKSPACE_ID},
    )
    assert rp2_resp.status_code == 201
    reviewer_id_2 = rp2_resp.json()["id"]

    with checkpoint(ctx, "create_session"):
        resp = await client.post(
            f"{BASE}/sessions", json={"reviewer_id": reviewer_id_1}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["reviewer_id"] == reviewer_id_1
        assert body["message"] == "session_created"
        assert "molabel_session" in resp.cookies
        client._session_cookie = resp.cookies.get("molabel_session")

    with checkpoint(ctx, "get_me"):
        resp = await client.get(f"{BASE}/me")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["reviewer_id"] == reviewer_id_1
        assert body["display_name"] == "Session User 1"
        assert "is_active" in body
        assert "created_at" in body

    with checkpoint(ctx, "switch_session"):
        resp = await client.post(
            f"{BASE}/sessions/switch",
            json={"reviewer_id": reviewer_id_2},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["reviewer_id"] == reviewer_id_2
        assert body["message"] == "session_switched"
        client._session_cookie = resp.cookies.get("molabel_session")

    with checkpoint(ctx, "me_after_switch"):
        resp = await client.get(f"{BASE}/me")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["reviewer_id"] == reviewer_id_2

    with checkpoint(ctx, "delete_session"):
        resp = await client.delete(f"{BASE}/sessions")
        assert resp.status_code == 204, resp.text
        # Clear the cookie to simulate logout
        client._session_cookie = None

    with checkpoint(ctx, "me_after_logout_returns_401"):
        resp = await client.get(f"{BASE}/me")
        assert resp.status_code == 401, resp.text
        body = resp.json()
        assert "error" in body

    with checkpoint(ctx, "401_on_no_session_cookie"):
        resp = await client.post(
            f"{BASE}/sessions/switch", json={"reviewer_id": reviewer_id_1}
        )
        assert resp.status_code == 401, resp.text

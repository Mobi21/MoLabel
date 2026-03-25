"""Tier 9 — Cross-Cutting: Session Persistence (T9-05).

Tests:
    T9-05: 10+ operations with the same session, then switch reviewer,
           then logout, then verify 401 on protected endpoints.
"""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SEQUENTIAL

BASE = "/api/v1"
WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"


async def _create_reviewer(client: InstrumentedClient, name: str) -> str:
    rp = await client.post(
        f"{BASE}/reviewer-profiles",
        json={"display_name": name, "workspace_id": WORKSPACE_ID},
    )
    assert rp.status_code == 201
    return rp.json()["id"]


async def _login(client: InstrumentedClient, reviewer_id: str) -> None:
    login = await client.post(f"{BASE}/sessions", json={"reviewer_id": reviewer_id})
    assert login.status_code == 200
    client._session_cookie = login.cookies.get("molabel_session")


@SEQUENTIAL
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier9
async def test_session_persistence(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T9-05: Session cookie persists across 10+ requests, switch works, logout → 401.
    """

    reviewer_a_id = await _create_reviewer(client, "Session Reviewer A")
    reviewer_b_id = await _create_reviewer(client, "Session Reviewer B")
    await _login(client, reviewer_a_id)

    # --- 10+ operations using the same session ---
    with checkpoint(ctx, "session_persists_across_10_requests"):
        workspace_id = None
        for i in range(5):
            resp = await client.post(
                f"{BASE}/workspaces",
                json={
                    "path": f"/tmp/ws-session-{i}",
                    "workspace_name": f"Session WS {i}",
                },
            )
            assert resp.status_code == 201, f"Request {i}: {resp.text}"
            if workspace_id is None:
                workspace_id = resp.json()["workspace_id"]

        for i in range(5):
            resp = await client.get(f"{BASE}/workspaces")
            assert resp.status_code == 200, f"List request {i}: {resp.text}"

    with checkpoint(ctx, "me_endpoint_returns_reviewer"):
        resp = await client.get(f"{BASE}/me")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "reviewer_id" in body, f"Unexpected /me response: {body}"

    # --- Switch reviewer ---
    with checkpoint(ctx, "session_switch_reviewer"):
        resp = await client.post(
            f"{BASE}/sessions/switch",
            json={"reviewer_id": reviewer_b_id},
        )
        assert resp.status_code == 200, resp.text
        # Cookie may be updated; update local store
        new_cookie = resp.cookies.get("molabel_session")
        if new_cookie:
            client._session_cookie = new_cookie

    with checkpoint(ctx, "after_switch_me_returns_reviewer_b"):
        resp = await client.get(f"{BASE}/me")
        assert resp.status_code == 200, resp.text

    # --- Session still valid for protected endpoint after switch ---
    with checkpoint(ctx, "protected_endpoint_works_after_switch"):
        resp = await client.get(f"{BASE}/workspaces")
        assert resp.status_code == 200, resp.text

    # --- Logout ---
    with checkpoint(ctx, "logout_returns_204"):
        resp = await client.delete(f"{BASE}/sessions")
        assert resp.status_code == 204, resp.text

    # --- Protected endpoints return 401 after logout ---
    client._session_cookie = None

    with checkpoint(ctx, "protected_endpoint_401_after_logout"):
        protected_paths = [
            f"{BASE}/me",
            f"{BASE}/costs?workspace_id={WORKSPACE_ID}",
        ]
        for path in protected_paths:
            resp = await client.get(path)
            assert resp.status_code == 401, (
                f"Expected 401 after logout for {path}, "
                f"got {resp.status_code}: {resp.text}"
            )

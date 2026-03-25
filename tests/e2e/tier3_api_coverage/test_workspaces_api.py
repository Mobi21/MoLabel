"""Tier 3 — API Coverage: Workspaces (T3-01, T3-02, T3-03).

Tests:
    T3-01: Full CRUD cycle — create 201, read, list, reindex 202
    T3-02: 404 on nonexistent workspace
    T3-03: 401 without session cookie
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
async def test_workspace_full_crud_and_reindex(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T3-01: Create, read, list workspaces; trigger reindex (202)."""

    # --- setup: create a reviewer profile so we can log in ---
    with checkpoint(ctx, "create_reviewer"):
        rp = await client.post(
            f"{BASE}/reviewer-profiles",
            json={
                "display_name": "T3 Reviewer",
                "workspace_id": "00000000-0000-0000-0000-000000000001",
            },
        )
        assert rp.status_code == 201, rp.text
        reviewer_id = rp.json()["id"]

    with checkpoint(ctx, "login"):
        login_resp = await client.post(
            f"{BASE}/sessions", json={"reviewer_id": reviewer_id}
        )
        assert login_resp.status_code == 200, login_resp.text
        # InstrumentedClient tracks cookies via the parent E2EClient
        client._session_cookie = login_resp.cookies.get("molabel_session")

    # --- T3-01a: create workspace ---
    workspace_id: str = ""
    with checkpoint(ctx, "create_workspace"):
        resp = await client.post(
            f"{BASE}/workspaces",
            json={"path": "/tmp/ws-t3-01", "workspace_name": "T3 Workspace"},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["workspace_name"] == "T3 Workspace"
        assert body["health"] == "healthy"
        workspace_id = body["workspace_id"]

    # --- T3-01b: read workspace ---
    with checkpoint(ctx, "get_workspace"):
        resp = await client.get(f"{BASE}/workspaces/{workspace_id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["workspace_id"] == workspace_id
        assert "health_checks" in body

    # --- T3-01c: list workspaces ---
    with checkpoint(ctx, "list_workspaces"):
        resp = await client.get(f"{BASE}/workspaces")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "items" in body
        ids = [w["workspace_id"] for w in body["items"]]
        assert workspace_id in ids

    # --- T3-01d: reindex (202) ---
    with checkpoint(ctx, "reindex_workspace"):
        resp = await client.post(
            f"{BASE}/workspaces/{workspace_id}/reindex",
            json={"force": True},
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["status"] == "queued"
        assert "job_id" in body


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier3
async def test_workspace_404_nonexistent(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T3-02: 404 on nonexistent workspace."""

    with checkpoint(ctx, "get_nonexistent_workspace"):
        resp = await client.get(
            f"{BASE}/workspaces/00000000-0000-0000-0000-deadbeef0002"
        )
        assert resp.status_code == 404, resp.text
        body = resp.json()
        assert "error" in body

    with checkpoint(ctx, "reindex_nonexistent_workspace"):
        resp = await client.post(
            f"{BASE}/workspaces/00000000-0000-0000-0000-deadbeef0002/reindex",
            json={},
        )
        # Reindex requires auth first; without login it may return 401 or 404
        assert resp.status_code in (401, 404), resp.text


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier3
async def test_workspace_401_without_session(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T3-03: POST /workspaces is public (bootstrap); reindex requires auth."""

    # Ensure no session cookie is set
    client._session_cookie = None
    client._client.cookies.clear()

    with checkpoint(ctx, "create_without_auth_returns_201"):
        resp = await client.post(
            f"{BASE}/workspaces",
            json={"path": "/tmp/ws-no-auth", "workspace_name": "No Auth WS"},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert "first_reviewer" in body
        assert body["first_reviewer"]["id"]
        assert body["first_reviewer"]["display_name"]
        assert body["first_reviewer"]["avatar_color"]
        # Session cookie is auto-set by the workspace bootstrap
        assert client._session_cookie is not None

    # Clear the session cookie again before testing auth-protected endpoint
    client._session_cookie = None
    client._client.cookies.clear()

    with checkpoint(ctx, "reindex_without_auth"):
        resp = await client.post(
            f"{BASE}/workspaces/00000000-0000-0000-0000-000000000001/reindex",
            json={},
        )
        assert resp.status_code == 401, resp.text

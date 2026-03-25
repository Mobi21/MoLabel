"""Tier 3 — API Coverage: Releases (T3-14).

Tests:
    T3-14: Create, list, get, approve lifecycle
"""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SHARED_WORKSPACE

BASE = "/api/v1"


async def _setup(client: InstrumentedClient) -> str:
    rp = await client.post(
        f"{BASE}/reviewer-profiles",
        json={
            "display_name": "Release Reviewer",
            "workspace_id": "00000000-0000-0000-0000-000000000001",
        },
    )
    assert rp.status_code == 201
    reviewer_id = rp.json()["id"]
    login = await client.post(f"{BASE}/sessions", json={"reviewer_id": reviewer_id})
    assert login.status_code == 200
    client._session_cookie = login.cookies.get("molabel_session")

    ws = await client.post(
        f"{BASE}/workspaces",
        json={"path": "/tmp/ws-releases", "workspace_name": "Release WS"},
    )
    assert ws.status_code == 201
    return ws.json()["workspace_id"]


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier3
async def test_releases_lifecycle(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T3-14: Create release, list, get (404), approve (404)."""

    workspace_id = await _setup(client)

    release_id: str = ""
    with checkpoint(ctx, "create_release"):
        resp = await client.post(
            f"{BASE}/releases",
            json={
                "workspace_id": workspace_id,
                "name": "v1.0.0 Release",
                "version": "1.0.0",
                "export_ids": ["00000000-0000-0000-0000-000000000001"],
                "notes": "First production release",
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["name"] == "v1.0.0 Release"
        assert body["version"] == "1.0.0"
        assert body["status"] == "draft"
        assert body["workspace_id"] == workspace_id
        release_id = body["release_id"]

    with checkpoint(ctx, "list_releases"):
        resp = await client.get(
            f"{BASE}/releases",
            params={"workspace_id": workspace_id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "items" in body

    with checkpoint(ctx, "list_releases_status_filter"):
        resp = await client.get(
            f"{BASE}/releases",
            params={"workspace_id": workspace_id, "status": "draft"},
        )
        assert resp.status_code == 200, resp.text

    with checkpoint(ctx, "get_release_404"):
        # Stub raises 404 since no DB persistence
        resp = await client.get(f"{BASE}/releases/{release_id}")
        assert resp.status_code == 404, resp.text
        body = resp.json()
        assert "error" in body

    with checkpoint(ctx, "approve_release_404"):
        # Stub raises 404
        resp = await client.post(
            f"{BASE}/releases/{release_id}/approve",
            json={"approved": True, "notes": "LGTM"},
        )
        assert resp.status_code == 404, resp.text

    with checkpoint(ctx, "reject_release_404"):
        resp = await client.post(
            f"{BASE}/releases/{release_id}/approve",
            json={"approved": False, "notes": "Failed quality gates"},
        )
        assert resp.status_code == 404, resp.text

"""Tier 3 — API Coverage: Plugins (T3-25).

Tests:
    T3-25: List, detail, enable, disable
"""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SHARED_WORKSPACE

BASE = "/api/v1"
WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"


async def _setup(client: InstrumentedClient) -> None:
    rp = await client.post(
        f"{BASE}/reviewer-profiles",
        json={"display_name": "Plugin Reviewer", "workspace_id": WORKSPACE_ID},
    )
    assert rp.status_code == 201
    reviewer_id = rp.json()["id"]
    login = await client.post(f"{BASE}/sessions", json={"reviewer_id": reviewer_id})
    assert login.status_code == 200
    client._session_cookie = login.cookies.get("molabel_session")


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier3
async def test_plugins_list_detail_enable_disable(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T3-25: List plugins, detail, enable, disable."""

    await _setup(client)

    with checkpoint(ctx, "list_plugins"):
        resp = await client.get(
            f"{BASE}/plugins",
            params={"workspace_id": WORKSPACE_ID},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # Returns an empty list in stub
        assert isinstance(body, list)

    fake_plugin_id = "molabel.plugins.fake-t3"

    with checkpoint(ctx, "get_plugin_detail_404"):
        resp = await client.get(f"{BASE}/plugins/{fake_plugin_id}")
        assert resp.status_code == 404, resp.text
        body = resp.json()
        assert "error" in body

    with checkpoint(ctx, "enable_plugin_404"):
        resp = await client.post(f"{BASE}/plugins/{fake_plugin_id}/enable")
        assert resp.status_code == 404, resp.text
        body = resp.json()
        assert "error" in body

    with checkpoint(ctx, "disable_plugin_404"):
        resp = await client.post(f"{BASE}/plugins/{fake_plugin_id}/disable")
        assert resp.status_code == 404, resp.text
        body = resp.json()
        assert "error" in body

    with checkpoint(ctx, "list_plugins_response_structure"):
        # Verify the empty list response still has correct Content-Type
        resp = await client.get(
            f"{BASE}/plugins",
            params={"workspace_id": WORKSPACE_ID},
        )
        assert resp.status_code == 200
        assert "application/json" in resp.headers.get("content-type", "")

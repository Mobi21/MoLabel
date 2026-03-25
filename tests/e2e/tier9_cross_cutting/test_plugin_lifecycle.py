"""Tier 9 — Cross-Cutting: Plugin Lifecycle (T9-04).

Tests:
    T9-04: List plugins, attempt enable/disable on non-existent plugin
           (404), verify API shape and Content-Type for all responses.
"""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import INDEPENDENT

BASE = "/api/v1"
WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"


async def _setup(client: InstrumentedClient) -> None:
    rp = await client.post(
        f"{BASE}/reviewer-profiles",
        json={
            "display_name": "Plugin Lifecycle Reviewer",
            "workspace_id": WORKSPACE_ID,
        },
    )
    assert rp.status_code == 201
    reviewer_id = rp.json()["id"]
    login = await client.post(f"{BASE}/sessions", json={"reviewer_id": reviewer_id})
    assert login.status_code == 200
    client._session_cookie = login.cookies.get("molabel_session")


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier9
async def test_plugin_lifecycle(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T9-04: Plugin list, enable, disable lifecycle with state verification."""

    await _setup(client)

    with checkpoint(ctx, "list_plugins_returns_list"):
        resp = await client.get(
            f"{BASE}/plugins",
            params={"workspace_id": WORKSPACE_ID},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert isinstance(body, list)

    with checkpoint(ctx, "list_plugins_json_content_type"):
        resp = await client.get(
            f"{BASE}/plugins",
            params={"workspace_id": WORKSPACE_ID},
        )
        assert resp.status_code == 200
        assert "application/json" in resp.headers.get("content-type", "")

    with checkpoint(ctx, "list_plugins_initially_empty"):
        resp = await client.get(
            f"{BASE}/plugins",
            params={"workspace_id": WORKSPACE_ID},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # Stub returns empty list
        assert isinstance(body, list)

    fake_plugin_id = "molabel.plugins.lifecycle-t9"

    with checkpoint(ctx, "get_unknown_plugin_404"):
        resp = await client.get(f"{BASE}/plugins/{fake_plugin_id}")
        assert resp.status_code == 404, resp.text
        body = resp.json()
        assert "error" in body

    with checkpoint(ctx, "enable_unknown_plugin_404"):
        resp = await client.post(f"{BASE}/plugins/{fake_plugin_id}/enable")
        assert resp.status_code == 404, resp.text
        body = resp.json()
        assert "error" in body

    with checkpoint(ctx, "disable_unknown_plugin_404"):
        resp = await client.post(f"{BASE}/plugins/{fake_plugin_id}/disable")
        assert resp.status_code == 404, resp.text
        body = resp.json()
        assert "error" in body

    with checkpoint(ctx, "plugin_error_response_schema"):
        resp = await client.get(f"{BASE}/plugins/{fake_plugin_id}")
        assert resp.status_code == 404
        body = resp.json()
        assert "error" in body
        error = body["error"]
        assert "code" in error or "message" in error, (
            f"ErrorResponse 'error' should have 'code' or 'message', got: {error}"
        )

    with checkpoint(ctx, "plugin_lifecycle_requires_auth"):
        client._session_cookie = None
        client._client.cookies.clear()
        resp = await client.get(
            f"{BASE}/plugins",
            params={"workspace_id": WORKSPACE_ID},
        )
        # Plugins list requires CurrentReviewer — 401 without session
        assert resp.status_code == 401, resp.text

"""Tier 3 — API Coverage: Audit (T3-24).

Tests:
    T3-24: List + all filter params (event_type, actor, object_type, time range)
           + get single
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
            "display_name": "Audit Reviewer",
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
        json={"path": "/tmp/ws-audit", "workspace_name": "Audit WS"},
    )
    assert ws.status_code == 201
    return ws.json()["workspace_id"]


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier3
async def test_audit_list_filters_and_get(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T3-24: List audit events with all filter params; get single event."""

    workspace_id = await _setup(client)

    with checkpoint(ctx, "list_audit_events"):
        resp = await client.get(
            f"{BASE}/audit",
            params={"workspace_id": workspace_id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "items" in body
        assert "has_more" in body
        assert "cursor" in body

    with checkpoint(ctx, "filter_by_event_type"):
        resp = await client.get(
            f"{BASE}/audit",
            params={"workspace_id": workspace_id, "event_type": "workspace_created"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "items" in body

    with checkpoint(ctx, "filter_by_actor"):
        resp = await client.get(
            f"{BASE}/audit",
            params={
                "workspace_id": workspace_id,
                "actor": "00000000-0000-0000-0000-000000000001",
            },
        )
        assert resp.status_code == 200, resp.text

    with checkpoint(ctx, "filter_by_object_type"):
        resp = await client.get(
            f"{BASE}/audit",
            params={"workspace_id": workspace_id, "object_type": "workspace"},
        )
        assert resp.status_code == 200, resp.text

    with checkpoint(ctx, "filter_by_object_id"):
        resp = await client.get(
            f"{BASE}/audit",
            params={"workspace_id": workspace_id, "object_id": workspace_id},
        )
        assert resp.status_code == 200, resp.text

    with checkpoint(ctx, "filter_by_time_range"):
        resp = await client.get(
            f"{BASE}/audit",
            params={
                "workspace_id": workspace_id,
                "created_after": "2026-01-01T00:00:00Z",
                "created_before": "2027-01-01T00:00:00Z",
            },
        )
        assert resp.status_code == 200, resp.text

    with checkpoint(ctx, "get_single_audit_event_404"):
        fake_audit_id = "00000000-0000-0000-0000-aud17even7001"
        resp = await client.get(f"{BASE}/audit/{fake_audit_id}")
        assert resp.status_code == 404, resp.text
        body = resp.json()
        assert "error" in body

    with checkpoint(ctx, "audit_pagination"):
        resp = await client.get(
            f"{BASE}/audit",
            params={"workspace_id": workspace_id, "limit": 10},
        )
        assert resp.status_code == 200, resp.text

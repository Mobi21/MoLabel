"""Tier 3 — API Coverage: Reviewer Profiles (T3-20).

Tests:
    T3-20: CRUD + active filtering + auto avatar color
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
async def test_reviewer_profiles_crud_active_avatar(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T3-20: Create, list, get, update reviewer profiles; active filter; auto avatar.
    """

    profile_id: str = ""
    with checkpoint(ctx, "create_profile"):
        resp = await client.post(
            f"{BASE}/reviewer-profiles",
            json={"display_name": "Alice T3", "workspace_id": WORKSPACE_ID},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["display_name"] == "Alice T3"
        assert body["is_active"] is True
        # Avatar color is auto-assigned (hex format)
        assert body["avatar_color"] is not None
        assert body["avatar_color"].startswith("#")
        assert len(body["avatar_color"]) == 7
        profile_id = body["id"]
        body["avatar_color"]

    with checkpoint(ctx, "auto_avatar_color_distinct"):
        # Create a second profile — should get a different color
        resp2 = await client.post(
            f"{BASE}/reviewer-profiles",
            json={"display_name": "Bob T3", "workspace_id": WORKSPACE_ID},
        )
        assert resp2.status_code == 201, resp2.text
        body2 = resp2.json()
        # Colors should differ (the palette cycles to avoid adjacent duplicates)
        assert body2["avatar_color"] is not None

    with checkpoint(ctx, "get_profile"):
        resp = await client.get(f"{BASE}/reviewer-profiles/{profile_id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == profile_id
        assert body["display_name"] == "Alice T3"

    with checkpoint(ctx, "list_profiles_active_only"):
        resp = await client.get(
            f"{BASE}/reviewer-profiles",
            params={"active_only": True, "workspace_id": WORKSPACE_ID},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert isinstance(body, list)
        ids = [p["id"] for p in body]
        assert profile_id in ids

    with checkpoint(ctx, "list_profiles_all"):
        resp = await client.get(
            f"{BASE}/reviewer-profiles",
            params={"active_only": False},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert isinstance(body, list)

    with checkpoint(ctx, "update_profile_name"):
        resp = await client.patch(
            f"{BASE}/reviewer-profiles/{profile_id}",
            json={"display_name": "Alice T3 Updated"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["display_name"] == "Alice T3 Updated"

    with checkpoint(ctx, "update_profile_deactivate"):
        resp = await client.patch(
            f"{BASE}/reviewer-profiles/{profile_id}",
            json={"is_active": False},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["is_active"] is False

    with checkpoint(ctx, "list_active_excludes_inactive"):
        resp = await client.get(
            f"{BASE}/reviewer-profiles",
            params={"active_only": True, "workspace_id": WORKSPACE_ID},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        ids = [p["id"] for p in body]
        # Alice is now inactive, should not appear
        assert profile_id not in ids

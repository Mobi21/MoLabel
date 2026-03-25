"""Tier 3 — API Coverage: Runtime Profiles (T3-19).

Tests:
    T3-19: Full CRUD + retry config endpoint
"""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SHARED_WORKSPACE

BASE = "/api/v1"


async def _setup(client: InstrumentedClient) -> None:
    rp = await client.post(
        f"{BASE}/reviewer-profiles",
        json={
            "display_name": "RP Reviewer",
            "workspace_id": "00000000-0000-0000-0000-000000000001",
        },
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
async def test_runtime_profiles_crud_retry(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T3-19: Create, list, get, update, retry config, delete runtime profiles."""

    await _setup(client)

    profile_id: str = ""
    with checkpoint(ctx, "create_runtime_profile"):
        resp = await client.post(
            f"{BASE}/runtime-profiles",
            json={
                "runtime_profile_slug": "production-t3",
                "display_name": "Production T3",
                "max_retries": 3,
                "timeout_seconds": 30,
                "batch_size": 10,
                "concurrency": 5,
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["max_retries"] == 3
        assert body["batch_size"] == 10
        profile_id = body["id"]

    with checkpoint(ctx, "list_runtime_profiles"):
        resp = await client.get(f"{BASE}/runtime-profiles")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert isinstance(body, list)
        ids = [p["id"] for p in body]
        assert profile_id in ids

    with checkpoint(ctx, "get_runtime_profile"):
        resp = await client.get(f"{BASE}/runtime-profiles/{profile_id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == profile_id

    with checkpoint(ctx, "update_runtime_profile"):
        resp = await client.patch(
            f"{BASE}/runtime-profiles/{profile_id}",
            json={"max_retries": 5, "timeout_seconds": 60},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == profile_id

    with checkpoint(ctx, "get_retry_config"):
        resp = await client.get(f"{BASE}/runtime-profiles/{profile_id}/retry-config")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "max_retries" in body

    with checkpoint(ctx, "delete_runtime_profile"):
        resp = await client.delete(f"{BASE}/runtime-profiles/{profile_id}")
        assert resp.status_code == 204, resp.text

    with checkpoint(ctx, "get_deleted_404"):
        resp = await client.get(f"{BASE}/runtime-profiles/{profile_id}")
        assert resp.status_code == 404, resp.text

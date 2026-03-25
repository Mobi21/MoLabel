"""Tier 3 — API Coverage: Model Profiles (T3-18).

Tests:
    T3-18: Full CRUD + test connectivity + delete verify 404
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
            "display_name": "MP Reviewer",
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
async def test_model_profiles_crud_connectivity_delete(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T3-18: Create, list, get, patch, test, delete, verify 404."""

    await _setup(client)

    profile_id: str = ""
    with checkpoint(ctx, "create_model_profile"):
        resp = await client.post(
            f"{BASE}/model-profiles",
            json={
                "model_profile_slug": "gpt4-turbo-t3",
                "provider_type": "openai_compatible",
                "model_identifier": "gpt-4-turbo",
                "display_name": "GPT-4 Turbo",
                "base_url": "https://api.openai.com/v1",
                "transport": "http",
                "supports_structured_output": True,
                "supports_tool_use": True,
                "context_window": 128000,
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["model_identifier"] == "gpt-4-turbo"
        assert body["provider_type"] == "openai_compatible"
        profile_id = body["id"]

    with checkpoint(ctx, "list_model_profiles"):
        resp = await client.get(f"{BASE}/model-profiles")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert isinstance(body, list)
        ids = [p["id"] for p in body]
        assert profile_id in ids

    with checkpoint(ctx, "list_model_profiles_filtered"):
        resp = await client.get(
            f"{BASE}/model-profiles",
            params={"provider_type": "openai_compatible"},
        )
        assert resp.status_code == 200, resp.text

    with checkpoint(ctx, "get_model_profile"):
        resp = await client.get(f"{BASE}/model-profiles/{profile_id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == profile_id

    with checkpoint(ctx, "update_model_profile"):
        resp = await client.patch(
            f"{BASE}/model-profiles/{profile_id}",
            json={"display_name": "GPT-4 Turbo (Updated)", "context_window": 256000},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == profile_id

    with checkpoint(ctx, "test_connectivity"):
        resp = await client.post(f"{BASE}/model-profiles/{profile_id}/test")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "is_reachable" in body

    with checkpoint(ctx, "delete_model_profile"):
        resp = await client.delete(f"{BASE}/model-profiles/{profile_id}")
        assert resp.status_code == 204, resp.text

    with checkpoint(ctx, "get_deleted_returns_404"):
        resp = await client.get(f"{BASE}/model-profiles/{profile_id}")
        assert resp.status_code == 404, resp.text
        body = resp.json()
        assert "error" in body

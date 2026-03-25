"""Tier 3 — API Coverage: Costs (T3-23).

Tests:
    T3-23: Summary + estimate endpoints
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
            "display_name": "Cost Reviewer",
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
        json={"path": "/tmp/ws-costs", "workspace_name": "Costs WS"},
    )
    assert ws.status_code == 201
    return ws.json()["workspace_id"]


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier3
async def test_costs_summary_and_estimate(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T3-23: Cost summary (with all filter params) + estimate endpoint."""

    workspace_id = await _setup(client)

    with checkpoint(ctx, "cost_summary_basic"):
        resp = await client.get(
            f"{BASE}/costs",
            params={"workspace_id": workspace_id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["workspace_id"] == workspace_id
        assert "total_cost_usd" in body
        assert "total_tokens_input" in body
        assert "total_tokens_output" in body
        assert "by_model" in body
        assert "by_role" in body
        assert "daily_trend" in body

    with checkpoint(ctx, "cost_summary_filtered_by_model"):
        resp = await client.get(
            f"{BASE}/costs",
            params={
                "workspace_id": workspace_id,
                "model_profile_id": "00000000-0000-0000-0000-000000000001",
            },
        )
        assert resp.status_code == 200, resp.text

    with checkpoint(ctx, "cost_summary_filtered_by_role"):
        resp = await client.get(
            f"{BASE}/costs",
            params={"workspace_id": workspace_id, "agent_role": "proposer"},
        )
        assert resp.status_code == 200, resp.text

    with checkpoint(ctx, "cost_summary_with_period"):
        resp = await client.get(
            f"{BASE}/costs",
            params={"workspace_id": workspace_id, "period": "7d"},
        )
        assert resp.status_code == 200, resp.text

    with checkpoint(ctx, "cost_estimate_basic"):
        resp = await client.get(f"{BASE}/costs/estimate")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "model_profile_id" in body
        assert "estimated_cost_usd" in body
        assert "confidence" in body
        assert "warnings" in body

    with checkpoint(ctx, "cost_estimate_with_params"):
        resp = await client.get(
            f"{BASE}/costs/estimate",
            params={
                "workspace_id": workspace_id,
                "dataset_id": "00000000-0000-0000-0000-000000000001",
                "model_profile_id": "00000000-0000-0000-0000-000000000001",
                "agent_role": "proposer",
                "record_count": 100,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["estimated_records"] == 100

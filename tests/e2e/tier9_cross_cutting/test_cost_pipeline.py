"""Tier 9 — Cross-Cutting: Cost Pipeline (T9-02).

Tests:
    T9-02: Verify cost aggregation endpoint returns correct schema with
           by_model, by_role, and daily_trend fields; test filtering.
"""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import INDEPENDENT

BASE = "/api/v1"


async def _setup(client: InstrumentedClient) -> str:
    """Create reviewer, log in, create workspace; return workspace_id."""
    rp = await client.post(
        f"{BASE}/reviewer-profiles",
        json={
            "display_name": "Cost Pipeline Reviewer",
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
        json={"path": "/tmp/ws-cost-pipeline", "workspace_name": "Cost Pipeline WS"},
    )
    assert ws.status_code == 201
    return ws.json()["workspace_id"]


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier9
async def test_cost_pipeline(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T9-02: Cost aggregation returns correct schema.

    Fields: by_model, by_role, daily_trend.
    """

    workspace_id = await _setup(client)

    with checkpoint(ctx, "cost_summary_schema"):
        resp = await client.get(
            f"{BASE}/costs",
            params={"workspace_id": workspace_id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "workspace_id" in body
        assert "total_cost_usd" in body
        assert "total_tokens_input" in body
        assert "total_tokens_output" in body
        assert "total_runs" in body
        assert "by_model" in body
        assert "by_role" in body
        assert "daily_trend" in body

    with checkpoint(ctx, "cost_summary_workspace_id_matches"):
        resp = await client.get(
            f"{BASE}/costs",
            params={"workspace_id": workspace_id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["workspace_id"] == workspace_id

    with checkpoint(ctx, "cost_summary_by_model_is_list"):
        resp = await client.get(
            f"{BASE}/costs",
            params={"workspace_id": workspace_id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert isinstance(body["by_model"], list)

    with checkpoint(ctx, "cost_summary_by_role_is_list"):
        resp = await client.get(
            f"{BASE}/costs",
            params={"workspace_id": workspace_id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert isinstance(body["by_role"], list)

    with checkpoint(ctx, "cost_summary_daily_trend_is_list"):
        resp = await client.get(
            f"{BASE}/costs",
            params={"workspace_id": workspace_id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert isinstance(body["daily_trend"], list)

    with checkpoint(ctx, "cost_summary_numeric_types"):
        resp = await client.get(
            f"{BASE}/costs",
            params={"workspace_id": workspace_id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert isinstance(body["total_cost_usd"], (int, float))
        assert isinstance(body["total_tokens_input"], int)
        assert isinstance(body["total_tokens_output"], int)
        assert isinstance(body["total_runs"], int)

    with checkpoint(ctx, "cost_filter_by_model_profile"):
        resp = await client.get(
            f"{BASE}/costs",
            params={
                "workspace_id": workspace_id,
                "model_profile_id": "00000000-0000-0000-0000-000000000001",
            },
        )
        assert resp.status_code == 200, resp.text

    with checkpoint(ctx, "cost_filter_by_agent_role"):
        resp = await client.get(
            f"{BASE}/costs",
            params={
                "workspace_id": workspace_id,
                "agent_role": "proposer",
            },
        )
        assert resp.status_code == 200, resp.text

    with checkpoint(ctx, "cost_filter_by_period"):
        for period in ["7d", "30d", "all"]:
            resp = await client.get(
                f"{BASE}/costs",
                params={"workspace_id": workspace_id, "period": period},
            )
            assert resp.status_code == 200, (
                f"Expected 200 for period={period}, got {resp.status_code}: {resp.text}"
            )

    with checkpoint(ctx, "cost_filter_by_time_range"):
        resp = await client.get(
            f"{BASE}/costs",
            params={
                "workspace_id": workspace_id,
                "created_after": "2026-01-01T00:00:00Z",
                "created_before": "2027-01-01T00:00:00Z",
            },
        )
        assert resp.status_code == 200, resp.text

    with checkpoint(ctx, "cost_estimate_schema"):
        resp = await client.get(
            f"{BASE}/costs/estimate",
            params={
                "workspace_id": workspace_id,
                "record_count": 100,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "model_profile_id" in body
        assert "model_identifier" in body
        assert "estimated_records" in body
        assert "estimated_tokens_input" in body
        assert "estimated_tokens_output" in body
        assert "estimated_cost_usd" in body
        assert "confidence" in body
        assert "pricing_source" in body
        assert "warnings" in body
        assert isinstance(body["warnings"], list)

    with checkpoint(ctx, "cost_requires_auth"):
        client._session_cookie = None
        resp = await client.get(
            f"{BASE}/costs",
            params={"workspace_id": workspace_id},
        )
        assert resp.status_code == 401, resp.text

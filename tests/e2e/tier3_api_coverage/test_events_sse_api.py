"""Tier 3 — API Coverage: SSE Event Streams (T3-27).

Tests:
    T3-27: All 4 SSE streams (agent-runs, queue, workflow, providers)
           — verify Content-Type, 401 without session
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
            "display_name": "SSE Reviewer",
            "workspace_id": "00000000-0000-0000-0000-000000000001",
        },
    )
    assert rp.status_code == 201
    reviewer_id = rp.json()["id"]
    login = await client.post(f"{BASE}/sessions", json={"reviewer_id": reviewer_id})
    assert login.status_code == 200
    client._session_cookie = login.cookies.get("molabel_session")
    return rp.json()["id"]


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier3
async def test_sse_streams_content_type_and_401(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T3-27: Verify SSE Content-Type for all streams; 401 without session."""

    await _setup(client)

    fake_agent_run_id = "00000000-0000-0000-0000-a9en7run0001"
    fake_queue_id = "00000000-0000-0000-0000-0000000queue"
    fake_execution_id = "00000000-0000-0000-0000-execu710n001"

    # --- Agent run SSE stream ---
    with checkpoint(ctx, "agent_run_sse_content_type"):
        resp = await client.get(f"{BASE}/events/agent-runs/{fake_agent_run_id}")
        assert resp.status_code == 200, resp.text
        assert "text/event-stream" in resp.headers.get("content-type", "")

    with checkpoint(ctx, "agent_run_sse_initial_event"):
        resp = await client.get(f"{BASE}/events/agent-runs/{fake_agent_run_id}")
        assert resp.status_code == 200
        # Should contain SSE event structure (id: ... event: ... data: ...)
        content = resp.text
        assert "event:" in content or "data:" in content

    # --- Queue SSE stream ---
    with checkpoint(ctx, "queue_sse_content_type"):
        resp = await client.get(f"{BASE}/events/queue/{fake_queue_id}")
        assert resp.status_code == 200, resp.text
        assert "text/event-stream" in resp.headers.get("content-type", "")

    with checkpoint(ctx, "queue_sse_stats_update_event"):
        resp = await client.get(f"{BASE}/events/queue/{fake_queue_id}")
        assert resp.status_code == 200
        content = resp.text
        assert "stats_update" in content or "data:" in content

    # --- Workflow SSE stream ---
    with checkpoint(ctx, "workflow_sse_content_type"):
        resp = await client.get(f"{BASE}/events/workflow/{fake_execution_id}")
        assert resp.status_code == 200, resp.text
        assert "text/event-stream" in resp.headers.get("content-type", "")

    # --- Providers SSE stream ---
    with checkpoint(ctx, "providers_sse_content_type"):
        resp = await client.get(f"{BASE}/events/providers")
        assert resp.status_code == 200, resp.text
        assert "text/event-stream" in resp.headers.get("content-type", "")

    # --- 401 without session cookie ---
    client._session_cookie = None

    with checkpoint(ctx, "agent_run_sse_401_no_session"):
        resp = await client.get(f"{BASE}/events/agent-runs/{fake_agent_run_id}")
        assert resp.status_code == 401, resp.text

    with checkpoint(ctx, "queue_sse_401_no_session"):
        resp = await client.get(f"{BASE}/events/queue/{fake_queue_id}")
        assert resp.status_code == 401, resp.text

    with checkpoint(ctx, "workflow_sse_401_no_session"):
        resp = await client.get(f"{BASE}/events/workflow/{fake_execution_id}")
        assert resp.status_code == 401, resp.text

    with checkpoint(ctx, "providers_sse_401_no_session"):
        resp = await client.get(f"{BASE}/events/providers")
        assert resp.status_code == 401, resp.text

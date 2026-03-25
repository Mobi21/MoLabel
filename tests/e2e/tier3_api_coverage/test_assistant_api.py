"""Tier 3 — API Coverage: Assistant (T3-26).

Tests:
    T3-26: Query (SSE) + context
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
            "display_name": "Asst Reviewer",
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
async def test_assistant_query_and_context(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T3-26: Assistant query (SSE stream) and context endpoint."""

    await _setup(client)

    with checkpoint(ctx, "assistant_query_sse"):
        resp = await client.post(
            f"{BASE}/assistant/query",
            json={
                "query": "How many records are labeled in my workspace?",
                "screen": "dashboard",
            },
        )
        assert resp.status_code == 200, resp.text
        # Response is an SSE stream
        assert "text/event-stream" in resp.headers.get("content-type", "")

    with checkpoint(ctx, "assistant_query_sse_content"):
        resp = await client.post(
            f"{BASE}/assistant/query",
            json={
                "query": "What is the agreement rate?",
                "screen": "quality",
                "record_id": None,
            },
        )
        assert resp.status_code == 200, resp.text
        content = resp.text
        # SSE body contains data: lines and [DONE]
        assert "data:" in content
        assert "[DONE]" in content

    with checkpoint(ctx, "assistant_query_with_model"):
        resp = await client.post(
            f"{BASE}/assistant/query",
            json={
                "query": "Summarize the quality metrics.",
                "screen": "quality",
                "model_profile_id": "00000000-0000-0000-0000-000000000001",
            },
        )
        assert resp.status_code == 200, resp.text

    with checkpoint(ctx, "assistant_context"):
        resp = await client.get(f"{BASE}/assistant/context")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "workspace_summary" in body
        assert "recent_agent_runs" in body
        assert "context_token_count" in body

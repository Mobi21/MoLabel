"""Tier 3 — API Coverage: SSE Event Streams (T3-27).

Tests:
    T3-27: All 4 SSE streams (agent-runs, queue, workflow, providers)
           — verify Content-Type, initial event, and 401 without session.

SSE streams are infinite by design.  Tests connect, read the first chunk,
then disconnect rather than consuming the full stream.
"""

from __future__ import annotations

import asyncio
import contextlib

import httpx
import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SHARED_WORKSPACE

BASE = "/api/v1"

# Short read timeout so we get headers + first event then disconnect cleanly.
_SSE_TIMEOUT = httpx.Timeout(connect=10.0, read=2.0, write=10.0, pool=10.0)


async def _setup(client: InstrumentedClient) -> str:
    ws_resp = await client.post(
        f"{BASE}/workspaces",
        json={"path": "/tmp/sse-ws", "workspace_name": "SSE WS"},
    )
    assert ws_resp.status_code == 201
    return ws_resp.json()["workspace_id"]


async def _sse_get(client: InstrumentedClient, url: str) -> tuple[int, str, str]:
    """GET an SSE endpoint, read the first chunk, then disconnect.

    Returns (status_code, content_type, first_chunk_text).
    Uses asyncio.wait_for to cancel the connection after the first event
    arrives, avoiding hangs caused by server-side keepalive sleeps.
    """
    cookies = {}
    if client._session_cookie:
        cookies["molabel_session"] = client._session_cookie

    status_code = 0
    content_type = ""
    first_chunk = ""

    async def _read() -> None:
        nonlocal status_code, content_type, first_chunk
        async with client._client.stream(
            "GET", url, cookies=cookies, timeout=_SSE_TIMEOUT
        ) as resp:
            status_code = resp.status_code
            content_type = resp.headers.get("content-type", "")
            async for chunk in resp.aiter_text():
                first_chunk += chunk
                if first_chunk.strip():
                    return  # Got first event — exit via return, not break

    with contextlib.suppress(TimeoutError, httpx.ReadTimeout):
        await asyncio.wait_for(_read(), timeout=1.0)

    return status_code, content_type, first_chunk


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

    fake_run_id = "00000000-0000-0000-0000-a9en7run0001"
    fake_queue_id = "00000000-0000-0000-0000-0000000queue"
    fake_exec_id = "00000000-0000-0000-0000-execu710n001"

    # ── Agent run SSE ─────────────────────────────────────────────────────
    with checkpoint(ctx, "agent_run_sse_content_type"):
        status, ct, chunk = await _sse_get(
            client, f"{BASE}/events/agent-runs/{fake_run_id}"
        )
        assert status == 200, f"Expected 200, got {status}"
        assert "text/event-stream" in ct, f"Bad Content-Type: {ct}"

    with checkpoint(ctx, "agent_run_sse_initial_event"):
        status, ct, chunk = await _sse_get(
            client, f"{BASE}/events/agent-runs/{fake_run_id}"
        )
        assert status == 200
        assert "event:" in chunk or "data:" in chunk, (
            f"No SSE event in chunk: {chunk!r}"
        )

    # ── Queue SSE ─────────────────────────────────────────────────────────
    with checkpoint(ctx, "queue_sse_content_type"):
        status, ct, chunk = await _sse_get(
            client, f"{BASE}/events/queue/{fake_queue_id}"
        )
        assert status == 200, f"Expected 200, got {status}"
        assert "text/event-stream" in ct, f"Bad Content-Type: {ct}"

    with checkpoint(ctx, "queue_sse_stats_event"):
        status, ct, chunk = await _sse_get(
            client, f"{BASE}/events/queue/{fake_queue_id}"
        )
        assert status == 200
        assert "stats_update" in chunk or "data:" in chunk, f"No stats event: {chunk!r}"

    # ── Workflow SSE ──────────────────────────────────────────────────────
    with checkpoint(ctx, "workflow_sse_content_type"):
        status, ct, _ = await _sse_get(client, f"{BASE}/events/workflow/{fake_exec_id}")
        assert status == 200, f"Expected 200, got {status}"
        assert "text/event-stream" in ct, f"Bad Content-Type: {ct}"

    # ── Providers SSE ─────────────────────────────────────────────────────
    with checkpoint(ctx, "providers_sse_content_type"):
        status, ct, _ = await _sse_get(client, f"{BASE}/events/providers")
        assert status == 200, f"Expected 200, got {status}"
        assert "text/event-stream" in ct, f"Bad Content-Type: {ct}"

    # ── 401 without session ───────────────────────────────────────────────
    saved_cookie = client._session_cookie
    client._session_cookie = None
    client._client.cookies.clear()

    with checkpoint(ctx, "agent_run_sse_401"):
        status, _, _ = await _sse_get(client, f"{BASE}/events/agent-runs/{fake_run_id}")
        assert status == 401, f"Expected 401, got {status}"

    with checkpoint(ctx, "queue_sse_401"):
        status, _, _ = await _sse_get(client, f"{BASE}/events/queue/{fake_queue_id}")
        assert status == 401, f"Expected 401, got {status}"

    with checkpoint(ctx, "workflow_sse_401"):
        status, _, _ = await _sse_get(client, f"{BASE}/events/workflow/{fake_exec_id}")
        assert status == 401, f"Expected 401, got {status}"

    with checkpoint(ctx, "providers_sse_401"):
        status, _, _ = await _sse_get(client, f"{BASE}/events/providers")
        assert status == 401, f"Expected 401, got {status}"

    client._session_cookie = saved_cookie

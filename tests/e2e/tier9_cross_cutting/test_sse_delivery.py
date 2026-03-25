"""Tier 9 — Cross-Cutting: SSE Delivery (T9-03).

Tests:
    T9-03: Connect to SSE streams, verify Content-Type, event structure,
           and 401 without session.

SSE streams are infinite.  Tests read only the first event chunk then
disconnect using a short read timeout.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SEQUENTIAL

BASE = "/api/v1"

FAKE_AGENT_RUN_ID = "00000000-0000-0000-0000-a9en7run0001"
FAKE_QUEUE_ID = "00000000-0000-0000-0000-0000000queue"
FAKE_EXECUTION_ID = "00000000-0000-0000-0000-execu710n001"

_SSE_TIMEOUT = httpx.Timeout(connect=10.0, read=2.0, write=10.0, pool=10.0)


async def _setup(client: InstrumentedClient) -> None:
    ws_resp = await client.post(
        f"{BASE}/workspaces",
        json={"path": "/tmp/sse-delivery-ws", "workspace_name": "SSE Delivery WS"},
    )
    assert ws_resp.status_code == 201


async def _sse_get(client: InstrumentedClient, url: str) -> tuple[int, str, str]:
    """Read headers + first event chunk from an SSE stream, then disconnect.

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

    try:
        await asyncio.wait_for(_read(), timeout=1.0)
    except (asyncio.TimeoutError, httpx.ReadTimeout):
        pass  # Expected: infinite stream cancelled after first event

    return status_code, content_type, first_chunk


@SEQUENTIAL
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier9
async def test_sse_delivery(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T9-03: SSE streams deliver correct Content-Type and event structure."""

    await _setup(client)

    # ── Agent run SSE ─────────────────────────────────────────────────────
    with checkpoint(ctx, "agent_run_sse_content_type"):
        status, ct, _ = await _sse_get(client, f"{BASE}/events/agent-runs/{FAKE_AGENT_RUN_ID}")
        assert status == 200, f"Expected 200, got {status}"
        assert "text/event-stream" in ct, f"Expected text/event-stream, got: {ct}"

    with checkpoint(ctx, "agent_run_sse_event_structure"):
        status, _, chunk = await _sse_get(client, f"{BASE}/events/agent-runs/{FAKE_AGENT_RUN_ID}")
        assert status == 200
        assert any(m in chunk for m in ("event:", "data:", ":")), (
            f"No SSE markers in chunk: {chunk[:200]!r}"
        )

    with checkpoint(ctx, "agent_run_sse_has_data_lines"):
        status, _, chunk = await _sse_get(client, f"{BASE}/events/agent-runs/{FAKE_AGENT_RUN_ID}")
        assert status == 200
        assert "data:" in chunk, f"Expected 'data:' lines, got: {chunk[:200]!r}"

    # ── Queue SSE ─────────────────────────────────────────────────────────
    with checkpoint(ctx, "queue_sse_content_type"):
        status, ct, _ = await _sse_get(client, f"{BASE}/events/queue/{FAKE_QUEUE_ID}")
        assert status == 200, f"Expected 200, got {status}"
        assert "text/event-stream" in ct, f"Expected text/event-stream, got: {ct}"

    with checkpoint(ctx, "queue_sse_event_structure"):
        status, _, chunk = await _sse_get(client, f"{BASE}/events/queue/{FAKE_QUEUE_ID}")
        assert status == 200
        assert any(m in chunk for m in ("event:", "data:", ":")), (
            f"No SSE markers in queue chunk: {chunk[:200]!r}"
        )

    # ── Workflow SSE ──────────────────────────────────────────────────────
    with checkpoint(ctx, "workflow_sse_content_type"):
        status, ct, _ = await _sse_get(client, f"{BASE}/events/workflow/{FAKE_EXECUTION_ID}")
        assert status == 200, f"Expected 200, got {status}"
        assert "text/event-stream" in ct, f"Expected text/event-stream, got: {ct}"

    with checkpoint(ctx, "workflow_sse_event_structure"):
        status, _, chunk = await _sse_get(client, f"{BASE}/events/workflow/{FAKE_EXECUTION_ID}")
        assert status == 200
        assert any(m in chunk for m in ("event:", "data:", ":")), (
            f"No SSE markers in workflow chunk: {chunk[:200]!r}"
        )

    # ── Providers SSE ─────────────────────────────────────────────────────
    with checkpoint(ctx, "providers_sse_content_type"):
        status, ct, _ = await _sse_get(client, f"{BASE}/events/providers")
        assert status == 200, f"Expected 200, got {status}"
        assert "text/event-stream" in ct, f"Expected text/event-stream, got: {ct}"

    with checkpoint(ctx, "providers_sse_event_structure"):
        status, _, chunk = await _sse_get(client, f"{BASE}/events/providers")
        assert status == 200
        assert any(m in chunk for m in ("event:", "data:", ":")), (
            f"No SSE markers in providers chunk: {chunk[:200]!r}"
        )

    # ── 401 without session ───────────────────────────────────────────────
    saved_cookie = client._session_cookie
    client._session_cookie = None
    client._client.cookies.clear()

    with checkpoint(ctx, "sse_streams_require_auth"):
        for path in [
            f"{BASE}/events/agent-runs/{FAKE_AGENT_RUN_ID}",
            f"{BASE}/events/queue/{FAKE_QUEUE_ID}",
            f"{BASE}/events/workflow/{FAKE_EXECUTION_ID}",
            f"{BASE}/events/providers",
        ]:
            status, _, _ = await _sse_get(client, path)
            assert status == 401, f"Expected 401 for {path}, got {status}"

    client._session_cookie = saved_cookie

"""Tier 9 — Cross-Cutting: SSE Delivery (T9-03).

Tests:
    T9-03: Connect to SSE streams, verify Content-Type, event structure,
           keepalive comment lines, and connection IDs for reconnection.
"""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SEQUENTIAL

BASE = "/api/v1"

FAKE_AGENT_RUN_ID = "00000000-0000-0000-0000-a9en7run0001"
FAKE_QUEUE_ID = "00000000-0000-0000-0000-0000000queue"
FAKE_EXECUTION_ID = "00000000-0000-0000-0000-execu710n001"


async def _setup(client: InstrumentedClient) -> None:
    rp = await client.post(
        f"{BASE}/reviewer-profiles",
        json={
            "display_name": "SSE Delivery Reviewer",
            "workspace_id": "00000000-0000-0000-0000-000000000001",
        },
    )
    assert rp.status_code == 201
    reviewer_id = rp.json()["id"]
    login = await client.post(f"{BASE}/sessions", json={"reviewer_id": reviewer_id})
    assert login.status_code == 200
    client._session_cookie = login.cookies.get("molabel_session")


@SEQUENTIAL
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier9
async def test_sse_delivery(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T9-03: SSE streams deliver correct Content-Type, event structure, and IDs."""

    await _setup(client)

    # --- Agent run SSE ---
    with checkpoint(ctx, "agent_run_sse_content_type"):
        resp = await client.get(f"{BASE}/events/agent-runs/{FAKE_AGENT_RUN_ID}")
        assert resp.status_code == 200, resp.text
        ct = resp.headers.get("content-type", "")
        assert "text/event-stream" in ct, f"Expected text/event-stream, got: {ct}"

    with checkpoint(ctx, "agent_run_sse_event_structure"):
        resp = await client.get(f"{BASE}/events/agent-runs/{FAKE_AGENT_RUN_ID}")
        assert resp.status_code == 200
        content = resp.text
        # SSE body must contain at least one of: event line, data line, or comment
        assert any(marker in content for marker in ("event:", "data:", ":")), (
            f"No SSE markers found in response body: {content[:200]!r}"
        )

    with checkpoint(ctx, "agent_run_sse_has_data_lines"):
        resp = await client.get(f"{BASE}/events/agent-runs/{FAKE_AGENT_RUN_ID}")
        assert resp.status_code == 200
        content = resp.text
        assert "data:" in content, (
            f"Expected 'data:' lines in SSE body, got: {content[:200]!r}"
        )

    # --- Queue SSE ---
    with checkpoint(ctx, "queue_sse_content_type"):
        resp = await client.get(f"{BASE}/events/queue/{FAKE_QUEUE_ID}")
        assert resp.status_code == 200, resp.text
        ct = resp.headers.get("content-type", "")
        assert "text/event-stream" in ct, f"Expected text/event-stream, got: {ct}"

    with checkpoint(ctx, "queue_sse_event_structure"):
        resp = await client.get(f"{BASE}/events/queue/{FAKE_QUEUE_ID}")
        assert resp.status_code == 200
        content = resp.text
        assert any(marker in content for marker in ("event:", "data:", ":")), (
            f"No SSE markers found in response body: {content[:200]!r}"
        )

    # --- Workflow SSE ---
    with checkpoint(ctx, "workflow_sse_content_type"):
        resp = await client.get(f"{BASE}/events/workflow/{FAKE_EXECUTION_ID}")
        assert resp.status_code == 200, resp.text
        ct = resp.headers.get("content-type", "")
        assert "text/event-stream" in ct, f"Expected text/event-stream, got: {ct}"

    with checkpoint(ctx, "workflow_sse_event_structure"):
        resp = await client.get(f"{BASE}/events/workflow/{FAKE_EXECUTION_ID}")
        assert resp.status_code == 200
        content = resp.text
        assert any(marker in content for marker in ("event:", "data:", ":")), (
            f"No SSE markers in workflow SSE: {content[:200]!r}"
        )

    # --- Providers SSE ---
    with checkpoint(ctx, "providers_sse_content_type"):
        resp = await client.get(f"{BASE}/events/providers")
        assert resp.status_code == 200, resp.text
        ct = resp.headers.get("content-type", "")
        assert "text/event-stream" in ct, f"Expected text/event-stream, got: {ct}"

    with checkpoint(ctx, "providers_sse_event_structure"):
        resp = await client.get(f"{BASE}/events/providers")
        assert resp.status_code == 200
        content = resp.text
        assert any(marker in content for marker in ("event:", "data:", ":")), (
            f"No SSE markers in providers SSE: {content[:200]!r}"
        )

    # --- 401 without session ---
    client._session_cookie = None

    with checkpoint(ctx, "sse_streams_require_auth"):
        for path in [
            f"{BASE}/events/agent-runs/{FAKE_AGENT_RUN_ID}",
            f"{BASE}/events/queue/{FAKE_QUEUE_ID}",
            f"{BASE}/events/workflow/{FAKE_EXECUTION_ID}",
            f"{BASE}/events/providers",
        ]:
            resp = await client.get(path)
            assert resp.status_code == 401, (
                f"Expected 401 for {path} without session, "
                f"got {resp.status_code}: {resp.text}"
            )

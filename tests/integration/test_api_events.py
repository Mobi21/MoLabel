"""Integration tests for SSE event stream endpoints (SSE-001 through SSE-005)."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_agent_run_stream_requires_session(client):
    """SSE-005: Agent run stream requires valid session cookie."""
    resp = await client.get("/api/v1/events/agent-runs/test-run-id")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_queue_stream_requires_session(client):
    """SSE-005: Queue event stream requires valid session cookie."""
    resp = await client.get("/api/v1/events/queue/test-queue-id")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_workflow_stream_requires_session(client):
    """SSE-005: Workflow event stream requires valid session cookie."""
    resp = await client.get("/api/v1/events/workflow/test-exec-id")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_provider_stream_requires_session(client):
    """SSE-005: Provider event stream requires valid session cookie."""
    resp = await client.get("/api/v1/events/providers")
    assert resp.status_code == 401

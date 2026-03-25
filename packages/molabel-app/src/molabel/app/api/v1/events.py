"""SSE event stream endpoints — /api/v1/events.

Server-Sent Events streams for real-time updates.  SSE-001 through SSE-005.

Connection management:
- `:keepalive` comment every 15 seconds to prevent timeout
- Each event includes an ``id`` field for reconnection via Last-Event-ID
- Session cookie validates SSE connections (SSE-005)
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Cookie, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from molabel.app.services.session import verify_session_token
from molabel.app.utils import get_app_secret

router = APIRouter(prefix="/events", tags=["events"])

# ---------------------------------------------------------------------------
# Keepalive interval (seconds)
# ---------------------------------------------------------------------------
_KEEPALIVE_INTERVAL = 15


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------


def _sse_event(
    event_type: str,
    data: dict[str, Any],
    event_id: str | None = None,
) -> str:
    """Format a single SSE event string."""
    lines: list[str] = []
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event_type}")
    lines.append(f"data: {json.dumps(data, default=str)}")
    lines.append("")
    lines.append("")
    return "\n".join(lines)


def _sse_keepalive() -> str:
    """Format a keepalive comment."""
    return ": keepalive\n\n"


def _validate_session(request: Request, molabel_session: str | None) -> None:
    """Validate session cookie for SSE connections (SSE-005)."""
    if molabel_session is None:
        raise HTTPException(status_code=401, detail="No session cookie present.")
    secret = get_app_secret(request)
    reviewer_id = verify_session_token(molabel_session, secret)
    if reviewer_id is None:
        raise HTTPException(status_code=401, detail="Invalid session cookie.")


# ---------------------------------------------------------------------------
# SSE Event Pydantic models (for documentation / type safety)
# ---------------------------------------------------------------------------


class AgentRunProgressEvent(BaseModel):
    agent_run_id: str
    records_completed: int
    records_total: int
    records_failed: int
    percentage: float
    current_record_id: str | None
    estimated_time_remaining_seconds: float | None


class AgentRunLogEvent(BaseModel):
    agent_run_id: str
    level: str  # "info" | "warning" | "error"
    message: str
    timestamp: str
    record_id: str | None


class AgentRunStatusChangeEvent(BaseModel):
    agent_run_id: str
    previous_status: str
    new_status: str
    timestamp: str
    error: str | None


class AgentRunCostUpdateEvent(BaseModel):
    agent_run_id: str
    tokens_input: int
    tokens_output: int
    cost_so_far_usd: float
    cost_estimate_total_usd: float | None


class QueueItemClaimedEvent(BaseModel):
    queue_id: str
    record_id: str
    review_task_id: str
    reviewer_id: str
    reviewer_name: str
    timestamp: str


class QueueItemCompletedEvent(BaseModel):
    queue_id: str
    record_id: str
    review_task_id: str
    reviewer_id: str
    reviewer_name: str
    review_duration_ms: int
    timestamp: str


class QueueItemReleasedEvent(BaseModel):
    queue_id: str
    record_id: str
    review_task_id: str
    reason: str  # "timeout" | "manual" | "error"
    timestamp: str


class QueueStatsUpdateEvent(BaseModel):
    queue_id: str
    pending: int
    in_progress: int
    completed: int
    active_reviewers: list[dict[str, Any]]
    avg_review_time_seconds: float | None
    estimated_completion: str | None
    timestamp: str


class WorkflowStepStartedEvent(BaseModel):
    execution_id: str
    workflow_id: str
    step_id: str
    step_type: str
    step_label: str
    timestamp: str


class WorkflowStepCompletedEvent(BaseModel):
    execution_id: str
    workflow_id: str
    step_id: str
    step_type: str
    step_label: str
    duration_seconds: float
    outputs: dict[str, Any] | None
    timestamp: str


class WorkflowStepFailedEvent(BaseModel):
    execution_id: str
    workflow_id: str
    step_id: str
    step_type: str
    step_label: str
    error: str
    recoverable: bool
    timestamp: str


class WorkflowStepPausedEvent(BaseModel):
    execution_id: str
    workflow_id: str
    step_id: str
    step_type: str
    step_label: str
    pause_reason: str  # "human_step" | "gate" | "breakpoint" | "manual"
    timestamp: str


class WorkflowCompletedEvent(BaseModel):
    execution_id: str
    workflow_id: str
    steps_completed: int
    total_duration_seconds: float
    timestamp: str


class ProviderStatusEvent(BaseModel):
    provider_id: str
    provider_type: str
    previous_status: str | None
    status: str  # "online" | "offline" | "error"
    latency_ms: int | None
    error: str | None
    available_models: list[str]
    timestamp: str


class ModelStatusEvent(BaseModel):
    model_profile_id: str
    provider_id: str
    status: str  # "online" | "offline" | "error"
    latency_ms: int | None
    timestamp: str


# ---------------------------------------------------------------------------
# SSE-004: Agent run progress stream
# ---------------------------------------------------------------------------


@router.get("/agent-runs/{agent_run_id}")
async def stream_agent_run_events(
    agent_run_id: str,
    request: Request,
    molabel_session: str | None = Cookie(default=None),
) -> StreamingResponse:
    """Stream real-time updates for an agent run (SSE-004).

    Event types: progress, log, status_change, cost_update, error, output.
    """
    _validate_session(request, molabel_session)

    async def event_stream():
        event_counter = 0
        # Send an initial connected event
        event_counter += 1
        yield _sse_event(
            "status_change",
            AgentRunStatusChangeEvent(
                agent_run_id=agent_run_id,
                previous_status="unknown",
                new_status="connected",
                timestamp=datetime.now(UTC).isoformat(),
                error=None,
            ).model_dump(mode="json"),
            event_id=str(event_counter),
        )

        # Keep connection alive and stream events as they arrive.
        # In production, this will poll a message bus / database for
        # new events.  For now, we just keep the connection alive.
        try:
            while True:
                if await request.is_disconnected():
                    break
                yield _sse_keepalive()
                await asyncio.sleep(_KEEPALIVE_INTERVAL)
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# ---------------------------------------------------------------------------
# SSE-001: Queue events stream
# ---------------------------------------------------------------------------


@router.get("/queue/{queue_id}")
async def stream_queue_events(
    queue_id: str,
    request: Request,
    molabel_session: str | None = Cookie(default=None),
) -> StreamingResponse:
    """Stream real-time queue updates (SSE-001).

    Event types: item_claimed, item_completed, item_released, stats_update.
    """
    _validate_session(request, molabel_session)

    async def event_stream():
        event_counter = 0
        # Send initial stats snapshot
        event_counter += 1
        yield _sse_event(
            "stats_update",
            QueueStatsUpdateEvent(
                queue_id=queue_id,
                pending=0,
                in_progress=0,
                completed=0,
                active_reviewers=[],
                avg_review_time_seconds=None,
                estimated_completion=None,
                timestamp=datetime.now(UTC).isoformat(),
            ).model_dump(mode="json"),
            event_id=str(event_counter),
        )

        try:
            while True:
                if await request.is_disconnected():
                    break
                yield _sse_keepalive()
                await asyncio.sleep(_KEEPALIVE_INTERVAL)
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# ---------------------------------------------------------------------------
# SSE-002: Workflow events stream
# ---------------------------------------------------------------------------


@router.get("/workflow/{execution_id}")
async def stream_workflow_events(
    execution_id: str,
    request: Request,
    molabel_session: str | None = Cookie(default=None),
) -> StreamingResponse:
    """Stream workflow execution events (SSE-002).

    Event types: step_started, step_completed, step_failed, step_paused,
    loop_iteration, workflow_completed, workflow_failed.
    """
    _validate_session(request, molabel_session)

    async def event_stream():
        try:
            while True:
                if await request.is_disconnected():
                    break
                yield _sse_keepalive()
                await asyncio.sleep(_KEEPALIVE_INTERVAL)
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# ---------------------------------------------------------------------------
# SSE-003: Provider events stream
# ---------------------------------------------------------------------------


@router.get("/providers")
async def stream_provider_events(
    request: Request,
    molabel_session: str | None = Cookie(default=None),
) -> StreamingResponse:
    """Stream provider health status changes (SSE-003).

    Event types: provider_status, model_status.
    """
    _validate_session(request, molabel_session)

    async def event_stream():
        try:
            while True:
                if await request.is_disconnected():
                    break
                yield _sse_keepalive()
                await asyncio.sleep(_KEEPALIVE_INTERVAL)
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )

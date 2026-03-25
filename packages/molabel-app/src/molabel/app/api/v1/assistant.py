"""Assistant endpoints -- /api/v1/assistant.

Provides the AI assistant backend with SSE streaming for real-time
responses and context retrieval for workspace-aware assistance.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from molabel.app.middleware.session import CurrentReviewer

router = APIRouter(prefix="/assistant", tags=["assistant"])


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------


class AssistantQuery(BaseModel):
    """Request body for an assistant query."""

    query: str
    screen: str
    record_id: str | None = None
    model_profile_id: str | None = None


class ContextReference(BaseModel):
    """A reference to context used by the assistant."""

    type: str
    id: str | None = None
    summary: str = ""


class SuggestedAction(BaseModel):
    """A suggested follow-up action from the assistant."""

    action_type: str
    label: str
    target: str | None = None
    params: dict[str, Any] | None = None


class AssistantResponse(BaseModel):
    """Full assistant response model (sent via SSE)."""

    response: str
    context_used: list[ContextReference] = []
    suggested_actions: list[SuggestedAction] = []
    model_profile_id: str = "none"
    tokens_used: int | None = None


class AssistantContext(BaseModel):
    """Current assistant context for the workspace."""

    workspace_summary: dict[str, Any] = {}
    active_workflow: dict[str, Any] | None = None
    queue_stats: dict[str, Any] | None = None
    recent_agent_runs: list[dict[str, Any]] = []
    recent_validation_results: list[dict[str, Any]] = []
    context_token_count: int = 0


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/query")
async def assistant_query(
    data: AssistantQuery,
    reviewer: CurrentReviewer,
) -> StreamingResponse:
    """Query the AI assistant (SSE streaming response).

    Returns a Server-Sent Events stream containing the assistant's
    response, context references, and suggested actions.
    """

    async def event_stream():  # type: ignore[return]
        response = AssistantResponse(
            response=(
                "Assistant is not yet configured. Please set up a model profile first."
            ),
            context_used=[],
            suggested_actions=[],
            model_profile_id=data.model_profile_id or "none",
            tokens_used=0,
        )
        yield f"data: {json.dumps(response.model_dump(mode='json'))}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.get("/context", response_model=AssistantContext)
async def get_assistant_context(
    reviewer: CurrentReviewer,
) -> AssistantContext:
    """Get the current assistant context for the workspace.

    Returns workspace summary, active workflow, queue stats, and
    recent agent runs to inform assistant responses.
    """
    return AssistantContext(
        workspace_summary={},
        active_workflow=None,
        queue_stats=None,
        recent_agent_runs=[],
        recent_validation_results=[],
        context_token_count=0,
    )

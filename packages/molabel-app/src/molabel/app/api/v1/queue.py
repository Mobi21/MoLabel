"""Queue claim endpoints (SE-006 through SE-010).

Handles queue claiming, review submission, skipping, draft saving,
queue status, and mission control reviewer visibility. Adjudication lives
in ``adjudication.py``.

Uses raw SQL queries via ``sqlalchemy.text()`` (through the claims service)
to avoid triggering SQLAlchemy mapper configuration for the full model graph.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from molabel.app.middleware.session import CurrentReviewer
from molabel.app.services.claims import (
    apply_blind_review_policy,
    claim_next,
    close_open_copies,
    get_queue_status,
    get_reviewer_task,
    get_reviewer_visibility,
    list_queues,
    pop_expired_notifications,
    queue_in_workspace,
    release_claim,
    reveal_ai,
    reviewer_queue_tasks,
    save_draft,
    skip_task,
    submit_correction,
    submit_review,
)
from molabel.app.utils import get_engine
from molabel.core.types import (
    CANONICAL_REVIEW_DECISION,
    DeprecatedReviewDecision,
    ReviewDecision,
)

router = APIRouter(tags=["queue"])


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------


class ReviewTaskResponse(BaseModel):
    """Response model for a single review task."""

    id: str
    queue_id: str
    record_id: str
    task_schema_id: str
    status: str
    priority: int
    priority_reason: str | None = None
    claimed_by: str | None = None
    claimed_at: str | None = None
    claim_expired_count: int = 0
    is_overlap: bool = False
    is_calibration: bool = False
    draft_labels: dict[str, Any] | None = None
    ai_revealed: bool = False
    ai_revealed_at: str | None = None
    submitted_at: str | None = None
    created_at: str
    updated_at: str
    workspace_id: str
    dataset_id: str

    model_config = {"from_attributes": True}


class AgentOutputResponse(BaseModel):
    """Response model for an agent output attached to a task."""

    id: str
    agent_run_id: str
    record_id: str
    task_schema_id: str
    output_type: str
    labels: dict[str, Any]
    raw_response: dict[str, Any] | None = None
    confidence_self_reported: float | None = None
    confidence_self_consistency: float | None = None
    confidence_logprobs: float | None = None
    composite_confidence: float | None = None
    tokens_input: int | None = None
    tokens_output: int | None = None
    latency_ms: int | None = None
    validation_passed: bool = True
    validation_errors: list[dict[str, Any]] | None = None
    created_at: str | None = None
    workspace_id: str


class BlindReviewTaskResponse(BaseModel):
    """Review task with blind review policy and optional agent output (RV-001)."""

    id: str
    queue_id: str
    record_id: str
    task_schema_id: str
    status: str
    priority: int
    priority_reason: str | None = None
    claimed_by: str | None = None
    claimed_at: str | None = None
    claim_expired_count: int = 0
    is_overlap: bool = False
    is_calibration: bool = False
    draft_labels: dict[str, Any] | None = None
    ai_revealed: bool = False
    ai_revealed_at: str | None = None
    submitted_at: str | None = None
    created_at: str
    updated_at: str
    workspace_id: str
    dataset_id: str
    record_external_id: str | None = None
    record_view: dict[str, Any] | None = None
    record_text: str | None = None
    agent_output: AgentOutputResponse | None = None
    blind_review_policy: str | None = None

    model_config = {"from_attributes": True}


class ClaimResponse(BaseModel):
    """Response for a claim operation (SE-006).

    Uses BlindReviewTaskResponse to include agent_output and
    blind_review_policy based on the task schema's policy (RV-001).
    """

    task: BlindReviewTaskResponse | None = None
    queue_empty: bool = False
    message: str = "claimed"


class SubmitRequest(BaseModel):
    """Request body for submitting a review."""

    labels: dict[str, Any] = Field(..., description="Review labels/annotations")
    decision: ReviewDecision | DeprecatedReviewDecision | Literal["skip"] | None = (
        Field(
            default=None,
            description=(
                "accept, edit, or reject. Deprecated aliases are normalized. "
                "The deprecated 'skip' skips the task like POST .../skip."
            ),
        )
    )
    rationale: str | None = Field(
        default=None, description="Optional reviewer rationale"
    )
    auto_claim_next: bool = Field(
        default=True, description="Automatically claim next item after submit"
    )


class SubmitResponse(BaseModel):
    """Response for a submit operation."""

    submitted_task: ReviewTaskResponse
    next_task: BlindReviewTaskResponse | None = None
    queue_empty: bool = False
    message: str = "submitted"
    deprecations: list[str] = Field(default_factory=list)


class SkipResponse(BaseModel):
    """Response for a skip operation."""

    skipped_task: ReviewTaskResponse
    next_task: BlindReviewTaskResponse | None = None
    queue_empty: bool = False
    message: str = "skipped"


class ReleaseResponse(BaseModel):
    """Response for a release operation."""

    task: ReviewTaskResponse
    message: str = "released"


class DraftRequest(BaseModel):
    """Request body for saving a draft (SE-009)."""

    draft_labels: dict[str, Any] = Field(
        ..., description="Draft labels to save (last-write-wins)"
    )


class DraftResponse(BaseModel):
    """Response for a draft save operation."""

    task: ReviewTaskResponse
    message: str = "draft_saved"


class RevealAIResponse(BaseModel):
    """Response for the AI reveal operation (RV-002)."""

    task: BlindReviewTaskResponse
    message: str = "ai_revealed"


class CorrectionRequest(BaseModel):
    """Request body for submitting a review correction (RV-004)."""

    labels: dict[str, Any] = Field(..., description="Corrected labels")
    decision: ReviewDecision | DeprecatedReviewDecision | None = Field(
        default=None,
        description="accept, edit, or reject. Deprecated aliases are normalized.",
    )
    rationale: str | None = Field(
        default=None, description="Rationale for the correction"
    )


class CorrectionEventResponse(BaseModel):
    """Response model for a review correction event."""

    id: str
    review_task_id: str
    record_id: str
    task_schema_id: str
    task_schema_version: int
    reviewer_id: str
    source: str
    decision: str | None = None
    labels: dict[str, Any]
    previous_labels: dict[str, Any] | None = None
    rationale: str | None = None
    ai_was_revealed: bool = False
    supersedes_event_id: str
    created_at: str
    workspace_id: str


class CorrectionResponse(BaseModel):
    """Response for a correction operation (RV-004)."""

    event: CorrectionEventResponse
    message: str = "correction_submitted"
    deprecations: list[str] = Field(default_factory=list)


class QueueActiveReviewer(BaseModel):
    """A reviewer currently working on a queue."""

    reviewer_id: str
    display_name: str
    avatar_color: str | None = None
    current_task_id: str
    current_record_id: str


class QueueSummary(BaseModel):
    """One review queue with its per-status task counts.

    ``kind`` names the workflow step that created the queue, or is None for
    a queue no workflow step created. ``closed`` counts the copies closed
    unreviewed. ``my_remaining`` and ``my_submitted`` count the caller's own
    work: records they can still claim or hold, and tasks they submitted.
    """

    queue_id: str
    workspace_id: str
    task_schema_id: str
    task_schema_title: str | None = None
    kind: Literal["review", "triage", "calibrate", "adjudicate"] | None = None
    blind_review_policy: str | None = None
    total: int
    available: int
    claimed: int
    submitted: int
    skipped: int
    closed: int = 0
    my_remaining: int = 0
    my_submitted: int = 0
    created_at: str


class QueueListResponse(BaseModel):
    """Response for listing review queues."""

    items: list[QueueSummary]


class ReviewerTaskSummary(BaseModel):
    """One task the caller claimed, submitted, or skipped in a queue."""

    task_id: str
    record_id: str
    record_external_id: str | None = None
    status: str
    decision: str | None = None
    submitted_at: str | None = None
    ai_revealed: bool = False


class ReviewerTasksResponse(BaseModel):
    """The caller's latest tasks in a queue, oldest first, a held claim last."""

    queue_id: str
    items: list[ReviewerTaskSummary]


class SubmittedReview(BaseModel):
    """The caller's counted review event for a task."""

    review_event_id: str
    decision: str | None = None
    labels: dict[str, Any]
    rationale: str | None = None
    ai_was_revealed: bool = False
    created_at: str


class ReviewItemResponse(BlindReviewTaskResponse):
    """A task the caller worked on, with the agent output their claim showed."""

    review: SubmittedReview | None = None


class QueueStatusResponse(BaseModel):
    """Response for queue status query."""

    queue_id: str
    total: int = 0
    available: int = 0
    claimed: int = 0
    submitted: int = 0
    skipped: int = 0
    closed: int = 0
    active_reviewers: list[QueueActiveReviewer] = []


class CloseCopiesResponse(BaseModel):
    """How many copies a close closed, and how many claimed ones stay open."""

    queue_id: str
    closed: int
    claimed: int


class ReviewerVisibility(BaseModel):
    """Reviewer status for mission control display (SE-010)."""

    reviewer_id: str
    display_name: str
    avatar_color: str | None = None
    is_operator: bool = False
    last_active_at: str | None = None
    status: str  # "active", "idle", "offline"
    completed_count: int = 0
    current_queue: str | None = None
    current_task_id: str | None = None


class MissionControlResponse(BaseModel):
    """Response for mission control reviewer visibility (SE-010)."""

    reviewers: list[ReviewerVisibility]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _add_notification_headers(
    response: Response,
    reviewer_id: uuid.UUID,
) -> None:
    """Check for and add claim expiry notification headers (SE-008).

    If the reviewer had claims that expired while offline, adds the
    X-MoLabel-Notification header so the frontend can display a toast.
    """
    notifications = pop_expired_notifications(reviewer_id)
    if notifications:
        response.headers["X-MoLabel-Notification"] = "claim_expired"
        # Include count for the frontend to know how many expired.
        response.headers["X-MoLabel-Expired-Count"] = str(len(notifications))


def _canonical_decision(
    decision: ReviewDecision | DeprecatedReviewDecision | None,
) -> tuple[ReviewDecision | None, list[str]]:
    """Map a deprecated decision name to its canonical decision."""
    if not isinstance(decision, DeprecatedReviewDecision):
        return decision, []
    canonical = CANONICAL_REVIEW_DECISION[decision]
    return canonical, [
        f"Decision '{decision.value}' is deprecated; use '{canonical.value}'. "
        "Whether the AI suggestion was shown is recorded as ai_revealed."
    ]


# ---------------------------------------------------------------------------
# SE-006: Queue claim endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/queues/{queue_id}/claim",
    response_model=ClaimResponse,
)
async def claim_next_item(
    request: Request,
    response: Response,
    queue_id: str,
    reviewer: CurrentReviewer,
) -> ClaimResponse:
    """Claim the next available item from a queue (SE-006).

    Atomic claim using UPDATE...WHERE...(SELECT...LIMIT 1) pattern.
    One-item-at-a-time claims only, no bulk claim hoarding.

    Returns the claimed task, or queue_empty=True if no items available.
    Also checks for any expired claim notifications (SE-008).
    """
    engine = get_engine(request)

    # Check for expired claim notifications before claiming.
    _add_notification_headers(response, reviewer.id)

    task = claim_next(engine, queue_id, reviewer.id)

    if task is None:
        return ClaimResponse(task=None, queue_empty=True, message="queue_empty")

    # RV-001: Apply blind review policy to strip/include agent output.
    task = apply_blind_review_policy(engine, task)

    return ClaimResponse(
        task=BlindReviewTaskResponse(**task),
        queue_empty=False,
        message="claimed",
    )


# ---------------------------------------------------------------------------
# Submit / skip / release / draft endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/review-tasks/{task_id}/submit",
    response_model=SubmitResponse,
)
async def submit_review_endpoint(
    request: Request,
    response: Response,
    task_id: uuid.UUID,
    body: SubmitRequest,
    reviewer: CurrentReviewer,
) -> SubmitResponse:
    """Submit a review for a claimed task.

    Optionally auto-claims the next item from the same queue.
    """
    engine = get_engine(request)

    _add_notification_headers(response, reviewer.id)

    if body.decision == "skip":
        submitted = skip_task(engine, task_id, reviewer.id)
        message = "skipped"
        deprecations = [
            "Decision 'skip' is deprecated; use POST /review-tasks/{task_id}/skip "
            "(molabel review skip). The task was skipped and its labels and "
            "rationale were not stored."
        ]
    else:
        decision, deprecations = _canonical_decision(body.decision)
        try:
            submitted = submit_review(
                engine,
                task_id,
                reviewer.id,
                body.labels,
                decision,
                body.rationale,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        message = "submitted"

    if submitted is None:
        raise HTTPException(
            status_code=409,
            detail="Task not found or not claimed by you",
        )

    submitted_task = ReviewTaskResponse(**submitted)

    # Auto-claim next if requested.
    next_task_resp = None
    queue_empty = False
    if body.auto_claim_next:
        next_task = claim_next(engine, submitted["queue_id"], reviewer.id)
        if next_task is None:
            queue_empty = True
        else:
            next_task = apply_blind_review_policy(engine, next_task)
            next_task_resp = BlindReviewTaskResponse(**next_task)

    return SubmitResponse(
        submitted_task=submitted_task,
        next_task=next_task_resp,
        queue_empty=queue_empty,
        message=message,
        deprecations=deprecations,
    )


@router.post(
    "/review-tasks/{task_id}/skip",
    response_model=SkipResponse,
)
async def skip_task_endpoint(
    request: Request,
    response: Response,
    task_id: uuid.UUID,
    reviewer: CurrentReviewer,
) -> SkipResponse:
    """Skip a claimed task, returning it to the queue.

    Automatically claims the next available item.
    """
    engine = get_engine(request)

    _add_notification_headers(response, reviewer.id)

    skipped = skip_task(engine, task_id, reviewer.id)

    if skipped is None:
        raise HTTPException(
            status_code=409,
            detail="Task not found or not claimed by you",
        )

    skipped_task = ReviewTaskResponse(**skipped)

    # Auto-claim next.
    next_task = claim_next(engine, skipped["queue_id"], reviewer.id)
    next_task_resp = None
    queue_empty = False
    if next_task is None:
        queue_empty = True
    else:
        next_task = apply_blind_review_policy(engine, next_task)
        next_task_resp = BlindReviewTaskResponse(**next_task)

    return SkipResponse(
        skipped_task=skipped_task,
        next_task=next_task_resp,
        queue_empty=queue_empty,
        message="skipped",
    )


@router.post(
    "/review-tasks/{task_id}/release",
    response_model=ReleaseResponse,
)
async def release_claim_endpoint(
    request: Request,
    response: Response,
    task_id: uuid.UUID,
    reviewer: CurrentReviewer,
) -> ReleaseResponse:
    """Release a claim on a task back to the available pool."""
    engine = get_engine(request)

    _add_notification_headers(response, reviewer.id)

    released = release_claim(engine, task_id, reviewer.id)

    if released is None:
        raise HTTPException(
            status_code=409,
            detail="Task not found or not claimed by you",
        )

    return ReleaseResponse(
        task=ReviewTaskResponse(**released),
        message="released",
    )


@router.post(
    "/review-tasks/{task_id}/draft",
    response_model=DraftResponse,
)
async def save_draft_endpoint(
    request: Request,
    response: Response,
    task_id: uuid.UUID,
    body: DraftRequest,
    reviewer: CurrentReviewer,
) -> DraftResponse:
    """Save draft labels for a claimed task (SE-009: last-write-wins).

    In same-profile multi-session scenarios, the later save overwrites
    the earlier one. No conflict resolution is attempted.
    """
    engine = get_engine(request)

    _add_notification_headers(response, reviewer.id)

    updated = save_draft(engine, task_id, reviewer.id, body.draft_labels)

    if updated is None:
        raise HTTPException(
            status_code=409,
            detail="Task not found or not claimed by you",
        )

    return DraftResponse(
        task=ReviewTaskResponse(**updated),
        message="draft_saved",
    )


# ---------------------------------------------------------------------------
# RV-002: AI reveal endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/review-tasks/{task_id}/reveal-ai",
    response_model=RevealAIResponse,
)
async def reveal_ai_endpoint(
    request: Request,
    response: Response,
    task_id: uuid.UUID,
    reviewer: CurrentReviewer,
) -> RevealAIResponse:
    """Reveal agent output for a claimed task (RV-002).

    Verifies the task is claimed by the requesting reviewer, checks
    the blind_review_policy allows reveal, and sets ai_revealed=True
    with a timestamp. Returns the task with agent output included.
    """
    engine = get_engine(request)

    _add_notification_headers(response, reviewer.id)

    result = reveal_ai(engine, task_id, reviewer.id)

    if result is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Task not found, not claimed by you, "
                "or reveal not allowed by blind review policy"
            ),
        )

    return RevealAIResponse(
        task=BlindReviewTaskResponse(**result),
        message="ai_revealed",
    )


# ---------------------------------------------------------------------------
# RV-004: Correction endpoint (append-only)
# ---------------------------------------------------------------------------


@router.post(
    "/review-tasks/{task_id}/correct",
    response_model=CorrectionResponse,
)
async def submit_correction_endpoint(
    request: Request,
    response: Response,
    task_id: uuid.UUID,
    body: CorrectionRequest,
    reviewer: CurrentReviewer,
) -> CorrectionResponse:
    """Submit a correction for a previously reviewed task (RV-004).

    Creates a new review_event with supersedes_event_id pointing to the
    most recent event. Never updates or deletes the original event,
    preserving the append-only audit trail.
    """
    engine = get_engine(request)

    _add_notification_headers(response, reviewer.id)
    decision, deprecations = _canonical_decision(body.decision)

    try:
        result = submit_correction(
            engine,
            task_id,
            reviewer.id,
            body.labels,
            decision,
            body.rationale,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if result is None:
        raise HTTPException(
            status_code=409,
            detail="Task not found, not owned by you, or no prior review event exists",
        )

    return CorrectionResponse(
        event=CorrectionEventResponse(**result),
        message="correction_submitted",
        deprecations=deprecations,
    )


# ---------------------------------------------------------------------------
# Queue status
# ---------------------------------------------------------------------------


@router.get("/queues", response_model=QueueListResponse)
async def list_queues_endpoint(
    request: Request,
    response: Response,
    reviewer: CurrentReviewer,
    workspace_id: str | None = None,
) -> QueueListResponse:
    """List review queues, optionally limited to one workspace."""
    _add_notification_headers(response, reviewer.id)
    queues = list_queues(get_engine(request), workspace_id, reviewer.id)
    return QueueListResponse(items=[QueueSummary(**queue) for queue in queues])


@router.get("/queues/{queue_id}/my-tasks", response_model=ReviewerTasksResponse)
async def list_my_queue_tasks_endpoint(
    request: Request,
    queue_id: str,
    reviewer: CurrentReviewer,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> ReviewerTasksResponse:
    """List the caller's latest tasks in a queue, to step back through them."""
    engine = get_engine(request)
    if not queue_in_workspace(engine, queue_id, reviewer.workspace_id):
        raise HTTPException(status_code=404, detail="Review queue not found")
    items = reviewer_queue_tasks(engine, queue_id, reviewer.id, limit)
    return ReviewerTasksResponse(
        queue_id=queue_id,
        items=[ReviewerTaskSummary(**item) for item in items],
    )


@router.get("/review-tasks/{task_id}", response_model=ReviewItemResponse)
async def get_review_task_endpoint(
    request: Request,
    task_id: uuid.UUID,
    reviewer: CurrentReviewer,
) -> ReviewItemResponse:
    """Read a task the caller claimed, submitted, or skipped.

    It shows the agent output the claim or reveal showed, so a read never
    reveals a blind proposal, and the caller's counted review event.
    """
    task = get_reviewer_task(
        get_engine(request), task_id, reviewer.id, reviewer.workspace_id
    )
    if task is None:
        raise HTTPException(status_code=404, detail="Review task not found")
    return ReviewItemResponse(**task)


@router.get(
    "/queues/{queue_id}/status",
    response_model=QueueStatusResponse,
)
async def get_queue_status_endpoint(
    request: Request,
    response: Response,
    queue_id: str,
    reviewer: CurrentReviewer,
) -> QueueStatusResponse:
    """Get queue status including item counts and active reviewers."""
    engine = get_engine(request)

    _add_notification_headers(response, reviewer.id)

    status = get_queue_status(engine, queue_id)

    return QueueStatusResponse(
        queue_id=status["queue_id"],
        total=status["total"],
        available=status["available"],
        claimed=status["claimed"],
        submitted=status["submitted"],
        skipped=status["skipped"],
        closed=status["closed"],
        active_reviewers=[QueueActiveReviewer(**r) for r in status["active_reviewers"]],
    )


@router.post("/queues/{queue_id}/close-copies", response_model=CloseCopiesResponse)
async def close_queue_copies(
    request: Request,
    queue_id: str,
    reviewer: CurrentReviewer,
) -> CloseCopiesResponse:
    """Close every unclaimed copy of a queue, so its review ends with the copies in.

    A queue with more copies of a record than reviewers keeps the extra copies
    available, and no reviewer gets two copies of one record. Closing them
    lets adjudication list the record and the workflow's ``human_review``
    step advance. A closed copy is never reviewed and never counts as a
    rater. A claimed copy stays open, because a reviewer holds it. A queue of
    another workspace answers 404.
    """
    engine = get_engine(request)
    if not queue_in_workspace(engine, queue_id, reviewer.workspace_id):
        raise HTTPException(status_code=404, detail="Review queue not found")
    return CloseCopiesResponse(queue_id=queue_id, **close_open_copies(engine, queue_id))


# ---------------------------------------------------------------------------
# SE-010: Mission control reviewer visibility
# ---------------------------------------------------------------------------


@router.get(
    "/mission-control/reviewers",
    response_model=MissionControlResponse,
)
async def get_mission_control_reviewers(
    request: Request,
    response: Response,
    reviewer: CurrentReviewer,
) -> MissionControlResponse:
    """Get reviewer visibility for mission control (SE-010).

    Returns all active reviewer profiles with their status:
    - Active: last_active_at within 5 minutes
    - Idle: last_active_at 5-30 minutes ago
    - Offline: last_active_at > 30 minutes or null

    Also includes current queue positions for active reviewers.
    """
    engine = get_engine(request)

    _add_notification_headers(response, reviewer.id)

    visibility = get_reviewer_visibility(engine, reviewer.workspace_id)

    return MissionControlResponse(
        reviewers=[ReviewerVisibility(**r) for r in visibility],
    )

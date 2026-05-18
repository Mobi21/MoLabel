"""Queue claim endpoints (SE-006 through SE-010) and adjudication.

Handles queue claiming, review submission, skipping, draft saving,
queue status, mission control reviewer visibility, and adjudication
(AJ-001 through AJ-007).

Uses raw SQL queries via ``sqlalchemy.text()`` (through the claims service)
to avoid triggering SQLAlchemy mapper configuration for the full model graph.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from molabel.app.middleware.session import CurrentReviewer
from molabel.app.services.claims import (
    apply_blind_review_policy,
    claim_next,
    get_queue_status,
    get_reviewer_visibility,
    pop_expired_notifications,
    release_claim,
    reveal_ai,
    save_draft,
    skip_task,
    submit_correction,
    submit_review,
)
from molabel.app.utils import get_engine
from molabel.core.adjudication.adjudication_service import (
    AdjudicationQueueItem as AdjQueueItem,
)
from molabel.core.adjudication.adjudication_service import (
    AdjudicationService,
)
from molabel.core.types import AdjudicationResolution, ReviewDecision

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
    decision: ReviewDecision | None = Field(
        default=None, description="Optional review decision (accept/reject/etc.)"
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
    decision: ReviewDecision | None = Field(
        default=None, description="Updated review decision"
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


class QueueActiveReviewer(BaseModel):
    """A reviewer currently working on a queue."""

    reviewer_id: str
    display_name: str
    avatar_color: str | None = None
    current_task_id: str
    current_record_id: str


class QueueStatusResponse(BaseModel):
    """Response for queue status query."""

    queue_id: str
    total: int = 0
    available: int = 0
    claimed: int = 0
    submitted: int = 0
    skipped: int = 0
    active_reviewers: list[QueueActiveReviewer] = []


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

    try:
        submitted = submit_review(
            engine,
            task_id,
            reviewer.id,
            body.labels,
            body.decision,
            body.rationale,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

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
        message="submitted",
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

    try:
        result = submit_correction(
            engine,
            task_id,
            reviewer.id,
            body.labels,
            body.decision,
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
    )


# ---------------------------------------------------------------------------
# Queue status
# ---------------------------------------------------------------------------


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
        active_reviewers=[QueueActiveReviewer(**r) for r in status["active_reviewers"]],
    )


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


# ---------------------------------------------------------------------------
# Adjudication Pydantic models (AJ-001 through AJ-007)
# ---------------------------------------------------------------------------


class DisagreementResponse(BaseModel):
    """Response model for a detected disagreement."""

    record_id: str
    task_schema_id: str
    conflicting_event_ids: list[str]
    disagreement_type: str
    fields_in_conflict: list[str]
    reviewer_labels: dict[str, dict[str, Any]] = {}


class AdjudicationQueueItemResponse(BaseModel):
    """Response model for an adjudication queue item."""

    id: str
    record_id: str
    task_schema_id: str
    disagreement: DisagreementResponse
    severity: str
    adjudication_type: str
    created_at: str
    resolved: bool = False


class AdjudicationQueueResponse(BaseModel):
    """Response for the full adjudication queue."""

    items: list[AdjudicationQueueItemResponse]
    total: int = 0
    unresolved: int = 0


class DetectDisagreementsRequest(BaseModel):
    """Request body for disagreement detection."""

    review_events_by_record: dict[str, list[dict[str, Any]]] = Field(
        ...,
        description="Mapping of record_id -> list of review event dicts",
    )
    task_schema_id: str = Field(..., description="Task schema ID for these events")


class DetectDisagreementsResponse(BaseModel):
    """Response for disagreement detection."""

    disagreements: list[DisagreementResponse]
    total: int = 0


class ResolveRequest(BaseModel):
    """Request body for adjudication resolution."""

    queue_item_id: str = Field(..., description="Adjudication queue item ID")
    resolution: AdjudicationResolution = Field(..., description="Resolution type")
    resolved_labels: dict[str, Any] | None = Field(
        default=None, description="Resolved labels (required for 'resolve')"
    )
    rationale: str | None = Field(
        default=None, description="Rationale for the resolution"
    )


class ResolveResponse(BaseModel):
    """Response for an adjudication resolution."""

    adjudication_id: str
    record_id: str
    resolution: str
    resolved_labels: dict[str, Any] | None = None
    rationale: str | None = None
    review_event_id: str | None = None
    message: str = "resolved"


class FieldComparisonResponse(BaseModel):
    """Response model for a single field comparison."""

    field_name: str
    sources: list[dict[str, Any]]
    is_in_conflict: bool


class ComparisonResponse(BaseModel):
    """Response for side-by-side comparison data."""

    record_id: str
    task_schema_id: str
    field_comparisons: list[FieldComparisonResponse]
    event_ids: list[str]


class BuildQueueRequest(BaseModel):
    """Request body for building an adjudication queue from disagreements."""

    disagreements: list[dict[str, Any]] = Field(
        ..., description="List of disagreement dicts from detect endpoint"
    )


# ---------------------------------------------------------------------------
# Adjudication endpoint helpers
# ---------------------------------------------------------------------------


def _disagreement_to_response(d: Any) -> DisagreementResponse:
    """Convert a Disagreement dataclass to a response model."""
    return DisagreementResponse(
        record_id=str(d.record_id),
        task_schema_id=str(d.task_schema_id),
        conflicting_event_ids=[str(eid) for eid in d.conflicting_event_ids],
        disagreement_type=d.disagreement_type.value,
        fields_in_conflict=d.fields_in_conflict,
        reviewer_labels=d.reviewer_labels,
    )


def _queue_item_to_response(item: AdjQueueItem) -> AdjudicationQueueItemResponse:
    """Convert an AdjudicationQueueItem to a response model."""
    return AdjudicationQueueItemResponse(
        id=str(item.id),
        record_id=str(item.record_id),
        task_schema_id=str(item.task_schema_id),
        disagreement=_disagreement_to_response(item.disagreement),
        severity=item.severity.value,
        adjudication_type=item.adjudication_type.value,
        created_at=item.created_at,
        resolved=item.resolved,
    )


# Store adjudication service instances keyed by workspace.
# NOTE: This dict is per-process. In a multi-worker deployment (e.g.
# gunicorn with N workers), each worker has its own adjudication state.
# Acceptable for local-first / Tauri single-worker deployments. For
# multi-worker, move state to the database or use FastAPI DI with a
# shared lifecycle scope.
_adjudication_services: dict[str, AdjudicationService] = {}


def _get_adjudication_service(workspace_id: str) -> AdjudicationService:
    """Get or create an adjudication service for a workspace."""
    if workspace_id not in _adjudication_services:
        _adjudication_services[workspace_id] = AdjudicationService()
    return _adjudication_services[workspace_id]


# ---------------------------------------------------------------------------
# Adjudication endpoints (AJ-001 through AJ-007)
# ---------------------------------------------------------------------------


@router.post(
    "/adjudication/detect",
    response_model=DetectDisagreementsResponse,
)
async def detect_disagreements_endpoint(
    request: Request,
    response: Response,
    body: DetectDisagreementsRequest,
    reviewer: CurrentReviewer,
) -> DetectDisagreementsResponse:
    """Detect disagreements in review events (AJ-001).

    Compares review events for overlapping records and identifies both
    human-human and human-agent disagreements at the field level.
    """
    _add_notification_headers(response, reviewer.id)

    workspace_id = str(reviewer.workspace_id) if reviewer.workspace_id else "default"
    service = _get_adjudication_service(workspace_id)

    task_schema_id = uuid.UUID(body.task_schema_id)
    disagreements = service.detect_disagreements(
        body.review_events_by_record, task_schema_id
    )

    return DetectDisagreementsResponse(
        disagreements=[_disagreement_to_response(d) for d in disagreements],
        total=len(disagreements),
    )


@router.post(
    "/adjudication/queue/build",
    response_model=AdjudicationQueueResponse,
)
async def build_adjudication_queue_endpoint(
    request: Request,
    response: Response,
    body: DetectDisagreementsRequest,
    reviewer: CurrentReviewer,
) -> AdjudicationQueueResponse:
    """Detect disagreements and build an adjudication queue (AJ-001, AJ-002).

    Detects disagreements, classifies severity and type, and builds a
    prioritized adjudication queue.
    """
    _add_notification_headers(response, reviewer.id)

    workspace_id = str(reviewer.workspace_id) if reviewer.workspace_id else "default"
    service = _get_adjudication_service(workspace_id)

    task_schema_id = uuid.UUID(body.task_schema_id)
    disagreements = service.detect_disagreements(
        body.review_events_by_record, task_schema_id
    )
    queue = service.build_queue(disagreements)

    return AdjudicationQueueResponse(
        items=[_queue_item_to_response(item) for item in queue],
        total=len(queue),
        unresolved=len([i for i in queue if not i.resolved]),
    )


@router.get(
    "/adjudication/queue",
    response_model=AdjudicationQueueResponse,
)
async def get_adjudication_queue_endpoint(
    request: Request,
    response: Response,
    reviewer: CurrentReviewer,
) -> AdjudicationQueueResponse:
    """Get the current adjudication queue (AJ-002)."""
    _add_notification_headers(response, reviewer.id)

    workspace_id = str(reviewer.workspace_id) if reviewer.workspace_id else "default"
    service = _get_adjudication_service(workspace_id)

    queue = service.get_queue()
    unresolved = service.get_unresolved_queue()

    return AdjudicationQueueResponse(
        items=[_queue_item_to_response(item) for item in queue],
        total=len(queue),
        unresolved=len(unresolved),
    )


@router.post(
    "/adjudication/resolve",
    response_model=ResolveResponse,
)
async def resolve_adjudication_endpoint(
    request: Request,
    response: Response,
    body: ResolveRequest,
    reviewer: CurrentReviewer,
) -> ResolveResponse:
    """Resolve an adjudication queue item (AJ-003, AJ-007).

    Applies a resolution and creates a review event for the audit trail.
    """
    _add_notification_headers(response, reviewer.id)

    workspace_id = str(reviewer.workspace_id) if reviewer.workspace_id else "default"
    service = _get_adjudication_service(workspace_id)

    try:
        result = service.resolve(
            queue_item_id=uuid.UUID(body.queue_item_id),
            adjudicator_id=reviewer.id,
            resolution=body.resolution,
            resolved_labels=body.resolved_labels,
            rationale=body.rationale,
            workspace_id=reviewer.workspace_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    resolved_labels = (
        result.resolved_labels.labels if result.resolved_labels is not None else None
    )

    return ResolveResponse(
        adjudication_id=str(result.adjudication_id),
        record_id=str(result.record_id),
        resolution=result.resolution.value,
        resolved_labels=resolved_labels,
        rationale=result.rationale,
        review_event_id=(
            str(result.review_event_id) if result.review_event_id else None
        ),
        message="resolved",
    )

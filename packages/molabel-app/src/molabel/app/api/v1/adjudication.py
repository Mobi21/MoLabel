"""Adjudication of a review queue's disagreements -- /api/v1/adjudication/queues.

A disagreement is derived on every read from the queue's counted review
events, the values agreement rates. A resolution is an ``adjudications`` row.
Resolving with labels also appends a review event with no review task (AJ-007),
so it never counts as a rater, and makes those labels the record's latest
label, which export reads. Both rows take the queue's workspace.

A record is adjudicated only once every review task the queue holds for it is
submitted or skipped. While a copy is available or claimed, its disagreement is
not listed and its detail answers 404. So no reviewer sees the other
reviewers' labels, or on a blind queue the agent proposal, before their own
review of the record is in.

Every endpoint reads only a queue of the caller's workspace, and answers 404
for a queue of any other.

The detect, build, queue, and resolve endpoints in ``queue.py`` take review
events from the caller and keep nothing. The CLI's adjudication commands use
them.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import bindparam, text

from molabel.app.middleware.session import CurrentReviewer
from molabel.app.services.claims import (
    load_task_schema_version,
    prepare_review_labels,
    reviewer_record_context,
)
from molabel.app.services.review_events import json_object, queue_review_events
from molabel.app.utils import get_engine, parse_bool
from molabel.core.adjudication.adjudication_service import (
    AdjudicationQueueItem,
    disagreements_from_reviews,
)
from molabel.core.agents.queue_binding import deserialize_agent_output_ids
from molabel.core.types import (
    AdjudicationResolution,
    ReviewEventSource,
    canonical_review_decision,
)

router = APIRouter(prefix="/adjudication", tags=["adjudication"])


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------


class ReviewerLabelSet(BaseModel):
    """The labels one reviewer's counted review event gives the record."""

    reviewer_id: str
    reviewer_name: str
    review_event_id: str
    decision: str | None = None
    labels: dict[str, Any]
    rationale: str | None = None
    ai_was_revealed: bool = False
    created_at: str


class AgentLabelSet(BaseModel):
    """An agent proposal the record's review tasks are bound to."""

    agent_output_id: str
    agent_run_id: str
    labels: dict[str, Any]
    confidence: float | None = None


class FieldDisagreement(BaseModel):
    """One field in conflict, with each reviewer's value by reviewer ID."""

    field_name: str
    values: dict[str, Any]


class AdjudicationOutcome(BaseModel):
    """A stored resolution of the disagreement."""

    adjudication_id: str
    resolution: AdjudicationResolution
    resolved_labels: dict[str, Any] | None = None
    rationale: str | None = None
    adjudicator_id: str
    adjudicator_name: str | None = None
    review_event_id: str | None = None
    resolved_at: str


class DisagreementSummary(BaseModel):
    """A record whose reviewers gave different values on some field."""

    record_id: str
    record_external_id: str | None = None
    task_schema_id: str
    dataset_id: str
    severity: str
    adjudication_type: str
    fields_in_conflict: list[str]
    reviewer_count: int
    status: Literal["pending", "resolved"]
    adjudication_id: str | None = None


class DisagreementQueue(BaseModel):
    """A queue's disagreements, most severe first."""

    queue_id: str
    items: list[DisagreementSummary]
    total: int
    unresolved: int


class DisagreementDetail(DisagreementSummary):
    """A disagreement with the record, every reviewer's labels, and its outcome."""

    record_view: dict[str, Any] | None = None
    record_text: str | None = None
    reviewer_labels: list[ReviewerLabelSet]
    agent_labels: list[AgentLabelSet]
    disagreeing_fields: list[FieldDisagreement]
    resolution: AdjudicationOutcome | None = None


class ResolveDisagreement(BaseModel):
    """Request body for resolving a disagreement."""

    resolution: AdjudicationResolution = Field(
        default=AdjudicationResolution.resolve,
        description="resolve takes resolved_labels as the record's labels",
    )
    resolved_labels: dict[str, Any] | None = Field(
        default=None, description="Required for resolve"
    )
    rationale: str | None = None
    review_event_ids: list[str] = Field(
        description=(
            "The review_event_id of each reviewer_labels entry as read. 409 when "
            "the disagreement's review events differ, so the caller reloads it"
        )
    )


# ---------------------------------------------------------------------------
# Reading a queue's disagreements
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Queue:
    queue_id: str
    workspace_id: str
    task_schema_id: str


def _queue(conn: Any, queue_id: str, workspace_id: uuid.UUID) -> _Queue:
    row = conn.execute(
        text(
            "SELECT workspace_id, task_schema_id FROM review_tasks "
            "WHERE queue_id = :q AND workspace_id = :w LIMIT 1"
        ),
        {"q": queue_id, "w": str(workspace_id)},
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Review queue not found")
    return _Queue(queue_id, str(row[0]), str(row[1]))


@dataclass(frozen=True)
class _Disagreement:
    item: AdjudicationQueueItem
    record_external_id: str | None
    dataset_id: str
    outcome: AdjudicationOutcome | None

    @property
    def event_ids(self) -> set[str]:
        return {
            str(event_id) for event_id in self.item.disagreement.conflicting_event_ids
        }

    def summary(self) -> dict[str, Any]:
        return {
            "record_id": str(self.item.record_id),
            "record_external_id": self.record_external_id,
            "task_schema_id": str(self.item.task_schema_id),
            "dataset_id": self.dataset_id,
            "severity": self.item.severity.value,
            "adjudication_type": self.item.adjudication_type.value,
            "fields_in_conflict": self.item.disagreement.fields_in_conflict,
            "reviewer_count": len(self.item.disagreement.reviewer_labels),
            "status": "pending" if self.outcome is None else "resolved",
            "adjudication_id": self.outcome.adjudication_id if self.outcome else None,
        }


def _expanding(sql: str, name: str) -> Any:
    return text(sql).bindparams(bindparam(name, expanding=True))


def _outcomes_by_record(
    conn: Any, task_schema_id: str, record_ids: list[str]
) -> dict[str, list[tuple[set[str], AdjudicationOutcome]]]:
    rows = conn.execute(
        _expanding(
            "SELECT a.id, a.record_id, a.resolution, a.resolved_labels, "
            "a.rationale, a.adjudicator_id, p.display_name, a.metadata, "
            "a.created_at, a.conflicting_event_ids "
            "FROM adjudications a "
            "LEFT JOIN reviewer_profiles p ON p.id = a.adjudicator_id "
            "WHERE a.task_schema_id = :task_schema_id "
            "AND a.record_id IN :record_ids ORDER BY a.created_at",
            "record_ids",
        ),
        {"task_schema_id": task_schema_id, "record_ids": record_ids},
    ).fetchall()
    outcomes: dict[str, list[tuple[set[str], AdjudicationOutcome]]] = {}
    for row in rows:
        raw_ids = row[9]
        event_ids = json.loads(raw_ids) if isinstance(raw_ids, str) else raw_ids
        resolved_labels = json_object(row[3]) if row[3] is not None else None
        outcomes.setdefault(str(row[1]), []).append(
            (
                {str(event_id) for event_id in event_ids or []},
                AdjudicationOutcome(
                    adjudication_id=str(row[0]),
                    resolution=AdjudicationResolution(str(row[2])),
                    resolved_labels=resolved_labels,
                    rationale=row[4],
                    adjudicator_id=str(row[5]),
                    adjudicator_name=str(row[6]) if row[6] else None,
                    review_event_id=json_object(row[7]).get("review_event_id"),
                    resolved_at=str(row[8]),
                ),
            )
        )
    return outcomes


def _queue_disagreements(conn: Any, queue: _Queue) -> list[_Disagreement]:
    open_records = {
        str(record_id)
        for (record_id,) in conn.execute(
            text(
                "SELECT DISTINCT record_id FROM review_tasks WHERE queue_id = :q "
                "AND status IN ('available', 'claimed')"
            ),
            {"q": queue.queue_id},
        ).fetchall()
    }
    items = [
        item
        for item in disagreements_from_reviews(
            queue_review_events(conn, [queue.queue_id]),
            uuid.UUID(queue.task_schema_id),
        )
        if str(item.record_id) not in open_records
    ]
    record_ids = [str(item.record_id) for item in items]
    records = {
        str(row[0]): (str(row[1]) if row[1] else None, str(row[2]))
        for row in conn.execute(
            _expanding(
                "SELECT id, external_id, dataset_id FROM records WHERE id IN :ids",
                "ids",
            ),
            {"ids": record_ids},
        ).fetchall()
    }
    outcomes = _outcomes_by_record(conn, queue.task_schema_id, record_ids)

    disagreements = []
    for item in items:
        external_id, dataset_id = records[str(item.record_id)]
        event_ids = {str(e) for e in item.disagreement.conflicting_event_ids}
        covering = [
            outcome
            for covered, outcome in outcomes.get(str(item.record_id), [])
            if covered == event_ids
        ]
        disagreements.append(
            _Disagreement(
                item=item,
                record_external_id=external_id,
                dataset_id=dataset_id,
                outcome=covering[-1] if covering else None,
            )
        )
    return disagreements


def _find_or_none(conn: Any, queue: _Queue, record_id: str) -> _Disagreement | None:
    for disagreement in _queue_disagreements(conn, queue):
        if str(disagreement.item.record_id) == record_id:
            return disagreement
    return None


def _find(conn: Any, queue: _Queue, record_id: str) -> _Disagreement:
    disagreement = _find_or_none(conn, queue, record_id)
    if disagreement is None:
        raise HTTPException(status_code=404, detail="No disagreement on this record")
    return disagreement


def _detail(
    conn: Any, queue: _Queue, disagreement: _Disagreement
) -> DisagreementDetail:
    record_id = str(disagreement.item.record_id)
    event_rows = conn.execute(
        _expanding(
            "SELECT e.id, e.reviewer_id, p.display_name, e.decision, e.labels, "
            "e.rationale, e.ai_was_revealed, e.created_at "
            "FROM review_events e "
            "LEFT JOIN reviewer_profiles p ON p.id = e.reviewer_id "
            "WHERE e.id IN :ids ORDER BY e.created_at",
            "ids",
        ),
        {"ids": sorted(disagreement.event_ids)},
    ).fetchall()
    bound_output_ids = {
        str(output_id)
        for (raw,) in conn.execute(
            text(
                "SELECT agent_output_ids FROM review_tasks "
                "WHERE queue_id = :q AND record_id = :r"
            ),
            {"q": queue.queue_id, "r": record_id},
        ).fetchall()
        for output_id in deserialize_agent_output_ids(raw)
    }
    output_rows = conn.execute(
        _expanding(
            "SELECT id, agent_run_id, labels, composite_confidence "
            "FROM agent_outputs WHERE id IN :ids ORDER BY created_at",
            "ids",
        ),
        {"ids": sorted(bound_output_ids)},
    ).fetchall()
    context = reviewer_record_context(conn, record_id)
    reviewer_labels = disagreement.item.disagreement.reviewer_labels

    return DisagreementDetail(
        **disagreement.summary(),
        record_view=context["record_view"],
        record_text=context["record_text"],
        reviewer_labels=[
            ReviewerLabelSet(
                reviewer_id=str(row[1]),
                reviewer_name=str(row[2]) if row[2] else str(row[1]),
                review_event_id=str(row[0]),
                decision=canonical_review_decision(str(row[3])) if row[3] else None,
                labels=json_object(row[4]),
                rationale=row[5],
                ai_was_revealed=parse_bool(row[6]),
                created_at=str(row[7]),
            )
            for row in event_rows
        ],
        agent_labels=[
            AgentLabelSet(
                agent_output_id=str(row[0]),
                agent_run_id=str(row[1]),
                labels=json_object(row[2]),
                confidence=float(row[3]) if row[3] is not None else None,
            )
            for row in output_rows
        ],
        disagreeing_fields=[
            FieldDisagreement(
                field_name=field_name,
                values={
                    reviewer_id: labels[field_name]
                    for reviewer_id, labels in reviewer_labels.items()
                    if field_name in labels
                },
            )
            for field_name in disagreement.item.disagreement.fields_in_conflict
        ],
        resolution=disagreement.outcome,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/queues/{queue_id}/disagreements", response_model=DisagreementQueue)
async def list_queue_disagreements(
    request: Request,
    queue_id: str,
    reviewer: CurrentReviewer,
) -> DisagreementQueue:
    """List the records a queue's reviewers disagree on, most severe first.

    A record is listed once every review task the queue holds for it is
    submitted or skipped.
    """
    with get_engine(request).connect() as conn:
        queue = _queue(conn, queue_id, reviewer.workspace_id)
        disagreements = _queue_disagreements(conn, queue)
    items = [DisagreementSummary(**d.summary()) for d in disagreements]
    return DisagreementQueue(
        queue_id=queue_id,
        items=items,
        total=len(items),
        unresolved=sum(item.status == "pending" for item in items),
    )


@router.get(
    "/queues/{queue_id}/disagreements/{record_id}",
    response_model=DisagreementDetail,
)
async def get_queue_disagreement(
    request: Request,
    queue_id: str,
    record_id: str,
    reviewer: CurrentReviewer,
) -> DisagreementDetail:
    """Show a disagreement side by side: the record and each reviewer's labels."""
    with get_engine(request).connect() as conn:
        queue = _queue(conn, queue_id, reviewer.workspace_id)
        return _detail(conn, queue, _find(conn, queue, record_id))


@router.post(
    "/queues/{queue_id}/disagreements/{record_id}/resolve",
    response_model=DisagreementDetail,
)
async def resolve_queue_disagreement(
    request: Request,
    queue_id: str,
    record_id: str,
    body: ResolveDisagreement,
    reviewer: CurrentReviewer,
) -> DisagreementDetail:
    """Resolve a disagreement and store the outcome (AJ-003, AJ-007).

    A disagreement is resolved once for the review events it covers. A new
    review on the record makes a new disagreement to resolve. The request
    names the review events it read, and a disagreement whose events differ,
    or that is gone, answers 409.
    """
    resolve_with_labels = body.resolution == AdjudicationResolution.resolve
    if resolve_with_labels and not body.resolved_labels:
        raise HTTPException(status_code=422, detail="resolve needs resolved_labels")

    with get_engine(request).begin() as conn:
        queue = _queue(conn, queue_id, reviewer.workspace_id)
        disagreement = _find_or_none(conn, queue, record_id)
        if disagreement is None or disagreement.event_ids != set(body.review_event_ids):
            raise HTTPException(
                status_code=409,
                detail="This disagreement changed since it was read; reload it",
            )
        if disagreement.outcome is not None:
            raise HTTPException(
                status_code=409, detail="This disagreement is already resolved"
            )
        task_schema_id = str(disagreement.item.task_schema_id)
        now = datetime.now(UTC).isoformat()
        adjudication_id = str(uuid.uuid4())
        review_event_id: str | None = None
        labels: dict[str, Any] | None = None

        if resolve_with_labels:
            try:
                labels = prepare_review_labels(
                    conn,
                    task_schema_id=task_schema_id,
                    record_id=record_id,
                    labels=body.resolved_labels or {},
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            review_event_id = str(uuid.uuid4())
            conn.execute(
                text(
                    "INSERT INTO review_events (id, record_id, task_schema_id, "
                    "task_schema_version, reviewer_id, source, labels, rationale, "
                    "ai_was_revealed, created_at, workspace_id) VALUES (:id, "
                    ":record_id, :task_schema_id, :version, :reviewer_id, :source, "
                    ":labels, :rationale, 1, :now, :workspace_id)"
                ),
                {
                    "id": review_event_id,
                    "record_id": record_id,
                    "task_schema_id": task_schema_id,
                    "version": load_task_schema_version(conn, task_schema_id),
                    "reviewer_id": str(reviewer.id),
                    "source": ReviewEventSource.human.value,
                    "labels": json.dumps(labels),
                    "rationale": body.rationale,
                    "now": now,
                    "workspace_id": queue.workspace_id,
                },
            )
            conn.execute(
                text(
                    "UPDATE records SET latest_label = :labels, updated_at = :now "
                    "WHERE id = :record_id"
                ),
                {"labels": json.dumps(labels), "now": now, "record_id": record_id},
            )

        conn.execute(
            text(
                "INSERT INTO adjudications (id, record_id, dataset_id, "
                "task_schema_id, adjudicator_id, conflicting_event_ids, resolution, "
                "resolved_labels, rationale, metadata, created_at, workspace_id) "
                "VALUES (:id, :record_id, :dataset_id, :task_schema_id, "
                ":adjudicator_id, :event_ids, :resolution, :labels, :rationale, "
                ":metadata, :now, :workspace_id)"
            ),
            {
                "id": adjudication_id,
                "record_id": record_id,
                "dataset_id": disagreement.dataset_id,
                "task_schema_id": task_schema_id,
                "adjudicator_id": str(reviewer.id),
                "event_ids": json.dumps(sorted(disagreement.event_ids)),
                "resolution": body.resolution.value,
                "labels": json.dumps(labels) if labels is not None else None,
                "rationale": body.rationale,
                "metadata": json.dumps(
                    {"queue_id": queue_id, "review_event_id": review_event_id}
                ),
                "now": now,
                "workspace_id": queue.workspace_id,
            },
        )
        return _detail(conn, queue, _find(conn, queue, record_id))

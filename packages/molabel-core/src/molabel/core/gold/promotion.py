"""Which reviewed records may become gold items, and with which labels.

A record's expected labels always come from people: an adjudication that
resolved it with labels, two or more reviewers who gave identical labels, or,
when the caller opts in, one reviewer. An agent proposal no human confirmed
never becomes gold. ``docs/architecture/gold-sets.md`` states the rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from molabel.core.gold.model import (
    GoldAdjudication,
    GoldInputRef,
    GoldItem,
    GoldModelFailure,
    GoldProvenance,
    GoldReview,
    GoldSource,
    expected_labels,
)
from molabel.core.types import AdjudicationResolution, ReviewDecision
from molabel.core.utils.canonical import present_label_value


@dataclass(frozen=True)
class CountedReview:
    """A reviewer's counted event for the record, and the labels it rates."""

    review_event_id: str
    reviewer_id: str
    decision: str | None
    ai_revealed: bool
    labels: dict[str, Any] | None
    """None when the decision gives no value, such as a reject."""


@dataclass(frozen=True)
class Resolution:
    """The adjudication that covers the record's current disagreement."""

    adjudication_id: str
    adjudicator_id: str
    resolution: AdjudicationResolution
    labels: dict[str, Any] | None
    review_event_id: str | None
    ai_revealed: bool
    agent_sources: dict[str, str] = field(default_factory=dict)
    """Each field the adjudicator took from an agent proposal, and that proposal.

    The resolve endpoint stores a field only when the proposal gave the
    resolved value for it.
    """


@dataclass(frozen=True)
class Proposal:
    """An agent output bound to the record's review tasks."""

    agent_output_id: str
    agent_run_id: str
    labels: dict[str, Any]


@dataclass(frozen=True)
class ReviewedRecord:
    """One record of a review queue, with everything promotion decides on."""

    input_ref: GoldInputRef
    input: dict[str, Any]
    queue_id: str
    workflow_execution_id: str | None
    open_copies: int
    reviews: tuple[CountedReview, ...]
    disagreement: bool
    """Whether adjudication lists the record's reviews as a disagreement."""
    resolution: Resolution | None
    proposals: tuple[Proposal, ...]


class SkipReason(StrEnum):
    open_copies = "open_copies"
    unresolved_disagreement = "unresolved_disagreement"
    resolved_without_labels = "resolved_without_labels"
    no_human_label = "no_human_label"
    review_without_labels = "review_without_labels"
    partial_agreement = "partial_agreement"
    single_reviewer = "single_reviewer"
    no_model_proposal = "no_model_proposal"
    model_agreed = "model_agreed"


_SKIP_MESSAGES = {
    SkipReason.open_copies: "A copy of the record is still unclaimed or claimed.",
    SkipReason.unresolved_disagreement: (
        "The reviewers disagree and no adjudication resolved it."
    ),
    SkipReason.resolved_without_labels: (
        "The adjudication kept no labels (preserve_disagreement, downgrade or exclude)."
    ),
    SkipReason.no_human_label: "No reviewer gave the record labels.",
    SkipReason.review_without_labels: (
        "A counted reviewer rejected or skipped the record without labels."
    ),
    SkipReason.partial_agreement: (
        "The reviewers set different fields, so they do not agree on every label."
    ),
    SkipReason.single_reviewer: (
        "One reviewer labelled the record; pass allow_single_reviewer to promote it."
    ),
    SkipReason.no_model_proposal: "No agent proposal is bound to the record.",
    SkipReason.model_agreed: "The agent proposal matches the human label.",
}


class Skipped(BaseModel):
    """A record that was not promoted, and why."""

    record_id: str | None
    external_id: str | None
    reason: SkipReason
    message: str


@dataclass(frozen=True)
class _Settled:
    expected: dict[str, Any]
    source: GoldSource


def _settle(
    record: ReviewedRecord, allow_single_reviewer: bool
) -> _Settled | SkipReason:
    if record.open_copies:
        return SkipReason.open_copies
    if record.disagreement:
        resolution = record.resolution
        if resolution is None:
            return SkipReason.unresolved_disagreement
        if (
            resolution.resolution != AdjudicationResolution.resolve
            or not resolution.labels
        ):
            return SkipReason.resolved_without_labels
        return _Settled(resolution.labels, GoldSource.adjudication)
    rated = [review.labels for review in record.reviews if review.labels is not None]
    if not rated:
        return SkipReason.no_human_label
    if len(rated) < len(record.reviews):
        return SkipReason.review_without_labels
    if len(rated) == 1:
        if not allow_single_reviewer:
            return SkipReason.single_reviewer
        return _Settled(rated[0], GoldSource.single_reviewer)
    first = expected_labels(rated[0])
    if any(expected_labels(labels) != first for labels in rated[1:]):
        return SkipReason.partial_agreement
    return _Settled(first, GoldSource.reviewer_agreement)


def _differing_fields(expected: dict[str, Any], proposed: dict[str, Any]) -> list[str]:
    return sorted(
        name
        for name in expected.keys() | proposed.keys()
        if present_label_value(expected.get(name))
        != present_label_value(proposed.get(name))
    )


def model_failure(
    expected: dict[str, Any], proposals: tuple[Proposal, ...]
) -> GoldModelFailure | SkipReason:
    """The first proposal the expected labels contradict, or why there is none."""
    if not proposals:
        return SkipReason.no_model_proposal
    for proposal in proposals:
        fields = _differing_fields(expected, proposal.labels)
        if fields:
            return GoldModelFailure(
                agent_output_id=proposal.agent_output_id,
                agent_run_id=proposal.agent_run_id,
                proposed=expected_labels(proposal.labels),
                failed_fields=fields,
            )
    return SkipReason.model_agreed


def _skipped(record: ReviewedRecord, reason: SkipReason) -> Skipped:
    return Skipped(
        record_id=record.input_ref.record_id,
        external_id=record.input_ref.external_id,
        reason=reason,
        message=_SKIP_MESSAGES[reason],
    )


def gold_candidate(
    record: ReviewedRecord,
    *,
    task_schema: str,
    promoted_by: str,
    promoted_at: str,
    allow_single_reviewer: bool = False,
    failures_only: bool = False,
) -> GoldItem | Skipped:
    """The gold item a reviewed record gives, or why it gives none.

    With *failures_only*, only a record whose labels contradict an agent
    proposal is a candidate, and its provenance records that proposal.
    """
    settled = _settle(record, allow_single_reviewer)
    if isinstance(settled, SkipReason):
        return _skipped(record, settled)
    failure = (
        model_failure(settled.expected, record.proposals) if failures_only else None
    )
    if isinstance(failure, SkipReason):
        return _skipped(record, failure)

    resolution = (
        record.resolution if settled.source == GoldSource.adjudication else None
    )
    adjudication = (
        GoldAdjudication(
            adjudication_id=resolution.adjudication_id,
            adjudicator_id=resolution.adjudicator_id,
            review_event_id=resolution.review_event_id,
            ai_revealed=resolution.ai_revealed,
        )
        if resolution is not None
        else None
    )
    reviews = [
        GoldReview(
            review_event_id=review.review_event_id,
            reviewer_id=review.reviewer_id,
            decision=review.decision,
            ai_revealed=review.ai_revealed,
        )
        for review in sorted(record.reviews, key=lambda r: r.review_event_id)
    ]
    reviewer_ids = {review.reviewer_id for review in reviews}
    if adjudication is not None:
        reviewer_ids.add(adjudication.adjudicator_id)
    adjudicator_took_ai = resolution is not None and (
        bool(resolution.agent_sources)
        or any(
            not _differing_fields(settled.expected, p.labels) for p in record.proposals
        )
    )
    return GoldItem.build(
        task_schema=task_schema,
        input=record.input,
        expected=settled.expected,
        input_ref=record.input_ref,
        provenance=GoldProvenance(
            source=settled.source,
            queue_id=record.queue_id,
            workflow_execution_id=record.workflow_execution_id,
            adjudication=adjudication,
            reviews=reviews,
            reviewer_ids=sorted(reviewer_ids),
            ai_revealed=any(r.ai_revealed for r in reviews)
            or (adjudication is not None and adjudication.ai_revealed),
            accepted_ai_proposal=adjudicator_took_ai
            or any(
                r.ai_revealed and r.decision == ReviewDecision.accept for r in reviews
            ),
            adjudicator_took_ai=adjudicator_took_ai,
            model_failure=failure,
            promoted_at=promoted_at,
            promoted_by=promoted_by,
        ),
    )

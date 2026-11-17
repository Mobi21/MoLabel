"""Agreement records built from review events and agent proposals.

Each reviewer is one rater, keyed by ``reviewer_id``, and each agent run is
another, keyed by its run id. A reviewer's value for a record comes from one
review event, the head of its correction chain: the event no correction
supersedes. A reviewer with heads in two tasks for one record, such as an
overlap copy or a later loop pass, counts the latest. The event's decision,
after ``canonical_review_decision``, says whether it gives a value:

- ``accept``, ``edit``, and a submission with no decision give the labels the
  event stores. Submission stores the labels the reviewer sent, and an accept
  with none stores the labels of the proposal the reviewer was shown.
- ``reject`` and ``skip`` give no value, and neither does an event that
  stores no labels.

``docs/guides/agreement-metrics.md`` documents these rules.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from molabel.core.quality.agreement_metrics import (
    AgreementAnnotation,
    AgreementRecord,
)
from molabel.core.types import ReviewDecision, canonical_review_decision


@dataclass(frozen=True)
class ReviewEventLabels:
    """A human review event and the labels it stores."""

    event_id: str
    record_id: str
    reviewer_id: str
    decision: str | None
    labels: dict[str, Any]
    supersedes_event_id: str | None
    created_at: datetime


@dataclass(frozen=True)
class AgentProposal:
    """An agent run's labels for one record."""

    record_id: str
    agent_run_id: str
    labels: dict[str, Any]


def rated_labels(event: ReviewEventLabels) -> dict[str, Any] | None:
    """The labels an event rates, or None when its decision gives no value."""
    decision = (
        None if event.decision is None else canonical_review_decision(event.decision)
    )
    if decision in (ReviewDecision.accept, ReviewDecision.edit, None):
        return event.labels or None
    return None


def counted_review_events(
    events: Iterable[ReviewEventLabels],
) -> list[ReviewEventLabels]:
    """Each reviewer's counted event per record: the latest correction-chain head."""
    events = list(events)
    superseded = {event.supersedes_event_id for event in events}
    latest: dict[tuple[str, str], ReviewEventLabels] = {}
    for event in sorted(events, key=lambda event: event.created_at):
        if event.event_id not in superseded:
            latest[(event.reviewer_id, event.record_id)] = event
    return list(latest.values())


def agreement_records_from_reviews(
    events: Iterable[ReviewEventLabels],
    proposals: Iterable[AgentProposal],
    *,
    record_ids: Sequence[str],
) -> list[AgreementRecord]:
    """Group the counted human values and agent proposals by record."""
    in_scope = set(record_ids)
    annotations: dict[str, list[AgreementAnnotation]] = defaultdict(list)
    for event in counted_review_events(events):
        labels = rated_labels(event)
        if labels is not None and event.record_id in in_scope:
            annotations[event.record_id].append(
                AgreementAnnotation(
                    source="human", rater_id=event.reviewer_id, labels=labels
                )
            )
    for proposal in proposals:
        if proposal.record_id in in_scope:
            annotations[proposal.record_id].append(
                AgreementAnnotation(
                    source="agent",
                    rater_id=proposal.agent_run_id,
                    labels=proposal.labels,
                )
            )
    return [
        AgreementRecord(record_id=record_id, annotations=record_annotations)
        for record_id, record_annotations in annotations.items()
    ]

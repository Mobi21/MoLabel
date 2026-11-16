"""Agreement records built from review events and agent proposals."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from molabel.core.quality.agreement_metrics import AgreementMetricsService
from molabel.core.quality.review_agreement import (
    AgentProposal,
    ReviewEventLabels,
    agreement_records_from_reviews,
)

T0 = datetime(2026, 11, 16, tzinfo=UTC)
PROPOSAL = {"sentiment": "positive"}
SUBMITTED = {"sentiment": "negative"}


def _event(
    event_id: str,
    decision: str | None,
    *,
    reviewer: str = "alice",
    record: str = "r1",
    labels: dict[str, Any] | None = None,
    supersedes: str | None = None,
    minute: int = 0,
) -> ReviewEventLabels:
    return ReviewEventLabels(
        event_id=event_id,
        record_id=record,
        reviewer_id=reviewer,
        decision=decision,
        labels=SUBMITTED if labels is None else labels,
        supersedes_event_id=supersedes,
        created_at=T0 + timedelta(minutes=minute),
    )


def _rated(
    events: list[ReviewEventLabels],
    proposals: list[AgentProposal] = (),
    record_ids: tuple[str, ...] = ("r1", "r2"),
) -> dict[str, list[tuple[str, str, dict[str, Any]]]]:
    records = agreement_records_from_reviews(events, proposals, record_ids=record_ids)
    return {
        record.record_id: [
            (annotation.source, annotation.rater_id, annotation.labels)
            for annotation in record.annotations
        ]
        for record in records
    }


@pytest.mark.parametrize(
    "decision", ["accept", "edit", None, "accept_ai", "edit_ai", "correct"]
)
def test_a_decision_rates_the_labels_the_event_stores(decision: str | None) -> None:
    assert _rated([_event("e1", decision)]) == {"r1": [("human", "alice", SUBMITTED)]}


@pytest.mark.parametrize("decision", ["reject", "reject_ai", "skip"])
def test_reject_and_skip_give_no_value(decision: str) -> None:
    assert _rated([_event("e1", decision)]) == {}


@pytest.mark.parametrize("decision", ["accept", "edit", None])
def test_an_event_with_no_labels_gives_no_value(decision: str | None) -> None:
    assert _rated([_event("e1", decision, labels={})]) == {}


def test_an_event_with_no_labels_withdraws_the_value_it_corrects() -> None:
    events = [
        _event("e1", "edit", minute=0),
        _event("e2", "accept", labels={}, supersedes="e1", minute=1),
    ]

    assert _rated(events) == {}


def test_the_head_of_a_correction_chain_counts() -> None:
    events = [
        _event("e1", "accept", minute=0),
        _event("e2", "edit", supersedes="e1", minute=1),
        _event(
            "e3", "edit", labels={"sentiment": "neutral"}, supersedes="e2", minute=2
        ),
    ]

    assert _rated(events) == {"r1": [("human", "alice", {"sentiment": "neutral"})]}


def test_a_correction_to_reject_withdraws_the_value() -> None:
    events = [
        _event("e1", "accept", minute=0),
        _event("e2", "reject", supersedes="e1", minute=1),
    ]

    assert _rated(events) == {}


def test_the_latest_head_counts_when_a_reviewer_reviewed_a_record_twice() -> None:
    events = [
        _event("e1", "accept", minute=5),
        _event("e2", "edit", minute=9),
        _event("e3", "edit", labels={"sentiment": "neutral"}, minute=1),
    ]

    assert _rated(events) == {"r1": [("human", "alice", SUBMITTED)]}


def test_each_reviewer_and_each_agent_run_is_a_rater() -> None:
    events = [
        _event("e1", "accept", reviewer="alice"),
        _event("e2", "edit", reviewer="bob"),
        _event("e3", "edit", reviewer="bob", record="r2"),
    ]
    proposals = [
        AgentProposal(record_id="r1", agent_run_id="run-1", labels=PROPOSAL),
        AgentProposal(record_id="r2", agent_run_id="run-1", labels=PROPOSAL),
    ]

    assert _rated(events, proposals) == {
        "r1": [
            ("human", "alice", SUBMITTED),
            ("human", "bob", SUBMITTED),
            ("agent", "run-1", PROPOSAL),
        ],
        "r2": [("human", "bob", SUBMITTED), ("agent", "run-1", PROPOSAL)],
    }


def test_records_outside_the_workflow_are_left_out() -> None:
    events = [_event("e1", "edit", record="r1"), _event("e2", "edit", record="r9")]
    proposals = [AgentProposal(record_id="r9", agent_run_id="run-1", labels={})]

    assert _rated(events, proposals, record_ids=("r1",)) == {
        "r1": [("human", "alice", SUBMITTED)]
    }


def test_two_reviewers_give_a_two_rater_alpha() -> None:
    values = {"r1": ("pos", "pos"), "r2": ("neg", "neu"), "r3": ("neg", "neg")}
    events = [
        _event(
            f"{record}-{reviewer}",
            "edit",
            reviewer=reviewer,
            record=record,
            labels={"sentiment": value},
        )
        for record, pair in values.items()
        for reviewer, value in zip(("alice", "bob"), pair, strict=True)
    ]

    result = AgreementMetricsService().analyze(
        agreement_records_from_reviews(events, [], record_ids=tuple(values)),
        analysis_type="inter_annotator",
    )

    # n = 6 with pos = 2, neg = 3, neu = 1. Only r2 mismatches, 2 coincidences:
    # alpha = 1 - 5 * 2 / (36 - 4 - 9 - 1) = 6 / 11.
    assert result.fields["sentiment"].krippendorff_alpha == pytest.approx(6 / 11)
    assert "cohen_kappa" not in result.fields["sentiment"].null_reasons

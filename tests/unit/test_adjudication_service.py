"""Unit tests for adjudication service (AJ-001 through AJ-005, AJ-007).

Tests cover:
- AJ-001: Disagreement detection (human-human and human-agent)
- AJ-002: Adjudication queue with severity/type classification
- AJ-003: Adjudication resolutions
- AJ-004: Side-by-side comparison data
- AJ-005: Policy context matching
- AJ-007: Adjudication creates review events
"""

from __future__ import annotations

import uuid

import pytest

from molabel.core.adjudication.adjudication_service import (
    AdjudicationQueueItem,
    AdjudicationService,
    AdjudicationSeverity,
    AdjudicationType,
    Disagreement,
    DisagreementType,
)
from molabel.core.types import AdjudicationResolution

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


TASK_SCHEMA_ID = uuid.uuid4()
WORKSPACE_ID = uuid.uuid4()


def _make_event(
    *,
    record_id: uuid.UUID,
    reviewer_id: uuid.UUID | None = None,
    source: str = "human",
    labels: dict | None = None,
    event_id: uuid.UUID | None = None,
) -> dict:
    """Build a review event dict for testing."""
    return {
        "id": str(event_id or uuid.uuid4()),
        "reviewer_id": str(reviewer_id or uuid.uuid4()),
        "source": source,
        "labels": labels or {},
        "record_id": str(record_id),
    }


@pytest.fixture()
def service() -> AdjudicationService:
    """Fresh AdjudicationService instance."""
    return AdjudicationService()


# ---------------------------------------------------------------------------
# AJ-001: Disagreement detection
# ---------------------------------------------------------------------------


class TestDisagreementDetection:
    """Tests for detecting disagreements between reviewers (AJ-001)."""

    def test_human_human_disagreement(self, service: AdjudicationService) -> None:
        """Detect field-level disagreement between two human reviewers."""
        record_id = uuid.uuid4()
        events_by_record = {
            str(record_id): [
                _make_event(
                    record_id=record_id,
                    source="human",
                    labels={"sentiment": "positive"},
                ),
                _make_event(
                    record_id=record_id,
                    source="human",
                    labels={"sentiment": "negative"},
                ),
            ]
        }

        disagreements = service.detect_disagreements(events_by_record, TASK_SCHEMA_ID)
        assert len(disagreements) == 1
        d = disagreements[0]
        assert d.disagreement_type == DisagreementType.human_human
        assert "sentiment" in d.fields_in_conflict
        assert d.record_id == record_id

    def test_human_agent_disagreement(self, service: AdjudicationService) -> None:
        """Detect disagreement between human and agent reviewers."""
        record_id = uuid.uuid4()
        events_by_record = {
            str(record_id): [
                _make_event(
                    record_id=record_id,
                    source="human",
                    labels={"sentiment": "positive"},
                ),
                _make_event(
                    record_id=record_id,
                    source="agent",
                    labels={"sentiment": "negative"},
                ),
            ]
        }

        disagreements = service.detect_disagreements(events_by_record, TASK_SCHEMA_ID)
        assert len(disagreements) == 1
        assert disagreements[0].disagreement_type == DisagreementType.human_agent

    def test_no_disagreement_when_labels_match(
        self, service: AdjudicationService
    ) -> None:
        """No disagreement detected when all reviewers agree."""
        record_id = uuid.uuid4()
        events_by_record = {
            str(record_id): [
                _make_event(
                    record_id=record_id,
                    source="human",
                    labels={"sentiment": "positive"},
                ),
                _make_event(
                    record_id=record_id,
                    source="human",
                    labels={"sentiment": "positive"},
                ),
            ]
        }

        disagreements = service.detect_disagreements(events_by_record, TASK_SCHEMA_ID)
        assert len(disagreements) == 0

    def test_single_event_no_disagreement(self, service: AdjudicationService) -> None:
        """No disagreement possible with only one event per record."""
        record_id = uuid.uuid4()
        events_by_record = {
            str(record_id): [
                _make_event(
                    record_id=record_id,
                    labels={"sentiment": "positive"},
                ),
            ]
        }
        disagreements = service.detect_disagreements(events_by_record, TASK_SCHEMA_ID)
        assert len(disagreements) == 0

    def test_multiple_field_disagreements(self, service: AdjudicationService) -> None:
        """Detect disagreements across multiple fields."""
        record_id = uuid.uuid4()
        events_by_record = {
            str(record_id): [
                _make_event(
                    record_id=record_id,
                    source="human",
                    labels={"sentiment": "positive", "toxicity": "none"},
                ),
                _make_event(
                    record_id=record_id,
                    source="human",
                    labels={"sentiment": "negative", "toxicity": "high"},
                ),
            ]
        }

        disagreements = service.detect_disagreements(events_by_record, TASK_SCHEMA_ID)
        assert len(disagreements) == 1
        d = disagreements[0]
        assert "sentiment" in d.fields_in_conflict
        assert "toxicity" in d.fields_in_conflict

    def test_both_human_and_agent_disagreements(
        self, service: AdjudicationService
    ) -> None:
        """Detect both types when humans disagree and agent also differs."""
        record_id = uuid.uuid4()
        r1, r2 = uuid.uuid4(), uuid.uuid4()
        events_by_record = {
            str(record_id): [
                _make_event(
                    record_id=record_id,
                    reviewer_id=r1,
                    source="human",
                    labels={"sentiment": "positive"},
                ),
                _make_event(
                    record_id=record_id,
                    reviewer_id=r2,
                    source="human",
                    labels={"sentiment": "negative"},
                ),
                _make_event(
                    record_id=record_id,
                    source="agent",
                    labels={"sentiment": "neutral"},
                ),
            ]
        }

        disagreements = service.detect_disagreements(events_by_record, TASK_SCHEMA_ID)
        # Should detect both human-human and human-agent
        types = {d.disagreement_type for d in disagreements}
        assert DisagreementType.human_human in types
        assert DisagreementType.human_agent in types

    def test_reviewer_labels_tracked(self, service: AdjudicationService) -> None:
        """Detected disagreements include per-reviewer label values."""
        record_id = uuid.uuid4()
        r1, r2 = uuid.uuid4(), uuid.uuid4()
        events_by_record = {
            str(record_id): [
                _make_event(
                    record_id=record_id,
                    reviewer_id=r1,
                    source="human",
                    labels={"sentiment": "positive"},
                ),
                _make_event(
                    record_id=record_id,
                    reviewer_id=r2,
                    source="human",
                    labels={"sentiment": "negative"},
                ),
            ]
        }

        disagreements = service.detect_disagreements(events_by_record, TASK_SCHEMA_ID)
        assert len(disagreements) == 1
        d = disagreements[0]
        assert str(r1) in d.reviewer_labels
        assert d.reviewer_labels[str(r1)]["sentiment"] == "positive"
        assert str(r2) in d.reviewer_labels
        assert d.reviewer_labels[str(r2)]["sentiment"] == "negative"


# ---------------------------------------------------------------------------
# AJ-002: Adjudication queue with severity/type
# ---------------------------------------------------------------------------


class TestAdjudicationQueue:
    """Tests for building adjudication queue with severity (AJ-002)."""

    def _build_disagreement(
        self,
        *,
        fields: list[str],
        reviewer_labels: dict | None = None,
        dtype: DisagreementType = DisagreementType.human_human,
    ) -> Disagreement:
        """Helper to build a Disagreement for queue tests."""
        return Disagreement(
            record_id=uuid.uuid4(),
            task_schema_id=TASK_SCHEMA_ID,
            conflicting_event_ids=[uuid.uuid4(), uuid.uuid4()],
            disagreement_type=dtype,
            fields_in_conflict=fields,
            reviewer_labels=reviewer_labels or {},
        )

    def test_build_queue(self, service: AdjudicationService) -> None:
        """build_queue creates items from disagreements."""
        d = self._build_disagreement(fields=["sentiment"])
        queue = service.build_queue([d])
        assert len(queue) == 1
        assert queue[0].record_id == d.record_id

    def test_severity_low_single_field(self, service: AdjudicationService) -> None:
        """Single non-contradictory field disagreement is low severity."""
        d = self._build_disagreement(
            fields=["score"],
            reviewer_labels={
                "r1": {"score": "3"},
                "r2": {"score": "4"},
            },
        )
        queue = service.build_queue([d])
        assert queue[0].severity == AdjudicationSeverity.low

    def test_severity_high_contradictory(self, service: AdjudicationService) -> None:
        """Contradictory labels (positive vs negative) are high severity."""
        d = self._build_disagreement(
            fields=["sentiment"],
            reviewer_labels={
                "r1": {"sentiment": "positive"},
                "r2": {"sentiment": "negative"},
            },
        )
        queue = service.build_queue([d])
        assert queue[0].severity == AdjudicationSeverity.high

    def test_severity_high_many_fields(self, service: AdjudicationService) -> None:
        """Three or more conflicting fields are high severity."""
        d = self._build_disagreement(
            fields=["f1", "f2", "f3"],
            reviewer_labels={
                "r1": {"f1": "a", "f2": "b", "f3": "c"},
                "r2": {"f1": "x", "f2": "y", "f3": "z"},
            },
        )
        queue = service.build_queue([d])
        assert queue[0].severity == AdjudicationSeverity.high

    def test_severity_medium_two_fields(self, service: AdjudicationService) -> None:
        """Two non-contradictory conflicting fields are medium severity."""
        d = self._build_disagreement(
            fields=["f1", "f2"],
            reviewer_labels={
                "r1": {"f1": "a", "f2": "b"},
                "r2": {"f1": "x", "f2": "y"},
            },
        )
        queue = service.build_queue([d])
        assert queue[0].severity == AdjudicationSeverity.medium

    def test_type_edge_case_for_human_agent(self, service: AdjudicationService) -> None:
        """Human-agent disagreements are classified as edge_case."""
        d = self._build_disagreement(
            fields=["sentiment"],
            dtype=DisagreementType.human_agent,
        )
        queue = service.build_queue([d])
        assert queue[0].adjudication_type == AdjudicationType.edge_case

    def test_type_subjective_single_field(self, service: AdjudicationService) -> None:
        """Single-field human-human disagreement is subjective."""
        d = self._build_disagreement(
            fields=["sentiment"],
            reviewer_labels={
                "r1": {"sentiment": "somewhat_positive"},
                "r2": {"sentiment": "neutral"},
            },
        )
        queue = service.build_queue([d])
        assert queue[0].adjudication_type == AdjudicationType.subjective

    def test_queue_sorted_by_severity(self, service: AdjudicationService) -> None:
        """Queue is sorted with high severity first."""
        low = self._build_disagreement(
            fields=["score"],
            reviewer_labels={"r1": {"score": "3"}, "r2": {"score": "4"}},
        )
        high = self._build_disagreement(
            fields=["sentiment"],
            reviewer_labels={
                "r1": {"sentiment": "positive"},
                "r2": {"sentiment": "negative"},
            },
        )
        queue = service.build_queue([low, high])
        assert queue[0].severity == AdjudicationSeverity.high
        assert queue[1].severity == AdjudicationSeverity.low

    def test_get_unresolved_queue(self, service: AdjudicationService) -> None:
        """get_unresolved_queue filters out resolved items."""
        d = self._build_disagreement(fields=["f"])
        queue = service.build_queue([d])
        assert len(service.get_unresolved_queue()) == 1

        # Resolve the item
        service.resolve(
            queue[0].id,
            uuid.uuid4(),
            AdjudicationResolution.preserve_disagreement,
        )
        assert len(service.get_unresolved_queue()) == 0


# ---------------------------------------------------------------------------
# AJ-003: Adjudication resolutions
# ---------------------------------------------------------------------------


class TestAdjudicationResolutions:
    """Tests for applying adjudication resolutions (AJ-003)."""

    def _make_queue(self, service: AdjudicationService) -> list[AdjudicationQueueItem]:
        """Helper to create a queue with one item."""
        d = Disagreement(
            record_id=uuid.uuid4(),
            task_schema_id=TASK_SCHEMA_ID,
            conflicting_event_ids=[uuid.uuid4(), uuid.uuid4()],
            disagreement_type=DisagreementType.human_human,
            fields_in_conflict=["sentiment"],
            reviewer_labels={
                "r1": {"sentiment": "positive"},
                "r2": {"sentiment": "negative"},
            },
        )
        return service.build_queue([d])

    def test_resolve_with_labels(self, service: AdjudicationService) -> None:
        """Resolution type 'resolve' produces final labels."""
        queue = self._make_queue(service)
        result = service.resolve(
            queue[0].id,
            uuid.uuid4(),
            AdjudicationResolution.resolve,
            resolved_labels={"sentiment": "positive"},
            rationale="Reviewer 1 was more careful",
        )
        assert result.resolution == AdjudicationResolution.resolve
        assert result.resolved_labels is not None
        assert result.resolved_labels.labels == {"sentiment": "positive"}
        assert result.rationale == "Reviewer 1 was more careful"

    def test_preserve_disagreement(self, service: AdjudicationService) -> None:
        """Resolution type 'preserve_disagreement' keeps both labels."""
        queue = self._make_queue(service)
        result = service.resolve(
            queue[0].id,
            uuid.uuid4(),
            AdjudicationResolution.preserve_disagreement,
        )
        assert result.resolution == AdjudicationResolution.preserve_disagreement
        assert result.resolved_labels is None

    def test_exclude_resolution(self, service: AdjudicationService) -> None:
        """Resolution type 'exclude' excludes the record."""
        queue = self._make_queue(service)
        result = service.resolve(
            queue[0].id,
            uuid.uuid4(),
            AdjudicationResolution.exclude,
        )
        assert result.resolution == AdjudicationResolution.exclude
        assert result.resolved_labels is not None
        assert result.resolved_labels.labels == {}

    def test_downgrade_resolution(self, service: AdjudicationService) -> None:
        """Resolution type 'downgrade' marks for re-review."""
        queue = self._make_queue(service)
        result = service.resolve(
            queue[0].id,
            uuid.uuid4(),
            AdjudicationResolution.downgrade,
            rationale="Needs re-review with updated guidelines",
        )
        assert result.resolution == AdjudicationResolution.downgrade
        assert result.rationale == "Needs re-review with updated guidelines"

    def test_resolve_marks_item_resolved(self, service: AdjudicationService) -> None:
        """Resolving marks the queue item as resolved."""
        queue = self._make_queue(service)
        assert queue[0].resolved is False
        service.resolve(
            queue[0].id,
            uuid.uuid4(),
            AdjudicationResolution.resolve,
            resolved_labels={"sentiment": "neutral"},
        )
        assert queue[0].resolved is True

    def test_resolve_nonexistent_raises(self, service: AdjudicationService) -> None:
        """Resolving a non-existent queue item raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            service.resolve(
                uuid.uuid4(),
                uuid.uuid4(),
                AdjudicationResolution.resolve,
            )

    def test_source_event_ids_tracked(self, service: AdjudicationService) -> None:
        """Resolved labels track which events were considered."""
        queue = self._make_queue(service)
        result = service.resolve(
            queue[0].id,
            uuid.uuid4(),
            AdjudicationResolution.resolve,
            resolved_labels={"sentiment": "positive"},
        )
        assert result.resolved_labels is not None
        assert len(result.resolved_labels.source_event_ids) == 2

    def test_get_resolution(self, service: AdjudicationService) -> None:
        """get_resolution retrieves a stored resolution."""
        queue = self._make_queue(service)
        result = service.resolve(
            queue[0].id,
            uuid.uuid4(),
            AdjudicationResolution.resolve,
            resolved_labels={"sentiment": "positive"},
        )
        fetched = service.get_resolution(result.adjudication_id)
        assert fetched is not None
        assert fetched.adjudication_id == result.adjudication_id


# ---------------------------------------------------------------------------
# AJ-004: Side-by-side comparison
# ---------------------------------------------------------------------------


class TestSideBySideComparison:
    """Tests for building comparison data (AJ-004)."""

    def test_build_comparison(self, service: AdjudicationService) -> None:
        """build_comparison produces per-field alignment."""
        record_id = uuid.uuid4()
        r1, r2 = uuid.uuid4(), uuid.uuid4()
        e1_id, e2_id = uuid.uuid4(), uuid.uuid4()

        disagreement = Disagreement(
            record_id=record_id,
            task_schema_id=TASK_SCHEMA_ID,
            conflicting_event_ids=[e1_id, e2_id],
            disagreement_type=DisagreementType.human_human,
            fields_in_conflict=["sentiment"],
        )

        events = [
            {
                "id": str(e1_id),
                "reviewer_id": str(r1),
                "source": "human",
                "labels": {"sentiment": "positive", "confidence": 0.9},
            },
            {
                "id": str(e2_id),
                "reviewer_id": str(r2),
                "source": "human",
                "labels": {"sentiment": "negative", "confidence": 0.8},
            },
        ]

        panel = service.build_comparison(disagreement, events)
        assert panel.record_id == record_id
        assert len(panel.field_comparisons) == 2  # sentiment + confidence

        # Sentiment should be in conflict
        sentiment_fc = next(
            fc for fc in panel.field_comparisons if fc.field_name == "sentiment"
        )
        assert sentiment_fc.is_in_conflict is True
        assert len(sentiment_fc.sources) == 2

        # Confidence should not be in conflict
        confidence_fc = next(
            fc for fc in panel.field_comparisons if fc.field_name == "confidence"
        )
        assert confidence_fc.is_in_conflict is False

    def test_comparison_with_agent(self, service: AdjudicationService) -> None:
        """Comparison includes agent sources with proper type."""
        record_id = uuid.uuid4()
        e1_id, e2_id = uuid.uuid4(), uuid.uuid4()

        disagreement = Disagreement(
            record_id=record_id,
            task_schema_id=TASK_SCHEMA_ID,
            conflicting_event_ids=[e1_id, e2_id],
            disagreement_type=DisagreementType.human_agent,
            fields_in_conflict=["sentiment"],
        )

        events = [
            {
                "id": str(e1_id),
                "reviewer_id": str(uuid.uuid4()),
                "source": "human",
                "labels": {"sentiment": "positive"},
            },
            {
                "id": str(e2_id),
                "reviewer_id": None,
                "source": "agent",
                "labels": {"sentiment": "negative"},
            },
        ]

        panel = service.build_comparison(disagreement, events)
        sentiment_fc = next(
            fc for fc in panel.field_comparisons if fc.field_name == "sentiment"
        )
        sources = sentiment_fc.sources
        source_types = {s.source_type for s in sources}
        assert "human" in source_types
        assert "agent" in source_types

    def test_comparison_event_ids(self, service: AdjudicationService) -> None:
        """Comparison panel includes all event IDs."""
        record_id = uuid.uuid4()
        e1_id, e2_id = uuid.uuid4(), uuid.uuid4()

        disagreement = Disagreement(
            record_id=record_id,
            task_schema_id=TASK_SCHEMA_ID,
            conflicting_event_ids=[e1_id, e2_id],
            disagreement_type=DisagreementType.human_human,
            fields_in_conflict=["sentiment"],
        )

        events = [
            {
                "id": str(e1_id),
                "reviewer_id": "r1",
                "source": "human",
                "labels": {"sentiment": "a"},
            },
            {
                "id": str(e2_id),
                "reviewer_id": "r2",
                "source": "human",
                "labels": {"sentiment": "b"},
            },
        ]

        panel = service.build_comparison(disagreement, events)
        assert e1_id in panel.event_ids
        assert e2_id in panel.event_ids


# ---------------------------------------------------------------------------
# AJ-005: Policy context
# ---------------------------------------------------------------------------


class TestPolicyContext:
    """Tests for policy context matching (AJ-005)."""

    def test_match_policy_by_field(self, service: AdjudicationService) -> None:
        """Policy sections matching the conflict field are returned."""
        service.set_policy_sections(
            [
                {
                    "section_id": "s1",
                    "title": "Sentiment Guidelines",
                    "content": "When labeling sentiment, consider the overall tone.",
                    "keywords": ["sentiment"],
                },
                {
                    "section_id": "s2",
                    "title": "Toxicity Guidelines",
                    "content": "Toxicity includes hate speech and threats.",
                    "keywords": ["toxicity"],
                },
            ]
        )

        disagreement = Disagreement(
            record_id=uuid.uuid4(),
            task_schema_id=TASK_SCHEMA_ID,
            conflicting_event_ids=[uuid.uuid4()],
            disagreement_type=DisagreementType.human_human,
            fields_in_conflict=["sentiment"],
            reviewer_labels={"r1": {"sentiment": "positive"}},
        )

        contexts = service.get_policy_context(disagreement)
        assert len(contexts) == 1
        assert contexts[0].field_name == "sentiment"
        assert len(contexts[0].excerpts) >= 1
        assert contexts[0].excerpts[0].section_id == "s1"

    def test_match_policy_by_value(self, service: AdjudicationService) -> None:
        """Policy sections matching label values are returned."""
        service.set_policy_sections(
            [
                {
                    "section_id": "s1",
                    "title": "Positive Sentiment",
                    "content": "Assign positive when the text is clearly favorable.",
                    "keywords": ["positive"],
                },
            ]
        )

        disagreement = Disagreement(
            record_id=uuid.uuid4(),
            task_schema_id=TASK_SCHEMA_ID,
            conflicting_event_ids=[uuid.uuid4()],
            disagreement_type=DisagreementType.human_human,
            fields_in_conflict=["sentiment"],
            reviewer_labels={
                "r1": {"sentiment": "positive"},
                "r2": {"sentiment": "negative"},
            },
        )

        contexts = service.get_policy_context(disagreement)
        assert len(contexts) >= 1
        # Should match on "positive" keyword
        excerpts = contexts[0].excerpts
        assert any(e.section_id == "s1" for e in excerpts)

    def test_no_matching_policy(self, service: AdjudicationService) -> None:
        """No contexts returned when no policy sections match."""
        service.set_policy_sections(
            [
                {
                    "section_id": "s1",
                    "title": "Unrelated",
                    "content": "This is about something else.",
                    "keywords": ["unrelated_topic"],
                },
            ]
        )

        disagreement = Disagreement(
            record_id=uuid.uuid4(),
            task_schema_id=TASK_SCHEMA_ID,
            conflicting_event_ids=[uuid.uuid4()],
            disagreement_type=DisagreementType.human_human,
            fields_in_conflict=["sentiment"],
            reviewer_labels={"r1": {"sentiment": "positive"}},
        )

        contexts = service.get_policy_context(disagreement)
        assert len(contexts) == 0

    def test_relevance_scoring(self, service: AdjudicationService) -> None:
        """Policy excerpts are sorted by relevance score."""
        service.set_policy_sections(
            [
                {
                    "section_id": "less_relevant",
                    "title": "General Guidelines",
                    "content": "General text about labeling.",
                    "keywords": ["labeling"],
                },
                {
                    "section_id": "more_relevant",
                    "title": "Sentiment Labeling",
                    "content": "Sentiment guidelines for positive and negative.",
                    "keywords": ["sentiment", "positive", "negative"],
                },
            ]
        )

        disagreement = Disagreement(
            record_id=uuid.uuid4(),
            task_schema_id=TASK_SCHEMA_ID,
            conflicting_event_ids=[uuid.uuid4()],
            disagreement_type=DisagreementType.human_human,
            fields_in_conflict=["sentiment"],
            reviewer_labels={
                "r1": {"sentiment": "positive"},
                "r2": {"sentiment": "negative"},
            },
        )

        contexts = service.get_policy_context(disagreement)
        assert len(contexts) == 1
        excerpts = contexts[0].excerpts
        assert len(excerpts) >= 1
        # Most relevant should be first
        assert excerpts[0].section_id == "more_relevant"


# ---------------------------------------------------------------------------
# AJ-007: Adjudication creates review events
# ---------------------------------------------------------------------------


class TestAdjudicationReviewEvents:
    """Tests for review event creation from adjudication (AJ-007)."""

    def _make_queue(self, service: AdjudicationService) -> list[AdjudicationQueueItem]:
        """Helper to create a queue with one item."""
        d = Disagreement(
            record_id=uuid.uuid4(),
            task_schema_id=TASK_SCHEMA_ID,
            conflicting_event_ids=[uuid.uuid4(), uuid.uuid4()],
            disagreement_type=DisagreementType.human_human,
            fields_in_conflict=["sentiment"],
        )
        return service.build_queue([d])

    def test_resolve_creates_review_event(self, service: AdjudicationService) -> None:
        """Resolving with 'resolve' creates a review event ID."""
        queue = self._make_queue(service)
        result = service.resolve(
            queue[0].id,
            uuid.uuid4(),
            AdjudicationResolution.resolve,
            resolved_labels={"sentiment": "positive"},
            rationale="Adjudicator determined positive",
        )
        assert result.review_event_id is not None

    def test_preserve_does_not_create_event(self, service: AdjudicationService) -> None:
        """Preserving disagreement does not create a review event."""
        queue = self._make_queue(service)
        result = service.resolve(
            queue[0].id,
            uuid.uuid4(),
            AdjudicationResolution.preserve_disagreement,
        )
        assert result.review_event_id is None

    def test_review_event_is_append_only(self, service: AdjudicationService) -> None:
        """Each resolution creates a new event ID, never reusing old ones."""
        d1 = Disagreement(
            record_id=uuid.uuid4(),
            task_schema_id=TASK_SCHEMA_ID,
            conflicting_event_ids=[uuid.uuid4()],
            disagreement_type=DisagreementType.human_human,
            fields_in_conflict=["f"],
        )
        d2 = Disagreement(
            record_id=uuid.uuid4(),
            task_schema_id=TASK_SCHEMA_ID,
            conflicting_event_ids=[uuid.uuid4()],
            disagreement_type=DisagreementType.human_human,
            fields_in_conflict=["f"],
        )
        queue = service.build_queue([d1, d2])

        r1 = service.resolve(
            queue[0].id,
            uuid.uuid4(),
            AdjudicationResolution.resolve,
            resolved_labels={"f": "a"},
        )
        r2 = service.resolve(
            queue[1].id,
            uuid.uuid4(),
            AdjudicationResolution.resolve,
            resolved_labels={"f": "b"},
        )

        assert r1.review_event_id is not None
        assert r2.review_event_id is not None
        assert r1.review_event_id != r2.review_event_id

    def test_resolution_includes_workspace_id(
        self, service: AdjudicationService
    ) -> None:
        """Resolution can include workspace ID for audit trail."""
        queue = self._make_queue(service)
        result = service.resolve(
            queue[0].id,
            uuid.uuid4(),
            AdjudicationResolution.resolve,
            resolved_labels={"sentiment": "positive"},
            workspace_id=WORKSPACE_ID,
        )
        assert result.review_event_id is not None
        assert result.adjudication_id is not None

"""Unit tests for adjudication service (AJ-001 through AJ-005).

Tests cover:
- AJ-001: Disagreement detection (human-human and human-agent)
- AJ-002: Adjudication queue with severity/type classification
- AJ-004: Side-by-side comparison data
- AJ-005: Policy context matching
"""

from __future__ import annotations

import uuid

import pytest

from molabel.core.adjudication.adjudication_service import (
    AdjudicationService,
    AdjudicationSeverity,
    AdjudicationType,
    Disagreement,
    DisagreementType,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


TASK_SCHEMA_ID = uuid.uuid4()


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

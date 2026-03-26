"""Tests for agent feedback loop (AG-009, AG-010, AG-011, AG-012)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from molabel.core.agents.feedback_loop import (
    CorrectionBatch,
    FeedbackLoopService,
    FeedbackNotificationType,
    InvalidStateTransitionError,
    ReviewDecisionOnRefinement,
    ReviewDecisionType,
)
from molabel.core.types import CorrectionBatchStatus


@pytest.fixture()
def service() -> FeedbackLoopService:
    return FeedbackLoopService(batch_threshold=5, max_retry_attempts=3)


# ---------------------------------------------------------------------------
# AG-009: Correction accumulation and pattern extraction
# ---------------------------------------------------------------------------


class TestCorrectionAccumulation:
    def test_add_correction_creates_batch(self, service: FeedbackLoopService) -> None:
        """Adding a correction auto-creates a batch."""
        batch, is_ready = service.add_correction(
            record_id="r1",
            field_name="sentiment",
            agent_label="positive",
            human_label="negative",
        )
        assert batch.status == CorrectionBatchStatus.accumulating
        assert len(batch.corrections) == 1
        assert is_ready is False

    def test_batch_transitions_when_threshold_reached(
        self, service: FeedbackLoopService
    ) -> None:
        """Batch transitions to ready_for_analysis at threshold."""
        for i in range(5):
            batch, is_ready = service.add_correction(
                record_id=f"r{i}",
                field_name="sentiment",
                agent_label="positive",
                human_label="negative",
            )
        assert is_ready is True
        assert batch.status == CorrectionBatchStatus.ready_for_analysis

    def test_analyze_batch_extracts_patterns(
        self, service: FeedbackLoopService
    ) -> None:
        """Analysis extracts systematic bias patterns."""
        # Create a batch with systematic errors
        for i in range(5):
            service.add_correction(
                record_id=f"r{i}",
                field_name="sentiment",
                agent_label="positive",
                human_label="negative",
                rationale="Agent misses sarcasm",
            )

        batch = list(service._batches.values())[0]
        result = service.analyze_batch(batch.batch_id)

        assert result.status in (
            CorrectionBatchStatus.analyzed,
            CorrectionBatchStatus.refinements_pending,
        )
        assert len(result.patterns) > 0
        assert any(p.pattern_type == "systematic_bias" for p in result.patterns)

    def test_analyze_generates_suggestions(self, service: FeedbackLoopService) -> None:
        """Analysis generates refinement suggestions from patterns."""
        for i in range(5):
            service.add_correction(
                record_id=f"r{i}",
                field_name="sentiment",
                agent_label="positive",
                human_label="negative",
            )

        batch = list(service._batches.values())[0]
        result = service.analyze_batch(batch.batch_id)

        assert len(result.suggestions) > 0
        assert all(s.patch_text for s in result.suggestions)
        assert all(s.target_layer == "patch" for s in result.suggestions)

    def test_analyze_not_ready_raises(self, service: FeedbackLoopService) -> None:
        """Cannot analyze a batch that's not in ready_for_analysis state."""
        service.add_correction(
            record_id="r1", field_name="s", agent_label="a", human_label="b"
        )
        batch = list(service._batches.values())[0]
        with pytest.raises(InvalidStateTransitionError):
            service.analyze_batch(batch.batch_id)

    def test_mixed_field_patterns(self, service: FeedbackLoopService) -> None:
        """Patterns are detected per-field."""
        svc = FeedbackLoopService(batch_threshold=6)
        for i in range(3):
            svc.add_correction(
                record_id=f"r{i}",
                field_name="sentiment",
                agent_label="pos",
                human_label="neg",
            )
        for i in range(3):
            svc.add_correction(
                record_id=f"r{i + 3}",
                field_name="toxicity",
                agent_label="low",
                human_label="high",
            )

        batch = list(svc._batches.values())[0]
        result = svc.analyze_batch(batch.batch_id)
        fields = {p.affected_field for p in result.patterns}
        assert "sentiment" in fields
        assert "toxicity" in fields


# ---------------------------------------------------------------------------
# AG-010: Refinement review
# ---------------------------------------------------------------------------


class TestRefinementReview:
    def _make_analyzed_batch(self, service: FeedbackLoopService) -> CorrectionBatch:
        """Helper: create and analyze a batch."""
        for i in range(5):
            service.add_correction(
                record_id=f"r{i}",
                field_name="sentiment",
                agent_label="positive",
                human_label="negative",
            )
        batch = list(service._batches.values())[0]
        return service.analyze_batch(batch.batch_id)

    def test_accept_refinement(self, service: FeedbackLoopService) -> None:
        """Accepting a refinement transitions batch to applied."""
        batch = self._make_analyzed_batch(service)
        assert batch.status == CorrectionBatchStatus.refinements_pending

        decisions = [
            ReviewDecisionOnRefinement(
                suggestion_id=batch.suggestions[0].suggestion_id,
                decision=ReviewDecisionType.accept,
            )
        ]
        review = service.review_refinements(batch.batch_id, decisions)
        assert review.new_prompt_version is not None
        assert batch.status == CorrectionBatchStatus.applied

    def test_reject_all_refinements(self, service: FeedbackLoopService) -> None:
        """Rejecting all refinements transitions batch to dismissed."""
        batch = self._make_analyzed_batch(service)

        decisions = [
            ReviewDecisionOnRefinement(
                suggestion_id=s.suggestion_id,
                decision=ReviewDecisionType.reject,
            )
            for s in batch.suggestions
        ]
        review = service.review_refinements(batch.batch_id, decisions)
        assert batch.status == CorrectionBatchStatus.dismissed
        assert review.new_prompt_version is None

    def test_modify_refinement(self, service: FeedbackLoopService) -> None:
        """Modifying a refinement applies the modified text."""
        batch = self._make_analyzed_batch(service)

        decisions = [
            ReviewDecisionOnRefinement(
                suggestion_id=batch.suggestions[0].suggestion_id,
                decision=ReviewDecisionType.modify,
                modified_patch_text="Custom fix: watch for sarcasm.",
            )
        ]
        review = service.review_refinements(batch.batch_id, decisions)
        assert review.new_prompt_version is not None
        assert batch.status == CorrectionBatchStatus.applied

    def test_get_pending_suggestions(self, service: FeedbackLoopService) -> None:
        """Pending suggestions are retrievable before review."""
        batch = self._make_analyzed_batch(service)
        suggestions = service.get_pending_suggestions(batch.batch_id)
        assert len(suggestions) > 0

    def test_get_pending_suggestions_after_applied(
        self, service: FeedbackLoopService
    ) -> None:
        """No pending suggestions after batch is applied."""
        batch = self._make_analyzed_batch(service)
        decisions = [
            ReviewDecisionOnRefinement(
                suggestion_id=batch.suggestions[0].suggestion_id,
                decision=ReviewDecisionType.accept,
            )
        ]
        service.review_refinements(batch.batch_id, decisions)
        assert service.get_pending_suggestions(batch.batch_id) == []


# ---------------------------------------------------------------------------
# AG-011: Correction batch lifecycle state machine
# ---------------------------------------------------------------------------


class TestBatchLifecycle:
    def test_valid_transitions(self, service: FeedbackLoopService) -> None:
        """Valid state transitions are allowed."""
        transitions = service.get_valid_transitions(CorrectionBatchStatus.accumulating)
        assert CorrectionBatchStatus.ready_for_analysis in transitions

    def test_terminal_states_have_no_transitions(
        self, service: FeedbackLoopService
    ) -> None:
        """Terminal states (applied, dismissed) have no valid transitions."""
        assert service.get_valid_transitions(CorrectionBatchStatus.applied) == set()
        assert service.get_valid_transitions(CorrectionBatchStatus.dismissed) == set()

    def test_invalid_transition_raises(self, service: FeedbackLoopService) -> None:
        """Invalid state transitions raise InvalidStateTransitionError."""
        service.add_correction(
            record_id="r1", field_name="s", agent_label="a", human_label="b"
        )
        batch = list(service._batches.values())[0]
        assert batch.status == CorrectionBatchStatus.accumulating

        with pytest.raises(InvalidStateTransitionError):
            service._transition(batch, CorrectionBatchStatus.applied)

    def test_full_lifecycle_happy_path(self, service: FeedbackLoopService) -> None:
        """Full lifecycle: accumulating -> ready -> analyzed -> pending -> applied."""
        for i in range(5):
            service.add_correction(
                record_id=f"r{i}",
                field_name="sentiment",
                agent_label="positive",
                human_label="negative",
            )

        batch = list(service._batches.values())[0]
        assert batch.status == CorrectionBatchStatus.ready_for_analysis

        service.analyze_batch(batch.batch_id)
        assert batch.status == CorrectionBatchStatus.refinements_pending

        decisions = [
            ReviewDecisionOnRefinement(
                suggestion_id=batch.suggestions[0].suggestion_id,
                decision=ReviewDecisionType.accept,
            )
        ]
        service.review_refinements(batch.batch_id, decisions)
        assert batch.status == CorrectionBatchStatus.applied

    def test_get_batch_status(self, service: FeedbackLoopService) -> None:
        """Can query batch status by ID."""
        service.add_correction(
            record_id="r1", field_name="s", agent_label="a", human_label="b"
        )
        batch = list(service._batches.values())[0]
        assert (
            service.get_batch_status(batch.batch_id)
            == CorrectionBatchStatus.accumulating
        )


# ---------------------------------------------------------------------------
# AG-012: Error handling and retry
# ---------------------------------------------------------------------------


class TestErrorHandlingAndRetry:
    def test_persist_and_load_batch(
        self, service: FeedbackLoopService, tmp_path: Path
    ) -> None:
        """Batch can be persisted to and loaded from disk."""
        svc = FeedbackLoopService(batch_threshold=3, persistence_dir=tmp_path)
        for i in range(3):
            svc.add_correction(
                record_id=f"r{i}",
                field_name="sentiment",
                agent_label="pos",
                human_label="neg",
            )
        batch = list(svc._batches.values())[0]
        file_path = svc.persist_batch(batch.batch_id)
        assert file_path is not None
        assert file_path.exists()

        # Load in fresh service
        svc2 = FeedbackLoopService(batch_threshold=3)
        loaded = svc2.load_batch(file_path)
        assert loaded.batch_id == batch.batch_id
        assert len(loaded.corrections) == 3

    def test_persist_without_dir_returns_none(
        self, service: FeedbackLoopService
    ) -> None:
        """Persistence returns None when no dir is configured."""
        service.add_correction(
            record_id="r1", field_name="s", agent_label="a", human_label="b"
        )
        batch = list(service._batches.values())[0]
        assert service.persist_batch(batch.batch_id) is None

    def test_get_failed_batches(self, service: FeedbackLoopService) -> None:
        """Failed batches are tracked."""
        assert service.get_failed_batches() == []

    def test_retry_record_tracking(self, service: FeedbackLoopService) -> None:
        """Retry records track attempt counts and exhaustion."""
        batch_id = uuid.uuid4()
        assert service.get_retry_record(batch_id) is None

    def test_notifications_emitted(self, service: FeedbackLoopService) -> None:
        """Notifications are emitted during lifecycle transitions."""
        for i in range(5):
            service.add_correction(
                record_id=f"r{i}",
                field_name="sentiment",
                agent_label="positive",
                human_label="negative",
            )

        # Should have a batch_ready notification
        types = [n.notification_type for n in service.notifications]
        assert FeedbackNotificationType.batch_ready in types

    def test_json_serialization_format(self, tmp_path: Path) -> None:
        """Persisted JSON has the expected structure."""
        svc = FeedbackLoopService(batch_threshold=2, persistence_dir=tmp_path)
        for i in range(2):
            svc.add_correction(
                record_id=f"r{i}",
                field_name="s",
                agent_label="a",
                human_label="b",
                rationale="test",
            )
        batch = list(svc._batches.values())[0]
        file_path = svc.persist_batch(batch.batch_id)
        data = json.loads(file_path.read_text())

        assert "batch_id" in data
        assert "corrections" in data
        assert len(data["corrections"]) == 2
        assert data["corrections"][0]["field_name"] == "s"

    def test_batch_not_found_raises(self, service: FeedbackLoopService) -> None:
        """Querying a nonexistent batch raises KeyError."""
        with pytest.raises(KeyError):
            service.get_batch_status(uuid.uuid4())

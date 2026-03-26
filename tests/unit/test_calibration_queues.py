"""Unit tests for calibration queue service (RV-006).

Tests cover:
- Calibration item management
- Reviewer submission tracking
- Gold-standard evaluation
- Pass/fail threshold logic
- Per-field scoring
- Minimum reviewer requirements
"""

from __future__ import annotations

import uuid

import pytest

from molabel.core.review.calibration import (
    CalibrationConfig,
    CalibrationItem,
    CalibrationService,
    CalibrationStatus,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TASK_SCHEMA_ID = uuid.uuid4()


@pytest.fixture()
def config() -> CalibrationConfig:
    """Default calibration config."""
    return CalibrationConfig(min_reviewers=2, pass_threshold=0.8, item_count=3)


@pytest.fixture()
def items() -> list[CalibrationItem]:
    """Three calibration items with gold-standard labels."""
    return [
        CalibrationItem(
            record_id=uuid.uuid4(),
            gold_labels={"sentiment": "positive", "toxicity": "none"},
            task_schema_id=TASK_SCHEMA_ID,
        ),
        CalibrationItem(
            record_id=uuid.uuid4(),
            gold_labels={"sentiment": "negative", "toxicity": "low"},
            task_schema_id=TASK_SCHEMA_ID,
        ),
        CalibrationItem(
            record_id=uuid.uuid4(),
            gold_labels={"sentiment": "neutral", "toxicity": "none"},
            task_schema_id=TASK_SCHEMA_ID,
        ),
    ]


@pytest.fixture()
def service(
    config: CalibrationConfig, items: list[CalibrationItem]
) -> CalibrationService:
    """CalibrationService with items pre-loaded."""
    svc = CalibrationService(config)
    svc.set_items(items)
    return svc


# ---------------------------------------------------------------------------
# Tests: Item management
# ---------------------------------------------------------------------------


class TestCalibrationItemManagement:
    """Tests for calibration item setup and retrieval."""

    def test_set_items(self, config: CalibrationConfig) -> None:
        """set_items stores items for the session."""
        svc = CalibrationService(config)
        assert svc.items == []

        item = CalibrationItem(
            record_id=uuid.uuid4(),
            gold_labels={"x": "y"},
            task_schema_id=TASK_SCHEMA_ID,
        )
        svc.set_items([item])
        assert len(svc.items) == 1
        assert svc.items[0].record_id == item.record_id

    def test_items_are_copied(self, service: CalibrationService) -> None:
        """items property returns a copy, not a mutable reference."""
        items = service.items
        items.clear()
        assert len(service.items) == 3

    def test_config_accessible(self, service: CalibrationService) -> None:
        """config property returns the configuration."""
        assert service.config.min_reviewers == 2
        assert service.config.pass_threshold == 0.8


# ---------------------------------------------------------------------------
# Tests: Submission tracking
# ---------------------------------------------------------------------------


class TestCalibrationSubmissions:
    """Tests for reviewer submission recording and progress tracking."""

    def test_record_submission(
        self, service: CalibrationService, items: list[CalibrationItem]
    ) -> None:
        """record_submission tracks a reviewer's labels."""
        reviewer_id = uuid.uuid4()
        labels = {"sentiment": "positive", "toxicity": "none"}
        service.record_submission(reviewer_id, items[0].record_id, labels)
        assert service.get_reviewer_progress(reviewer_id) == 1

    def test_progress_counts_only_calibration_items(
        self, service: CalibrationService, items: list[CalibrationItem]
    ) -> None:
        """Progress counts only calibration items, not arbitrary records."""
        reviewer_id = uuid.uuid4()
        # Submit for a calibration item
        service.record_submission(
            reviewer_id, items[0].record_id, {"sentiment": "positive"}
        )
        # Submit for a random non-calibration record
        service.record_submission(reviewer_id, uuid.uuid4(), {"sentiment": "neutral"})
        assert service.get_reviewer_progress(reviewer_id) == 1

    def test_has_completed_calibration(
        self, service: CalibrationService, items: list[CalibrationItem]
    ) -> None:
        """has_completed_calibration returns True when all items reviewed."""
        reviewer_id = uuid.uuid4()
        for item in items:
            service.record_submission(reviewer_id, item.record_id, item.gold_labels)
        assert service.has_completed_calibration(reviewer_id) is True

    def test_has_not_completed_calibration(
        self, service: CalibrationService, items: list[CalibrationItem]
    ) -> None:
        """has_completed_calibration returns False when items remain."""
        reviewer_id = uuid.uuid4()
        service.record_submission(reviewer_id, items[0].record_id, items[0].gold_labels)
        assert service.has_completed_calibration(reviewer_id) is False

    def test_get_pending_items(
        self, service: CalibrationService, items: list[CalibrationItem]
    ) -> None:
        """get_pending_items returns items not yet completed by reviewer."""
        reviewer_id = uuid.uuid4()
        service.record_submission(
            reviewer_id, items[0].record_id, {"sentiment": "positive"}
        )
        pending = service.get_pending_items(reviewer_id)
        assert len(pending) == 2
        pending_ids = {p.record_id for p in pending}
        assert items[0].record_id not in pending_ids


# ---------------------------------------------------------------------------
# Tests: Gold-standard evaluation
# ---------------------------------------------------------------------------


class TestCalibrationEvaluation:
    """Tests for evaluating reviewer answers against gold labels."""

    def test_perfect_score(
        self, service: CalibrationService, items: list[CalibrationItem]
    ) -> None:
        """Reviewer with all correct answers gets 100% accuracy and passes."""
        reviewer_id = uuid.uuid4()
        for item in items:
            service.record_submission(reviewer_id, item.record_id, item.gold_labels)

        result = service.evaluate_reviewer(reviewer_id)
        assert result.accuracy == 1.0
        assert result.items_attempted == 3
        assert result.items_correct == 3
        assert result.status == CalibrationStatus.passed
        assert len(result.incorrect_items) == 0

    def test_failing_score(
        self, service: CalibrationService, items: list[CalibrationItem]
    ) -> None:
        """Reviewer below threshold fails calibration."""
        reviewer_id = uuid.uuid4()
        # Get all items wrong
        for item in items:
            service.record_submission(
                reviewer_id, item.record_id, {"sentiment": "WRONG", "toxicity": "WRONG"}
            )

        result = service.evaluate_reviewer(reviewer_id)
        assert result.accuracy == 0.0
        assert result.status == CalibrationStatus.failed
        assert len(result.incorrect_items) == 3

    def test_partial_score(
        self, service: CalibrationService, items: list[CalibrationItem]
    ) -> None:
        """Reviewer with mixed results gets proportional accuracy."""
        reviewer_id = uuid.uuid4()
        # First item: correct
        service.record_submission(reviewer_id, items[0].record_id, items[0].gold_labels)
        # Second item: wrong
        service.record_submission(
            reviewer_id, items[1].record_id, {"sentiment": "WRONG", "toxicity": "WRONG"}
        )
        # Third item: correct
        service.record_submission(reviewer_id, items[2].record_id, items[2].gold_labels)

        result = service.evaluate_reviewer(reviewer_id)
        assert result.items_attempted == 3
        assert result.items_correct == 2
        assert abs(result.accuracy - 2.0 / 3.0) < 0.01
        # 66.7% < 80% threshold => fail
        assert result.status == CalibrationStatus.failed

    def test_field_scores(
        self, service: CalibrationService, items: list[CalibrationItem]
    ) -> None:
        """Per-field scores are computed correctly."""
        reviewer_id = uuid.uuid4()
        # All sentiment correct, all toxicity wrong
        for item in items:
            service.record_submission(
                reviewer_id,
                item.record_id,
                {"sentiment": item.gold_labels["sentiment"], "toxicity": "WRONG"},
            )

        result = service.evaluate_reviewer(reviewer_id)
        assert result.field_scores["sentiment"] == 1.0
        assert result.field_scores["toxicity"] == 0.0

    def test_in_progress_status(
        self, service: CalibrationService, items: list[CalibrationItem]
    ) -> None:
        """Status is in_progress when not all items are completed."""
        reviewer_id = uuid.uuid4()
        service.record_submission(reviewer_id, items[0].record_id, items[0].gold_labels)

        result = service.evaluate_reviewer(reviewer_id)
        assert result.status == CalibrationStatus.in_progress

    def test_no_submissions_pending(self, service: CalibrationService) -> None:
        """Reviewer with no submissions is pending."""
        result = service.evaluate_reviewer(uuid.uuid4())
        assert result.status == CalibrationStatus.pending

    def test_empty_items_pending(self, config: CalibrationConfig) -> None:
        """Service with no items set returns pending."""
        svc = CalibrationService(config)
        result = svc.evaluate_reviewer(uuid.uuid4())
        assert result.status == CalibrationStatus.pending


# ---------------------------------------------------------------------------
# Tests: Minimum reviewer requirements
# ---------------------------------------------------------------------------


class TestCalibrationMinReviewers:
    """Tests for minimum reviewer threshold logic."""

    def test_has_enough_reviewers_true(
        self, service: CalibrationService, items: list[CalibrationItem]
    ) -> None:
        """has_enough_reviewers returns True when min_reviewers have passed."""
        for _ in range(2):
            reviewer_id = uuid.uuid4()
            for item in items:
                service.record_submission(reviewer_id, item.record_id, item.gold_labels)

        assert service.has_enough_reviewers() is True

    def test_has_enough_reviewers_false(
        self, service: CalibrationService, items: list[CalibrationItem]
    ) -> None:
        """has_enough_reviewers returns False when below threshold."""
        reviewer_id = uuid.uuid4()
        for item in items:
            service.record_submission(reviewer_id, item.record_id, item.gold_labels)

        assert service.has_enough_reviewers() is False

    def test_get_passed_reviewers(
        self, service: CalibrationService, items: list[CalibrationItem]
    ) -> None:
        """get_passed_reviewers returns only reviewers who met threshold."""
        # Perfect reviewer
        good = uuid.uuid4()
        for item in items:
            service.record_submission(good, item.record_id, item.gold_labels)

        # Failing reviewer
        bad = uuid.uuid4()
        for item in items:
            service.record_submission(
                bad, item.record_id, {"sentiment": "WRONG", "toxicity": "WRONG"}
            )

        passed = service.get_passed_reviewers()
        assert good in passed
        assert bad not in passed

    def test_get_completed_reviewers(
        self, service: CalibrationService, items: list[CalibrationItem]
    ) -> None:
        """get_completed_reviewers returns all who finished, pass or fail."""
        r1 = uuid.uuid4()
        r2 = uuid.uuid4()
        for item in items:
            service.record_submission(r1, item.record_id, item.gold_labels)
            service.record_submission(
                r2, item.record_id, {"sentiment": "WRONG", "toxicity": "WRONG"}
            )

        completed = service.get_completed_reviewers()
        assert r1 in completed
        assert r2 in completed

"""Calibration queue service (RV-006).

Manages shared calibration item sets that all reviewers must complete
before proceeding to the regular review queue. Compares reviewer answers
against gold-standard labels to assess readiness.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class CalibrationStatus(StrEnum):
    """Status of a reviewer's calibration progress."""

    pending = "pending"
    in_progress = "in_progress"
    passed = "passed"
    failed = "failed"


@dataclass(frozen=True)
class CalibrationConfig:
    """Configuration for a calibration session."""

    min_reviewers: int = 2
    pass_threshold: float = 0.8
    item_count: int = 10


@dataclass(frozen=True)
class CalibrationItem:
    """A single calibration item with its gold-standard labels."""

    record_id: uuid.UUID
    gold_labels: dict[str, Any]
    task_schema_id: uuid.UUID


@dataclass
class ReviewerCalibrationResult:
    """Result of a single reviewer's calibration attempt."""

    reviewer_id: uuid.UUID
    items_attempted: int = 0
    items_correct: int = 0
    accuracy: float = 0.0
    status: CalibrationStatus = CalibrationStatus.pending
    field_scores: dict[str, float] = field(default_factory=dict)
    incorrect_items: list[uuid.UUID] = field(default_factory=list)


class CalibrationService:
    """Manages calibration item sets and tracks reviewer progress (RV-006).

    Pure computation service: takes data in, returns results. No database
    access or side effects.
    """

    def __init__(self, config: CalibrationConfig) -> None:
        self._config = config
        self._items: list[CalibrationItem] = []
        self._reviewer_submissions: dict[
            uuid.UUID, dict[uuid.UUID, dict[str, Any]]
        ] = {}

    @property
    def config(self) -> CalibrationConfig:
        """Return the current calibration configuration."""
        return self._config

    @property
    def items(self) -> list[CalibrationItem]:
        """Return the list of calibration items."""
        return list(self._items)

    def set_items(self, items: list[CalibrationItem]) -> None:
        """Set the calibration items for this session.

        All reviewers will be required to review these same items.
        """
        self._items = list(items)

    def record_submission(
        self,
        reviewer_id: uuid.UUID,
        record_id: uuid.UUID,
        labels: dict[str, Any],
    ) -> None:
        """Record a reviewer's labels for a calibration item."""
        if reviewer_id not in self._reviewer_submissions:
            self._reviewer_submissions[reviewer_id] = {}
        self._reviewer_submissions[reviewer_id][record_id] = labels

    def get_reviewer_progress(self, reviewer_id: uuid.UUID) -> int:
        """Return the number of calibration items completed by a reviewer."""
        submissions = self._reviewer_submissions.get(reviewer_id, {})
        return sum(1 for item in self._items if item.record_id in submissions)

    def get_pending_items(self, reviewer_id: uuid.UUID) -> list[CalibrationItem]:
        """Return calibration items not yet completed by the reviewer."""
        submissions = self._reviewer_submissions.get(reviewer_id, {})
        return [item for item in self._items if item.record_id not in submissions]

    def has_completed_calibration(self, reviewer_id: uuid.UUID) -> bool:
        """Check whether a reviewer has completed all calibration items."""
        return self.get_reviewer_progress(reviewer_id) >= len(self._items)

    def evaluate_reviewer(self, reviewer_id: uuid.UUID) -> ReviewerCalibrationResult:
        """Evaluate a reviewer's calibration submissions against gold labels.

        Compares each submitted label field against the gold-standard and
        computes overall accuracy plus per-field scores. A reviewer passes
        calibration if their accuracy meets or exceeds the configured
        ``pass_threshold``.
        """
        submissions = self._reviewer_submissions.get(reviewer_id, {})
        if not self._items:
            return ReviewerCalibrationResult(
                reviewer_id=reviewer_id,
                status=CalibrationStatus.pending,
            )

        items_attempted = 0
        items_correct = 0
        incorrect_items: list[uuid.UUID] = []
        field_correct: dict[str, int] = {}
        field_total: dict[str, int] = {}

        for item in self._items:
            reviewer_labels = submissions.get(item.record_id)
            if reviewer_labels is None:
                continue

            items_attempted += 1
            item_is_correct = True

            for field_name, gold_value in item.gold_labels.items():
                field_total[field_name] = field_total.get(field_name, 0) + 1
                reviewer_value = reviewer_labels.get(field_name)
                if reviewer_value == gold_value:
                    field_correct[field_name] = field_correct.get(field_name, 0) + 1
                else:
                    item_is_correct = False

            if item_is_correct:
                items_correct += 1
            else:
                incorrect_items.append(item.record_id)

        accuracy = items_correct / items_attempted if items_attempted > 0 else 0.0

        field_scores: dict[str, float] = {}
        for fname in field_total:
            total = field_total[fname]
            correct = field_correct.get(fname, 0)
            field_scores[fname] = correct / total if total > 0 else 0.0

        all_completed = items_attempted >= len(self._items)
        if items_attempted == 0:
            status = CalibrationStatus.pending
        elif not all_completed:
            status = CalibrationStatus.in_progress
        elif accuracy >= self._config.pass_threshold:
            status = CalibrationStatus.passed
        else:
            status = CalibrationStatus.failed

        return ReviewerCalibrationResult(
            reviewer_id=reviewer_id,
            items_attempted=items_attempted,
            items_correct=items_correct,
            accuracy=accuracy,
            status=status,
            field_scores=field_scores,
            incorrect_items=incorrect_items,
        )

    def get_completed_reviewers(self) -> list[uuid.UUID]:
        """Return IDs of reviewers who have completed all calibration items."""
        return [
            rid
            for rid in self._reviewer_submissions
            if self.has_completed_calibration(rid)
        ]

    def get_passed_reviewers(self) -> list[uuid.UUID]:
        """Return IDs of reviewers who passed calibration."""
        return [
            rid
            for rid in self._reviewer_submissions
            if self.evaluate_reviewer(rid).status == CalibrationStatus.passed
        ]

    def has_enough_reviewers(self) -> bool:
        """Check if the minimum number of reviewers have passed calibration."""
        return len(self.get_passed_reviewers()) >= self._config.min_reviewers

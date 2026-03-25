"""Calibration summary service (QA-006).

Analyzes calibration queue results, computes per-reviewer calibration
accuracy (% matching gold standard), and identifies reviewers needing
retraining.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, Field

from molabel.core.utils.canonical import canonical_label_value as _canonical_value


class ReviewerCalibration(BaseModel):
    """Calibration metrics for a single reviewer."""

    reviewer_id: str
    total_calibration_items: int = 0
    correct_items: int = 0
    accuracy: float = 0.0
    incorrect_fields: dict[str, int] = Field(default_factory=dict)
    """Count of incorrect labels per field name."""
    needs_retraining: bool = False


class CalibrationResult(BaseModel):
    """Full calibration summary output."""

    total_calibration_items: int = 0
    total_reviewers: int = 0
    overall_accuracy: float = 0.0
    reviewers: dict[str, ReviewerCalibration] = Field(default_factory=dict)
    reviewers_needing_retraining: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CalibrationRecord(BaseModel):
    """A single calibration review with gold standard comparison."""

    record_id: str
    reviewer_id: str
    reviewer_labels: dict[str, Any] = Field(default_factory=dict)
    gold_labels: dict[str, Any] = Field(default_factory=dict)


class CalibrationSummaryService:
    """Analyze calibration queue results and assess reviewer accuracy."""

    def __init__(
        self,
        *,
        retraining_threshold: float = 0.8,
    ) -> None:
        """Initialize with configurable thresholds.

        Parameters
        ----------
        retraining_threshold:
            Reviewers with accuracy below this value are flagged for
            retraining (default 80%).
        """
        self.retraining_threshold = retraining_threshold

    def analyze(
        self,
        records: Sequence[CalibrationRecord | dict[str, Any]],
        *,
        fields: Sequence[str] | None = None,
    ) -> CalibrationResult:
        """Compute calibration accuracy for each reviewer.

        Parameters
        ----------
        records:
            Calibration records with reviewer labels and gold standard labels.
        fields:
            If provided, restrict comparison to these field names.

        Returns
        -------
        CalibrationResult with per-reviewer accuracy and retraining flags.
        """
        normalized = [self._normalize_record(r) for r in records]

        if not normalized:
            return CalibrationResult(
                warnings=["No calibration records provided."],
            )

        field_names = self._resolve_fields(normalized, fields)

        # Group by reviewer
        reviewer_groups: dict[str, list[CalibrationRecord]] = defaultdict(list)
        for record in normalized:
            reviewer_groups[record.reviewer_id].append(record)

        reviewers: dict[str, ReviewerCalibration] = {}
        total_correct = 0
        total_items = 0
        reviewers_needing_retraining: list[str] = []

        for reviewer_id, reviewer_records in sorted(reviewer_groups.items()):
            calibration = self._compute_reviewer_calibration(
                reviewer_id, reviewer_records, field_names
            )
            reviewers[reviewer_id] = calibration
            total_correct += calibration.correct_items
            total_items += calibration.total_calibration_items
            if calibration.needs_retraining:
                reviewers_needing_retraining.append(reviewer_id)

        overall_accuracy = total_correct / total_items if total_items > 0 else 0.0

        warnings: list[str] = []
        if not field_names:
            warnings.append("No label fields found in calibration records.")

        return CalibrationResult(
            total_calibration_items=total_items,
            total_reviewers=len(reviewers),
            overall_accuracy=overall_accuracy,
            reviewers=reviewers,
            reviewers_needing_retraining=reviewers_needing_retraining,
            warnings=warnings,
        )

    def _compute_reviewer_calibration(
        self,
        reviewer_id: str,
        records: Sequence[CalibrationRecord],
        field_names: list[str],
    ) -> ReviewerCalibration:
        total_items = len(records)
        correct_items = 0
        incorrect_fields: dict[str, int] = defaultdict(int)

        for record in records:
            record_correct = True
            for field in field_names:
                reviewer_val = record.reviewer_labels.get(field)
                gold_val = record.gold_labels.get(field)

                # Skip fields absent from both
                if reviewer_val is None and gold_val is None:
                    continue

                if _canonical_value(reviewer_val) != _canonical_value(gold_val):
                    record_correct = False
                    incorrect_fields[field] += 1

            if record_correct:
                correct_items += 1

        accuracy = correct_items / total_items if total_items > 0 else 0.0
        needs_retraining = accuracy < self.retraining_threshold

        return ReviewerCalibration(
            reviewer_id=reviewer_id,
            total_calibration_items=total_items,
            correct_items=correct_items,
            accuracy=accuracy,
            incorrect_fields=dict(incorrect_fields),
            needs_retraining=needs_retraining,
        )

    def _normalize_record(
        self, record: CalibrationRecord | dict[str, Any]
    ) -> CalibrationRecord:
        if isinstance(record, CalibrationRecord):
            return record
        return CalibrationRecord.model_validate(record)

    def _resolve_fields(
        self,
        records: Sequence[CalibrationRecord],
        fields: Sequence[str] | None,
    ) -> list[str]:
        if fields is not None:
            return list(dict.fromkeys(fields))
        discovered: set[str] = set()
        for record in records:
            discovered.update(record.gold_labels.keys())
        return sorted(discovered)

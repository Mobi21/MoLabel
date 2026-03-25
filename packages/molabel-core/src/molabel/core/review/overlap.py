"""Overlap review service (RV-007).

Manages N-copy review of items so that multiple reviewers independently
review the same records, enabling inter-annotator agreement computation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum


class OverlapCompletionStatus(StrEnum):
    """Completion status for an overlap assignment."""

    pending = "pending"
    partial = "partial"
    complete = "complete"


@dataclass(frozen=True)
class OverlapConfig:
    """Configuration for overlap review assignments."""

    overlap_count: int = 2
    """Number of independent reviewers required per record."""

    overlap_rate: float = 1.0
    """Fraction of records in the dataset to assign overlap review (0.0-1.0)."""


@dataclass(frozen=True)
class OverlapAssignment:
    """Tracks which reviewers have been assigned to a record."""

    record_id: uuid.UUID
    required_reviewers: int
    assigned_reviewers: tuple[uuid.UUID, ...] = ()
    completed_reviewers: tuple[uuid.UUID, ...] = ()


@dataclass
class OverlapStatus:
    """Summary status of all overlap assignments."""

    total_records: int = 0
    completed_records: int = 0
    partially_completed_records: int = 0
    pending_records: int = 0
    completion_rate: float = 0.0
    average_reviewers_per_record: float = 0.0


class OverlapService:
    """Manages N-copy review of items (RV-007).

    Pure computation service that tracks overlap assignments and ensures
    each record receives the required number of independent reviews.
    """

    def __init__(self, config: OverlapConfig) -> None:
        self._config = config
        self._assignments: dict[uuid.UUID, OverlapAssignment] = {}

    @property
    def config(self) -> OverlapConfig:
        """Return the current overlap configuration."""
        return self._config

    def create_assignments(
        self,
        record_ids: list[uuid.UUID],
    ) -> list[OverlapAssignment]:
        """Create overlap assignments for the given records.

        Each record is assigned to require ``overlap_count`` reviewers.
        """
        assignments: list[OverlapAssignment] = []
        for record_id in record_ids:
            assignment = OverlapAssignment(
                record_id=record_id,
                required_reviewers=self._config.overlap_count,
            )
            self._assignments[record_id] = assignment
            assignments.append(assignment)
        return assignments

    def can_reviewer_claim(
        self,
        record_id: uuid.UUID,
        reviewer_id: uuid.UUID,
    ) -> bool:
        """Check if a reviewer can claim a record for overlap review.

        Returns False if:
        - The reviewer has already been assigned to this record
        - The record already has enough assigned reviewers
        """
        assignment = self._assignments.get(record_id)
        if assignment is None:
            return True

        if reviewer_id in assignment.assigned_reviewers:
            return False

        return len(assignment.assigned_reviewers) < assignment.required_reviewers

    def record_assignment(
        self,
        record_id: uuid.UUID,
        reviewer_id: uuid.UUID,
    ) -> bool:
        """Record that a reviewer has been assigned to a record.

        Returns True if the assignment was successful, False if the
        reviewer was already assigned or the record has enough reviewers.
        """
        if not self.can_reviewer_claim(record_id, reviewer_id):
            return False

        assignment = self._assignments.get(record_id)
        if assignment is None:
            assignment = OverlapAssignment(
                record_id=record_id,
                required_reviewers=self._config.overlap_count,
            )
            self._assignments[record_id] = assignment

        new_assigned = (*assignment.assigned_reviewers, reviewer_id)
        self._assignments[record_id] = OverlapAssignment(
            record_id=record_id,
            required_reviewers=assignment.required_reviewers,
            assigned_reviewers=new_assigned,
            completed_reviewers=assignment.completed_reviewers,
        )
        return True

    def record_completion(
        self,
        record_id: uuid.UUID,
        reviewer_id: uuid.UUID,
    ) -> bool:
        """Record that a reviewer has completed review of a record.

        Returns True if successfully recorded, False if the reviewer
        was not assigned or already completed.
        """
        assignment = self._assignments.get(record_id)
        if assignment is None:
            return False

        if reviewer_id not in assignment.assigned_reviewers:
            return False

        if reviewer_id in assignment.completed_reviewers:
            return False

        new_completed = (*assignment.completed_reviewers, reviewer_id)
        self._assignments[record_id] = OverlapAssignment(
            record_id=record_id,
            required_reviewers=assignment.required_reviewers,
            assigned_reviewers=assignment.assigned_reviewers,
            completed_reviewers=new_completed,
        )
        return True

    def is_record_complete(self, record_id: uuid.UUID) -> bool:
        """Check if a record has received the required number of reviews."""
        assignment = self._assignments.get(record_id)
        if assignment is None:
            return False
        return len(assignment.completed_reviewers) >= assignment.required_reviewers

    def get_record_status(self, record_id: uuid.UUID) -> OverlapCompletionStatus:
        """Get the completion status for a specific record."""
        assignment = self._assignments.get(record_id)
        if assignment is None:
            return OverlapCompletionStatus.pending

        completed = len(assignment.completed_reviewers)
        if completed >= assignment.required_reviewers:
            return OverlapCompletionStatus.complete
        if completed > 0:
            return OverlapCompletionStatus.partial
        return OverlapCompletionStatus.pending

    def get_reviewers_for_record(self, record_id: uuid.UUID) -> list[uuid.UUID]:
        """Return the list of reviewers who have completed review for a record."""
        assignment = self._assignments.get(record_id)
        if assignment is None:
            return []
        return list(assignment.completed_reviewers)

    def get_status(self) -> OverlapStatus:
        """Compute summary status across all overlap assignments."""
        if not self._assignments:
            return OverlapStatus()

        total = len(self._assignments)
        completed = 0
        partial = 0
        pending = 0
        total_reviewers = 0

        for assignment in self._assignments.values():
            num_completed = len(assignment.completed_reviewers)
            total_reviewers += num_completed
            if num_completed >= assignment.required_reviewers:
                completed += 1
            elif num_completed > 0:
                partial += 1
            else:
                pending += 1

        return OverlapStatus(
            total_records=total,
            completed_records=completed,
            partially_completed_records=partial,
            pending_records=pending,
            completion_rate=completed / total if total > 0 else 0.0,
            average_reviewers_per_record=(
                total_reviewers / total if total > 0 else 0.0
            ),
        )

    def needs_more_reviewers(self, record_id: uuid.UUID) -> bool:
        """Check if a record still needs additional reviewers."""
        assignment = self._assignments.get(record_id)
        if assignment is None:
            return True
        remaining = assignment.required_reviewers - len(assignment.assigned_reviewers)
        return remaining > 0

    def get_remaining_reviewer_count(self, record_id: uuid.UUID) -> int:
        """Return how many more reviewers are needed for a record."""
        assignment = self._assignments.get(record_id)
        if assignment is None:
            return self._config.overlap_count
        return max(
            0,
            assignment.required_reviewers - len(assignment.assigned_reviewers),
        )

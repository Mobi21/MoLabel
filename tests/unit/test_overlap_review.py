"""Unit tests for overlap review service (RV-007).

Tests cover:
- Overlap assignment creation
- Duplicate reviewer prevention
- Completion tracking
- Status reporting
- Remaining reviewer counts
"""

from __future__ import annotations

import uuid

import pytest

from molabel.core.review.overlap import (
    OverlapCompletionStatus,
    OverlapConfig,
    OverlapService,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def config() -> OverlapConfig:
    """Default overlap config requiring 2 reviewers per record."""
    return OverlapConfig(overlap_count=2, overlap_rate=1.0)


@pytest.fixture()
def service(config: OverlapConfig) -> OverlapService:
    """OverlapService with default config."""
    return OverlapService(config)


@pytest.fixture()
def record_ids() -> list[uuid.UUID]:
    """Five test record IDs."""
    return [uuid.uuid4() for _ in range(5)]


# ---------------------------------------------------------------------------
# Tests: Assignment creation
# ---------------------------------------------------------------------------


class TestOverlapAssignment:
    """Tests for creating and managing overlap assignments."""

    def test_create_assignments(
        self, service: OverlapService, record_ids: list[uuid.UUID]
    ) -> None:
        """create_assignments produces one assignment per record."""
        assignments = service.create_assignments(record_ids)
        assert len(assignments) == 5
        for assignment, record_id in zip(assignments, record_ids, strict=True):
            assert assignment.record_id == record_id
            assert assignment.required_reviewers == 2

    def test_initial_status_pending(
        self, service: OverlapService, record_ids: list[uuid.UUID]
    ) -> None:
        """All records start with pending status."""
        service.create_assignments(record_ids)
        for rid in record_ids:
            assert service.get_record_status(rid) == OverlapCompletionStatus.pending

    def test_unknown_record_pending(self, service: OverlapService) -> None:
        """Unknown record ID returns pending status."""
        assert (
            service.get_record_status(uuid.uuid4()) == OverlapCompletionStatus.pending
        )


# ---------------------------------------------------------------------------
# Tests: Reviewer assignment and duplicate prevention
# ---------------------------------------------------------------------------


class TestReviewerDuplicatePrevention:
    """Tests for preventing same reviewer from reviewing same record twice."""

    def test_record_assignment_succeeds(
        self, service: OverlapService, record_ids: list[uuid.UUID]
    ) -> None:
        """A new reviewer can be assigned to a record."""
        service.create_assignments(record_ids)
        reviewer = uuid.uuid4()
        assert service.record_assignment(record_ids[0], reviewer) is True

    def test_duplicate_assignment_prevented(
        self, service: OverlapService, record_ids: list[uuid.UUID]
    ) -> None:
        """Same reviewer cannot be assigned to the same record twice."""
        service.create_assignments(record_ids)
        reviewer = uuid.uuid4()
        assert service.record_assignment(record_ids[0], reviewer) is True
        assert service.record_assignment(record_ids[0], reviewer) is False

    def test_can_reviewer_claim_false_after_assignment(
        self, service: OverlapService, record_ids: list[uuid.UUID]
    ) -> None:
        """can_reviewer_claim returns False after assignment."""
        service.create_assignments(record_ids)
        reviewer = uuid.uuid4()
        service.record_assignment(record_ids[0], reviewer)
        assert service.can_reviewer_claim(record_ids[0], reviewer) is False

    def test_different_reviewers_can_claim(
        self, service: OverlapService, record_ids: list[uuid.UUID]
    ) -> None:
        """Different reviewers can be assigned to the same record."""
        service.create_assignments(record_ids)
        r1, r2 = uuid.uuid4(), uuid.uuid4()
        assert service.record_assignment(record_ids[0], r1) is True
        assert service.record_assignment(record_ids[0], r2) is True

    def test_max_reviewers_enforced(
        self, service: OverlapService, record_ids: list[uuid.UUID]
    ) -> None:
        """No more than overlap_count reviewers can be assigned."""
        service.create_assignments(record_ids)
        r1, r2, r3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        assert service.record_assignment(record_ids[0], r1) is True
        assert service.record_assignment(record_ids[0], r2) is True
        # Third reviewer should be rejected (overlap_count=2)
        assert service.record_assignment(record_ids[0], r3) is False

    def test_can_reviewer_claim_unknown_record(self, service: OverlapService) -> None:
        """Unknown records return True for can_reviewer_claim."""
        assert service.can_reviewer_claim(uuid.uuid4(), uuid.uuid4()) is True


# ---------------------------------------------------------------------------
# Tests: Completion tracking
# ---------------------------------------------------------------------------


class TestOverlapCompletion:
    """Tests for tracking review completion."""

    def test_record_completion(
        self, service: OverlapService, record_ids: list[uuid.UUID]
    ) -> None:
        """Recording completion updates the status."""
        service.create_assignments(record_ids)
        reviewer = uuid.uuid4()
        service.record_assignment(record_ids[0], reviewer)
        assert service.record_completion(record_ids[0], reviewer) is True

    def test_completion_without_assignment_fails(
        self, service: OverlapService, record_ids: list[uuid.UUID]
    ) -> None:
        """Completing review without assignment returns False."""
        service.create_assignments(record_ids)
        reviewer = uuid.uuid4()
        assert service.record_completion(record_ids[0], reviewer) is False

    def test_duplicate_completion_fails(
        self, service: OverlapService, record_ids: list[uuid.UUID]
    ) -> None:
        """Same reviewer cannot complete the same record twice."""
        service.create_assignments(record_ids)
        reviewer = uuid.uuid4()
        service.record_assignment(record_ids[0], reviewer)
        assert service.record_completion(record_ids[0], reviewer) is True
        assert service.record_completion(record_ids[0], reviewer) is False

    def test_record_complete_when_all_reviewers_done(
        self, service: OverlapService, record_ids: list[uuid.UUID]
    ) -> None:
        """is_record_complete returns True when required reviewers finish."""
        service.create_assignments(record_ids)
        r1, r2 = uuid.uuid4(), uuid.uuid4()
        service.record_assignment(record_ids[0], r1)
        service.record_assignment(record_ids[0], r2)
        service.record_completion(record_ids[0], r1)
        assert service.is_record_complete(record_ids[0]) is False
        service.record_completion(record_ids[0], r2)
        assert service.is_record_complete(record_ids[0]) is True

    def test_partial_status(
        self, service: OverlapService, record_ids: list[uuid.UUID]
    ) -> None:
        """Status is partial when some but not all reviewers complete."""
        service.create_assignments(record_ids)
        reviewer = uuid.uuid4()
        service.record_assignment(record_ids[0], reviewer)
        service.record_completion(record_ids[0], reviewer)
        assert (
            service.get_record_status(record_ids[0]) == OverlapCompletionStatus.partial
        )

    def test_complete_status(
        self, service: OverlapService, record_ids: list[uuid.UUID]
    ) -> None:
        """Status is complete when all required reviewers finish."""
        service.create_assignments(record_ids)
        r1, r2 = uuid.uuid4(), uuid.uuid4()
        service.record_assignment(record_ids[0], r1)
        service.record_assignment(record_ids[0], r2)
        service.record_completion(record_ids[0], r1)
        service.record_completion(record_ids[0], r2)
        assert (
            service.get_record_status(record_ids[0]) == OverlapCompletionStatus.complete
        )

    def test_get_reviewers_for_record(
        self, service: OverlapService, record_ids: list[uuid.UUID]
    ) -> None:
        """get_reviewers_for_record returns completed reviewers."""
        service.create_assignments(record_ids)
        r1 = uuid.uuid4()
        service.record_assignment(record_ids[0], r1)
        service.record_completion(record_ids[0], r1)
        reviewers = service.get_reviewers_for_record(record_ids[0])
        assert r1 in reviewers


# ---------------------------------------------------------------------------
# Tests: Status reporting
# ---------------------------------------------------------------------------


class TestOverlapStatus:
    """Tests for overall overlap status computation."""

    def test_empty_status(self, service: OverlapService) -> None:
        """Empty service returns zero status."""
        status = service.get_status()
        assert status.total_records == 0
        assert status.completion_rate == 0.0

    def test_status_after_assignments(
        self, service: OverlapService, record_ids: list[uuid.UUID]
    ) -> None:
        """Status shows all records as pending after initial assignment."""
        service.create_assignments(record_ids)
        status = service.get_status()
        assert status.total_records == 5
        assert status.pending_records == 5
        assert status.completed_records == 0

    def test_status_with_completions(
        self, service: OverlapService, record_ids: list[uuid.UUID]
    ) -> None:
        """Status reflects completed records correctly."""
        service.create_assignments(record_ids)
        r1, r2 = uuid.uuid4(), uuid.uuid4()
        # Complete first record
        service.record_assignment(record_ids[0], r1)
        service.record_assignment(record_ids[0], r2)
        service.record_completion(record_ids[0], r1)
        service.record_completion(record_ids[0], r2)

        status = service.get_status()
        assert status.completed_records == 1
        assert status.pending_records == 4
        assert abs(status.completion_rate - 0.2) < 0.01

    def test_needs_more_reviewers(
        self, service: OverlapService, record_ids: list[uuid.UUID]
    ) -> None:
        """needs_more_reviewers is True until overlap_count assigned."""
        service.create_assignments(record_ids)
        r1 = uuid.uuid4()
        assert service.needs_more_reviewers(record_ids[0]) is True
        service.record_assignment(record_ids[0], r1)
        assert service.needs_more_reviewers(record_ids[0]) is True
        r2 = uuid.uuid4()
        service.record_assignment(record_ids[0], r2)
        assert service.needs_more_reviewers(record_ids[0]) is False

    def test_remaining_reviewer_count(
        self, service: OverlapService, record_ids: list[uuid.UUID]
    ) -> None:
        """get_remaining_reviewer_count decreases as reviewers are assigned."""
        service.create_assignments(record_ids)
        assert service.get_remaining_reviewer_count(record_ids[0]) == 2
        service.record_assignment(record_ids[0], uuid.uuid4())
        assert service.get_remaining_reviewer_count(record_ids[0]) == 1

    def test_average_reviewers_per_record(
        self, service: OverlapService, record_ids: list[uuid.UUID]
    ) -> None:
        """average_reviewers_per_record is calculated across all records."""
        service.create_assignments(record_ids[:2])  # 2 records
        r1, r2 = uuid.uuid4(), uuid.uuid4()
        service.record_assignment(record_ids[0], r1)
        service.record_assignment(record_ids[0], r2)
        service.record_completion(record_ids[0], r1)
        service.record_completion(record_ids[0], r2)
        # record 0: 2 completions, record 1: 0 completions => avg 1.0
        status = service.get_status()
        assert abs(status.average_reviewers_per_record - 1.0) < 0.01

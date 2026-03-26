"""Tests for the reviewer throughput metrics service (QA-005)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from molabel.core.quality.throughput_metrics import (
    ThroughputMetricsService,
    ThroughputRecord,
)


def _record(
    record_id: str,
    reviewer_id: str,
    duration_ms: int | None = None,
    created_at: datetime | None = None,
) -> ThroughputRecord:
    return ThroughputRecord(
        record_id=record_id,
        reviewer_id=reviewer_id,
        review_duration_ms=duration_ms,
        created_at=created_at,
    )


def test_basic_throughput_computation() -> None:
    t1 = datetime(2026, 3, 24, 10, 0, 0, tzinfo=UTC)
    t2 = datetime(2026, 3, 24, 11, 0, 0, tzinfo=UTC)
    t3 = datetime(2026, 3, 24, 12, 0, 0, tzinfo=UTC)

    service = ThroughputMetricsService()
    result = service.analyze(
        [
            _record("r1", "alice", duration_ms=5000, created_at=t1),
            _record("r2", "alice", duration_ms=3000, created_at=t2),
            _record("r3", "alice", duration_ms=4000, created_at=t3),
        ]
    )

    assert result.total_reviews == 3
    assert result.total_duration_ms == 12000
    assert result.avg_duration_ms == pytest.approx(4000.0)
    # 3 reviews over 2 hours = 1.5 reviews/hour
    assert result.overall_reviews_per_hour == pytest.approx(1.5)


def test_per_reviewer_breakdown() -> None:
    t1 = datetime(2026, 3, 24, 10, 0, 0, tzinfo=UTC)
    t2 = datetime(2026, 3, 24, 11, 0, 0, tzinfo=UTC)
    t3 = datetime(2026, 3, 24, 10, 30, 0, tzinfo=UTC)

    service = ThroughputMetricsService()
    result = service.analyze(
        [
            _record("r1", "alice", duration_ms=5000, created_at=t1),
            _record("r2", "alice", duration_ms=3000, created_at=t2),
            _record("r3", "bob", duration_ms=4000, created_at=t3),
        ]
    )

    assert len(result.reviewers) == 2
    assert "alice" in result.reviewers
    assert "bob" in result.reviewers

    alice = result.reviewers["alice"]
    assert alice.total_reviews == 2
    assert alice.avg_duration_ms == pytest.approx(4000.0)
    # 2 reviews over 1 hour
    assert alice.reviews_per_hour == pytest.approx(2.0)
    assert alice.first_review_at == t1
    assert alice.last_review_at == t2

    bob = result.reviewers["bob"]
    assert bob.total_reviews == 1
    # Single review: can't compute rate
    assert bob.reviews_per_hour == pytest.approx(0.0)


def test_reviewer_filter() -> None:
    t1 = datetime(2026, 3, 24, 10, 0, 0, tzinfo=UTC)

    service = ThroughputMetricsService()
    result = service.analyze(
        [
            _record("r1", "alice", duration_ms=5000, created_at=t1),
            _record("r2", "bob", duration_ms=3000, created_at=t1),
        ],
        reviewer_filter="alice",
    )

    assert result.total_reviews == 1
    assert len(result.reviewers) == 1
    assert "alice" in result.reviewers


def test_hourly_time_series() -> None:
    t1 = datetime(2026, 3, 24, 10, 15, 0, tzinfo=UTC)
    t2 = datetime(2026, 3, 24, 10, 45, 0, tzinfo=UTC)
    t3 = datetime(2026, 3, 24, 11, 30, 0, tzinfo=UTC)

    service = ThroughputMetricsService()
    result = service.analyze(
        [
            _record("r1", "alice", duration_ms=5000, created_at=t1),
            _record("r2", "alice", duration_ms=3000, created_at=t2),
            _record("r3", "alice", duration_ms=4000, created_at=t3),
        ],
        bucket_size="hourly",
    )

    assert len(result.time_series) == 2
    # First bucket: 10:00-11:00, 2 records
    assert result.time_series[0].record_count == 2
    assert result.time_series[0].bucket_start.hour == 10
    # Second bucket: 11:00-12:00, 1 record
    assert result.time_series[1].record_count == 1
    assert result.time_series[1].bucket_start.hour == 11


def test_daily_time_series() -> None:
    t1 = datetime(2026, 3, 24, 10, 0, 0, tzinfo=UTC)
    t2 = datetime(2026, 3, 24, 14, 0, 0, tzinfo=UTC)
    t3 = datetime(2026, 3, 25, 9, 0, 0, tzinfo=UTC)

    service = ThroughputMetricsService()
    result = service.analyze(
        [
            _record("r1", "alice", duration_ms=5000, created_at=t1),
            _record("r2", "alice", duration_ms=3000, created_at=t2),
            _record("r3", "alice", duration_ms=4000, created_at=t3),
        ],
        bucket_size="daily",
    )

    assert len(result.time_series) == 2
    # First day: 2 records
    assert result.time_series[0].record_count == 2
    assert result.time_series[0].bucket_start.day == 24
    # Second day: 1 record
    assert result.time_series[1].record_count == 1
    assert result.time_series[1].bucket_start.day == 25


def test_empty_input() -> None:
    service = ThroughputMetricsService()
    result = service.analyze([])

    assert result.total_reviews == 0
    assert len(result.reviewers) == 0
    assert len(result.warnings) > 0


def test_no_duration_data_warning() -> None:
    t1 = datetime(2026, 3, 24, 10, 0, 0, tzinfo=UTC)

    service = ThroughputMetricsService()
    result = service.analyze(
        [
            _record("r1", "alice", created_at=t1),
            _record("r2", "alice", created_at=t1),
        ]
    )

    assert result.total_reviews == 2
    assert result.total_duration_ms == 0
    assert result.avg_duration_ms == pytest.approx(0.0)
    assert any("duration" in w.lower() for w in result.warnings)


def test_no_timestamp_data_warning() -> None:
    service = ThroughputMetricsService()
    result = service.analyze(
        [
            _record("r1", "alice", duration_ms=5000),
            _record("r2", "alice", duration_ms=3000),
        ]
    )

    assert result.total_reviews == 2
    assert result.overall_reviews_per_hour == pytest.approx(0.0)
    assert any("timestamp" in w.lower() for w in result.warnings)


def test_dict_input_normalization() -> None:
    t1 = datetime(2026, 3, 24, 10, 0, 0, tzinfo=UTC)
    service = ThroughputMetricsService()
    result = service.analyze(
        [
            {
                "record_id": "r1",
                "reviewer_id": "alice",
                "review_duration_ms": 5000,
                "created_at": t1.isoformat(),
            },
        ]
    )

    assert result.total_reviews == 1
    assert result.total_duration_ms == 5000

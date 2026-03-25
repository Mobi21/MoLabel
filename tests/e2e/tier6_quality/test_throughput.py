"""Throughput metrics test (T6-06).

Records/hour, per-reviewer throughput, average review time.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from molabel.core.quality.throughput_metrics import (
    ThroughputMetricsService,
    ThroughputRecord,
)
from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SHARED_WORKSPACE


def _make_review_records(
    reviewer_id: str,
    count: int,
    start: datetime,
    interval_minutes: int = 5,
    duration_ms: int = 60_000,
) -> list[ThroughputRecord]:
    """Build review records with controlled timing."""
    return [
        ThroughputRecord(
            record_id=f"{reviewer_id}-r{i}",
            reviewer_id=reviewer_id,
            review_duration_ms=duration_ms,
            created_at=start + timedelta(minutes=i * interval_minutes),
        )
        for i in range(count)
    ]


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier6
async def test_throughput_records_per_hour(
    ctx: TestContext,
    client: InstrumentedClient,
) -> None:
    """T6-06: Records/hour, per-reviewer throughput, average review time."""
    service = ThroughputMetricsService()
    start = datetime(2026, 3, 25, 9, 0, 0, tzinfo=UTC)

    with checkpoint(ctx, "single_reviewer_throughput"):
        # 12 reviews over 1 hour (every 5 minutes)
        records = _make_review_records("reviewer-a", 12, start, interval_minutes=5)

        result = service.analyze(records)
        assert result.total_reviews == 12
        assert result.avg_duration_ms == pytest.approx(60_000)

        # 12 reviews spanning 55 minutes → 12 / (55/60) ≈ 13.09 reviews/hour
        expected_rph = 12 / (55 / 60)
        assert result.overall_reviews_per_hour == pytest.approx(expected_rph, rel=0.01)

    with checkpoint(ctx, "per_reviewer_breakdown"):
        records_b = _make_review_records("reviewer-b", 6, start, interval_minutes=10)
        all_records = records + records_b

        result_multi = service.analyze(all_records)
        assert result_multi.total_reviews == 18

        assert "reviewer-a" in result_multi.reviewers
        assert "reviewer-b" in result_multi.reviewers

        rv_a = result_multi.reviewers["reviewer-a"]
        assert rv_a.total_reviews == 12
        assert rv_a.avg_duration_ms == pytest.approx(60_000)

        rv_b = result_multi.reviewers["reviewer-b"]
        assert rv_b.total_reviews == 6

    with checkpoint(ctx, "time_series_buckets"):
        result_ts = service.analyze(records, bucket_size="hourly")
        assert len(result_ts.time_series) >= 1

        for bucket in result_ts.time_series:
            assert bucket.record_count > 0
            assert bucket.bucket_end > bucket.bucket_start

    with checkpoint(ctx, "reviewer_filter"):
        result_a_only = service.analyze(
            records + _make_review_records("reviewer-c", 5, start),
            reviewer_filter="reviewer-a",
        )
        assert result_a_only.total_reviews == 12
        assert "reviewer-c" not in result_a_only.reviewers

    with checkpoint(ctx, "no_duration_data_warns"):
        no_duration_records = [
            ThroughputRecord(
                record_id=f"r{i}",
                reviewer_id="rev-x",
                review_duration_ms=None,
                created_at=start + timedelta(minutes=i * 10),
            )
            for i in range(5)
        ]
        result_nd = service.analyze(no_duration_records)
        assert result_nd.avg_duration_ms == 0.0
        assert any("duration" in w.lower() for w in result_nd.warnings)

    with checkpoint(ctx, "first_and_last_review_times"):
        result_times = service.analyze(records)
        rv_a_times = result_times.reviewers["reviewer-a"]
        assert rv_a_times.first_review_at == start
        assert rv_a_times.last_review_at == start + timedelta(minutes=55)

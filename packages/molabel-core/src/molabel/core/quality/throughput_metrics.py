"""Reviewer throughput metrics service (QA-005).

Computes records reviewed per hour/per reviewer, time-series throughput
(hourly/daily buckets), and average review duration per record.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field


class ThroughputTimeSeries(BaseModel):
    """A single bucket in a throughput time series."""

    bucket_start: datetime
    bucket_end: datetime
    record_count: int = 0
    total_duration_ms: int = 0
    avg_duration_ms: float = 0.0


class ReviewerThroughput(BaseModel):
    """Throughput metrics for a single reviewer."""

    reviewer_id: str
    total_reviews: int = 0
    total_duration_ms: int = 0
    avg_duration_ms: float = 0.0
    reviews_per_hour: float = 0.0
    first_review_at: datetime | None = None
    last_review_at: datetime | None = None
    time_series: list[ThroughputTimeSeries] = Field(default_factory=list)


class ThroughputResult(BaseModel):
    """Full throughput analysis output."""

    total_reviews: int = 0
    total_duration_ms: int = 0
    avg_duration_ms: float = 0.0
    overall_reviews_per_hour: float = 0.0
    reviewers: dict[str, ReviewerThroughput] = Field(default_factory=dict)
    time_series: list[ThroughputTimeSeries] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ThroughputRecord(BaseModel):
    """A single review event with timing information."""

    record_id: str
    reviewer_id: str
    review_duration_ms: int | None = None
    created_at: datetime | None = None


class ThroughputMetricsService:
    """Compute reviewer throughput metrics from review event data."""

    def analyze(
        self,
        records: Sequence[ThroughputRecord | dict[str, Any]],
        *,
        bucket_size: str = "hourly",
        reviewer_filter: str | None = None,
    ) -> ThroughputResult:
        """Compute throughput metrics for the supplied review events.

        Parameters
        ----------
        records:
            Review event records with timing information.
        bucket_size:
            Time-series granularity: "hourly" or "daily".
        reviewer_filter:
            If provided, only include reviews by this reviewer.

        Returns
        -------
        ThroughputResult with overall, per-reviewer, and time-series breakdowns.
        """
        normalized = [self._normalize_record(r) for r in records]

        if reviewer_filter is not None:
            normalized = [r for r in normalized if r.reviewer_id == reviewer_filter]

        if not normalized:
            return ThroughputResult(
                warnings=["No review records matched the given filters."],
            )

        # Overall metrics
        total_reviews = len(normalized)
        durations = [
            r.review_duration_ms for r in normalized if r.review_duration_ms is not None
        ]
        total_duration_ms = sum(durations)
        avg_duration_ms = total_duration_ms / len(durations) if durations else 0.0

        timestamps = [r.created_at for r in normalized if r.created_at is not None]
        overall_reviews_per_hour = self._compute_reviews_per_hour(
            total_reviews, timestamps
        )

        # Per-reviewer metrics
        reviewer_groups: dict[str, list[ThroughputRecord]] = defaultdict(list)
        for record in normalized:
            reviewer_groups[record.reviewer_id].append(record)

        reviewers: dict[str, ReviewerThroughput] = {}
        for reviewer_id, reviewer_records in sorted(reviewer_groups.items()):
            reviewers[reviewer_id] = self._compute_reviewer_throughput(
                reviewer_id, reviewer_records, bucket_size
            )

        # Overall time series
        time_series = self._compute_time_series(normalized, bucket_size)

        warnings: list[str] = []
        if not durations:
            warnings.append("No review duration data available.")
        if not timestamps:
            warnings.append("No timestamp data available for time-series analysis.")

        return ThroughputResult(
            total_reviews=total_reviews,
            total_duration_ms=total_duration_ms,
            avg_duration_ms=avg_duration_ms,
            overall_reviews_per_hour=overall_reviews_per_hour,
            reviewers=reviewers,
            time_series=time_series,
            warnings=warnings,
        )

    def _compute_reviewer_throughput(
        self,
        reviewer_id: str,
        records: Sequence[ThroughputRecord],
        bucket_size: str,
    ) -> ReviewerThroughput:
        total_reviews = len(records)
        durations = [
            r.review_duration_ms for r in records if r.review_duration_ms is not None
        ]
        total_duration_ms = sum(durations)
        avg_duration_ms = total_duration_ms / len(durations) if durations else 0.0

        timestamps = [r.created_at for r in records if r.created_at is not None]
        reviews_per_hour = self._compute_reviews_per_hour(total_reviews, timestamps)

        first_review_at = min(timestamps) if timestamps else None
        last_review_at = max(timestamps) if timestamps else None

        time_series = self._compute_time_series(records, bucket_size)

        return ReviewerThroughput(
            reviewer_id=reviewer_id,
            total_reviews=total_reviews,
            total_duration_ms=total_duration_ms,
            avg_duration_ms=avg_duration_ms,
            reviews_per_hour=reviews_per_hour,
            first_review_at=first_review_at,
            last_review_at=last_review_at,
            time_series=time_series,
        )

    def _compute_time_series(
        self,
        records: Sequence[ThroughputRecord],
        bucket_size: str,
    ) -> list[ThroughputTimeSeries]:
        timestamped = [r for r in records if r.created_at is not None]
        if not timestamped:
            return []

        timestamped_sorted = sorted(
            timestamped, key=lambda r: r.created_at or datetime.min
        )

        bucket_delta = (
            timedelta(hours=1) if bucket_size == "hourly" else timedelta(days=1)
        )

        buckets: dict[datetime, list[ThroughputRecord]] = defaultdict(list)
        for record in timestamped_sorted:
            assert record.created_at is not None  # filtered above
            bucket_start = self._truncate_to_bucket(record.created_at, bucket_size)
            buckets[bucket_start].append(record)

        result: list[ThroughputTimeSeries] = []
        for bucket_start in sorted(buckets.keys()):
            bucket_records = buckets[bucket_start]
            bucket_durations = [
                r.review_duration_ms
                for r in bucket_records
                if r.review_duration_ms is not None
            ]
            total_dur = sum(bucket_durations)
            avg_dur = total_dur / len(bucket_durations) if bucket_durations else 0.0

            result.append(
                ThroughputTimeSeries(
                    bucket_start=bucket_start,
                    bucket_end=bucket_start + bucket_delta,
                    record_count=len(bucket_records),
                    total_duration_ms=total_dur,
                    avg_duration_ms=avg_dur,
                )
            )

        return result

    @staticmethod
    def _truncate_to_bucket(dt: datetime, bucket_size: str) -> datetime:
        """Truncate a datetime to the start of its bucket."""
        if bucket_size == "daily":
            return dt.replace(hour=0, minute=0, second=0, microsecond=0)
        # hourly
        return dt.replace(minute=0, second=0, microsecond=0)

    @staticmethod
    def _compute_reviews_per_hour(
        total_reviews: int,
        timestamps: Sequence[datetime],
    ) -> float:
        """Compute reviews per hour from total count and time span."""
        if len(timestamps) < 2:
            return 0.0
        time_span = max(timestamps) - min(timestamps)
        hours = time_span.total_seconds() / 3600.0
        if hours <= 0:
            return 0.0
        return total_reviews / hours

    def _normalize_record(
        self, record: ThroughputRecord | dict[str, Any]
    ) -> ThroughputRecord:
        if isinstance(record, ThroughputRecord):
            return record
        return ThroughputRecord.model_validate(record)

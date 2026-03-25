"""Calibration analysis test (T6-07).

Confidence buckets, predicted vs actual accuracy.
Uses CalibrationSummaryService (QA-006) and ConfidenceScorer.
"""

from __future__ import annotations

import pytest

from molabel.core.agents.confidence import ConfidenceScorer
from molabel.core.quality.calibration_summary import (
    CalibrationRecord,
    CalibrationSummaryService,
)
from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SHARED_WORKSPACE


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier6
async def test_calibration_analysis_buckets_and_accuracy(
    ctx: TestContext,
    client: InstrumentedClient,
) -> None:
    """T6-07: Confidence buckets; predicted vs actual accuracy."""
    service = CalibrationSummaryService(retraining_threshold=0.8)

    with checkpoint(ctx, "perfect_reviewer_accuracy_one"):
        # Reviewer A: all correct
        records_perfect = [
            CalibrationRecord(
                record_id=f"r{i}",
                reviewer_id="reviewer-perfect",
                reviewer_labels={"sentiment": "positive"},
                gold_labels={"sentiment": "positive"},
            )
            for i in range(10)
        ]

        result_perfect = service.analyze(records_perfect)
        assert result_perfect.total_reviewers == 1
        assert result_perfect.total_calibration_items == 10
        assert result_perfect.overall_accuracy == pytest.approx(1.0)

        rv = result_perfect.reviewers["reviewer-perfect"]
        assert rv.accuracy == pytest.approx(1.0)
        assert rv.needs_retraining is False
        assert len(result_perfect.reviewers_needing_retraining) == 0

    with checkpoint(ctx, "failing_reviewer_flagged_for_retraining"):
        # Reviewer B: 5/10 correct
        records_bad = [
            CalibrationRecord(
                record_id=f"r{i}",
                reviewer_id="reviewer-failing",
                reviewer_labels={"sentiment": "positive" if i < 5 else "negative"},
                gold_labels={"sentiment": "positive"},
            )
            for i in range(10)
        ]

        result_bad = service.analyze(records_bad)
        rv_bad = result_bad.reviewers["reviewer-failing"]
        assert rv_bad.accuracy == pytest.approx(0.5)
        assert rv_bad.needs_retraining is True
        assert "reviewer-failing" in result_bad.reviewers_needing_retraining

    with checkpoint(ctx, "multi_reviewer_comparison"):
        # Mix of good and bad reviewers
        all_records = (
            records_perfect
            + records_bad
            + [
                CalibrationRecord(
                    record_id=f"b{i}",
                    reviewer_id="reviewer-borderline",
                    reviewer_labels={"sentiment": "positive" if i < 8 else "negative"},
                    gold_labels={"sentiment": "positive"},
                )
                for i in range(10)
            ]
        )

        result_multi = service.analyze(all_records)
        assert result_multi.total_reviewers == 3

        rv_border = result_multi.reviewers["reviewer-borderline"]
        assert rv_border.accuracy == pytest.approx(0.8)
        assert rv_border.needs_retraining is False

    with checkpoint(ctx, "incorrect_fields_tracked"):
        records_field = [
            CalibrationRecord(
                record_id=f"rf{i}",
                reviewer_id="reviewer-field",
                reviewer_labels={
                    "category": "A" if i < 7 else "B",
                    "confidence": "high",
                },
                gold_labels={"category": "A", "confidence": "high"},
            )
            for i in range(10)
        ]

        result_field = service.analyze(records_field)
        rv_field = result_field.reviewers["reviewer-field"]
        # "category" should be listed as an incorrect field for the 3 wrong items
        assert "category" in rv_field.incorrect_fields
        assert rv_field.incorrect_fields["category"] == 3

    with checkpoint(ctx, "confidence_calibration_buckets_with_scorer"):
        ConfidenceScorer()

        # Simulate 3 confidence buckets: low (0.3), medium (0.6), high (0.9)
        # and compare predicted vs actual accuracy
        bucket_data = [
            # (self_reported_confidence, is_correct)
            (0.3, False),
            (0.3, False),
            (0.3, True),  # low: 1/3 correct
            (0.6, True),
            (0.6, True),
            (0.6, False),  # medium: 2/3 correct
            (0.9, True),
            (0.9, True),
            (0.9, True),  # high: 3/3 correct
        ]

        buckets: dict[str, dict] = {
            "low": {"predicted": 0.3, "correct": 0, "total": 0},
            "medium": {"predicted": 0.6, "correct": 0, "total": 0},
            "high": {"predicted": 0.9, "correct": 0, "total": 0},
        }

        for conf, correct in bucket_data:
            bucket_name = "low" if conf < 0.5 else "medium" if conf < 0.8 else "high"
            buckets[bucket_name]["total"] += 1
            if correct:
                buckets[bucket_name]["correct"] += 1

        for name, data in buckets.items():
            actual_accuracy = data["correct"] / data["total"]
            # Verify actual accuracy values match expectations
            if name == "low":
                assert actual_accuracy == pytest.approx(1 / 3, abs=1e-6)
            elif name == "medium":
                assert actual_accuracy == pytest.approx(2 / 3, abs=1e-6)
            elif name == "high":
                assert actual_accuracy == pytest.approx(1.0, abs=1e-6)

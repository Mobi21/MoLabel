"""Tests for the calibration summary service (QA-006)."""

from __future__ import annotations

import pytest

from molabel.core.quality.calibration_summary import (
    CalibrationRecord,
    CalibrationSummaryService,
)


def _record(
    record_id: str,
    reviewer_id: str,
    reviewer_labels: dict[str, object],
    gold_labels: dict[str, object],
) -> CalibrationRecord:
    return CalibrationRecord(
        record_id=record_id,
        reviewer_id=reviewer_id,
        reviewer_labels=reviewer_labels,
        gold_labels=gold_labels,
    )


def test_perfect_calibration() -> None:
    service = CalibrationSummaryService()
    pos = {"sentiment": "positive"}
    neg = {"sentiment": "negative"}
    result = service.analyze(
        [
            _record("r1", "alice", pos, pos),
            _record("r2", "alice", neg, neg),
            _record("r3", "bob", pos, pos),
        ]
    )

    assert result.total_calibration_items == 3
    assert result.total_reviewers == 2
    assert result.overall_accuracy == pytest.approx(1.0)
    assert result.reviewers["alice"].accuracy == pytest.approx(1.0)
    assert result.reviewers["bob"].accuracy == pytest.approx(1.0)
    assert len(result.reviewers_needing_retraining) == 0


def test_partial_calibration_accuracy() -> None:
    service = CalibrationSummaryService(retraining_threshold=0.8)
    pos = {"sentiment": "positive"}
    neg = {"sentiment": "negative"}
    result = service.analyze(
        [
            _record("r1", "alice", pos, pos),
            _record("r2", "alice", pos, neg),
            _record("r3", "alice", neg, neg),
        ]
    )

    alice = result.reviewers["alice"]
    assert alice.total_calibration_items == 3
    assert alice.correct_items == 2
    assert alice.accuracy == pytest.approx(2 / 3)
    assert alice.needs_retraining is True
    assert "sentiment" in alice.incorrect_fields
    assert alice.incorrect_fields["sentiment"] == 1


def test_retraining_detection() -> None:
    service = CalibrationSummaryService(retraining_threshold=0.75)
    result = service.analyze(
        [
            # Alice: 1/2 correct = 50% -> needs retraining
            _record("r1", "alice", {"s": "positive"}, {"s": "positive"}),
            _record("r2", "alice", {"s": "positive"}, {"s": "negative"}),
            # Bob: 3/3 correct = 100% -> fine
            _record("r3", "bob", {"s": "positive"}, {"s": "positive"}),
            _record("r4", "bob", {"s": "negative"}, {"s": "negative"}),
            _record("r5", "bob", {"s": "neutral"}, {"s": "neutral"}),
        ]
    )

    assert "alice" in result.reviewers_needing_retraining
    assert "bob" not in result.reviewers_needing_retraining
    assert result.reviewers["alice"].needs_retraining is True
    assert result.reviewers["bob"].needs_retraining is False


def test_multiple_fields() -> None:
    service = CalibrationSummaryService()
    result = service.analyze(
        [
            _record(
                "r1",
                "alice",
                {"sentiment": "positive", "tone": "formal"},
                {"sentiment": "positive", "tone": "informal"},
            ),
        ]
    )

    alice = result.reviewers["alice"]
    # One field correct, one wrong -> record is incorrect
    assert alice.correct_items == 0
    assert alice.total_calibration_items == 1
    assert "tone" in alice.incorrect_fields
    assert alice.incorrect_fields["tone"] == 1
    # sentiment was correct, should not appear in incorrect_fields
    assert "sentiment" not in alice.incorrect_fields


def test_field_filter() -> None:
    service = CalibrationSummaryService()
    result = service.analyze(
        [
            _record(
                "r1",
                "alice",
                {"sentiment": "positive", "tone": "formal"},
                {"sentiment": "positive", "tone": "informal"},
            ),
        ],
        fields=["sentiment"],
    )

    alice = result.reviewers["alice"]
    # Only checking sentiment, which is correct
    assert alice.correct_items == 1
    assert alice.accuracy == pytest.approx(1.0)


def test_empty_input() -> None:
    service = CalibrationSummaryService()
    result = service.analyze([])

    assert result.total_calibration_items == 0
    assert result.total_reviewers == 0
    assert result.overall_accuracy == pytest.approx(0.0)
    assert len(result.warnings) > 0


def test_overall_accuracy_across_reviewers() -> None:
    service = CalibrationSummaryService()
    result = service.analyze(
        [
            # Alice: 2/2 correct
            _record("r1", "alice", {"s": "a"}, {"s": "a"}),
            _record("r2", "alice", {"s": "b"}, {"s": "b"}),
            # Bob: 1/2 correct
            _record("r3", "bob", {"s": "a"}, {"s": "a"}),
            _record("r4", "bob", {"s": "a"}, {"s": "b"}),
        ]
    )

    # 3 correct out of 4 total
    assert result.overall_accuracy == pytest.approx(3 / 4)


def test_dict_input_normalization() -> None:
    service = CalibrationSummaryService()
    result = service.analyze(
        [
            {
                "record_id": "r1",
                "reviewer_id": "alice",
                "reviewer_labels": {"s": "positive"},
                "gold_labels": {"s": "positive"},
            },
        ]
    )

    assert result.total_calibration_items == 1
    assert result.reviewers["alice"].accuracy == pytest.approx(1.0)


def test_none_labels_treated_as_null() -> None:
    service = CalibrationSummaryService()
    result = service.analyze(
        [
            _record("r1", "alice", {"s": None}, {"s": None}),
        ]
    )

    # Both None -> canonical "__null__" matches
    assert result.reviewers["alice"].correct_items == 1
    assert result.reviewers["alice"].accuracy == pytest.approx(1.0)

"""Tests for the drift detection service (QA-007)."""

from __future__ import annotations

import pytest

from molabel.core.quality.drift_detection import (
    DriftDetectionService,
    DriftRecord,
    DriftSeverity,
)


def _record(record_id: str, labels: dict[str, object]) -> DriftRecord:
    return DriftRecord(record_id=record_id, labels=labels)


def test_no_drift_identical_distributions() -> None:
    reference = [
        _record("r1", {"sentiment": "positive"}),
        _record("r2", {"sentiment": "negative"}),
        _record("r3", {"sentiment": "positive"}),
        _record("r4", {"sentiment": "negative"}),
    ]
    current = [
        _record("c1", {"sentiment": "positive"}),
        _record("c2", {"sentiment": "negative"}),
        _record("c3", {"sentiment": "positive"}),
        _record("c4", {"sentiment": "negative"}),
    ]

    service = DriftDetectionService()
    result = service.analyze(reference, current)

    assert result.drift_detected is False
    assert result.overall_severity == DriftSeverity.none
    assert result.max_shift == pytest.approx(0.0, abs=1e-6)
    assert len(result.affected_fields) == 0


def test_significant_drift_detected() -> None:
    reference = [
        _record("r1", {"sentiment": "positive"}),
        _record("r2", {"sentiment": "positive"}),
        _record("r3", {"sentiment": "positive"}),
        _record("r4", {"sentiment": "positive"}),
        _record("r5", {"sentiment": "negative"}),
    ]
    current = [
        _record("c1", {"sentiment": "negative"}),
        _record("c2", {"sentiment": "negative"}),
        _record("c3", {"sentiment": "negative"}),
        _record("c4", {"sentiment": "negative"}),
        _record("c5", {"sentiment": "positive"}),
    ]

    service = DriftDetectionService(drift_threshold=0.05)
    result = service.analyze(reference, current)

    assert result.drift_detected is True
    assert result.max_shift > 0.05
    assert "sentiment" in result.affected_fields
    field_drift = result.fields["sentiment"]
    assert field_drift.severity != DriftSeverity.none
    assert len(field_drift.shifted_values) > 0


def test_chi_squared_computed() -> None:
    reference = [
        _record("r1", {"color": "red"}),
        _record("r2", {"color": "red"}),
        _record("r3", {"color": "blue"}),
    ]
    current = [
        _record("c1", {"color": "red"}),
        _record("c2", {"color": "blue"}),
        _record("c3", {"color": "blue"}),
    ]

    service = DriftDetectionService()
    result = service.analyze(reference, current)

    field_drift = result.fields["color"]
    assert field_drift.chi_squared > 0.0
    assert 0.0 <= field_drift.chi_squared_p_value <= 1.0


def test_kl_divergence_positive() -> None:
    reference = [
        _record("r1", {"sentiment": "positive"}),
        _record("r2", {"sentiment": "positive"}),
        _record("r3", {"sentiment": "positive"}),
    ]
    current = [
        _record("c1", {"sentiment": "negative"}),
        _record("c2", {"sentiment": "negative"}),
        _record("c3", {"sentiment": "negative"}),
    ]

    service = DriftDetectionService()
    result = service.analyze(reference, current)

    field_drift = result.fields["sentiment"]
    assert field_drift.kl_divergence > 0.0


def test_severity_levels() -> None:
    service = DriftDetectionService(
        drift_threshold=0.1,
        medium_threshold=0.3,
        high_threshold=0.6,
    )

    # Completely different distributions -> high drift
    reference = [_record(f"r{i}", {"s": "a"}) for i in range(20)]
    current = [_record(f"c{i}", {"s": "b"}) for i in range(20)]

    result = service.analyze(reference, current)
    assert result.overall_severity == DriftSeverity.high

    # Identical distributions -> no drift
    same = [_record(f"s{i}", {"s": "a"}) for i in range(20)]
    result2 = service.analyze(same, same)
    assert result2.overall_severity == DriftSeverity.none


def test_multiple_fields() -> None:
    reference = [
        _record("r1", {"sentiment": "positive", "topic": "sports"}),
        _record("r2", {"sentiment": "positive", "topic": "politics"}),
        _record("r3", {"sentiment": "negative", "topic": "sports"}),
    ]
    current = [
        _record("c1", {"sentiment": "positive", "topic": "tech"}),
        _record("c2", {"sentiment": "positive", "topic": "tech"}),
        _record("c3", {"sentiment": "negative", "topic": "tech"}),
    ]

    service = DriftDetectionService(drift_threshold=0.01)
    result = service.analyze(reference, current)

    assert "sentiment" in result.fields
    assert "topic" in result.fields
    # Topic distribution changed completely
    topic_kl = result.fields["topic"].kl_divergence
    sent_kl = result.fields["sentiment"].kl_divergence
    assert topic_kl > sent_kl


def test_field_filter() -> None:
    reference = [
        _record("r1", {"sentiment": "positive", "topic": "sports"}),
    ]
    current = [
        _record("c1", {"sentiment": "negative", "topic": "tech"}),
    ]

    service = DriftDetectionService()
    result = service.analyze(reference, current, fields=["sentiment"])

    assert "sentiment" in result.fields
    assert "topic" not in result.fields


def test_empty_reference() -> None:
    service = DriftDetectionService()
    result = service.analyze([], [_record("c1", {"s": "positive"})])

    assert result.drift_detected is False
    assert len(result.warnings) > 0
    assert any("reference" in w.lower() for w in result.warnings)


def test_empty_current() -> None:
    service = DriftDetectionService()
    result = service.analyze([_record("r1", {"s": "positive"})], [])

    assert result.drift_detected is False
    assert len(result.warnings) > 0
    assert any("current" in w.lower() for w in result.warnings)


def test_detect_workflow_interface() -> None:
    """Test the workflow-compatible detect() method."""
    service = DriftDetectionService(drift_threshold=0.05)
    result = service.detect(
        record_ids=["c1", "c2"],
        reference="snapshot-123",
        config={
            "reference_records": [
                {"record_id": "r1", "labels": {"s": "positive"}},
                {"record_id": "r2", "labels": {"s": "positive"}},
                {"record_id": "r3", "labels": {"s": "positive"}},
            ],
            "current_records": [
                {"record_id": "c1", "labels": {"s": "negative"}},
                {"record_id": "c2", "labels": {"s": "negative"}},
                {"record_id": "c3", "labels": {"s": "negative"}},
            ],
        },
    )

    assert isinstance(result, dict)
    assert "max_shift" in result
    assert "affected_fields" in result
    assert "drift_detected" in result
    assert result["drift_detected"] is True
    assert result["max_shift"] > 0.0


def test_new_category_in_current() -> None:
    """Test drift when current data has a new category not in reference."""
    reference = [
        _record("r1", {"s": "positive"}),
        _record("r2", {"s": "negative"}),
    ]
    current = [
        _record("c1", {"s": "positive"}),
        _record("c2", {"s": "neutral"}),
    ]

    service = DriftDetectionService(drift_threshold=0.01)
    result = service.analyze(reference, current)

    field_drift = result.fields["s"]
    assert "neutral" in field_drift.current_distribution
    # neutral should show up as a shifted value
    assert "neutral" in field_drift.shifted_values

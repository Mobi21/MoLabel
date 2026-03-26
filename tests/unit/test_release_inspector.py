"""Tests for release bundle inspection and diff (EX-009).

Covers ReleaseInspector, ReleaseInspection, ReleaseDiff, and ReleaseReport.
"""

from __future__ import annotations

from typing import Any

from molabel.core.release.release_inspector import (
    ReleaseInspector,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sample_records() -> list[dict[str, Any]]:
    return [
        {"id": "r1", "text": "hello", "sentiment": "pos"},
        {"id": "r2", "text": "world", "sentiment": "neg"},
        {"id": "r3", "text": "test", "sentiment": "neutral"},
    ]


def _extended_records() -> list[dict[str, Any]]:
    return [
        {"id": "r1", "text": "hello", "sentiment": "pos", "confidence": 0.95},
        {"id": "r2", "text": "world", "sentiment": "neg", "confidence": 0.87},
        {"id": "r3", "text": "test", "sentiment": "pos", "confidence": 0.92},
        {"id": "r4", "text": "new", "sentiment": "neg", "confidence": 0.80},
    ]


# ---------------------------------------------------------------------------
# EX-009: ReleaseInspection
# ---------------------------------------------------------------------------


class TestReleaseInspection:
    def test_inspect_basic(self) -> None:
        inspector = ReleaseInspector()
        records = _sample_records()
        result = inspector.inspect("rel-001", records, format="jsonl")

        assert result.release_id == "rel-001"
        assert result.record_count == 3
        assert result.format == "jsonl"
        assert "text" in result.field_names
        assert "sentiment" in result.field_names
        assert "id" in result.field_names

    def test_inspect_label_counts(self) -> None:
        inspector = ReleaseInspector()
        records = _sample_records()
        result = inspector.inspect("rel-001", records)

        assert result.label_counts["text"] == 3
        assert result.label_counts["sentiment"] == 3
        assert result.label_counts["id"] == 3

    def test_inspect_empty_records(self) -> None:
        inspector = ReleaseInspector()
        result = inspector.inspect("rel-empty", [])
        assert result.record_count == 0
        assert result.field_names == []
        assert result.label_counts == {}

    def test_inspect_with_metadata(self) -> None:
        inspector = ReleaseInspector()
        result = inspector.inspect(
            "rel-001",
            _sample_records(),
            file_size_bytes=1024,
            content_hash="abc123",
            metadata={"source": "test"},
        )
        assert result.file_size_bytes == 1024
        assert result.content_hash == "abc123"
        assert result.metadata["source"] == "test"

    def test_inspect_heterogeneous_fields(self) -> None:
        """Records with different field sets."""
        inspector = ReleaseInspector()
        records = [
            {"id": "r1", "text": "a"},
            {"id": "r2", "text": "b", "extra": 42},
        ]
        result = inspector.inspect("rel", records)
        assert "extra" in result.field_names
        assert result.label_counts["extra"] == 1
        assert result.label_counts["text"] == 2


# ---------------------------------------------------------------------------
# EX-009: ReleaseDiff
# ---------------------------------------------------------------------------


class TestReleaseDiff:
    def test_diff_basic(self) -> None:
        inspector = ReleaseInspector()
        prev = inspector.inspect("rel-001", _sample_records())
        curr = inspector.inspect("rel-002", _extended_records())

        diff = inspector.diff(prev, curr)
        assert diff.previous_release_id == "rel-001"
        assert diff.current_release_id == "rel-002"
        assert diff.record_count_delta == 1
        assert "confidence" in diff.fields_added
        assert diff.fields_removed == []

    def test_diff_with_record_ids(self) -> None:
        inspector = ReleaseInspector()
        prev = inspector.inspect("v1", _sample_records())
        curr = inspector.inspect("v2", _extended_records())

        diff = inspector.diff(
            prev,
            curr,
            previous_record_ids={"r1", "r2", "r3"},
            current_record_ids={"r1", "r2", "r3", "r4"},
        )
        assert diff.records_added == 1
        assert diff.records_removed == 0

    def test_diff_records_removed(self) -> None:
        inspector = ReleaseInspector()
        prev = inspector.inspect("v1", _sample_records())
        curr_records = [
            {"id": "r1", "text": "hello", "sentiment": "pos"},
        ]
        curr = inspector.inspect("v2", curr_records)

        diff = inspector.diff(
            prev,
            curr,
            previous_record_ids={"r1", "r2", "r3"},
            current_record_ids={"r1"},
        )
        assert diff.records_removed == 2
        assert diff.records_added == 0

    def test_diff_no_changes(self) -> None:
        inspector = ReleaseInspector()
        records = _sample_records()
        prev = inspector.inspect("v1", records)
        curr = inspector.inspect("v2", records)

        diff = inspector.diff(prev, curr)
        assert diff.record_count_delta == 0
        assert diff.fields_added == []
        assert diff.fields_removed == []
        assert "No significant changes" in diff.summary

    def test_diff_fields_removed(self) -> None:
        inspector = ReleaseInspector()
        prev = inspector.inspect(
            "v1",
            [{"id": "r1", "text": "a", "old_field": 1}],
        )
        curr = inspector.inspect(
            "v2",
            [{"id": "r1", "text": "a"}],
        )
        diff = inspector.diff(prev, curr)
        assert "old_field" in diff.fields_removed

    def test_diff_label_changes(self) -> None:
        inspector = ReleaseInspector()
        prev = inspector.inspect("v1", _sample_records())
        # Change: one record gains 'confidence' field
        extra = {"id": "r4", "text": "new", "confidence": 0.5}
        curr_records = _sample_records() + [extra]
        curr = inspector.inspect("v2", curr_records)

        diff = inspector.diff(prev, curr)
        assert "confidence" in diff.label_changes
        assert diff.label_changes["confidence"]["delta"] == 1


# ---------------------------------------------------------------------------
# EX-009: ReleaseReport
# ---------------------------------------------------------------------------


class TestReleaseReport:
    def test_generate_report_basic(self) -> None:
        inspector = ReleaseInspector()
        report = inspector.generate_report(
            "rel-001",
            _sample_records(),
            format="jsonl",
        )
        assert report.release_id == "rel-001"
        assert report.inspection.record_count == 3
        assert report.diff is None
        assert report.generated_at != ""

    def test_generate_report_with_diff(self) -> None:
        inspector = ReleaseInspector()
        prev_inspection = inspector.inspect("v1", _sample_records())

        report = inspector.generate_report(
            "v2",
            _extended_records(),
            previous_inspection=prev_inspection,
            previous_record_ids={"r1", "r2", "r3"},
            current_record_ids={"r1", "r2", "r3", "r4"},
        )
        assert report.diff is not None
        assert report.diff.record_count_delta == 1
        assert report.diff.records_added == 1

    def test_report_warns_on_fewer_records(self) -> None:
        inspector = ReleaseInspector()
        prev_inspection = inspector.inspect("v1", _sample_records())

        report = inspector.generate_report(
            "v2",
            [{"id": "r1", "text": "a", "sentiment": "pos"}],
            previous_inspection=prev_inspection,
        )
        assert report.diff is not None
        assert any("fewer records" in n for n in report.notes)

    def test_report_warns_on_removed_fields(self) -> None:
        inspector = ReleaseInspector()
        prev_inspection = inspector.inspect(
            "v1",
            [{"id": "r1", "text": "a", "old_col": 1}],
        )
        report = inspector.generate_report(
            "v2",
            [{"id": "r1", "text": "a"}],
            previous_inspection=prev_inspection,
        )
        assert any("removed" in n.lower() for n in report.notes)

    def test_report_no_notes_when_growing(self) -> None:
        inspector = ReleaseInspector()
        prev_inspection = inspector.inspect("v1", _sample_records())
        report = inspector.generate_report(
            "v2",
            _extended_records(),
            previous_inspection=prev_inspection,
        )
        # No warnings about fewer records or removed fields
        assert not any("fewer records" in n for n in report.notes)

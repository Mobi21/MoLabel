"""Tests for export builder and filters (EX-004, EX-005).

Covers ExportBuilder, ExportConfig, InclusionFlags, ExportFilters,
apply_filters, and apply_field_filters.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from molabel.core.export.export_builder import (
    ExportBuilder,
    ExportConfig,
    ExportFilters,
    InclusionFlags,
    apply_field_filters,
    apply_filters,
)
from molabel.core.types import Record, ReviewEvent

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_DATASET_ID = UUID("00000000-0000-0000-0000-000000000001")


def _make_record(
    text: str = "sample",
    record_id: UUID | None = None,
    flags: dict[str, Any] | None = None,
) -> Record:
    return Record(
        id=record_id or uuid4(),
        dataset_id=_DATASET_ID,
        stable_fields={"text": text},
        payload={"text": text},
        flags=flags,
    )


def _make_event(record_id: UUID, labels: dict[str, Any]) -> ReviewEvent:
    return ReviewEvent(
        id=uuid4(),
        record_id=record_id,
        source="human",
        decision="accept",
        labels=labels,
    )


# ---------------------------------------------------------------------------
# EX-004: ExportBuilder
# ---------------------------------------------------------------------------


class TestExportBuilder:
    def test_default_config(self) -> None:
        config = ExportBuilder().build()
        assert config.inclusion.record_data is True
        assert config.inclusion.labels is True
        assert config.inclusion.agent_labels is False
        assert config.inclusion.review_metadata is False
        assert config.inclusion.adjudication_history is False
        assert config.inclusion.provenance is False

    def test_include_all(self) -> None:
        config = (
            ExportBuilder()
            .include_record_data()
            .include_labels()
            .include_agent_labels()
            .include_review_metadata()
            .include_adjudication_history()
            .include_provenance()
            .build()
        )
        assert config.inclusion.record_data is True
        assert config.inclusion.labels is True
        assert config.inclusion.agent_labels is True
        assert config.inclusion.review_metadata is True
        assert config.inclusion.adjudication_history is True
        assert config.inclusion.provenance is True

    def test_disable_labels(self) -> None:
        config = ExportBuilder().include_labels(False).build()
        assert config.inclusion.labels is False

    def test_builder_returns_self_for_chaining(self) -> None:
        builder = ExportBuilder()
        result = builder.include_labels()
        assert result is builder

    def test_filter_min_agreement(self) -> None:
        config = ExportBuilder().min_agreement(0.85).build()
        assert config.filters.min_agreement == 0.85

    def test_filter_exclude_flagged(self) -> None:
        config = ExportBuilder().exclude_flagged().build()
        assert config.filters.exclude_flagged is True

    def test_filter_include_fields(self) -> None:
        config = ExportBuilder().include_fields(["text", "sentiment"]).build()
        assert config.filters.include_fields == ["text", "sentiment"]

    def test_filter_exclude_fields(self) -> None:
        config = ExportBuilder().exclude_fields(["internal_id"]).build()
        assert config.filters.exclude_fields == ["internal_id"]

    def test_extra_config(self) -> None:
        config = (
            ExportBuilder()
            .extra_config("label_strategy", "first")
            .extra_config("delimiter", "\t")
            .build()
        )
        assert config.extra["label_strategy"] == "first"
        assert config.extra["delimiter"] == "\t"

    def test_combined_builder(self) -> None:
        config = (
            ExportBuilder()
            .include_labels()
            .include_agent_labels()
            .include_provenance()
            .min_agreement(0.9)
            .exclude_flagged()
            .include_fields(["text", "label"])
            .build()
        )
        assert config.inclusion.agent_labels is True
        assert config.inclusion.provenance is True
        assert config.filters.min_agreement == 0.9
        assert config.filters.exclude_flagged is True
        assert config.filters.include_fields == ["text", "label"]


# ---------------------------------------------------------------------------
# EX-004: InclusionFlags and ExportConfig immutability
# ---------------------------------------------------------------------------


class TestInclusionFlags:
    def test_frozen(self) -> None:
        flags = InclusionFlags()
        with pytest.raises(AttributeError):
            flags.labels = False  # type: ignore[misc]

    def test_defaults(self) -> None:
        flags = InclusionFlags()
        assert flags.record_data is True
        assert flags.labels is True
        assert flags.agent_labels is False


class TestExportConfig:
    def test_frozen(self) -> None:
        config = ExportConfig()
        with pytest.raises(AttributeError):
            config.inclusion = InclusionFlags()  # type: ignore[misc]

    def test_default_filters(self) -> None:
        config = ExportConfig()
        assert config.filters.min_agreement is None
        assert config.filters.exclude_flagged is False


# ---------------------------------------------------------------------------
# EX-005: apply_filters
# ---------------------------------------------------------------------------


class TestApplyFilters:
    def test_no_filters_passes_all(self) -> None:
        r1 = _make_record("a")
        r2 = _make_record("b")
        labels = {str(r1.id): [_make_event(r1.id, {"l": "x"})]}
        filters = ExportFilters()

        filtered_records, filtered_labels = apply_filters([r1, r2], labels, filters)
        assert len(filtered_records) == 2
        assert str(r1.id) in filtered_labels

    def test_min_agreement_filter(self) -> None:
        r1 = _make_record("a")
        r2 = _make_record("b")
        r3 = _make_record("c")
        labels: dict[str, list[ReviewEvent]] = {}
        scores = {str(r1.id): 0.9, str(r2.id): 0.5, str(r3.id): 0.85}
        filters = ExportFilters(min_agreement=0.85)

        filtered, _ = apply_filters(
            [r1, r2, r3], labels, filters, agreement_scores=scores
        )
        filtered_ids = {str(r.id) for r in filtered}
        assert str(r1.id) in filtered_ids
        assert str(r2.id) not in filtered_ids
        assert str(r3.id) in filtered_ids

    def test_min_agreement_excludes_missing_scores(self) -> None:
        r1 = _make_record("a")
        filters = ExportFilters(min_agreement=0.5)
        filtered, _ = apply_filters([r1], {}, filters, agreement_scores={})
        assert len(filtered) == 0

    def test_exclude_flagged(self) -> None:
        r1 = _make_record("clean")
        r2 = _make_record("flagged", flags={"quality": "low"})
        filters = ExportFilters(exclude_flagged=True)

        filtered, _ = apply_filters([r1, r2], {}, filters)
        assert len(filtered) == 1
        assert filtered[0].id == r1.id

    def test_exclude_flagged_empty_flags_passes(self) -> None:
        r1 = _make_record("empty_flags")
        r1_with_empty = Record(
            id=r1.id,
            dataset_id=r1.dataset_id,
            stable_fields=r1.stable_fields,
            payload=r1.payload,
            flags={},
        )
        filters = ExportFilters(exclude_flagged=True)
        filtered, _ = apply_filters([r1_with_empty], {}, filters)
        # Empty dict is falsy, so record passes
        assert len(filtered) == 1

    def test_combined_filters(self) -> None:
        r1 = _make_record("good")
        r2 = _make_record("flagged", flags={"issue": True})
        r3 = _make_record("low_agreement")
        scores = {str(r1.id): 0.95, str(r2.id): 0.99, str(r3.id): 0.3}
        filters = ExportFilters(min_agreement=0.8, exclude_flagged=True)

        filtered, _ = apply_filters([r1, r2, r3], {}, filters, agreement_scores=scores)
        assert len(filtered) == 1
        assert filtered[0].id == r1.id


# ---------------------------------------------------------------------------
# EX-005: apply_field_filters
# ---------------------------------------------------------------------------


class TestApplyFieldFilters:
    def test_include_fields(self) -> None:
        row = {"text": "hello", "sentiment": "pos", "extra": 42}
        filters = ExportFilters(include_fields=["text", "sentiment"])
        result = apply_field_filters(row, filters)
        assert result == {"text": "hello", "sentiment": "pos"}

    def test_exclude_fields(self) -> None:
        row = {"text": "hello", "internal": "secret", "sentiment": "pos"}
        filters = ExportFilters(exclude_fields=["internal"])
        result = apply_field_filters(row, filters)
        assert "internal" not in result
        assert "text" in result

    def test_no_field_filters(self) -> None:
        row = {"a": 1, "b": 2}
        filters = ExportFilters()
        result = apply_field_filters(row, filters)
        assert result == {"a": 1, "b": 2}

    def test_include_and_exclude_combined(self) -> None:
        row = {"a": 1, "b": 2, "c": 3}
        filters = ExportFilters(include_fields=["a", "b"], exclude_fields=["b"])
        result = apply_field_filters(row, filters)
        assert result == {"a": 1}

    def test_include_missing_fields(self) -> None:
        row = {"a": 1}
        filters = ExportFilters(include_fields=["a", "nonexistent"])
        result = apply_field_filters(row, filters)
        assert result == {"a": 1}

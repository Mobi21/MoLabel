"""Tests for frozen release views and report generation (EX-015, EX-016).

Covers FrozenViewManager, FrozenView, FrozenSplit, ViewSnapshot,
ReadinessReport, ValidationSummary, and ReportManifest.
"""

from __future__ import annotations

from typing import Any

import pytest

from molabel.core.release.frozen_views import (
    FrozenSplit,
    FrozenViewManager,
)

# ---------------------------------------------------------------------------
# EX-016: FrozenView creation
# ---------------------------------------------------------------------------


class TestFrozenViewCreation:
    def test_freeze_basic(self) -> None:
        mgr = FrozenViewManager()
        view = mgr.freeze(
            "rel-001",
            "ds-001",
            record_ids=["r1", "r2", "r3"],
            labels={"r1": {"sentiment": "pos"}, "r2": {"sentiment": "neg"}},
        )
        assert view.release_id == "rel-001"
        assert view.dataset_id == "ds-001"
        assert view.record_ids == ["r1", "r2", "r3"]
        assert len(view.labels) == 2
        assert view.content_hash != ""
        assert view.frozen_at != ""

    def test_freeze_with_splits(self) -> None:
        mgr = FrozenViewManager()
        splits = [
            FrozenSplit(split_name="train", record_ids=["r1", "r2"], record_count=2),
            FrozenSplit(split_name="test", record_ids=["r3"], record_count=1),
        ]
        view = mgr.freeze(
            "rel-001",
            "ds-001",
            record_ids=["r1", "r2", "r3"],
            labels={},
            splits=splits,
        )
        assert len(view.splits) == 2
        assert view.splits[0].split_name == "train"
        assert view.splits[1].record_count == 1

    def test_freeze_with_metrics(self) -> None:
        mgr = FrozenViewManager()
        view = mgr.freeze(
            "rel-001",
            "ds-001",
            record_ids=["r1"],
            labels={},
            metrics={"agreement": 0.92, "coverage": 0.98},
        )
        assert view.metrics["agreement"] == 0.92
        assert view.metrics["coverage"] == 0.98

    def test_freeze_with_field_names(self) -> None:
        mgr = FrozenViewManager()
        view = mgr.freeze(
            "rel-001",
            "ds-001",
            record_ids=["r1"],
            labels={},
            field_names=["text", "sentiment", "confidence"],
        )
        assert view.field_names == ["text", "sentiment", "confidence"]

    def test_freeze_immutable_deep_copy(self) -> None:
        """Verify that modifying the original data doesn't affect the view."""
        mgr = FrozenViewManager()
        labels = {"r1": {"sentiment": "pos"}}
        record_ids = ["r1"]

        view = mgr.freeze(
            "rel-001",
            "ds-001",
            record_ids=record_ids,
            labels=labels,
        )

        # Mutate originals
        record_ids.append("r2")
        labels["r1"]["sentiment"] = "CHANGED"
        labels["r2"] = {"sentiment": "new"}

        # View should be unchanged
        assert view.record_ids == ["r1"]
        assert view.labels["r1"]["sentiment"] == "pos"
        assert "r2" not in view.labels

    def test_freeze_content_hash_deterministic(self) -> None:
        mgr = FrozenViewManager()
        kwargs: dict[str, Any] = {
            "record_ids": ["r1", "r2"],
            "labels": {"r1": {"s": "a"}, "r2": {"s": "b"}},
        }
        v1 = mgr.freeze("rel-a", "ds-001", **kwargs)
        v2 = mgr.freeze("rel-b", "ds-001", **kwargs)
        assert v1.content_hash == v2.content_hash

    def test_get_frozen_view(self) -> None:
        mgr = FrozenViewManager()
        mgr.freeze("rel-001", "ds-001", record_ids=["r1"], labels={})
        view = mgr.get_frozen_view("rel-001")
        assert view is not None
        assert view.release_id == "rel-001"

    def test_get_frozen_view_missing(self) -> None:
        mgr = FrozenViewManager()
        assert mgr.get_frozen_view("nonexistent") is None


# ---------------------------------------------------------------------------
# EX-016: ViewSnapshot (compare frozen vs current)
# ---------------------------------------------------------------------------


class TestViewSnapshot:
    def test_compare_no_changes(self) -> None:
        mgr = FrozenViewManager()
        mgr.freeze(
            "rel-001",
            "ds-001",
            record_ids=["r1", "r2"],
            labels={"r1": {"s": "a"}, "r2": {"s": "b"}},
        )
        snapshot = mgr.compare_with_current(
            "rel-001",
            current_record_ids=["r1", "r2"],
            current_labels={"r1": {"s": "a"}, "r2": {"s": "b"}},
        )
        assert snapshot.records_added_since_freeze == []
        assert snapshot.records_removed_since_freeze == []
        assert snapshot.labels_changed_since_freeze == []
        assert "No changes" in snapshot.summary

    def test_compare_records_added(self) -> None:
        mgr = FrozenViewManager()
        mgr.freeze(
            "rel-001",
            "ds-001",
            record_ids=["r1"],
            labels={"r1": {"s": "a"}},
        )
        snapshot = mgr.compare_with_current(
            "rel-001",
            current_record_ids=["r1", "r2", "r3"],
            current_labels={"r1": {"s": "a"}, "r2": {"s": "b"}, "r3": {"s": "c"}},
        )
        assert sorted(snapshot.records_added_since_freeze) == ["r2", "r3"]
        assert snapshot.records_removed_since_freeze == []

    def test_compare_records_removed(self) -> None:
        mgr = FrozenViewManager()
        mgr.freeze(
            "rel-001",
            "ds-001",
            record_ids=["r1", "r2", "r3"],
            labels={},
        )
        snapshot = mgr.compare_with_current(
            "rel-001",
            current_record_ids=["r1"],
            current_labels={},
        )
        assert sorted(snapshot.records_removed_since_freeze) == ["r2", "r3"]

    def test_compare_labels_changed(self) -> None:
        mgr = FrozenViewManager()
        mgr.freeze(
            "rel-001",
            "ds-001",
            record_ids=["r1", "r2"],
            labels={"r1": {"s": "pos"}, "r2": {"s": "neg"}},
        )
        snapshot = mgr.compare_with_current(
            "rel-001",
            current_record_ids=["r1", "r2"],
            current_labels={"r1": {"s": "pos"}, "r2": {"s": "CHANGED"}},
        )
        assert snapshot.labels_changed_since_freeze == ["r2"]

    def test_compare_nonexistent_release(self) -> None:
        mgr = FrozenViewManager()
        with pytest.raises(ValueError, match="No frozen view"):
            mgr.compare_with_current(
                "nonexistent",
                current_record_ids=[],
                current_labels={},
            )

    def test_compare_summary_includes_counts(self) -> None:
        mgr = FrozenViewManager()
        mgr.freeze(
            "rel-001",
            "ds-001",
            record_ids=["r1", "r2"],
            labels={"r1": {"s": "a"}, "r2": {"s": "b"}},
        )
        snapshot = mgr.compare_with_current(
            "rel-001",
            current_record_ids=["r1", "r3"],
            current_labels={"r1": {"s": "CHANGED"}, "r3": {"s": "c"}},
        )
        assert "1 records added" in snapshot.summary
        assert "1 records removed" in snapshot.summary
        assert "1 records with label changes" in snapshot.summary


# ---------------------------------------------------------------------------
# EX-015: ReadinessReport
# ---------------------------------------------------------------------------


class TestReadinessReport:
    def test_report_all_gates_pass(self) -> None:
        mgr = FrozenViewManager()
        report = mgr.generate_readiness_report(
            "rel-001",
            "ds-001",
            record_count=100,
            labeled_count=100,
            gate_results=[
                {"gate_id": "g1", "passed": True, "message": "OK"},
                {"gate_id": "g2", "passed": True, "message": "OK"},
            ],
            quality_metrics={"agreement": 0.95},
        )
        assert report.is_ready is True
        assert report.coverage_percent == 100.0
        assert report.validation.total_gates == 2
        assert report.validation.gates_passed == 2
        assert report.validation.overall_status == "passed"

    def test_report_gate_failure(self) -> None:
        mgr = FrozenViewManager()
        report = mgr.generate_readiness_report(
            "rel-001",
            "ds-001",
            record_count=100,
            labeled_count=100,
            gate_results=[
                {"gate_id": "g1", "passed": True, "message": "OK"},
                {"gate_id": "g2", "passed": False, "message": "Too low"},
            ],
        )
        assert report.is_ready is False
        assert report.validation.gates_failed == 1
        assert report.validation.overall_status == "failed"
        assert len(report.blocking_issues) > 0

    def test_report_partial_coverage(self) -> None:
        mgr = FrozenViewManager()
        report = mgr.generate_readiness_report(
            "rel-001",
            "ds-001",
            record_count=200,
            labeled_count=150,
            gate_results=[{"gate_id": "g1", "passed": True, "message": "OK"}],
        )
        assert report.coverage_percent == 75.0
        assert any("coverage" in w.lower() for w in report.warnings)

    def test_report_zero_records(self) -> None:
        mgr = FrozenViewManager()
        report = mgr.generate_readiness_report(
            "rel-001",
            "ds-001",
            record_count=0,
            labeled_count=0,
        )
        assert report.coverage_percent == 0.0
        assert report.is_ready is False

    def test_report_no_gates(self) -> None:
        mgr = FrozenViewManager()
        report = mgr.generate_readiness_report(
            "rel-001",
            "ds-001",
            record_count=100,
            labeled_count=100,
        )
        assert report.is_ready is False  # No gates means not ready
        assert report.validation.overall_status == "pending"

    def test_report_quality_metrics(self) -> None:
        mgr = FrozenViewManager()
        report = mgr.generate_readiness_report(
            "rel-001",
            "ds-001",
            record_count=50,
            labeled_count=50,
            gate_results=[{"gate_id": "g1", "passed": True, "message": "OK"}],
            quality_metrics={"kappa": 0.88, "coverage": 1.0},
        )
        assert report.quality_metrics["kappa"] == 0.88
        assert report.is_ready is True


# ---------------------------------------------------------------------------
# EX-015: ReportManifest
# ---------------------------------------------------------------------------


class TestReportManifest:
    def test_manifest_basic(self) -> None:
        mgr = FrozenViewManager()
        manifest = mgr.generate_report_manifest(
            "rel-001",
            "my_project",
            report_names=["readiness", "validation_summary"],
        )
        assert manifest.release_id == "rel-001"
        assert "my_project" in manifest.report_dir
        assert "rel-001" in manifest.report_dir
        assert len(manifest.reports_generated) == 2
        assert manifest.generated_at != ""

    def test_manifest_empty_reports(self) -> None:
        mgr = FrozenViewManager()
        manifest = mgr.generate_report_manifest("rel-001", "proj")
        assert manifest.reports_generated == []

    def test_manifest_path_format(self) -> None:
        mgr = FrozenViewManager()
        manifest = mgr.generate_report_manifest("rel-v2", "analytics")
        assert manifest.report_dir == "workbench/reports/analytics/rel-v2/"


# ---------------------------------------------------------------------------
# EX-016: FrozenSplit
# ---------------------------------------------------------------------------


class TestFrozenSplit:
    def test_basic_split(self) -> None:
        split = FrozenSplit(
            split_name="train",
            record_ids=["r1", "r2"],
            record_count=2,
        )
        assert split.split_name == "train"
        assert len(split.record_ids) == 2

    def test_split_with_metadata(self) -> None:
        split = FrozenSplit(
            split_name="eval",
            record_ids=["r3"],
            record_count=1,
            metadata={"strategy": "random"},
        )
        assert split.metadata["strategy"] == "random"

    def test_frozen(self) -> None:
        split = FrozenSplit(split_name="test", record_ids=[], record_count=0)
        with pytest.raises(AttributeError):
            split.split_name = "other"  # type: ignore[misc]

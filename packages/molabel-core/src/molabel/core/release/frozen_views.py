"""Frozen release views and report generation (EX-015, EX-016).

Provides immutable snapshots of dataset state at release time and
structured report data for readiness/validation summaries.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes — Frozen Views (EX-016)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FrozenSplit:
    """A frozen partition of records within a release (EX-016)."""

    split_name: str
    record_ids: list[str] = field(default_factory=list)
    record_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FrozenView:
    """An immutable snapshot of dataset state at release time (EX-016).

    Captures record IDs, labels, splits, and quality metrics so they
    can be inspected independently of the live dataset.
    """

    release_id: str
    dataset_id: str
    frozen_at: str
    record_ids: list[str] = field(default_factory=list)
    labels: dict[str, dict[str, Any]] = field(default_factory=dict)
    splits: list[FrozenSplit] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    field_names: list[str] = field(default_factory=list)
    content_hash: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ViewSnapshot:
    """Comparison between a frozen view and the current live state (EX-016)."""

    frozen_view: FrozenView
    current_record_ids: list[str] = field(default_factory=list)
    current_labels: dict[str, dict[str, Any]] = field(default_factory=dict)
    records_added_since_freeze: list[str] = field(default_factory=list)
    records_removed_since_freeze: list[str] = field(default_factory=list)
    labels_changed_since_freeze: list[str] = field(default_factory=list)
    summary: str = ""


# ---------------------------------------------------------------------------
# Data classes — Reports (EX-015)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationSummary:
    """Summary of validation results for a release (EX-015)."""

    total_gates: int = 0
    gates_passed: int = 0
    gates_failed: int = 0
    gate_details: list[dict[str, Any]] = field(default_factory=list)
    overall_status: str = "pending"


@dataclass(frozen=True)
class ReadinessReport:
    """Readiness/validation summary report (EX-015)."""

    release_id: str
    dataset_id: str
    generated_at: str
    record_count: int = 0
    labeled_count: int = 0
    coverage_percent: float = 0.0
    validation: ValidationSummary = field(default_factory=ValidationSummary)
    quality_metrics: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    blocking_issues: list[str] = field(default_factory=list)
    is_ready: bool = False


@dataclass(frozen=True)
class ReportManifest:
    """Manifest for generated reports (EX-015)."""

    release_id: str
    report_dir: str
    reports_generated: list[str] = field(default_factory=list)
    generated_at: str = ""


# ---------------------------------------------------------------------------
# Frozen View Manager (EX-016)
# ---------------------------------------------------------------------------


class FrozenViewManager:
    """Creates and inspects frozen dataset views for releases (EX-015, EX-016).

    All operations are pure computation on in-memory data.
    """

    def __init__(self) -> None:
        self._frozen_views: dict[str, FrozenView] = {}

    def freeze(
        self,
        release_id: str,
        dataset_id: str,
        *,
        record_ids: list[str],
        labels: dict[str, dict[str, Any]],
        splits: list[FrozenSplit] | None = None,
        metrics: dict[str, float] | None = None,
        field_names: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> FrozenView:
        """Create an immutable frozen view of the dataset at release time (EX-016).

        Parameters
        ----------
        release_id:
            The release this view belongs to.
        dataset_id:
            The dataset being frozen.
        record_ids:
            Ordered list of record IDs included in the release.
        labels:
            Mapping of record ID -> label dict.
        splits:
            Optional split definitions.
        metrics:
            Quality metrics at freeze time.
        field_names:
            Field names present in the data.
        metadata:
            Additional metadata.
        """
        now = datetime.now(UTC).isoformat()

        # Deep copy to ensure immutability
        frozen_labels = copy.deepcopy(labels)
        frozen_record_ids = list(record_ids)
        frozen_splits = list(splits) if splits else []
        frozen_metrics = dict(metrics) if metrics else {}
        frozen_field_names = list(field_names) if field_names else []
        frozen_metadata = dict(metadata) if metadata else {}

        content_hash = self._compute_view_hash(frozen_record_ids, frozen_labels)

        view = FrozenView(
            release_id=release_id,
            dataset_id=dataset_id,
            frozen_at=now,
            record_ids=frozen_record_ids,
            labels=frozen_labels,
            splits=frozen_splits,
            metrics=frozen_metrics,
            field_names=frozen_field_names,
            content_hash=content_hash,
            metadata=frozen_metadata,
        )

        self._frozen_views[release_id] = view
        logger.info(
            "Frozen view created for release '%s' with %d records.",
            release_id,
            len(frozen_record_ids),
        )
        return view

    def get_frozen_view(self, release_id: str) -> FrozenView | None:
        """Retrieve a previously frozen view."""
        return self._frozen_views.get(release_id)

    def compare_with_current(
        self,
        release_id: str,
        *,
        current_record_ids: list[str],
        current_labels: dict[str, dict[str, Any]],
    ) -> ViewSnapshot:
        """Compare a frozen view with the current live dataset state (EX-016).

        Parameters
        ----------
        release_id:
            The release whose frozen view to compare against.
        current_record_ids:
            Record IDs in the current live dataset.
        current_labels:
            Current label mapping.

        Raises
        ------
        ValueError
            If no frozen view exists for the given release.
        """
        view = self._frozen_views.get(release_id)
        if view is None:
            raise ValueError(f"No frozen view for release '{release_id}'.")

        frozen_set = set(view.record_ids)
        current_set = set(current_record_ids)

        added = sorted(current_set - frozen_set)
        removed = sorted(frozen_set - current_set)

        changed: list[str] = []
        for rid in sorted(frozen_set & current_set):
            frozen_label = view.labels.get(rid, {})
            current_label = current_labels.get(rid, {})
            if frozen_label != current_label:
                changed.append(rid)

        parts: list[str] = []
        if added:
            parts.append(f"{len(added)} records added since freeze")
        if removed:
            parts.append(f"{len(removed)} records removed since freeze")
        if changed:
            parts.append(f"{len(changed)} records with label changes")
        summary = "; ".join(parts) if parts else "No changes since freeze."

        return ViewSnapshot(
            frozen_view=view,
            current_record_ids=list(current_record_ids),
            current_labels=current_labels,
            records_added_since_freeze=added,
            records_removed_since_freeze=removed,
            labels_changed_since_freeze=changed,
            summary=summary,
        )

    def generate_readiness_report(
        self,
        release_id: str,
        dataset_id: str,
        *,
        record_count: int,
        labeled_count: int,
        gate_results: list[dict[str, Any]] | None = None,
        quality_metrics: dict[str, float] | None = None,
    ) -> ReadinessReport:
        """Generate a readiness/validation summary report (EX-015).

        Parameters
        ----------
        release_id:
            The release this report is for.
        dataset_id:
            The dataset ID.
        record_count:
            Total record count.
        labeled_count:
            Number of labeled records.
        gate_results:
            List of dicts with keys ``gate_id``, ``passed``, ``message``.
        quality_metrics:
            Quality metric values.
        """
        now = datetime.now(UTC).isoformat()
        coverage = (labeled_count / record_count * 100.0) if record_count > 0 else 0.0

        gate_results = gate_results or []
        quality_metrics = quality_metrics or {}

        total_gates = len(gate_results)
        gates_passed = sum(1 for g in gate_results if g.get("passed", False))
        gates_failed = total_gates - gates_passed

        if gates_failed == 0 and total_gates > 0:
            overall_status = "passed"
        else:
            overall_status = "pending"
        if gates_failed > 0:
            overall_status = "failed"

        validation = ValidationSummary(
            total_gates=total_gates,
            gates_passed=gates_passed,
            gates_failed=gates_failed,
            gate_details=list(gate_results),
            overall_status=overall_status,
        )

        warnings: list[str] = []
        blocking: list[str] = []

        if coverage < 100.0:
            warnings.append(
                f"Label coverage is {coverage:.1f}% "
                f"({labeled_count}/{record_count} records)."
            )

        if gates_failed > 0:
            failed_names = [
                g.get("gate_id", "unknown")
                for g in gate_results
                if not g.get("passed", False)
            ]
            blocking.append(f"Failed validation gates: {failed_names}")

        is_ready = len(blocking) == 0 and total_gates > 0 and gates_failed == 0

        return ReadinessReport(
            release_id=release_id,
            dataset_id=dataset_id,
            generated_at=now,
            record_count=record_count,
            labeled_count=labeled_count,
            coverage_percent=round(coverage, 2),
            validation=validation,
            quality_metrics=quality_metrics,
            warnings=warnings,
            blocking_issues=blocking,
            is_ready=is_ready,
        )

    def generate_report_manifest(
        self,
        release_id: str,
        project: str,
        *,
        report_names: list[str] | None = None,
    ) -> ReportManifest:
        """Generate a report manifest for a release (EX-015).

        Parameters
        ----------
        release_id:
            The release the reports belong to.
        project:
            Project identifier for path generation.
        report_names:
            Names of reports generated.
        """
        now = datetime.now(UTC).isoformat()
        report_dir = f"workbench/reports/{project}/{release_id}/"
        return ReportManifest(
            release_id=release_id,
            report_dir=report_dir,
            reports_generated=report_names or [],
            generated_at=now,
        )

    @staticmethod
    def _compute_view_hash(
        record_ids: list[str],
        labels: dict[str, dict[str, Any]],
    ) -> str:
        """Compute a deterministic hash of the frozen view content."""
        hasher = hashlib.sha256()
        for rid in sorted(record_ids):
            hasher.update(rid.encode("utf-8"))
            label_data = labels.get(rid, {})
            hasher.update(
                json.dumps(label_data, sort_keys=True, default=str).encode("utf-8")
            )
        return hasher.hexdigest()

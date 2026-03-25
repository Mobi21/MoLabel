"""Release bundle inspection and diff (EX-009).

Provides tools to inspect a release bundle's contents and compare it
against a previous release.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class ReleaseInspection:
    """Inspection summary of a single release bundle (EX-009)."""

    release_id: str
    record_count: int
    field_names: list[str] = field(default_factory=list)
    label_counts: dict[str, int] = field(default_factory=dict)
    format: str = ""
    file_size_bytes: int = 0
    content_hash: str = ""
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReleaseDiff:
    """Diff between two release bundles (EX-009)."""

    previous_release_id: str
    current_release_id: str
    record_count_delta: int = 0
    records_added: int = 0
    records_removed: int = 0
    fields_added: list[str] = field(default_factory=list)
    fields_removed: list[str] = field(default_factory=list)
    label_changes: dict[str, dict[str, int]] = field(default_factory=dict)
    summary: str = ""


@dataclass(frozen=True)
class ReleaseReport:
    """Generated report data for a release (EX-009)."""

    release_id: str
    inspection: ReleaseInspection
    diff: ReleaseDiff | None = None
    generated_at: str = ""
    notes: list[str] = field(default_factory=list)


class ReleaseInspector:
    """Inspects and compares release bundles (EX-009).

    Operates on in-memory record data. Callers load the data and pass it in;
    the inspector performs pure computation.
    """

    def inspect(
        self,
        release_id: str,
        records: list[dict[str, Any]],
        *,
        format: str = "",
        file_size_bytes: int = 0,
        content_hash: str = "",
        created_at: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ReleaseInspection:
        """Inspect a release bundle's contents.

        Parameters
        ----------
        release_id:
            Identifier for the release.
        records:
            The record dicts comprising the release.
        format:
            The export format used.
        file_size_bytes:
            Size of the exported file.
        content_hash:
            SHA-256 hash of the export content.
        created_at:
            ISO timestamp of creation.
        metadata:
            Additional metadata.
        """
        field_names = _collect_field_names(records)
        label_counts = _count_labels(records)

        return ReleaseInspection(
            release_id=release_id,
            record_count=len(records),
            field_names=field_names,
            label_counts=label_counts,
            format=format,
            file_size_bytes=file_size_bytes,
            content_hash=content_hash,
            created_at=created_at,
            metadata=metadata or {},
        )

    def diff(
        self,
        previous: ReleaseInspection,
        current: ReleaseInspection,
        *,
        previous_record_ids: set[str] | None = None,
        current_record_ids: set[str] | None = None,
    ) -> ReleaseDiff:
        """Compare two release inspections and produce a diff (EX-009).

        Parameters
        ----------
        previous:
            Inspection of the previous release.
        current:
            Inspection of the current release.
        previous_record_ids:
            Set of record IDs in the previous release (for add/remove counts).
        current_record_ids:
            Set of record IDs in the current release.
        """
        record_count_delta = current.record_count - previous.record_count

        prev_fields = set(previous.field_names)
        curr_fields = set(current.field_names)
        fields_added = sorted(curr_fields - prev_fields)
        fields_removed = sorted(prev_fields - curr_fields)

        records_added = 0
        records_removed = 0
        if previous_record_ids is not None and current_record_ids is not None:
            records_added = len(current_record_ids - previous_record_ids)
            records_removed = len(previous_record_ids - current_record_ids)

        label_changes = _compute_label_changes(
            previous.label_counts, current.label_counts
        )

        parts: list[str] = []
        if record_count_delta != 0:
            parts.append(f"Record count: {record_count_delta:+d}")
        if records_added:
            parts.append(f"{records_added} records added")
        if records_removed:
            parts.append(f"{records_removed} records removed")
        if fields_added:
            parts.append(f"Fields added: {fields_added}")
        if fields_removed:
            parts.append(f"Fields removed: {fields_removed}")
        summary = "; ".join(parts) if parts else "No significant changes."

        return ReleaseDiff(
            previous_release_id=previous.release_id,
            current_release_id=current.release_id,
            record_count_delta=record_count_delta,
            records_added=records_added,
            records_removed=records_removed,
            fields_added=fields_added,
            fields_removed=fields_removed,
            label_changes=label_changes,
            summary=summary,
        )

    def generate_report(
        self,
        release_id: str,
        records: list[dict[str, Any]],
        *,
        previous_inspection: ReleaseInspection | None = None,
        previous_record_ids: set[str] | None = None,
        current_record_ids: set[str] | None = None,
        format: str = "",
        file_size_bytes: int = 0,
        content_hash: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ReleaseReport:
        """Generate a full release report with optional diff (EX-009).

        Parameters
        ----------
        release_id:
            Identifier for the current release.
        records:
            The record dicts in the current release.
        previous_inspection:
            If provided, a diff is computed against this.
        previous_record_ids:
            Record IDs from the previous release.
        current_record_ids:
            Record IDs from the current release.
        format:
            Export format.
        file_size_bytes:
            File size.
        content_hash:
            Content hash.
        metadata:
            Additional metadata.
        """
        now = datetime.now(UTC).isoformat()

        inspection = self.inspect(
            release_id,
            records,
            format=format,
            file_size_bytes=file_size_bytes,
            content_hash=content_hash,
            created_at=now,
            metadata=metadata,
        )

        diff_result: ReleaseDiff | None = None
        notes: list[str] = []
        if previous_inspection is not None:
            diff_result = self.diff(
                previous_inspection,
                inspection,
                previous_record_ids=previous_record_ids,
                current_record_ids=current_record_ids,
            )
            if diff_result.record_count_delta < 0:
                notes.append(
                    f"Warning: {abs(diff_result.record_count_delta)} fewer records "
                    f"than previous release."
                )
            if diff_result.fields_removed:
                notes.append(f"Warning: Fields removed: {diff_result.fields_removed}")

        return ReleaseReport(
            release_id=release_id,
            inspection=inspection,
            diff=diff_result,
            generated_at=now,
            notes=notes,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _collect_field_names(records: list[dict[str, Any]]) -> list[str]:
    """Collect all unique field names across records, sorted."""
    names: set[str] = set()
    for record in records:
        names.update(record.keys())
    return sorted(names)


def _count_labels(records: list[dict[str, Any]]) -> dict[str, int]:
    """Count occurrences of each field across records."""
    counts: dict[str, int] = {}
    for record in records:
        for key in record:
            counts[key] = counts.get(key, 0) + 1
    return counts


def _compute_label_changes(
    previous: dict[str, int],
    current: dict[str, int],
) -> dict[str, dict[str, int]]:
    """Compute per-field count changes between two releases."""
    changes: dict[str, dict[str, int]] = {}
    all_keys = set(previous) | set(current)
    for key in sorted(all_keys):
        prev_count = previous.get(key, 0)
        curr_count = current.get(key, 0)
        if prev_count != curr_count:
            changes[key] = {
                "previous": prev_count,
                "current": curr_count,
                "delta": curr_count - prev_count,
            }
    return changes

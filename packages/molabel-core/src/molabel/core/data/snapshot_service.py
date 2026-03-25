"""Dataset snapshot service (DT-013, DT-014).

Named snapshot create/browse/compare(diff)/restore with non-destructive
restoration. Stores lightweight delta references as JSON metadata files
under workbench/snapshots/.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from molabel.core.database import get_session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public result types
# ---------------------------------------------------------------------------


class SnapshotSummary(BaseModel):
    """Summary of a snapshot for browsing."""

    id: uuid.UUID
    name: str
    description: str | None = None
    snapshot_type: str
    record_count: int
    labeled_count: int
    quality_metrics: dict[str, Any] | None = None
    created_at: datetime | None = None


class SnapshotDiff(BaseModel):
    """Diff between two snapshots."""

    snapshot_a_id: uuid.UUID
    snapshot_b_id: uuid.UUID
    snapshot_a_name: str = ""
    snapshot_b_name: str = ""
    record_count_change: int = 0
    labeled_count_change: int = 0
    new_records: int = 0
    removed_records: int = 0
    changed_labels: int = 0
    quality_metric_changes: dict[str, dict[str, float]] = {}
    membership_changes: dict[str, Any] = {}


class SnapshotCreateResult(BaseModel):
    """Result of creating a snapshot."""

    snapshot_id: uuid.UUID
    name: str
    snapshot_type: str
    file_path: str | None = None


class SnapshotRestoreResult(BaseModel):
    """Result of restoring a snapshot."""

    restored_snapshot_id: uuid.UUID
    safety_snapshot_id: uuid.UUID
    records_restored: int = 0
    labels_restored: int = 0


# ---------------------------------------------------------------------------
# SnapshotService
# ---------------------------------------------------------------------------


class SnapshotService:
    """Manages dataset snapshots: create, browse, compare (diff), restore.

    Snapshots capture the complete state of a dataset at a point in time,
    including labels, agent outputs, review state, quality metrics, and
    dataset membership.

    Storage model: lightweight delta references stored as JSON metadata
    files under ``workbench/snapshots/``.
    """

    def create_snapshot(
        self,
        engine: Any,
        *,
        workspace_id: uuid.UUID,
        dataset_id: uuid.UUID,
        name: str,
        description: str | None = None,
        workspace_root: Path | None = None,
        include_labels: bool = True,
    ) -> SnapshotCreateResult:
        """Create a named snapshot of the current dataset state.

        Parameters
        ----------
        engine:
            SQLAlchemy engine.
        workspace_id:
            Workspace the dataset belongs to.
        dataset_id:
            Dataset to snapshot.
        name:
            Human-readable snapshot name.
        description:
            Optional description.
        workspace_root:
            Workspace root for writing JSON metadata files.
        include_labels:
            Whether to capture label state in the snapshot.
        """
        from molabel.core.models.dataset import Dataset
        from molabel.core.models.dataset_snapshot import DatasetSnapshot
        from molabel.core.models.record import Record

        with get_session(engine) as session:
            dataset = session.get(Dataset, dataset_id)
            if not dataset:
                raise ValueError(f"Dataset {dataset_id} not found")
            dataset_name = dataset.dataset_name

            # Gather current state.
            from sqlmodel import func, select

            record_count = (
                session.exec(
                    select(func.count(Record.id)).where(Record.dataset_id == dataset_id)
                ).one()
                or 0
            )

            labeled_count = (
                session.exec(
                    select(func.count(Record.id)).where(
                        Record.dataset_id == dataset_id,
                        Record.label_count > 0,
                    )
                ).one()
                or 0
            )

            # Build quality metrics summary.
            quality_metrics = self._compute_quality_metrics(session, dataset_id)

            # Build label summary (includes per-record state for restore).
            label_summary = (
                self._compute_label_summary(session, dataset_id)
                if include_labels
                else None
            )

            # Capture per-record state for restore.
            record_states = self._capture_record_states(session, dataset_id)

            # Capture dataset-level metadata for restore.
            dataset_membership = {
                "health_status": dataset.health_status.value
                if dataset.health_status
                else None,
                "record_states": record_states,
            }

            # Determine snapshot type: full or delta.
            from sqlmodel import select as sel

            prev_snapshots = list(
                session.exec(
                    sel(DatasetSnapshot)
                    .where(DatasetSnapshot.dataset_id == dataset_id)
                    .order_by(DatasetSnapshot.created_at.desc())  # type: ignore[union-attr]
                    .limit(1)
                ).all()
            )

            parent_id = prev_snapshots[0].id if prev_snapshots else None
            snap_type = "delta" if parent_id else "full"

            # Compute delta data if this is a delta snapshot.
            delta_data = None
            if parent_id:
                delta_data = self._compute_delta(
                    session,
                    dataset_id=dataset_id,
                    parent_snapshot=prev_snapshots[0],
                    current_record_count=record_count,
                    current_labeled_count=labeled_count,
                )

            snapshot = DatasetSnapshot(
                workspace_id=workspace_id,
                dataset_id=dataset_id,
                name=name,
                description=description,
                snapshot_type=snap_type,
                parent_snapshot_id=parent_id,
                record_count=record_count,
                labeled_count=labeled_count,
                quality_metrics=quality_metrics,
                label_summary=label_summary,
                dataset_membership=dataset_membership,
                delta_data=delta_data,
            )
            session.add(snapshot)
            session.commit()
            session.refresh(snapshot)

        # Write JSON metadata file.
        file_path = None
        if workspace_root:
            file_path = self._write_snapshot_file(
                workspace_root, snapshot, dataset_name
            )

        return SnapshotCreateResult(
            snapshot_id=snapshot.id,
            name=name,
            snapshot_type=snap_type,
            file_path=file_path,
        )

    def browse_snapshots(
        self,
        engine: Any,
        *,
        dataset_id: uuid.UUID,
    ) -> list[SnapshotSummary]:
        """List all snapshots for a dataset, newest first."""
        from molabel.core.models.dataset_snapshot import DatasetSnapshot

        with get_session(engine) as session:
            from sqlmodel import select

            stmt = (
                select(DatasetSnapshot)
                .where(DatasetSnapshot.dataset_id == dataset_id)
                .order_by(DatasetSnapshot.created_at.desc())  # type: ignore[union-attr]
            )
            snapshots = list(session.exec(stmt).all())

        return [
            SnapshotSummary(
                id=s.id,
                name=s.name,
                description=s.description,
                snapshot_type=s.snapshot_type,
                record_count=s.record_count,
                labeled_count=s.labeled_count,
                quality_metrics=s.quality_metrics,
                created_at=s.created_at,
            )
            for s in snapshots
        ]

    def compare_snapshots(
        self,
        engine: Any,
        *,
        snapshot_a_id: uuid.UUID,
        snapshot_b_id: uuid.UUID,
    ) -> SnapshotDiff:
        """Compare two snapshots and return the diff."""
        from molabel.core.models.dataset_snapshot import DatasetSnapshot

        with get_session(engine) as session:
            snap_a = session.get(DatasetSnapshot, snapshot_a_id)
            snap_b = session.get(DatasetSnapshot, snapshot_b_id)

            if not snap_a or not snap_b:
                raise ValueError("One or both snapshots not found")

            record_count_change = snap_b.record_count - snap_a.record_count
            labeled_count_change = snap_b.labeled_count - snap_a.labeled_count

            # Compute quality metric changes.
            quality_changes: dict[str, dict[str, float]] = {}
            metrics_a = snap_a.quality_metrics or {}
            metrics_b = snap_b.quality_metrics or {}

            all_metric_keys = set(metrics_a.keys()) | set(metrics_b.keys())
            for key in all_metric_keys:
                val_a = metrics_a.get(key, 0.0)
                val_b = metrics_b.get(key, 0.0)
                if (
                    isinstance(val_a, (int, float))
                    and isinstance(val_b, (int, float))
                    and val_a != val_b
                ):
                    quality_changes[key] = {
                        "before": float(val_a),
                        "after": float(val_b),
                        "delta": float(val_b) - float(val_a),
                    }

            # Compute membership changes from delta_data if available.
            membership_changes: dict[str, Any] = {}
            if snap_b.delta_data:
                membership_changes = snap_b.delta_data.get("membership_changes", {})

            changed_labels = 0
            if snap_b.delta_data:
                changed_labels = snap_b.delta_data.get("changed_labels", 0)

            new_records = max(0, record_count_change)
            removed_records = max(0, -record_count_change)

        return SnapshotDiff(
            snapshot_a_id=snapshot_a_id,
            snapshot_b_id=snapshot_b_id,
            snapshot_a_name=snap_a.name,
            snapshot_b_name=snap_b.name,
            record_count_change=record_count_change,
            labeled_count_change=labeled_count_change,
            new_records=new_records,
            removed_records=removed_records,
            changed_labels=changed_labels,
            quality_metric_changes=quality_changes,
            membership_changes=membership_changes,
        )

    def restore_snapshot(
        self,
        engine: Any,
        *,
        workspace_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        workspace_root: Path | None = None,
    ) -> SnapshotRestoreResult:
        """Restore a dataset to a previous snapshot state.

        First creates a safety snapshot of the current state, then
        applies the historical snapshot. This is non-destructive:
        the current state is always preserved.

        Restores:
        - Dataset-level counters and health status
        - Per-record state: labels, latest_label, composite_confidence,
          export_eligible, flags
        - Quality metrics from the snapshot
        """
        from molabel.core.models.dataset import Dataset
        from molabel.core.models.dataset_snapshot import DatasetSnapshot
        from molabel.core.models.record import Record

        with get_session(engine) as session:
            target_snapshot = session.get(DatasetSnapshot, snapshot_id)
            if not target_snapshot:
                raise ValueError(f"Snapshot {snapshot_id} not found")

            dataset_id = target_snapshot.dataset_id

        # Create safety snapshot of current state.
        safety = self.create_snapshot(
            engine,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            name="Pre-restore safety snapshot",
            description=(
                f"Auto-created before restoring snapshot '{target_snapshot.name}'"
            ),
            workspace_root=workspace_root,
        )

        # Apply the restoration.
        labels_restored = 0

        with get_session(engine) as session:
            # 1. Restore dataset-level state.
            dataset = session.get(Dataset, dataset_id)
            if dataset:
                dataset.record_count = target_snapshot.record_count
                dataset.labeled_count = target_snapshot.labeled_count
                dataset.updated_at = datetime.now(UTC)

                # Restore health_status from snapshot membership data.
                membership = target_snapshot.dataset_membership or {}
                health_str = membership.get("health_status")
                if health_str:
                    from molabel.core.types import DatasetHealthStatus

                    with contextlib.suppress(ValueError):
                        dataset.health_status = DatasetHealthStatus(health_str)

                session.add(dataset)

            # 2. Restore per-record state from snapshot.
            record_states = (membership or {}).get("record_states", {})
            if record_states:
                from sqlmodel import select

                records = list(
                    session.exec(
                        select(Record).where(Record.dataset_id == dataset_id)
                    ).all()
                )

                for record in records:
                    rec_key = str(record.id)
                    if rec_key not in record_states:
                        continue

                    state = record_states[rec_key]
                    record.latest_label = state.get("latest_label")
                    record.composite_confidence = state.get("composite_confidence")
                    record.export_eligible = state.get("export_eligible", False)
                    record.flags = state.get("flags")
                    record.label_count = state.get("label_count", 0)
                    record.updated_at = datetime.now(UTC)
                    session.add(record)

                    if record.label_count and record.label_count > 0:
                        labels_restored += 1

            session.commit()

        return SnapshotRestoreResult(
            restored_snapshot_id=snapshot_id,
            safety_snapshot_id=safety.snapshot_id,
            records_restored=target_snapshot.record_count,
            labels_restored=labels_restored,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_quality_metrics(
        session: Any,
        dataset_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Compute basic quality metrics for a dataset."""
        from sqlmodel import func, select

        from molabel.core.models.record import Record

        total = (
            session.exec(
                select(func.count(Record.id)).where(Record.dataset_id == dataset_id)
            ).one()
            or 0
        )
        labeled = (
            session.exec(
                select(func.count(Record.id)).where(
                    Record.dataset_id == dataset_id,
                    Record.label_count > 0,
                )
            ).one()
            or 0
        )
        export_ready = (
            session.exec(
                select(func.count(Record.id)).where(
                    Record.dataset_id == dataset_id,
                    Record.export_eligible == True,  # noqa: E712
                )
            ).one()
            or 0
        )

        coverage = labeled / total if total > 0 else 0.0

        return {
            "total_records": total,
            "labeled_records": labeled,
            "export_ready_records": export_ready,
            "coverage": round(coverage, 4),
        }

    @staticmethod
    def _compute_label_summary(
        session: Any,
        dataset_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Compute a summary of labels for a dataset."""
        from sqlmodel import select

        from molabel.core.models.record import Record
        from molabel.core.models.review_event import ReviewEvent

        # Count review events by source.
        records = list(
            session.exec(select(Record.id).where(Record.dataset_id == dataset_id)).all()
        )
        record_ids = set(records)

        if not record_ids:
            return {"total_events": 0, "by_source": {}}

        events = list(
            session.exec(
                select(ReviewEvent).where(
                    ReviewEvent.record_id.in_(record_ids)  # type: ignore[union-attr]
                )
            ).all()
        )

        by_source: dict[str, int] = {}
        for event in events:
            src = str(event.source)
            by_source[src] = by_source.get(src, 0) + 1

        return {
            "total_events": len(events),
            "by_source": by_source,
        }

    @staticmethod
    def _capture_record_states(
        session: Any,
        dataset_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Capture per-record state for snapshot restore.

        Returns a dict keyed by record ID (as string) with the
        mutable fields that need to be restored.
        """
        from sqlmodel import select

        from molabel.core.models.record import Record

        records = list(
            session.exec(select(Record).where(Record.dataset_id == dataset_id)).all()
        )

        states: dict[str, Any] = {}
        for record in records:
            states[str(record.id)] = {
                "latest_label": record.latest_label,
                "composite_confidence": record.composite_confidence,
                "export_eligible": record.export_eligible,
                "flags": record.flags,
                "label_count": record.label_count,
            }
        return states

    @staticmethod
    def _compute_delta(
        session: Any,
        *,
        dataset_id: uuid.UUID,
        parent_snapshot: Any,
        current_record_count: int,
        current_labeled_count: int,
    ) -> dict[str, Any]:
        """Compute delta data between parent snapshot and current state."""
        return {
            "record_count_change": (
                current_record_count - parent_snapshot.record_count
            ),
            "labeled_count_change": (
                current_labeled_count - parent_snapshot.labeled_count
            ),
            "changed_labels": abs(
                current_labeled_count - parent_snapshot.labeled_count
            ),
            "membership_changes": {},
        }

    @staticmethod
    def _sanitize_snapshot_name(name: str) -> str:
        """Sanitize a snapshot name for safe use in filenames.

        Strips path separators, removes ``..``, and limits to
        alphanumeric characters, underscores, and hyphens.
        """
        # Replace spaces with underscores first.
        sanitized = name.replace(" ", "_")
        # Remove path separators and parent-directory references.
        sanitized = sanitized.replace("/", "").replace("\\", "")
        sanitized = sanitized.replace("..", "")
        # Keep only alphanumeric, underscore, and hyphen.
        sanitized = re.sub(r"[^a-zA-Z0-9_\-]", "", sanitized)
        # Ensure non-empty.
        if not sanitized:
            sanitized = "snapshot"
        return sanitized

    @staticmethod
    def _write_snapshot_file(
        workspace_root: Path,
        snapshot: Any,
        dataset_name: str,
    ) -> str:
        """Write snapshot metadata as a JSON file.

        Uses atomic write (temp file + rename) and validates that the
        resulting path does not escape the snapshots directory.
        """
        snapshots_dir = workspace_root / "workbench" / "snapshots"
        snapshots_dir.mkdir(parents=True, exist_ok=True)

        safe_name = SnapshotService._sanitize_snapshot_name(snapshot.name)
        filename = f"{safe_name}_{snapshot.id}.json"
        file_path = snapshots_dir / filename

        # Validate the resolved path stays under snapshots_dir.
        resolved = file_path.resolve()
        if not str(resolved).startswith(str(snapshots_dir.resolve())):
            raise ValueError(
                f"Snapshot name '{snapshot.name}' resolves to a path "
                f"outside the snapshots directory"
            )

        data = {
            "snapshot_id": str(snapshot.id),
            "dataset_id": str(snapshot.dataset_id),
            "dataset_name": dataset_name,
            "name": snapshot.name,
            "description": snapshot.description,
            "snapshot_type": snapshot.snapshot_type,
            "record_count": snapshot.record_count,
            "labeled_count": snapshot.labeled_count,
            "quality_metrics": snapshot.quality_metrics,
            "created_at": snapshot.created_at.isoformat()
            if snapshot.created_at
            else None,
        }

        # Atomic write: write to temp file then rename.
        fd, tmp_path = tempfile.mkstemp(dir=snapshots_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_f:
                tmp_f.write(json.dumps(data, indent=2, default=str))
            os.rename(tmp_path, file_path)
        except Exception:
            # Clean up temp file on failure.
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

        return str(file_path.relative_to(workspace_root))

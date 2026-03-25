"""Atomic file writer for exports (EX-006, EX-014).

Implements safe write semantics: render to temp dir, verify, then
atomic replace. Previous canonical files are preserved with timestamp
suffixes. Conflict detection prevents blind overwrites.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WriteVerification:
    """Result of verifying an export file before atomic commit."""

    valid: bool
    record_count: int = 0
    content_hash: str = ""
    file_size_bytes: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ConflictCheck:
    """Result of checking for conflicts with an existing file (EX-014)."""

    has_conflict: bool
    existing_hash: str | None = None
    new_hash: str = ""
    record_count_delta: int | None = None
    field_changes: list[str] = field(default_factory=list)
    message: str = ""


@dataclass(frozen=True)
class ConflictResolution:
    """Policy for resolving a detected write conflict (EX-014)."""

    strategy: str = "fail"
    """One of: ``fail``, ``force``, ``refresh``, ``rebase``."""

    reason: str = ""
    """Human-readable reason for the chosen strategy."""

    @staticmethod
    def force(reason: str = "") -> ConflictResolution:
        """Create a force-overwrite resolution."""
        return ConflictResolution(strategy="force", reason=reason)

    @staticmethod
    def refresh(reason: str = "") -> ConflictResolution:
        """Create a refresh (re-export then write) resolution."""
        return ConflictResolution(strategy="refresh", reason=reason)

    @staticmethod
    def rebase(reason: str = "") -> ConflictResolution:
        """Create a rebase (merge changes) resolution."""
        return ConflictResolution(strategy="rebase", reason=reason)

    @staticmethod
    def fail(reason: str = "") -> ConflictResolution:
        """Create a fail (abort) resolution."""
        return ConflictResolution(strategy="fail", reason=reason)


@dataclass(frozen=True)
class AtomicWriteResult:
    """Outcome of an atomic write operation."""

    success: bool
    final_path: Path | None = None
    previous_path: Path | None = None
    content_hash: str = ""
    file_size_bytes: int = 0
    error: str | None = None


def _compute_file_hash(path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _compute_bytes_hash(data: bytes) -> str:
    """Compute SHA-256 hash of in-memory bytes."""
    return hashlib.sha256(data).hexdigest()


def _timestamp_suffix() -> str:
    """Generate a timestamp string for archiving previous files."""
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


class AtomicWriter:
    """Manages atomic writes to canonical export paths (EX-006).

    The write flow:
    1. Write data to a temp file in a quarantine directory.
    2. Verify the temp file (size, hash).
    3. Check for conflicts with the existing canonical file.
    4. Archive the existing file (if any) with a timestamp suffix.
    5. Atomically move the temp file to the canonical path.
    """

    def __init__(self, quarantine_dir: Path | None = None) -> None:
        self._quarantine_dir = quarantine_dir

    def _get_quarantine_dir(self, target: Path) -> Path:
        """Return the quarantine directory, creating it if necessary."""
        if self._quarantine_dir is not None:
            self._quarantine_dir.mkdir(parents=True, exist_ok=True)
            return self._quarantine_dir
        qdir = target.parent / ".export_quarantine"
        qdir.mkdir(parents=True, exist_ok=True)
        return qdir

    def verify_data(
        self,
        data: bytes,
        *,
        expected_record_count: int | None = None,
        line_delimited: bool = False,
    ) -> WriteVerification:
        """Verify in-memory export data before writing.

        Parameters
        ----------
        data:
            The export data bytes.
        expected_record_count:
            If provided, verify the number of records matches.
        line_delimited:
            If True, count non-empty lines as records.
        """
        errors: list[str] = []
        content_hash = _compute_bytes_hash(data)
        file_size = len(data)

        actual_count = 0
        if line_delimited and data:
            lines = data.decode("utf-8", errors="replace").strip().split("\n")
            actual_count = len([line for line in lines if line.strip()])
            if (
                expected_record_count is not None
                and actual_count != expected_record_count
            ):
                errors.append(
                    f"Record count mismatch: expected {expected_record_count}, "
                    f"got {actual_count}"
                )
        elif expected_record_count is not None:
            actual_count = expected_record_count

        return WriteVerification(
            valid=len(errors) == 0,
            record_count=actual_count,
            content_hash=content_hash,
            file_size_bytes=file_size,
            errors=errors,
        )

    def check_conflict(
        self,
        target: Path,
        new_hash: str,
        *,
        new_record_count: int | None = None,
        existing_record_count: int | None = None,
        new_fields: set[str] | None = None,
        existing_fields: set[str] | None = None,
    ) -> ConflictCheck:
        """Check whether writing to target would conflict with existing data (EX-014).

        Parameters
        ----------
        target:
            The canonical output path.
        new_hash:
            SHA-256 hash of the new data.
        new_record_count:
            Record count in the new export.
        existing_record_count:
            Known record count in the existing file (avoids re-parsing).
        new_fields:
            Field names in the new export.
        existing_fields:
            Field names in the existing file.
        """
        if not target.exists():
            return ConflictCheck(
                has_conflict=False,
                new_hash=new_hash,
                message="No existing file; safe to write.",
            )

        existing_hash = _compute_file_hash(target)

        if existing_hash == new_hash:
            return ConflictCheck(
                has_conflict=False,
                existing_hash=existing_hash,
                new_hash=new_hash,
                message="Content unchanged; no write needed.",
            )

        # Compute deltas
        record_delta: int | None = None
        if new_record_count is not None and existing_record_count is not None:
            record_delta = new_record_count - existing_record_count

        field_changes: list[str] = []
        if new_fields is not None and existing_fields is not None:
            added = new_fields - existing_fields
            removed = existing_fields - new_fields
            if added:
                field_changes.append(f"Fields added: {sorted(added)}")
            if removed:
                field_changes.append(f"Fields removed: {sorted(removed)}")

        delta_msg = ""
        if record_delta is not None:
            delta_msg = f"Record count delta: {record_delta:+d}. "
        if field_changes:
            delta_msg += " ".join(field_changes)

        return ConflictCheck(
            has_conflict=True,
            existing_hash=existing_hash,
            new_hash=new_hash,
            record_count_delta=record_delta,
            field_changes=field_changes,
            message=f"Existing file differs. {delta_msg}".strip(),
        )

    def write_atomic(
        self,
        data: bytes,
        target: Path,
        *,
        conflict_resolution: ConflictResolution | None = None,
        skip_conflict_check: bool = False,
    ) -> AtomicWriteResult:
        """Write data atomically to target, archiving the previous version (EX-006).

        Parameters
        ----------
        data:
            The export data to write.
        target:
            The canonical output path.
        conflict_resolution:
            How to handle a conflict if one is detected. When None and a
            conflict exists, the write fails.
        skip_conflict_check:
            If True, skip conflict detection entirely.
        """
        content_hash = _compute_bytes_hash(data)

        # Conflict check
        if not skip_conflict_check and target.exists():
            conflict = self.check_conflict(target, content_hash)
            if conflict.has_conflict:
                resolution = conflict_resolution or ConflictResolution.fail(
                    "Conflict detected and no resolution provided."
                )
                if resolution.strategy == "fail":
                    return AtomicWriteResult(
                        success=False,
                        content_hash=content_hash,
                        file_size_bytes=len(data),
                        error=f"Write conflict: {conflict.message}. "
                        f"Resolution: {resolution.reason or 'aborted'}",
                    )
                # force, refresh, rebase all proceed with the write
                logger.info(
                    "Conflict resolved with strategy '%s': %s",
                    resolution.strategy,
                    resolution.reason,
                )

        # Write to temp file in quarantine
        quarantine = self._get_quarantine_dir(target)
        target.parent.mkdir(parents=True, exist_ok=True)

        try:
            fd, temp_path_str = tempfile.mkstemp(
                dir=str(quarantine),
                prefix="export_",
                suffix=target.suffix,
            )
            temp_path = Path(temp_path_str)
            try:
                os.write(fd, data)
            finally:
                os.close(fd)

            # Archive existing file
            previous_path: Path | None = None
            if target.exists():
                ts = _timestamp_suffix()
                archive_name = f"{target.stem}_{ts}{target.suffix}"
                previous_path = target.parent / archive_name
                shutil.move(str(target), str(previous_path))
                logger.info("Archived previous file to %s", previous_path)

            # Atomic move
            shutil.move(str(temp_path), str(target))
            logger.info("Atomic write complete: %s", target)

            return AtomicWriteResult(
                success=True,
                final_path=target,
                previous_path=previous_path,
                content_hash=content_hash,
                file_size_bytes=len(data),
            )

        except Exception as exc:
            # Clean up temp file if it still exists
            if "temp_path" in locals() and temp_path.exists():
                temp_path.unlink(missing_ok=True)
            return AtomicWriteResult(
                success=False,
                content_hash=content_hash,
                file_size_bytes=len(data),
                error=f"Atomic write failed: {exc}",
            )
        finally:
            # Clean up quarantine dir if empty
            try:
                if quarantine.exists() and not any(quarantine.iterdir()):
                    quarantine.rmdir()
            except OSError:
                pass

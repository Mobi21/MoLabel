"""Artifact indexing, reindexing, and drift detection (DT-002, DT-017, DT-018).

Scans files, computes hashes, detects staleness, supports selective or full
reindex, and filesystem drift detection with conflict resolution.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from molabel.core.database import get_session

logger = logging.getLogger(__name__)

# Size threshold for fast hash (only hash first/last chunks).
_FAST_HASH_THRESHOLD = 100 * 1024 * 1024  # 100 MB


class DriftType(StrEnum):
    """Types of filesystem drift."""

    modified = "modified"
    deleted = "deleted"
    new_file = "new_file"


class DriftEntry(BaseModel):
    """A single filesystem drift event."""

    drift_type: DriftType
    file_path: str
    artifact_id: uuid.UUID | None = None
    old_hash: str | None = None
    new_hash: str | None = None
    message: str = ""


class IndexResult(BaseModel):
    """Result of an indexing or reindexing operation."""

    artifacts_indexed: int = 0
    artifacts_updated: int = 0
    artifacts_stale: int = 0
    artifacts_deleted: int = 0
    errors: list[dict[str, Any]] = []


class ArtifactIndexer:
    """Indexes source files on disk into the operational database.

    Computes file hashes for change detection, marks stale artifacts when
    files change, and supports selective or full reindexing.
    """

    def compute_file_hash(self, path: Path) -> str:
        """Compute a SHA-256 hash for the file at *path*.

        For very large files (> 100 MB), hashes only the first and last
        64 KB chunks plus the file size for performance.
        """
        file_size = path.stat().st_size
        if file_size > _FAST_HASH_THRESHOLD:
            return self._fast_hash(path, file_size)
        return self._full_hash(path)

    def index_file(
        self,
        engine: Any,
        *,
        workspace_id: uuid.UUID,
        dataset_id: uuid.UUID | None = None,
        file_path: Path,
        workspace_root: Path,
        loader_plugin: str | None = None,
    ) -> uuid.UUID:
        """Index a single file, creating or updating its artifact record.

        Returns the artifact UUID.
        """
        from molabel.core.models.artifact import Artifact

        rel_path = str(file_path.relative_to(workspace_root))
        file_hash = self.compute_file_hash(file_path)
        file_size = file_path.stat().st_size
        file_format = self._detect_format(file_path)

        with get_session(engine) as session:
            from sqlmodel import select

            stmt = select(Artifact).where(
                Artifact.workspace_id == workspace_id,
                Artifact.file_path == rel_path,
            )
            existing = session.exec(stmt).first()

            if existing:
                if existing.file_hash != file_hash:
                    existing.file_hash = file_hash
                    existing.file_size_bytes = file_size
                    existing.stale = False
                    existing.indexed_at = datetime.now(UTC)
                    existing.loader_plugin = loader_plugin
                    session.add(existing)
                    session.commit()
                    return existing.id
                existing.stale = False
                existing.indexed_at = datetime.now(UTC)
                session.add(existing)
                session.commit()
                return existing.id

            artifact = Artifact(
                workspace_id=workspace_id,
                dataset_id=dataset_id,
                file_path=rel_path,
                file_hash=file_hash,
                file_size_bytes=file_size,
                file_format=file_format,
                loader_plugin=loader_plugin,
                stale=False,
            )
            session.add(artifact)
            session.commit()
            session.refresh(artifact)
            return artifact.id

    def index_workspace(
        self,
        engine: Any,
        *,
        workspace_id: uuid.UUID,
        workspace_root: Path,
        source_paths: list[str] | None = None,
    ) -> IndexResult:
        """Index all data files in a workspace.

        Parameters
        ----------
        source_paths:
            Optional list of relative paths to index. If None, scans
            all recognised data files under *workspace_root*.
        """
        result = IndexResult()

        if source_paths is None:
            from molabel.core.data.workspace_bootstrap import DATA_FILE_EXTENSIONS

            files_to_index = []
            for item in workspace_root.rglob("*"):
                if (
                    item.is_file()
                    and item.suffix.lower() in DATA_FILE_EXTENSIONS
                    and "workbench" not in item.parts
                ):
                    files_to_index.append(item)
        else:
            files_to_index = [workspace_root / p for p in source_paths]

        for fp in files_to_index:
            if not fp.exists():
                result.errors.append({"file": str(fp), "error": "File not found"})
                continue
            try:
                self.index_file(
                    engine,
                    workspace_id=workspace_id,
                    file_path=fp,
                    workspace_root=workspace_root,
                )
                result.artifacts_indexed += 1
            except Exception as exc:
                logger.warning("Failed to index %s: %s", fp, exc)
                result.errors.append({"file": str(fp), "error": str(exc)})

        return result

    def detect_drift(
        self,
        engine: Any,
        *,
        workspace_id: uuid.UUID,
        workspace_root: Path,
    ) -> list[DriftEntry]:
        """Detect filesystem changes since last index.

        Compares stored artifact hashes with current file state on disk.
        Returns a list of drift entries describing modifications, deletions,
        and new files.
        """
        from molabel.core.models.artifact import Artifact

        drifts: list[DriftEntry] = []

        with get_session(engine) as session:
            from sqlmodel import select

            stmt = select(Artifact).where(Artifact.workspace_id == workspace_id)
            artifacts = list(session.exec(stmt).all())

        indexed_paths: set[str] = set()
        for artifact in artifacts:
            indexed_paths.add(artifact.file_path)
            full_path = workspace_root / artifact.file_path

            if not full_path.exists():
                drifts.append(
                    DriftEntry(
                        drift_type=DriftType.deleted,
                        file_path=artifact.file_path,
                        artifact_id=artifact.id,
                        old_hash=artifact.file_hash,
                        message=f"File deleted: {artifact.file_path}",
                    )
                )
                continue

            current_hash = self.compute_file_hash(full_path)
            if current_hash != artifact.file_hash:
                drifts.append(
                    DriftEntry(
                        drift_type=DriftType.modified,
                        file_path=artifact.file_path,
                        artifact_id=artifact.id,
                        old_hash=artifact.file_hash,
                        new_hash=current_hash,
                        message=f"File modified: {artifact.file_path}",
                    )
                )

        # Scan for new files not yet indexed.
        from molabel.core.data.workspace_bootstrap import DATA_FILE_EXTENSIONS

        for item in workspace_root.rglob("*"):
            if (
                item.is_file()
                and item.suffix.lower() in DATA_FILE_EXTENSIONS
                and "workbench" not in item.parts
            ):
                rel_path = str(item.relative_to(workspace_root))
                if rel_path not in indexed_paths:
                    drifts.append(
                        DriftEntry(
                            drift_type=DriftType.new_file,
                            file_path=rel_path,
                            new_hash=self.compute_file_hash(item),
                            message=f"New file discovered: {rel_path}",
                        )
                    )

        return drifts

    def mark_stale(
        self,
        engine: Any,
        *,
        artifact_ids: list[uuid.UUID],
    ) -> int:
        """Mark the given artifacts as stale.

        Returns the number of artifacts updated.
        """
        from molabel.core.models.artifact import Artifact

        count = 0
        with get_session(engine) as session:
            for aid in artifact_ids:
                artifact = session.get(Artifact, aid)
                if artifact and not artifact.stale:
                    artifact.stale = True
                    session.add(artifact)
                    count += 1
            session.commit()
        return count

    def reindex_selective(
        self,
        engine: Any,
        *,
        workspace_id: uuid.UUID,
        workspace_root: Path,
        artifact_ids: list[uuid.UUID],
    ) -> IndexResult:
        """Reindex only the specified artifacts.

        Reads the file path from each artifact and re-hashes.
        """
        from molabel.core.models.artifact import Artifact

        result = IndexResult()

        with get_session(engine) as session:
            for aid in artifact_ids:
                artifact = session.get(Artifact, aid)
                if not artifact:
                    continue

                full_path = workspace_root / artifact.file_path
                if not full_path.exists():
                    artifact.stale = True
                    session.add(artifact)
                    result.artifacts_stale += 1
                    continue

                try:
                    new_hash = self.compute_file_hash(full_path)
                    artifact.file_hash = new_hash
                    artifact.file_size_bytes = full_path.stat().st_size
                    artifact.stale = False
                    artifact.indexed_at = datetime.now(UTC)
                    session.add(artifact)
                    result.artifacts_updated += 1
                except Exception as exc:
                    result.errors.append({"artifact_id": str(aid), "error": str(exc)})
            session.commit()

        return result

    def resolve_drift(
        self,
        engine: Any,
        *,
        workspace_id: uuid.UUID,
        workspace_root: Path,
        drift_entries: list[DriftEntry],
        action: str = "reindex",
    ) -> IndexResult:
        """Apply resolution to detected drift entries.

        Parameters
        ----------
        action:
            One of ``reindex`` (update hashes), ``mark_stale`` (flag for
            later reindex), or ``remove`` (delete artifact records for
            deleted files).
        """
        from molabel.core.models.artifact import Artifact

        result = IndexResult()

        with get_session(engine) as session:
            for drift in drift_entries:
                if drift.drift_type == DriftType.deleted:
                    if action == "remove" and drift.artifact_id:
                        artifact = session.get(Artifact, drift.artifact_id)
                        if artifact:
                            session.delete(artifact)
                            result.artifacts_deleted += 1
                    elif drift.artifact_id:
                        artifact = session.get(Artifact, drift.artifact_id)
                        if artifact:
                            artifact.stale = True
                            session.add(artifact)
                            result.artifacts_stale += 1

                elif drift.drift_type == DriftType.modified:
                    if drift.artifact_id:
                        artifact = session.get(Artifact, drift.artifact_id)
                        if artifact:
                            if action == "reindex":
                                full_path = workspace_root / artifact.file_path
                                artifact.file_hash = self.compute_file_hash(full_path)
                                artifact.file_size_bytes = full_path.stat().st_size
                                artifact.stale = False
                                artifact.indexed_at = datetime.now(UTC)
                                result.artifacts_updated += 1
                            else:
                                artifact.stale = True
                                result.artifacts_stale += 1
                            session.add(artifact)

                elif drift.drift_type == DriftType.new_file and action == "reindex":
                    full_path = workspace_root / drift.file_path
                    if full_path.exists():
                        new_artifact = Artifact(
                            workspace_id=workspace_id,
                            file_path=drift.file_path,
                            file_hash=drift.new_hash
                            or self.compute_file_hash(full_path),
                            file_size_bytes=full_path.stat().st_size,
                            file_format=self._detect_format(full_path),
                            stale=False,
                        )
                        session.add(new_artifact)
                        result.artifacts_indexed += 1

            session.commit()

        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _full_hash(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _fast_hash(path: Path, file_size: int) -> str:
        h = hashlib.sha256()
        h.update(str(file_size).encode())
        with open(path, "rb") as f:
            h.update(f.read(65536))
            f.seek(max(0, file_size - 65536))
            h.update(f.read(65536))
        return h.hexdigest()

    @staticmethod
    def _detect_format(path: Path) -> str:
        ext = path.suffix.lower().lstrip(".")
        format_map = {
            "csv": "csv",
            "tsv": "csv",
            "jsonl": "jsonl",
            "json": "json",
            "yaml": "yaml",
            "yml": "yaml",
            "parquet": "parquet",
            "md": "markdown",
        }
        return format_map.get(ext, ext)

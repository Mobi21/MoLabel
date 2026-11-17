"""Workspace bootstrap and project detection (DT-001, DT-016).

Opens a folder, prefers manifest-driven startup, falls back to heuristic
project detection, initialises or rebuilds DB state from canonical files,
scans files, infers metadata, and surfaces missing requirements.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy import text

from molabel.core.manifest import (
    WorkspaceManifest,
    detect_conflicts,
    load_manifest,
    save_manifest,
)
from molabel.core.types import DatasetHealthStatus

logger = logging.getLogger(__name__)

# Well-known manifest filename.
MANIFEST_FILENAME = "workbench.project.yaml"

# File extensions recognised for heuristic detection.
DATA_FILE_EXTENSIONS = frozenset(
    {".csv", ".tsv", ".jsonl", ".json", ".yaml", ".yml", ".parquet", ".md"}
)

# Core version used for new workspaces.
_CORE_VERSION = "0.1.0"


# ---------------------------------------------------------------------------
# Public result types
# ---------------------------------------------------------------------------


class BootstrapResult(BaseModel):
    """Result of a workspace bootstrap operation."""

    workspace_id: uuid.UUID
    workspace_name: str
    root_path: str
    manifest_path: str
    mode: str  # "manifest" | "heuristic" | "empty"
    datasets_discovered: int = 0
    files_discovered: int = 0
    conflicts: list[dict[str, Any]] = []
    missing_requirements: list[str] = []


class ProjectDetectionResult(BaseModel):
    """Result of heuristic project detection."""

    is_project: bool
    detection_mode: str  # "manifest" | "heuristic" | "none"
    manifest_path: str | None = None
    data_files: list[str] = []
    suggested_name: str | None = None


# ---------------------------------------------------------------------------
# WorkspaceBootstrapper
# ---------------------------------------------------------------------------


class WorkspaceBootstrapper:
    """Bootstraps a workspace from a folder on disk.

    Prefers manifest-driven startup (``workbench.project.yaml``), falls back
    to heuristic detection of data files, and creates a minimal manifest and
    database when neither is present.
    """

    def detect_project(self, folder: Path) -> ProjectDetectionResult:
        """Detect whether *folder* is a MoLabel project.

        Checks for a manifest file first, then scans for data files as a
        heuristic fallback.
        """
        manifest_file = folder / MANIFEST_FILENAME
        if manifest_file.is_file():
            return ProjectDetectionResult(
                is_project=True,
                detection_mode="manifest",
                manifest_path=str(manifest_file),
                suggested_name=folder.name,
            )

        data_files = self._scan_data_files(folder)
        if data_files:
            return ProjectDetectionResult(
                is_project=True,
                detection_mode="heuristic",
                data_files=[f.relative_to(folder).as_posix() for f in data_files],
                suggested_name=folder.name,
            )

        return ProjectDetectionResult(
            is_project=False,
            detection_mode="none",
        )

    def bootstrap(
        self,
        folder: Path,
        *,
        engine: Any,
        workspace_name: str | None = None,
    ) -> BootstrapResult:
        """Bootstrap a workspace rooted at *folder*.

        Parameters
        ----------
        folder:
            Absolute path to the workspace root directory.
        engine:
            The server database. A workspace has no database of its own; its
            rows live in the server database, keyed by workspace id.
        workspace_name:
            Optional override for the workspace display name.
        """
        folder = folder.resolve()
        detection = self.detect_project(folder)

        if detection.detection_mode == "manifest":
            return self._bootstrap_from_manifest(
                folder, engine, workspace_name=workspace_name
            )
        elif detection.detection_mode == "heuristic":
            return self._bootstrap_heuristic(
                folder,
                engine,
                detection.data_files,
                workspace_name=workspace_name,
            )
        else:
            return self._bootstrap_empty(folder, engine, workspace_name=workspace_name)

    # ------------------------------------------------------------------
    # Internal bootstrap modes
    # ------------------------------------------------------------------

    def _bootstrap_from_manifest(
        self,
        folder: Path,
        engine: Any,
        *,
        workspace_name: str | None = None,
    ) -> BootstrapResult:
        manifest_path = folder / MANIFEST_FILENAME
        manifest = load_manifest(manifest_path)
        conflicts = detect_conflicts(manifest, folder)

        ws_name = workspace_name or manifest.workspace_name
        ws_id = uuid.UUID(manifest.workspace_id)

        self._upsert_workspace(
            engine,
            ws_id=ws_id,
            ws_name=ws_name,
            root_path=str(folder),
            manifest_path=MANIFEST_FILENAME,
        )

        files_discovered = 0
        datasets_discovered = 0
        for ds_entry in manifest.datasets:
            self._upsert_dataset(
                engine,
                workspace_id=ws_id,
                dataset_id=ds_entry.dataset_id,
                source_paths=ds_entry.source_paths,
                loader_plugin=ds_entry.loader_plugin,
                record_kind=ds_entry.record_kind,
                canonical_id_strategy=ds_entry.canonical_id_strategy,
                indexing_mode=ds_entry.indexing_mode,
            )
            datasets_discovered += 1
            files_discovered += len(ds_entry.source_paths)

        missing = self._check_requirements(manifest)

        return BootstrapResult(
            workspace_id=ws_id,
            workspace_name=ws_name,
            root_path=str(folder),
            manifest_path=MANIFEST_FILENAME,
            mode="manifest",
            datasets_discovered=datasets_discovered,
            files_discovered=files_discovered,
            conflicts=[
                {
                    "type": c.conflict_type.value,
                    "entity_type": c.entity_type,
                    "entity_id": c.entity_id,
                    "message": c.message,
                }
                for c in conflicts
            ],
            missing_requirements=missing,
        )

    def _bootstrap_heuristic(
        self,
        folder: Path,
        engine: Any,
        data_files: list[str],
        *,
        workspace_name: str | None = None,
    ) -> BootstrapResult:
        ws_id = uuid.uuid4()
        ws_name = workspace_name or folder.name

        # Group files by parent directory as candidate datasets.
        datasets: dict[str, list[str]] = {}
        for rel_path in data_files:
            parent = str(Path(rel_path).parent)
            ds_key = parent if parent != "." else "default"
            datasets.setdefault(ds_key, []).append(rel_path)

        # Create and save a manifest.
        from molabel.core.manifest import DatasetManifestEntry

        ds_entries = []
        for ds_name, paths in datasets.items():
            ds_entries.append(
                DatasetManifestEntry(
                    dataset_id=ds_name,
                    source_paths=paths,
                )
            )

        manifest = WorkspaceManifest(
            workspace_id=str(ws_id),
            workspace_name=ws_name,
            core_version=_CORE_VERSION,
            datasets=ds_entries,
        )
        manifest_path = folder / MANIFEST_FILENAME
        save_manifest(manifest, manifest_path)

        self._upsert_workspace(
            engine,
            ws_id=ws_id,
            ws_name=ws_name,
            root_path=str(folder),
            manifest_path=MANIFEST_FILENAME,
        )

        for ds_entry in ds_entries:
            self._upsert_dataset(
                engine,
                workspace_id=ws_id,
                dataset_id=ds_entry.dataset_id,
                source_paths=ds_entry.source_paths,
                canonical_id_strategy=ds_entry.canonical_id_strategy,
                indexing_mode=ds_entry.indexing_mode,
            )

        return BootstrapResult(
            workspace_id=ws_id,
            workspace_name=ws_name,
            root_path=str(folder),
            manifest_path=MANIFEST_FILENAME,
            mode="heuristic",
            datasets_discovered=len(datasets),
            files_discovered=len(data_files),
        )

    def _bootstrap_empty(
        self,
        folder: Path,
        engine: Any,
        *,
        workspace_name: str | None = None,
    ) -> BootstrapResult:
        ws_id = uuid.uuid4()
        ws_name = workspace_name or folder.name

        manifest = WorkspaceManifest(
            workspace_id=str(ws_id),
            workspace_name=ws_name,
            core_version=_CORE_VERSION,
        )
        manifest_path = folder / MANIFEST_FILENAME
        save_manifest(manifest, manifest_path)

        self._upsert_workspace(
            engine,
            ws_id=ws_id,
            ws_name=ws_name,
            root_path=str(folder),
            manifest_path=MANIFEST_FILENAME,
        )

        return BootstrapResult(
            workspace_id=ws_id,
            workspace_name=ws_name,
            root_path=str(folder),
            manifest_path=MANIFEST_FILENAME,
            mode="empty",
        )

    # ------------------------------------------------------------------
    # Database helpers
    # ------------------------------------------------------------------

    def _upsert_workspace(
        self,
        engine: Any,
        *,
        ws_id: uuid.UUID,
        ws_name: str,
        root_path: str,
        manifest_path: str,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO workspaces "
                    "(id, workspace_name, workspace_slug, core_version, root_path, "
                    "manifest_path, created_at, updated_at) "
                    "VALUES (:id, :name, :slug, :version, :root_path, :manifest, "
                    ":now, :now) "
                    "ON CONFLICT(id) DO UPDATE SET "
                    "workspace_name = excluded.workspace_name, "
                    "root_path = excluded.root_path, "
                    "manifest_path = excluded.manifest_path, "
                    "updated_at = excluded.updated_at"
                ),
                {
                    "id": str(ws_id),
                    "name": ws_name,
                    "slug": _slugify(ws_name),
                    "version": _CORE_VERSION,
                    "root_path": root_path,
                    "manifest": manifest_path,
                    "now": now,
                },
            )

    def _upsert_dataset(
        self,
        engine: Any,
        *,
        workspace_id: uuid.UUID,
        dataset_id: str,
        source_paths: list[str],
        loader_plugin: str | None = None,
        record_kind: str | None = None,
        canonical_id_strategy: str = "source_record_id",
        indexing_mode: str = "projection",
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with engine.begin() as conn:
            existing = conn.execute(
                text(
                    "SELECT id FROM datasets "
                    "WHERE workspace_id = :wid AND dataset_slug = :slug"
                ),
                {"wid": str(workspace_id), "slug": dataset_id},
            ).first()
            if existing is not None:
                conn.execute(
                    text(
                        "UPDATE datasets SET updated_at = :now, "
                        "health_status = :health WHERE id = :id"
                    ),
                    {
                        "now": now,
                        "health": DatasetHealthStatus.stale.value,
                        "id": str(existing[0]),
                    },
                )
                return
            conn.execute(
                text(
                    "INSERT INTO datasets "
                    "(id, dataset_name, dataset_slug, workspace_id, source_type, "
                    "source_config, loader_plugin, record_kind, "
                    "canonical_id_strategy, indexing_mode, health_status, "
                    "created_at, updated_at) "
                    "VALUES (:id, :slug, :slug, :wid, 'local_file', :config, "
                    ":loader, :kind, :cid_strategy, :idx_mode, :health, :now, :now)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "slug": dataset_id,
                    "wid": str(workspace_id),
                    "config": json.dumps({"paths": source_paths}),
                    "loader": loader_plugin,
                    "kind": record_kind,
                    "cid_strategy": canonical_id_strategy,
                    "idx_mode": indexing_mode,
                    "health": DatasetHealthStatus.stale.value,
                    "now": now,
                },
            )

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _scan_data_files(self, folder: Path) -> list[Path]:
        """Scan *folder* (non-recursively into first level) for data files."""
        results: list[Path] = []
        if not folder.is_dir():
            return results
        for item in sorted(folder.iterdir()):
            if item.is_file() and item.suffix.lower() in DATA_FILE_EXTENSIONS:
                results.append(item)
            elif item.is_dir() and not item.name.startswith("."):
                for child in sorted(item.iterdir()):
                    if child.is_file() and child.suffix.lower() in DATA_FILE_EXTENSIONS:
                        results.append(child)
        return results

    @staticmethod
    def _check_requirements(manifest: WorkspaceManifest) -> list[str]:
        """Check for missing optional requirements based on manifest content."""
        missing: list[str] = []
        for ds in manifest.datasets:
            for sp in ds.source_paths:
                if sp.endswith(".parquet"):
                    try:
                        import pyarrow  # noqa: F401
                    except ImportError:
                        if "pyarrow (for Parquet files)" not in missing:
                            missing.append("pyarrow (for Parquet files)")
        return missing


def _slugify(name: str) -> str:
    """Create a URL-safe slug from a workspace name."""
    import re

    slug = re.sub(r"[^\w\s-]", "", name.lower())
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug.strip("-")[:64]

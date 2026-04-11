"""Workspace manifest contract (DM-033, DM-034).

Parses and writes ``workbench.project.yaml`` files, and detects conflicts
between the on-disk manifest and workspace state.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel
from pydantic import Field as PydanticField

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Manifest sub-models
# ---------------------------------------------------------------------------


class DatasetManifestEntry(BaseModel):
    """A dataset declaration within the workspace manifest."""

    dataset_id: str
    source_paths: list[str] = PydanticField(default_factory=list)
    loader_plugin: str | None = None
    record_kind: str | None = None
    canonical_id_strategy: str = "source_record_id"
    indexing_mode: str = "projection"


class TaskSchemaManifestEntry(BaseModel):
    """A task schema reference within the workspace manifest."""

    task_schema_id: str
    task_type_plugin: str | None = None
    definition_path: str | None = None


# ---------------------------------------------------------------------------
# WorkspaceManifest
# ---------------------------------------------------------------------------


class WorkspaceManifest(BaseModel):
    """Top-level Pydantic model for ``workbench.project.yaml``."""

    workspace_id: str
    workspace_name: str
    core_version: str
    enabled_plugins: list[str] = PydanticField(default_factory=list)
    datasets: list[DatasetManifestEntry] = PydanticField(default_factory=list)
    task_schemas: list[TaskSchemaManifestEntry] = PydanticField(default_factory=list)
    export_targets: list[dict[str, Any]] = PydanticField(default_factory=list)
    validation_gates: list[dict[str, Any]] = PydanticField(default_factory=list)


# ---------------------------------------------------------------------------
# Load / Save
# ---------------------------------------------------------------------------


def load_manifest(path: Path) -> WorkspaceManifest:
    """Parse a ``workbench.project.yaml`` file into a *WorkspaceManifest*.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    yaml.YAMLError
        If the file cannot be parsed as valid YAML.
    pydantic.ValidationError
        If the parsed YAML does not conform to the manifest schema.
    """
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if data is None:
        data = {}
    return WorkspaceManifest.model_validate(data)


def save_manifest(manifest: WorkspaceManifest, path: Path) -> None:
    """Write a *WorkspaceManifest* to *path* as YAML.

    Uses ``default_flow_style=False`` and ``sort_keys=False`` so the
    output matches the human-authored fixture style.
    """
    data = manifest.model_dump(mode="json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------


class ConflictType(StrEnum):
    """Categories of manifest-vs-workspace conflicts."""

    file_changed_on_disk = "file_changed_on_disk"
    file_deleted = "file_deleted"
    plugin_unavailable = "plugin_unavailable"
    schema_mismatch = "schema_mismatch"
    db_draft_modified_elsewhere = "db_draft_modified_elsewhere"


@dataclass
class ManifestConflict:
    """A single detected conflict between manifest and workspace state."""

    conflict_type: ConflictType
    entity_type: str
    entity_id: str
    message: str
    detected_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def detect_conflicts(
    manifest: WorkspaceManifest,
    workspace_path: Path,
) -> list[ManifestConflict]:
    """Run basic conflict checks between *manifest* and files on disk.

    Checks performed:

    1. **Dataset source files** -- verifies each ``source_paths`` entry exists
       relative to *workspace_path*.
    2. **Task schema definition files** -- verifies each ``definition_path``
       exists relative to *workspace_path*.
    3. **Plugin availability** -- verifies enabled plugins can be imported.

    Returns a (possibly empty) list of :class:`ManifestConflict` instances.
    """
    conflicts: list[ManifestConflict] = []

    # 1. Dataset source file existence
    for ds in manifest.datasets:
        for src in ds.source_paths:
            full = workspace_path / src
            if not full.exists():
                conflicts.append(
                    ManifestConflict(
                        conflict_type=ConflictType.file_deleted,
                        entity_type="dataset",
                        entity_id=ds.dataset_id,
                        message=f"Source path does not exist: {src}",
                    )
                )

    # 2. Task schema definition file existence
    for ts in manifest.task_schemas:
        if ts.definition_path:
            full = workspace_path / ts.definition_path
            if not full.exists():
                conflicts.append(
                    ManifestConflict(
                        conflict_type=ConflictType.file_deleted,
                        entity_type="task_schema",
                        entity_id=ts.task_schema_id,
                        message=(
                            f"Definition path does not exist: {ts.definition_path}"
                        ),
                    )
                )

    # 3. Plugin availability (canonical plugin ID / capability checks)
    available_plugins: set[str] = set()
    available_loaders: set[str] = set()
    available_task_types: set[str] = set()
    try:
        from molabel.core.plugins.discovery import discover_plugins
        from molabel.core.plugins.registry import PluginRegistry

        registry = discover_plugins(PluginRegistry())
        available_plugins = set(registry.list_plugin_ids())
        available_loaders = set(registry.list_data_loaders())
        available_task_types = set(registry.list_task_types())
    except Exception:
        logger.exception("Failed to discover plugins during manifest validation")

    for plugin_id in manifest.enabled_plugins:
        if plugin_id not in available_plugins:
            conflicts.append(
                ManifestConflict(
                    conflict_type=ConflictType.plugin_unavailable,
                    entity_type="plugin",
                    entity_id=plugin_id,
                    message=f"Plugin not found: {plugin_id}",
                )
            )

    for ds in manifest.datasets:
        if ds.loader_plugin and ds.loader_plugin not in available_loaders:
            conflicts.append(
                ManifestConflict(
                    conflict_type=ConflictType.plugin_unavailable,
                    entity_type="dataset_loader",
                    entity_id=ds.dataset_id,
                    message=f"Loader plugin not found: {ds.loader_plugin}",
                )
            )

    for ts in manifest.task_schemas:
        if ts.task_type_plugin and ts.task_type_plugin not in available_task_types:
            conflicts.append(
                ManifestConflict(
                    conflict_type=ConflictType.plugin_unavailable,
                    entity_type="task_type",
                    entity_id=ts.task_schema_id,
                    message=f"Task-type plugin not found: {ts.task_type_plugin}",
                )
            )

    return conflicts

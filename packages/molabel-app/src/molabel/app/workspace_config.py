"""Config files in the workspace folder, and the manifest that lists them.

Task schemas, prompts and workflows are YAML files in the workspace folder,
listed in ``workbench.project.yaml``. Their database rows are an index of
those files. API creates and updates write the file in the same request, and
``workspace bootstrap`` rewrites the rows from the files, so the file wins
when the two disagree. Datasets are listed in the manifest too; their
imported records are review state and live only in the database.
"""

from __future__ import annotations

import os
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from fastapi import HTTPException
from sqlalchemy import text

from molabel.app.workspace_paths import WorkspacePathError, resolve_in_workspace
from molabel.core.manifest import (
    DatasetManifestEntry,
    PromptManifestEntry,
    TaskSchemaManifestEntry,
    WorkflowManifestEntry,
    WorkspaceManifest,
    load_manifest,
    save_manifest,
)

MANIFEST_FILENAME = "workbench.project.yaml"
_CORE_VERSION = "0.1.0"
_manifest_lock = threading.Lock()


@dataclass(frozen=True)
class ConfigKind:
    """Where one kind of config file lives and how the manifest lists it."""

    directory: str
    manifest_list: str
    id_field: str
    entry: Callable[[str, str], Any]


TASK_SCHEMA = ConfigKind(
    directory="workbench/config/task-schemas",
    manifest_list="task_schemas",
    id_field="task_schema_id",
    entry=lambda slug, path: TaskSchemaManifestEntry(
        task_schema_id=slug, definition_path=path
    ),
)
PROMPT = ConfigKind(
    directory="workbench/prompts",
    manifest_list="prompts",
    id_field="prompt_id",
    entry=lambda slug, path: PromptManifestEntry(prompt_id=slug, definition_path=path),
)
WORKFLOW = ConfigKind(
    directory="workbench/workflows",
    manifest_list="workflows",
    id_field="workflow_id",
    entry=lambda slug, path: WorkflowManifestEntry(
        workflow_id=slug, definition_path=path
    ),
)


@dataclass(frozen=True)
class WorkspaceFolder:
    workspace_id: str
    name: str
    path: Path


def workspace_folder(engine, workspace_id: str) -> WorkspaceFolder:
    """The folder of workspace *workspace_id*, which must exist on disk."""
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT workspace_name, root_path FROM workspaces WHERE id = :id"),
            {"id": workspace_id},
        ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    root = Path(str(row[1] or "")).expanduser().resolve()
    if not row[1] or not root.is_dir():
        raise WorkspacePathError(
            409,
            "WORKSPACE_FOLDER_MISSING",
            "The workspace folder does not exist; bootstrap it first",
            str(row[1] or ""),
        )
    return WorkspaceFolder(workspace_id, str(row[0]), root)


def _write_atomically(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temp.write_text(content, encoding="utf-8")
    os.replace(temp, path)


def _update_manifest(
    folder: WorkspaceFolder, change: Callable[[WorkspaceManifest], None]
) -> None:
    path = folder.path / MANIFEST_FILENAME
    with _manifest_lock:
        manifest = (
            load_manifest(path)
            if path.is_file()
            else WorkspaceManifest(
                workspace_id=folder.workspace_id,
                workspace_name=folder.name,
                core_version=_CORE_VERSION,
            )
        )
        change(manifest)
        save_manifest(manifest, path)


def write_config(
    folder: WorkspaceFolder,
    kind: ConfigKind,
    *,
    slug: str,
    document: dict[str, Any],
    file_path: str | None,
    overwrite: bool,
) -> str:
    """Write *document* as the file for *slug* and list it in the manifest.

    With ``overwrite=False`` an existing file is left as it is: it is the
    source, and the caller is registering it. Returns the path relative to
    the workspace folder.
    """
    target = resolve_in_workspace(
        folder.path, file_path or f"{kind.directory}/{slug}.yaml"
    )
    if overwrite or not target.exists():
        _write_atomically(
            target, yaml.safe_dump(document, sort_keys=False, allow_unicode=True)
        )
    relative = target.relative_to(folder.path).as_posix()

    def list_file(manifest: WorkspaceManifest) -> None:
        entries = getattr(manifest, kind.manifest_list)
        kept = [e for e in entries if getattr(e, kind.id_field) != slug]
        setattr(manifest, kind.manifest_list, [*kept, kind.entry(slug, relative)])

    _update_manifest(folder, list_file)
    return relative


def list_dataset(folder: WorkspaceFolder, entry: DatasetManifestEntry) -> None:
    """Add or replace the manifest entry for a dataset."""

    def list_entry(manifest: WorkspaceManifest) -> None:
        kept = [d for d in manifest.datasets if d.dataset_id != entry.dataset_id]
        manifest.datasets = [*kept, entry]

    _update_manifest(folder, list_entry)


def add_dataset_source(folder: WorkspaceFolder, dataset_id: str, path: str) -> None:
    """Record that *path*, relative to the workspace, was imported into a dataset."""

    def add_source(manifest: WorkspaceManifest) -> None:
        entry = next((d for d in manifest.datasets if d.dataset_id == dataset_id), None)
        if entry is None:
            manifest.datasets.append(
                DatasetManifestEntry(dataset_id=dataset_id, source_paths=[path])
            )
        elif path not in entry.source_paths:
            entry.source_paths.append(path)

    _update_manifest(folder, add_source)


def read_config(folder: WorkspaceFolder, definition_path: str) -> dict[str, Any]:
    """Parse a listed config file into a mapping."""
    path = resolve_in_workspace(folder.path, definition_path)
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{definition_path} does not contain a mapping")
    return loaded

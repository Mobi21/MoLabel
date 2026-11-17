"""Config files in the workspace folder, and the manifest that lists them.

Task schemas, prompts and workflows are YAML files in the workspace folder,
listed in ``workbench.project.yaml``. Their database rows are an index of
those files. API creates and updates write the file, the manifest and the
row as one unit (see ``workspace_files``), and ``workspace bootstrap``
rewrites the rows from the files, so the file wins when the two disagree.
Datasets are listed in the manifest too; their imported records are review
state and live only in the database.
"""

from __future__ import annotations

import errno
import os
import stat
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from fastapi import HTTPException
from filelock import FileLock
from sqlalchemy import text

from molabel.app.workspace_paths import (
    WorkspacePathError,
    require_portable,
    resolve_in_workspace,
)
from molabel.core.gold.model import (
    GOLD_DIRECTORY,
    HEADER_FILENAME,
    ITEMS_FILENAME,
)
from molabel.core.manifest import (
    DatasetManifestEntry,
    GoldSetManifestEntry,
    PromptManifestEntry,
    TaskSchemaManifestEntry,
    WorkflowManifestEntry,
    WorkspaceManifest,
    dump_manifest,
    load_manifest,
)
from molabel.core.utils.round_trip_yaml import dump_yaml

MANIFEST_FILENAME = "workbench.project.yaml"
_CORE_VERSION = "0.1.0"


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


WORKSPACE_STATE_DIR = ".molabel"
_IGNORE_ALL = b"*\n"


def _state_path(root: Path, *names: str) -> Path:
    """``.molabel/`` or a path in it, refused when a link leads out of *root*."""
    return resolve_in_workspace(root, "/".join((WORKSPACE_STATE_DIR, *names)))


def _state_dir(root: Path, name: str) -> Path:
    """The folder ``.molabel/<name>/`` in the workspace at *root*, created.

    ``.molabel/`` ignores itself in git. Its ``.gitignore`` is rewritten
    whenever it does not hold exactly ``*``, so a write cut short is
    repaired by the next one.
    """
    _state_path(root).mkdir(parents=True, exist_ok=True)
    ignore = _state_path(root, ".gitignore")
    if not (ignore.is_file() and ignore.read_bytes() == _IGNORE_ALL):
        temp = _state_path(root, f".gitignore.{uuid.uuid4().hex}.tmp")
        _write_atomically(ignore, _IGNORE_ALL, temp)
    folder = _state_path(root, name)
    folder.mkdir(exist_ok=True)
    return folder


def _write_atomically(path: Path, content: str | bytes, temp: Path) -> None:
    """Replace *path* with *content*, refusing a file its owner made read-only.

    The content goes to *temp*, on *path*'s filesystem, and moves into place,
    so a process killed partway leaves nothing beside *path*.
    """
    if path.exists() and not path.stat().st_mode & stat.S_IWUSR:
        raise PermissionError(errno.EACCES, "The file is read-only", str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if isinstance(content, str):
            temp.write_text(content, encoding="utf-8")
        else:
            temp.write_bytes(content)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _text_or_none(path: Path) -> str | None:
    return path.read_text(encoding="utf-8") if path.is_file() else None


def _replaced(entries: list[Any], entry: Any, id_field: str) -> list[Any]:
    """*entries* with *entry* where its id first appears, so the file keeps order.

    *entry* keeps the undeclared keys of the entry it replaces, which a person
    added by hand.
    """
    key = getattr(entry, id_field)
    ids = [getattr(e, id_field) for e in entries]
    if key in ids:
        index = ids.index(key)
        entry = entry.model_copy(update=entries[index].model_extra)
    else:
        index = len(entries)
    kept = [e for e, id_ in zip(entries, ids, strict=True) if id_ != key]
    return [*kept[:index], entry, *kept[index:]]


class WorkspaceFiles:
    """The config files and manifest that one request writes in a workspace."""

    def __init__(self, folder: WorkspaceFolder) -> None:
        self.folder = folder
        self._originals: dict[Path, bytes | None] = {}
        _state_dir(folder.path, "tmp")

    def write_config(
        self,
        kind: ConfigKind,
        *,
        slug: str,
        document: dict[str, Any],
        file_path: str | None,
        overwrite: bool,
    ) -> str:
        """Write *document* as the file for *slug* and list it in the manifest.

        With ``overwrite=False`` an existing file is left as it is: it is the
        source, and the caller is registering it. Returns the path relative
        to the workspace folder.
        """
        target = self._target(file_path or f"{kind.directory}/{slug}.yaml")
        if overwrite or not target.exists():
            self._write(target, dump_yaml(document, _text_or_none(target)))
        relative = target.relative_to(self.folder.path).as_posix()

        def list_file(manifest: WorkspaceManifest) -> None:
            entries = getattr(manifest, kind.manifest_list)
            setattr(
                manifest,
                kind.manifest_list,
                _replaced(entries, kind.entry(slug, relative), kind.id_field),
            )

        self._update_manifest(list_file)
        return relative

    def list_dataset(self, entry: DatasetManifestEntry) -> None:
        """Add or replace the manifest entry for a dataset."""

        def list_entry(manifest: WorkspaceManifest) -> None:
            manifest.datasets = _replaced(manifest.datasets, entry, "dataset_id")

        self._update_manifest(list_entry)

    def add_dataset_source(self, dataset_id: str, path: str) -> None:
        """Record that *path*, relative to the workspace, was imported."""

        def add_source(manifest: WorkspaceManifest) -> None:
            entry = next(
                (d for d in manifest.datasets if d.dataset_id == dataset_id), None
            )
            if entry is None:
                manifest.datasets.append(
                    DatasetManifestEntry(dataset_id=dataset_id, source_paths=[path])
                )
            elif path not in entry.source_paths:
                entry.source_paths.append(path)

        self._update_manifest(add_source)

    def write_gold_set(
        self,
        slug: str,
        *,
        header: dict[str, Any],
        items: bytes,
        definition_path: str | None,
    ) -> str:
        """Write a gold set's items and header and list the set in the manifest.

        The header keeps the comments and layout of the one it replaces, and
        both files end lines with LF. Returns the header's path relative to
        the workspace folder.

        The items go first, so the header's ``content_hash`` and
        ``item_count`` always describe a file already on disk. A process
        killed between the two leaves a header that names the previous file,
        which every read reports as ``content_hash_matches: false``.
        """
        header_path = self._target(
            definition_path or f"{GOLD_DIRECTORY}/{slug}/{HEADER_FILENAME}"
        )
        relative = header_path.relative_to(self.folder.path).as_posix()
        items_path = resolve_in_workspace(
            self.folder.path, f"{header_path.parent.as_posix()}/{ITEMS_FILENAME}"
        )
        self._write(items_path, items)
        self._write(
            header_path, dump_yaml(header, _text_or_none(header_path)).encode("utf-8")
        )

        def list_set(manifest: WorkspaceManifest) -> None:
            manifest.gold_sets = _replaced(
                manifest.gold_sets,
                GoldSetManifestEntry(gold_set_id=slug, definition_path=relative),
                "gold_set_id",
            )

        self._update_manifest(list_set)
        return relative

    def write_file(self, relative: str, content: bytes) -> str:
        """Write a generated file, such as an export, inside the workspace."""
        path = self._target(relative)
        self._write(path, content)
        return path.relative_to(self.folder.path).as_posix()

    def _target(self, raw: str) -> Path:
        """Where *raw* is in the workspace, checked before anything touches it."""
        require_portable(self.folder.path, raw)
        return resolve_in_workspace(self.folder.path, raw)

    def _update_manifest(self, change: Callable[[WorkspaceManifest], None]) -> None:
        path = resolve_in_workspace(self.folder.path, MANIFEST_FILENAME)
        previous = _text_or_none(path)
        manifest = (
            load_manifest(path)
            if previous is not None
            else WorkspaceManifest(
                workspace_id=self.folder.workspace_id,
                workspace_name=self.folder.name,
                core_version=_CORE_VERSION,
            )
        )
        change(manifest)
        self._write(path, dump_manifest(manifest, previous))

    def _temp_for(self, path: Path) -> Path:
        """A new file in ``.molabel/tmp/`` to stage *path*'s content in."""
        return _state_path(
            self.folder.path, "tmp", f"{path.name}.{uuid.uuid4().hex}.tmp"
        )

    def _write(self, path: Path, content: str | bytes) -> None:
        original = path.read_bytes() if path.exists() else None
        try:
            _write_atomically(path, content, self._temp_for(path))
        except OSError as exc:
            relative = path.relative_to(self.folder.path).as_posix()
            raise WorkspacePathError(
                409,
                "WORKSPACE_FILE_NOT_WRITABLE",
                f"Cannot write {relative}: {exc.strerror or exc}",
                relative,
            ) from exc
        self._originals.setdefault(path, original)

    def _restore(self) -> None:
        for path, original in reversed(self._originals.items()):
            if original is None:
                path.unlink(missing_ok=True)
            else:
                _write_atomically(path, original, self._temp_for(path))


def workspace_lock(root: Path) -> FileLock:
    """The OS-level lock every writer of files in the workspace at *root* holds.

    Take it before any database write, so writers wait for each other in one
    order and a rollback in ``workspace_files`` can only undo its own writes.
    The lock file lives in the workspace, so every writer shares it whatever
    its data directory, under ``.molabel/``, which ignores itself in git.
    """
    _state_dir(root, "locks")
    return FileLock(_state_path(root, "locks", "workspace.lock"))


@contextmanager
def workspace_files(folder: WorkspaceFolder) -> Iterator[WorkspaceFiles]:
    """Write config files and commit their rows as one unit.

    Holds ``workspace_lock``, so other writers, in this server process or
    another, wait their turn. Commit the database inside the block, as its
    last step: if anything in the block raises, every file it wrote gets its
    old content back, or is removed if it is new.
    """
    with workspace_lock(folder.path):
        files = WorkspaceFiles(folder)
        try:
            yield files
        except BaseException:
            files._restore()
            raise


def read_config(folder: WorkspaceFolder, definition_path: str) -> dict[str, Any]:
    """Parse a listed config file into a mapping."""
    path = resolve_in_workspace(folder.path, definition_path)
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{definition_path} does not contain a mapping")
    return loaded

"""CLI selector resolution and artifact read/write endpoints."""

from __future__ import annotations

import difflib
import hashlib
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from molabel.app.api.v1.cli.deps import CurrentCliReviewer
from molabel.app.utils import get_engine
from molabel.core.export.atomic_writer import AtomicWriter

router = APIRouter(prefix="", tags=["cli"])

ArtifactKind = Literal[
    "workspace_manifest",
    "workflow",
    "prompt",
    "task_schema",
]

SelectorKind = Literal[
    "workspace",
    "workspace_manifest",
    "dataset",
    "workflow",
    "prompt",
    "task_schema",
    "snapshot",
]


class SelectorResolveRequest(BaseModel):
    kind: SelectorKind
    selector: str
    workspace_id: str | None = None
    workspace_root: str | None = None


class SelectorResolveResponse(BaseModel):
    kind: SelectorKind
    selector: str
    resolved: bool = False
    resolved_id: str | None = None
    resolved_path: str | None = None
    display_name: str | None = None
    version: str | None = None
    workspace_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactReadRequest(BaseModel):
    kind: ArtifactKind
    selector: str
    workspace_id: str | None = None
    workspace_root: str | None = None


class ArtifactReadResponse(BaseModel):
    kind: ArtifactKind
    selector: str
    resolved_path: str
    exists: bool
    content: str | None = None
    content_hash: str | None = None
    file_size_bytes: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactDiffRequest(BaseModel):
    kind: ArtifactKind
    selector: str
    content: str
    workspace_id: str | None = None
    workspace_root: str | None = None
    expected_hash: str | None = None


class ArtifactDiffResponse(BaseModel):
    kind: ArtifactKind
    selector: str
    resolved_path: str
    current_hash: str | None = None
    new_hash: str
    has_conflict: bool
    diff: str


class ArtifactWriteRequest(BaseModel):
    kind: ArtifactKind
    selector: str
    content: str
    workspace_id: str | None = None
    workspace_root: str | None = None
    expected_hash: str | None = None


class ArtifactWriteResponse(BaseModel):
    kind: ArtifactKind
    selector: str
    resolved_path: str
    success: bool
    content_hash: str
    file_size_bytes: int
    previous_path: str | None = None


def _workspace_root_from_request(workspace_root: str | None) -> Path:
    if workspace_root is not None:
        return Path(workspace_root).expanduser().resolve()
    return Path.cwd().resolve()


def _hash_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _hash_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ensure_within_root(root: Path, candidate: Path) -> Path:
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise HTTPException(status_code=400, detail="Resolved path escapes workspace")
    return resolved


def _query_one(engine: Any, sql: str, params: dict[str, Any]) -> Any | None:
    with engine.connect() as conn:
        return conn.execute(text(sql), params).first()


def _resolve_db_artifact(
    request: Request,
    *,
    kind: ArtifactKind,
    selector: str,
    workspace_id: str | None,
) -> tuple[str, Path, dict[str, Any]]:
    engine = get_engine(request)
    if kind == "workspace_manifest":
        if workspace_id is None:
            row = _query_one(
                engine,
                (
                    "SELECT id, workspace_name, root_path, manifest_path "
                    "FROM workspaces "
                    "WHERE root_path = :selector "
                    "OR workspace_name = :selector "
                    "OR id = :selector LIMIT 1"
                ),
                {"selector": selector},
            )
        else:
            row = _query_one(
                engine,
                "SELECT id, workspace_name, root_path, manifest_path "
                "FROM workspaces WHERE id = :wid LIMIT 1",
                {"wid": workspace_id},
            )
        if row is None:
            raise HTTPException(status_code=404, detail="Workspace not found")
        root = Path(str(row[2])).expanduser().resolve()
        manifest = Path(str(row[3] or "workbench.project.yaml"))
        if not manifest.is_absolute():
            manifest = root / manifest
        path = _ensure_within_root(root, manifest)
        return str(row[0]), path, {"workspace_name": str(row[1])}

    if kind == "dataset":
        sql = (
            "SELECT id, dataset_slug, NULL, dataset_name, NULL, NULL "
            "FROM datasets "
            "WHERE (id = :selector "
            "OR dataset_slug = :selector "
            "OR dataset_name = :selector)"
        )
        params: dict[str, Any] = {"selector": selector}
        if workspace_id is not None:
            sql += " AND workspace_id = :workspace_id"
            params["workspace_id"] = workspace_id
        row = _query_one(engine, sql + " LIMIT 1", params)
        if row is None:
            raise HTTPException(status_code=404, detail="dataset not found")
        return str(row[0]), Path("."), {"slug": str(row[1]), "label": str(row[3])}

    if kind == "snapshot":
        sql = (
            "SELECT dataset_snapshots.id, NULL, NULL, dataset_snapshots.name, "
            "workspaces.root_path, NULL "
            "FROM dataset_snapshots "
            "JOIN workspaces ON workspaces.id = dataset_snapshots.workspace_id "
            "WHERE (dataset_snapshots.id = :selector "
            "OR dataset_snapshots.name = :selector)"
        )
        params = {"selector": selector}
        if workspace_id is not None:
            sql += " AND dataset_snapshots.workspace_id = :workspace_id"
            params["workspace_id"] = workspace_id
        row = _query_one(engine, sql + " LIMIT 1", params)
        if row is None:
            raise HTTPException(status_code=404, detail="snapshot not found")
        root = Path(str(row[4])).expanduser().resolve()
        snapshot_path = root / "workbench" / "snapshots" / f"{row[0]}.json"
        return str(row[0]), snapshot_path, {"label": str(row[3])}

    table_map = {
        "workflow": ("workflow_definitions", "workflow_slug", "file_path", "name"),
        "prompt": ("prompt_templates", "prompt_slug", "file_path", "name"),
        "task_schema": ("task_schemas", "task_schema_slug", "file_path", "title"),
    }
    table, slug_column, file_column, label_column = table_map[kind]

    if kind == "workflow" or kind == "prompt":
        sql = (
            f"SELECT {table}.id, {table}.{slug_column}, {table}.{file_column}, "
            f"{table}.{label_column}, workspaces.root_path, {table}.version "
            f"FROM {table} JOIN workspaces ON workspaces.id = {table}.workspace_id "
            f"WHERE ({table}.id = :selector OR {table}.{slug_column} = :selector "
            f"OR {table}.name = :selector OR {table}.{file_column} = :selector)"
        )
        params = {"selector": selector}
        if workspace_id is not None:
            sql += f" AND {table}.workspace_id = :workspace_id"
            params["workspace_id"] = workspace_id
    else:
        sql = (
            f"SELECT {table}.id, {table}.{slug_column}, {table}.{file_column}, "
            f"{table}.{label_column}, workspaces.root_path, NULL "
            f"FROM {table} JOIN workspaces ON workspaces.id = {table}.workspace_id "
            f"WHERE ({table}.id = :selector OR {table}.{slug_column} = :selector "
            f"OR {table}.{file_column} = :selector)"
        )
        params = {"selector": selector}
        if workspace_id is not None:
            sql += f" AND {table}.workspace_id = :workspace_id"
            params["workspace_id"] = workspace_id

    row = _query_one(engine, sql + " LIMIT 1", params)
    if row is None:
        raise HTTPException(status_code=404, detail=f"{kind} not found")

    root = Path(str(row[4])).expanduser().resolve()
    file_path = str(row[2]) if row[2] else None
    if file_path is None:
        raise HTTPException(status_code=404, detail="Artifact file path unavailable")
    path = Path(file_path)
    if not path.is_absolute():
        path = root / path
    path = _ensure_within_root(root, path)
    metadata = {
        "slug": str(row[1]),
        "label": str(row[3]),
        "version": str(row[5]) if row[5] is not None else None,
    }
    return str(row[0]), path, metadata


def _resolve_artifact_path(
    request: Request,
    *,
    kind: ArtifactKind,
    selector: str,
    workspace_root: str | None,
    workspace_id: str | None,
) -> tuple[Path, dict[str, Any]]:
    if kind == "workspace_manifest":
        root = _workspace_root_from_request(workspace_root)
        return root / "workbench.project.yaml", {}

    try:
        _artifact_id, path, metadata = _resolve_db_artifact(
            request,
            kind=kind,
            selector=selector,
            workspace_id=workspace_id,
        )
        return path, metadata
    except HTTPException:
        root = _workspace_root_from_request(workspace_root)
        candidate = Path(selector)
        if not candidate.is_absolute():
            candidate = root / candidate
        if not candidate.exists():
            raise
        return _ensure_within_root(root, candidate), {}


@router.post("/selectors/resolve", response_model=SelectorResolveResponse)
async def resolve_selector(
    request: Request,
    body: SelectorResolveRequest,
) -> SelectorResolveResponse:
    """Resolve a CLI selector into a concrete path or database id."""
    if body.kind == "workspace":
        engine = get_engine(request)
        row = _query_one(
            engine,
            "SELECT id, workspace_name, root_path, manifest_path "
            "FROM workspaces WHERE id = :selector OR workspace_name = :selector "
            "OR root_path = :selector LIMIT 1",
            {"selector": body.selector},
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Workspace not found")
        return SelectorResolveResponse(
            kind=body.kind,
            selector=body.selector,
            resolved=True,
            resolved_id=str(row[0]),
            resolved_path=str(row[2]),
            display_name=str(row[1]),
            workspace_id=str(row[0]),
            metadata={"manifest_path": str(row[3])},
        )

    if body.kind == "workspace_manifest":
        root = _workspace_root_from_request(body.workspace_root)
        return SelectorResolveResponse(
            kind=body.kind,
            selector=body.selector,
            resolved=True,
            resolved_path=str(root / "workbench.project.yaml"),
            display_name="workspace manifest",
            workspace_id=body.workspace_id,
        )

    if body.kind == "dataset":
        engine = get_engine(request)
        sql = (
            "SELECT id, dataset_slug, dataset_name, workspace_id "
            "FROM datasets "
            "WHERE id = :selector "
            "OR dataset_slug = :selector "
            "OR dataset_name = :selector"
        )
        params: dict[str, Any] = {"selector": body.selector}
        if body.workspace_id is not None:
            sql += " AND workspace_id = :workspace_id"
            params["workspace_id"] = body.workspace_id
        row = _query_one(engine, sql + " LIMIT 1", params)
        if row is None:
            raise HTTPException(status_code=404, detail="dataset not found")
        return SelectorResolveResponse(
            kind=body.kind,
            selector=body.selector,
            resolved=True,
            resolved_id=str(row[0]),
            resolved_path=None,
            display_name=str(row[2]),
            workspace_id=str(row[3]),
            metadata={"slug": str(row[1])},
        )

    artifact_id, path, metadata = _resolve_db_artifact(
        request,
        kind=body.kind,  # type: ignore[arg-type]
        selector=body.selector,
        workspace_id=body.workspace_id,
    )
    return SelectorResolveResponse(
        kind=body.kind,
        selector=body.selector,
        resolved=True,
        resolved_id=artifact_id,
        resolved_path=str(path),
        workspace_id=body.workspace_id,
        display_name=metadata.get("label"),
        version=metadata.get("version"),
        metadata=metadata,
    )


@router.post("/artifacts/read", response_model=ArtifactReadResponse)
async def read_artifact(
    request: Request,
    body: ArtifactReadRequest,
) -> ArtifactReadResponse:
    """Read a canonical artifact as UTF-8 text."""
    path, metadata = _resolve_artifact_path(
        request,
        kind=body.kind,
        selector=body.selector,
        workspace_root=body.workspace_root,
        workspace_id=body.workspace_id,
    )
    if not path.exists():
        return ArtifactReadResponse(
            kind=body.kind,
            selector=body.selector,
            resolved_path=str(path),
            exists=False,
            metadata=metadata,
        )

    content = path.read_text(encoding="utf-8")
    return ArtifactReadResponse(
        kind=body.kind,
        selector=body.selector,
        resolved_path=str(path),
        exists=True,
        content=content,
        content_hash=_hash_file(path),
        file_size_bytes=path.stat().st_size,
        metadata=metadata,
    )


@router.post("/artifacts/diff", response_model=ArtifactDiffResponse)
async def diff_artifact(
    request: Request,
    body: ArtifactDiffRequest,
) -> ArtifactDiffResponse:
    """Diff proposed content against the current canonical artifact."""
    path, _metadata = _resolve_artifact_path(
        request,
        kind=body.kind,
        selector=body.selector,
        workspace_root=body.workspace_root,
        workspace_id=body.workspace_id,
    )
    current_content = path.read_text(encoding="utf-8") if path.exists() else ""
    current_hash = _hash_file(path)
    new_hash = _hash_text(body.content)
    has_conflict = (
        current_hash is not None
        and body.expected_hash is not None
        and current_hash != body.expected_hash
    )
    diff = "".join(
        difflib.unified_diff(
            current_content.splitlines(keepends=True),
            body.content.splitlines(keepends=True),
            fromfile=str(path),
            tofile=f"{path} (proposed)",
        )
    )
    return ArtifactDiffResponse(
        kind=body.kind,
        selector=body.selector,
        resolved_path=str(path),
        current_hash=current_hash,
        new_hash=new_hash,
        has_conflict=has_conflict,
        diff=diff,
    )


@router.post("/artifacts/write", response_model=ArtifactWriteResponse)
async def write_artifact(
    request: Request,
    body: ArtifactWriteRequest,
    _reviewer: CurrentCliReviewer,
) -> ArtifactWriteResponse:
    """Write canonical artifact content after an expected-hash check."""
    path, _metadata = _resolve_artifact_path(
        request,
        kind=body.kind,
        selector=body.selector,
        workspace_root=body.workspace_root,
        workspace_id=body.workspace_id,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    current_hash = _hash_file(path)
    if path.exists():
        if body.expected_hash is None:
            raise HTTPException(
                status_code=409,
                detail="expected_hash is required when overwriting an existing file",
            )
        if current_hash != body.expected_hash:
            raise HTTPException(
                status_code=409,
                detail="Artifact changed since it was read",
            )

    writer = AtomicWriter()
    result = writer.write_atomic(
        body.content.encode("utf-8"),
        path,
        skip_conflict_check=True,
    )
    if not result.success or result.final_path is None:
        raise HTTPException(
            status_code=500,
            detail=result.error or "Artifact write failed",
        )

    return ArtifactWriteResponse(
        kind=body.kind,
        selector=body.selector,
        resolved_path=str(result.final_path),
        success=True,
        content_hash=result.content_hash,
        file_size_bytes=result.file_size_bytes,
        previous_path=str(result.previous_path) if result.previous_path else None,
    )

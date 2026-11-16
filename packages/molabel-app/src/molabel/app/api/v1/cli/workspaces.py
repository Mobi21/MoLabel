"""CLI workspace lifecycle endpoints."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import text

from molabel.app.api.v1.prompts import index_prompt
from molabel.app.api.v1.task_schemas import index_task_schema
from molabel.app.api.v1.workflows import index_workflow
from molabel.app.server_state import (
    LegacyDatabase,
    launch_folder_database,
    legacy_databases,
)
from molabel.app.services.session import (
    AVATAR_COLORS,
    COOKIE_HTTPONLY,
    COOKIE_NAME,
    COOKIE_PATH,
    COOKIE_SAMESITE,
    COOKIE_SECURE,
    create_session_token,
)
from molabel.app.utils import get_engine
from molabel.app.workspace_config import (
    MANIFEST_FILENAME,
    PROMPT,
    TASK_SCHEMA,
    WORKFLOW,
    WorkspaceFolder,
    read_config,
)
from molabel.app.workspace_paths import (
    WorkspacePathError,
    new_workspace_root,
    resolve_in_workspace,
)
from molabel.core.data.workspace_bootstrap import WorkspaceBootstrapper
from molabel.core.manifest import load_manifest

router = APIRouter(prefix="", tags=["cli"])
logger = logging.getLogger(__name__)

_APP_VERSION = "0.1.0"
_CORE_VERSION = "0.1.0"


class ManifestConflict(BaseModel):
    conflict_type: str
    entity_type: str
    entity_id: str
    message: str


class CLIStatusResponse(BaseModel):
    ok: bool = True
    app_version: str = _APP_VERSION
    core_version: str = _CORE_VERSION
    workspace_detected: bool = False
    workspace_name: str | None = None
    workspace_root: str | None = None
    manifest_path: str | None = None
    detection_mode: str | None = None
    workspace_count: int = 0
    legacy_databases: list[LegacyDatabase] = Field(default_factory=list)
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class WorkspaceDetectRequest(BaseModel):
    path: str


class WorkspaceDetectResponse(BaseModel):
    is_project: bool
    detection_mode: str
    manifest_path: str | None = None
    data_files: list[str] = Field(default_factory=list)
    suggested_name: str | None = None


class WorkspaceBootstrapRequest(BaseModel):
    path: str
    workspace_name: str | None = None
    reviewer_name: str | None = None


class WorkspaceBootstrapResponse(BaseModel):
    workspace_id: str
    workspace_name: str
    root_path: str
    manifest_path: str
    mode: str
    datasets_discovered: int
    files_discovered: int
    conflicts: list[ManifestConflict] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    session_created: bool = False
    reviewer_id: str | None = None
    legacy_databases: list[LegacyDatabase] = Field(default_factory=list)


def _detect_workspace(path: Path) -> object:
    return WorkspaceBootstrapper().detect_project(path)


def _reindex_config_files(engine, folder: WorkspaceFolder) -> list[ManifestConflict]:
    """Rewrite the index rows of every listed config file from the file.

    Missing files are already reported by manifest conflict detection; a file
    that cannot be read as its kind is reported here and its row left alone.
    """
    manifest = load_manifest(resolve_in_workspace(folder.path, MANIFEST_FILENAME))
    listed = [
        (kind, entry, index)
        for kind, entries, index in (
            (TASK_SCHEMA, manifest.task_schemas, index_task_schema),
            (PROMPT, manifest.prompts, index_prompt),
            (WORKFLOW, manifest.workflows, index_workflow),
        )
        for entry in entries
    ]
    problems: list[ManifestConflict] = []
    with engine.begin() as conn:
        for kind, entry, index in listed:
            slug = getattr(entry, kind.id_field)
            path = entry.definition_path
            if not path:
                continue
            try:
                if not resolve_in_workspace(folder.path, path).is_file():
                    continue
                index(
                    conn,
                    workspace_id=folder.workspace_id,
                    slug=slug,
                    document=read_config(folder, path),
                    file_path=path,
                )
            except (ValueError, yaml.YAMLError, WorkspacePathError) as exc:
                problems.append(
                    ManifestConflict(
                        conflict_type="schema_mismatch",
                        entity_type=kind.id_field.removesuffix("_id"),
                        entity_id=slug,
                        message=f"{path} was not indexed: {exc}",
                    )
                )
    return problems


@router.get("/status", response_model=CLIStatusResponse)
async def status(
    request: Request,
    path: str | None = Query(default=None),
) -> CLIStatusResponse:
    """Return backend and workspace status for CLI callers."""
    engine = get_engine(request)
    with engine.connect() as conn:
        workspace_count_row = conn.execute(
            text("SELECT count(*) FROM workspaces")
        ).first()
    workspace_count = int(workspace_count_row[0]) if workspace_count_row else 0
    legacy = legacy_databases(engine, [launch_folder_database()])

    if path is None:
        return CLIStatusResponse(
            workspace_count=workspace_count, legacy_databases=legacy
        )

    workspace_path = new_workspace_root(path)
    if not workspace_path.exists():
        return CLIStatusResponse(
            workspace_count=workspace_count,
            legacy_databases=legacy,
            workspace_detected=False,
            workspace_root=str(workspace_path),
        )

    detection = _detect_workspace(workspace_path)
    return CLIStatusResponse(
        workspace_count=workspace_count,
        legacy_databases=legacy,
        workspace_detected=bool(detection.is_project),
        workspace_name=detection.suggested_name,
        workspace_root=str(workspace_path),
        manifest_path=detection.manifest_path,
        detection_mode=detection.detection_mode,
    )


@router.post("/workspaces/detect", response_model=WorkspaceDetectResponse)
async def detect_workspace(
    body: WorkspaceDetectRequest,
) -> WorkspaceDetectResponse:
    """Detect whether a path contains a MoLabel workspace."""
    workspace_path = new_workspace_root(body.path)
    if not workspace_path.exists():
        raise HTTPException(status_code=404, detail="Workspace path not found")

    detection = _detect_workspace(workspace_path)
    return WorkspaceDetectResponse(
        is_project=bool(detection.is_project),
        detection_mode=detection.detection_mode,
        manifest_path=detection.manifest_path,
        data_files=list(detection.data_files),
        suggested_name=detection.suggested_name,
    )


@router.post(
    "/workspaces/bootstrap",
    response_model=WorkspaceBootstrapResponse,
    status_code=201,
)
async def bootstrap_workspace(
    request: Request,
    response: Response,
    body: WorkspaceBootstrapRequest,
) -> WorkspaceBootstrapResponse:
    """Bootstrap a workspace from a local path."""
    workspace_path = new_workspace_root(body.path)
    workspace_path.mkdir(parents=True, exist_ok=True)
    # Refuse a manifest that links out of the folder before bootstrap reads it.
    resolve_in_workspace(workspace_path, MANIFEST_FILENAME)

    engine = get_engine(request)
    legacy = legacy_databases(
        engine,
        [
            launch_folder_database(),
            resolve_in_workspace(workspace_path, "workbench/molabel.db"),
        ],
    )
    for notice in legacy:
        logger.warning("LEGACY DATABASE NOT LOADED: %s", notice.message)
    result = WorkspaceBootstrapper().bootstrap(
        workspace_path,
        engine=engine,
        workspace_name=body.workspace_name,
    )
    index_problems = _reindex_config_files(
        engine,
        WorkspaceFolder(
            str(result.workspace_id), result.workspace_name, Path(result.root_path)
        ),
    )
    reviewer_id: uuid.UUID | None = None
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id FROM reviewer_profiles "
                "WHERE workspace_id = :workspace_id AND is_active = 1 "
                "ORDER BY created_at ASC LIMIT 1"
            ),
            {"workspace_id": str(result.workspace_id)},
        ).first()
        if row is not None:
            reviewer_id = uuid.UUID(str(row[0]))
        else:
            reviewer_id = uuid.uuid4()
            conn.execute(
                text(
                    "INSERT INTO reviewer_profiles "
                    "(id, display_name, avatar_color, is_operator, is_active, "
                    "workspace_id, created_at) "
                    "VALUES (:id, :display_name, :avatar_color, 1, 1, :workspace_id, "
                    ":created_at)"
                ),
                {
                    "id": str(reviewer_id),
                    "display_name": body.reviewer_name or "Reviewer 1",
                    "avatar_color": AVATAR_COLORS[0],
                    "workspace_id": str(result.workspace_id),
                    "created_at": datetime.now(UTC).isoformat(),
                },
            )
            conn.commit()

    if reviewer_id is not None:
        token = create_session_token(reviewer_id, request.app.state.app_secret)
        response.set_cookie(
            key=COOKIE_NAME,
            value=token,
            path=COOKIE_PATH,
            httponly=COOKIE_HTTPONLY,
            samesite=COOKIE_SAMESITE,
            secure=COOKIE_SECURE,
        )

    return WorkspaceBootstrapResponse(
        workspace_id=str(result.workspace_id),
        workspace_name=result.workspace_name,
        root_path=result.root_path,
        manifest_path=result.manifest_path,
        mode=result.mode,
        datasets_discovered=result.datasets_discovered,
        files_discovered=result.files_discovered,
        conflicts=[
            ManifestConflict(
                conflict_type=conflict["type"],
                entity_type=conflict["entity_type"],
                entity_id=conflict["entity_id"],
                message=conflict["message"],
            )
            for conflict in result.conflicts
        ]
        + index_problems,
        missing_requirements=list(result.missing_requirements),
        session_created=reviewer_id is not None,
        reviewer_id=str(reviewer_id) if reviewer_id is not None else None,
        legacy_databases=legacy,
    )

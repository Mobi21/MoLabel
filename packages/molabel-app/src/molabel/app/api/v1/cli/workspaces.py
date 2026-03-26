"""CLI workspace lifecycle endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import text

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
from molabel.core.data.workspace_bootstrap import WorkspaceBootstrapper

router = APIRouter(prefix="", tags=["cli"])

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


def _resolve_path(path: str) -> Path:
    return Path(path).expanduser().resolve()


def _detect_workspace(path: Path) -> object:
    return WorkspaceBootstrapper().detect_project(path)


def _upsert_workspace(
    request: Request,
    *,
    workspace_id: uuid.UUID,
    workspace_name: str,
    root_path: str,
    manifest_path: str,
) -> None:
    engine = get_engine(request)
    now = datetime.now(UTC).isoformat()
    slug = workspace_name.lower().replace(" ", "-")
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO workspaces "
                "(id, workspace_name, workspace_slug, core_version, root_path, "
                "manifest_path, created_at, updated_at) "
                "VALUES (:id, :name, :slug, :version, :root_path, :manifest, "
                ":now, :now) "
                "ON CONFLICT(id) DO UPDATE SET "
                "workspace_name = excluded.workspace_name, "
                "workspace_slug = excluded.workspace_slug, "
                "core_version = excluded.core_version, "
                "root_path = excluded.root_path, "
                "manifest_path = excluded.manifest_path, "
                "updated_at = excluded.updated_at"
            ),
            {
                "id": str(workspace_id),
                "name": workspace_name,
                "slug": slug,
                "version": _CORE_VERSION,
                "root_path": root_path,
                "manifest": manifest_path,
                "now": now,
            },
        )
        conn.commit()


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

    if path is None:
        return CLIStatusResponse(workspace_count=workspace_count)

    workspace_path = _resolve_path(path)
    if not workspace_path.exists():
        return CLIStatusResponse(
            workspace_count=workspace_count,
            workspace_detected=False,
            workspace_root=str(workspace_path),
        )

    detection = _detect_workspace(workspace_path)
    return CLIStatusResponse(
        workspace_count=workspace_count,
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
    workspace_path = _resolve_path(body.path)
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
    workspace_path = _resolve_path(body.path)
    workspace_path.mkdir(parents=True, exist_ok=True)

    result = WorkspaceBootstrapper().bootstrap(
        workspace_path,
        workspace_name=body.workspace_name,
    )
    _upsert_workspace(
        request,
        workspace_id=result.workspace_id,
        workspace_name=result.workspace_name,
        root_path=result.root_path,
        manifest_path=result.manifest_path,
    )

    engine = get_engine(request)
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
        ],
        missing_requirements=list(result.missing_requirements),
        session_created=reviewer_id is not None,
        reviewer_id=str(reviewer_id) if reviewer_id is not None else None,
    )

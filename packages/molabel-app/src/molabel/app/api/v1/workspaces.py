"""Workspace endpoints — /api/v1/workspaces.

CRUD for workspaces plus reindex trigger (API-003 through API-006).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import text

from molabel.app.middleware.session import CurrentReviewer
from molabel.app.schemas import PaginatedResponse, QueryParams
from molabel.app.services.session import (
    AVATAR_COLORS,
    COOKIE_HTTPONLY,
    COOKIE_NAME,
    COOKIE_PATH,
    COOKIE_SAMESITE,
    COOKIE_SECURE,
    create_session_token,
)
from molabel.app.utils import get_app_secret, get_engine

router = APIRouter(prefix="/workspaces", tags=["workspaces"])

# ---------------------------------------------------------------------------
# Response / request models
# ---------------------------------------------------------------------------


class HealthCheck(BaseModel):
    """Individual health check within a workspace."""

    name: str
    status: str  # "ok" | "warning" | "error"
    message: str | None = None
    checked_at: datetime


class WorkspaceSummary(BaseModel):
    """Workspace list item."""

    workspace_id: str
    workspace_name: str
    path: str
    core_version: str
    health: str  # "healthy" | "stale" | "error"
    dataset_count: int
    plugin_count: int
    last_indexed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class FirstReviewerInfo(BaseModel):
    """Auto-created reviewer returned on workspace creation."""

    id: uuid.UUID
    display_name: str
    avatar_color: str | None


class WorkspaceDetail(BaseModel):
    """Full workspace detail."""

    workspace_id: str
    workspace_name: str
    path: str
    core_version: str
    health: str
    health_checks: list[HealthCheck]
    enabled_plugins: list[str]
    dataset_count: int
    active_workflow_count: int
    pending_review_count: int
    active_agent_runs: int
    last_indexed_at: datetime | None = None
    manifest_path: str | None = None
    created_at: datetime
    updated_at: datetime
    # Only present in the POST /workspaces response (bootstrap).
    first_reviewer: FirstReviewerInfo | None = None


class WorkspaceCreate(BaseModel):
    """Request body for creating a workspace."""

    path: str
    workspace_name: str | None = None
    reviewer_name: str | None = None  # defaults to "Reviewer 1"
    template: str | None = None
    enabled_plugins: list[str] = []


class ReindexRequest(BaseModel):
    """Request body for triggering a reindex."""

    dataset_ids: list[str] | None = None
    force: bool = False


class ReindexStatus(BaseModel):
    """Status of an asynchronous reindex job."""

    job_id: str
    status: str
    started_at: datetime | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_summary(row: Any) -> WorkspaceSummary:
    """Convert a database row to a WorkspaceSummary."""
    return WorkspaceSummary(
        workspace_id=str(row[0]),
        workspace_name=str(row[1]),
        path=str(row[2]),
        core_version=str(row[3]),
        health="healthy",
        dataset_count=int(row[4]) if row[4] is not None else 0,
        plugin_count=0,
        last_indexed_at=None,
        created_at=datetime.fromisoformat(str(row[5])) if row[5] else datetime.now(UTC),
        updated_at=datetime.fromisoformat(str(row[6])) if row[6] else datetime.now(UTC),
    )


def _row_to_detail(row: Any, dataset_count: int) -> WorkspaceDetail:
    """Convert a database row to a WorkspaceDetail."""
    return WorkspaceDetail(
        workspace_id=str(row[0]),
        workspace_name=str(row[1]),
        path=str(row[2]),
        core_version=str(row[3]),
        health="healthy",
        health_checks=[
            HealthCheck(
                name="database",
                status="ok",
                message=None,
                checked_at=datetime.now(UTC),
            )
        ],
        enabled_plugins=[],
        dataset_count=dataset_count,
        active_workflow_count=0,
        pending_review_count=0,
        active_agent_runs=0,
        last_indexed_at=None,
        manifest_path=str(row[4]) if row[4] else None,
        created_at=datetime.fromisoformat(str(row[5])) if row[5] else datetime.now(UTC),
        updated_at=datetime.fromisoformat(str(row[6])) if row[6] else datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedResponse[WorkspaceSummary])
async def list_workspaces(
    request: Request,
    params: Annotated[QueryParams, Depends()],
) -> PaginatedResponse[WorkspaceSummary]:
    """List all known workspaces (API-003)."""
    engine = get_engine(request)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT w.id, w.workspace_name, w.root_path, w.core_version, "
                "(SELECT count(*) FROM datasets d WHERE d.workspace_id = w.id), "
                "w.created_at, w.updated_at "
                "FROM workspaces w "
                "ORDER BY w.created_at DESC "
                "LIMIT :limit"
            ),
            {"limit": params.limit},
        ).fetchall()

    items = [_row_to_summary(r) for r in rows]
    return PaginatedResponse(items=items, cursor=None, has_more=False)


@router.get("/{workspace_id}", response_model=WorkspaceDetail)
async def get_workspace(
    request: Request,
    workspace_id: uuid.UUID,
) -> WorkspaceDetail:
    """Get workspace detail (API-004)."""
    engine = get_engine(request)
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, workspace_name, root_path, core_version, "
                "manifest_path, created_at, updated_at "
                "FROM workspaces WHERE id = :id"
            ),
            {"id": str(workspace_id)},
        ).first()

        if row is None:
            raise HTTPException(status_code=404, detail="Workspace not found")

        ds_count_row = conn.execute(
            text("SELECT count(*) FROM datasets WHERE workspace_id = :wid"),
            {"wid": str(workspace_id)},
        ).first()
        dataset_count = int(ds_count_row[0]) if ds_count_row else 0

    return _row_to_detail(row, dataset_count)


@router.post("", response_model=WorkspaceDetail, status_code=201)
async def create_workspace(
    request: Request,
    response: Response,
    body: WorkspaceCreate,
) -> WorkspaceDetail:
    """Create a new workspace and bootstrap the first reviewer session (API-005).

    No authentication required — this is the entry point for a fresh install.
    Creates the workspace, auto-creates the first reviewer profile (defaulting
    to "Reviewer 1"), and sets the molabel_session cookie so the caller is
    immediately logged in.
    """
    engine = get_engine(request)
    secret = get_app_secret(request)
    now = datetime.now(UTC).isoformat()

    # ── 1. Create workspace ──────────────────────────────────────────────────
    workspace_id = str(uuid.uuid4())
    name = body.workspace_name or body.path.rstrip("/").split("/")[-1]
    slug = name.lower().replace(" ", "-")

    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO workspaces "
                "(id, workspace_name, workspace_slug, core_version, root_path, "
                "manifest_path, created_at, updated_at) "
                "VALUES (:id, :name, :slug, :version, :path, :manifest, :now, :now)"
            ),
            {
                "id": workspace_id,
                "name": name,
                "slug": slug,
                "version": "0.1.0",
                "path": body.path,
                "manifest": f"{body.path}/.molabel/manifest.yaml",
                "now": now,
            },
        )
        conn.commit()

        ws_row = conn.execute(
            text(
                "SELECT id, workspace_name, root_path, core_version, "
                "manifest_path, created_at, updated_at "
                "FROM workspaces WHERE id = :id"
            ),
            {"id": workspace_id},
        ).first()

    # ── 2. Auto-create first reviewer ────────────────────────────────────────
    reviewer_id = uuid.uuid4()
    reviewer_name = body.reviewer_name or "Reviewer 1"
    avatar_color = AVATAR_COLORS[0]

    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO reviewer_profiles "
                "(id, display_name, avatar_color, is_operator, is_active, "
                "workspace_id, created_at) "
                "VALUES (:id, :name, :color, 1, 1, :ws, :now)"
            ),
            {
                "id": str(reviewer_id),
                "name": reviewer_name,
                "color": avatar_color,
                "ws": workspace_id,
                "now": now,
            },
        )
        conn.commit()

    # ── 3. Set session cookie — caller is immediately logged in ──────────────
    token = create_session_token(reviewer_id, secret)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        path=COOKIE_PATH,
        httponly=COOKIE_HTTPONLY,
        samesite=COOKIE_SAMESITE,
        secure=COOKIE_SECURE,
    )

    detail = _row_to_detail(ws_row, 0)
    detail.first_reviewer = FirstReviewerInfo(
        id=reviewer_id,
        display_name=reviewer_name,
        avatar_color=avatar_color,
    )
    return detail


@router.post(
    "/{workspace_id}/reindex",
    response_model=ReindexStatus,
    status_code=202,
)
async def reindex_workspace(
    request: Request,
    workspace_id: uuid.UUID,
    _reviewer: CurrentReviewer,
    body: ReindexRequest | None = None,
) -> ReindexStatus:
    """Trigger a workspace reindex (API-006).

    Returns a 202 with a job ID for the async reindex operation.
    """
    engine = get_engine(request)
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id FROM workspaces WHERE id = :id"),
            {"id": str(workspace_id)},
        ).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Workspace not found")

    job_id = str(uuid.uuid4())
    return ReindexStatus(
        job_id=job_id,
        status="queued",
        started_at=datetime.now(UTC),
    )

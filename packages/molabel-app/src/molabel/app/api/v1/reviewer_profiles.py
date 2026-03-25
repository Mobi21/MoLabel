"""Reviewer profile endpoints -- /api/v1/reviewer-profiles (SE-001, SE-003).

Manages reviewer identity creation, listing, and updates.  Reviewer
profiles are lightweight (no passwords) and are scoped to a workspace
in Phase 1.

Uses raw SQL queries via ``sqlalchemy.text()`` to avoid triggering
SQLAlchemy mapper configuration for the full model graph.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from molabel.app.services.session import pick_avatar_color
from molabel.app.utils import get_engine, parse_bool, parse_datetime

router = APIRouter(prefix="/reviewer-profiles", tags=["reviewer-profiles"])


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------


class CreateReviewerProfileRequest(BaseModel):
    """Request body for creating a new reviewer profile (SE-001)."""

    display_name: str = Field(
        ..., min_length=1, max_length=64, description="Reviewer display name"
    )
    workspace_id: str = Field(
        ..., description="Workspace to associate the profile with"
    )


class UpdateReviewerProfileRequest(BaseModel):
    """Request body for updating a reviewer profile."""

    display_name: str | None = Field(
        default=None, min_length=1, max_length=64, description="New display name"
    )
    avatar_color: str | None = Field(
        default=None,
        pattern=r"^#[0-9A-Fa-f]{6}$",
        description="Hex color (e.g. #4A90D9)",
    )
    is_active: bool | None = Field(default=None, description="Active status")


class ReviewerProfileResponse(BaseModel):
    """Response model for a single reviewer profile."""

    id: uuid.UUID
    display_name: str
    avatar_color: str | None
    is_operator: bool
    is_active: bool
    created_at: datetime
    last_active_at: datetime | None
    preferences: dict[str, Any] | None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_response(row) -> ReviewerProfileResponse:
    """Convert a database row tuple to a ReviewerProfileResponse."""
    return ReviewerProfileResponse(
        id=uuid.UUID(str(row[0])),
        display_name=str(row[1]),
        avatar_color=str(row[2]) if row[2] else None,
        is_operator=parse_bool(row[3]),
        is_active=parse_bool(row[4]),
        created_at=parse_datetime(row[6]) or datetime.now(UTC),
        last_active_at=parse_datetime(row[7]),
        preferences=None,  # row[5] is preferences JSON, skip for now
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

_SELECT_COLUMNS = (
    "id, display_name, avatar_color, is_operator, is_active, "
    "preferences, created_at, last_active_at"
)


@router.get("", response_model=list[ReviewerProfileResponse])
async def list_reviewer_profiles(
    request: Request,
    active_only: Annotated[
        bool, Query(description="Filter to active profiles only")
    ] = True,
    workspace_id: Annotated[
        str | None, Query(description="Filter by workspace")
    ] = None,
) -> list[ReviewerProfileResponse]:
    """List reviewer profiles (SE-003).

    Returns all active profiles by default.  Used by the "Who are you?"
    first-visit screen to show existing profiles.
    """
    engine = get_engine(request)
    conditions: list[str] = []
    params: dict[str, str] = {}

    if active_only:
        conditions.append("is_active = 1")
    if workspace_id is not None:
        conditions.append("workspace_id = :workspace_id")
        params["workspace_id"] = workspace_id

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = (
        f"SELECT {_SELECT_COLUMNS} FROM reviewer_profiles {where} ORDER BY display_name"
    )

    with engine.connect() as conn:
        rows = conn.execute(text(query), params).all()

    return [_row_to_response(row) for row in rows]


@router.post("", response_model=ReviewerProfileResponse, status_code=201)
async def create_reviewer_profile(
    request: Request,
    body: CreateReviewerProfileRequest,
) -> ReviewerProfileResponse:
    """Create a new reviewer profile (SE-001).

    The server assigns a UUID ``id`` and auto-selects an ``avatar_color``
    from a 12-color palette, cycling to avoid adjacent duplicates.
    """
    engine = get_engine(request)

    # Collect existing avatar colors to pick a distinct one.
    with engine.connect() as conn:
        color_rows = conn.execute(
            text(
                "SELECT avatar_color FROM reviewer_profiles "
                "WHERE workspace_id = :ws AND avatar_color IS NOT NULL"
            ),
            {"ws": body.workspace_id},
        ).all()

    existing_colors = [str(r[0]) for r in color_rows]
    avatar_color = pick_avatar_color(existing_colors)

    profile_id = uuid.uuid4()
    now = datetime.now(UTC).isoformat()

    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO reviewer_profiles "
                "(id, display_name, avatar_color, is_operator, is_active, "
                "workspace_id, created_at) "
                "VALUES (:id, :name, :color, 0, 1, :ws, :now)"
            ),
            {
                "id": str(profile_id),
                "name": body.display_name,
                "color": avatar_color,
                "ws": body.workspace_id,
                "now": now,
            },
        )
        conn.commit()

        # Read back the created profile.
        row = conn.execute(
            text(f"SELECT {_SELECT_COLUMNS} FROM reviewer_profiles WHERE id = :id"),
            {"id": str(profile_id)},
        ).first()

    if row is None:
        raise HTTPException(status_code=500, detail="Failed to create profile")

    return _row_to_response(row)


@router.get("/{profile_id}", response_model=ReviewerProfileResponse)
async def get_reviewer_profile(
    request: Request,
    profile_id: uuid.UUID,
) -> ReviewerProfileResponse:
    """Get a single reviewer profile by ID."""
    engine = get_engine(request)

    with engine.connect() as conn:
        row = conn.execute(
            text(f"SELECT {_SELECT_COLUMNS} FROM reviewer_profiles WHERE id = :id"),
            {"id": str(profile_id)},
        ).first()

    if row is None:
        raise HTTPException(status_code=404, detail="Reviewer profile not found")

    return _row_to_response(row)


@router.patch("/{profile_id}", response_model=ReviewerProfileResponse)
async def update_reviewer_profile(
    request: Request,
    profile_id: uuid.UUID,
    body: UpdateReviewerProfileRequest,
) -> ReviewerProfileResponse:
    """Update display_name, avatar_color, or is_active for a profile."""
    engine = get_engine(request)

    # Check profile exists.
    with engine.connect() as conn:
        existing = conn.execute(
            text(f"SELECT {_SELECT_COLUMNS} FROM reviewer_profiles WHERE id = :id"),
            {"id": str(profile_id)},
        ).first()

    if existing is None:
        raise HTTPException(status_code=404, detail="Reviewer profile not found")

    # Build SET clause dynamically.
    updates: list[str] = []
    params: dict[str, Any] = {"id": str(profile_id)}

    if body.display_name is not None:
        updates.append("display_name = :display_name")
        params["display_name"] = body.display_name
    if body.avatar_color is not None:
        updates.append("avatar_color = :avatar_color")
        params["avatar_color"] = body.avatar_color
    if body.is_active is not None:
        updates.append("is_active = :is_active")
        params["is_active"] = 1 if body.is_active else 0

    if not updates:
        return _row_to_response(existing)

    set_clause = ", ".join(updates)
    with engine.connect() as conn:
        conn.execute(
            text(f"UPDATE reviewer_profiles SET {set_clause} WHERE id = :id"),
            params,
        )
        conn.commit()

        # Read back updated profile.
        row = conn.execute(
            text(f"SELECT {_SELECT_COLUMNS} FROM reviewer_profiles WHERE id = :id"),
            {"id": str(profile_id)},
        ).first()

    if row is None:
        raise HTTPException(status_code=500, detail="Failed to update profile")

    return _row_to_response(row)

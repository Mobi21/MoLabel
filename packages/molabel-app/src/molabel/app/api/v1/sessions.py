"""Session endpoints -- /api/v1/sessions, /api/v1/me (SE-002, SE-003, SE-005).

Handles login (session creation), logout (cookie clearing), profile
switching, and "who am I?" queries.

Uses raw SQL queries via ``sqlalchemy.text()`` to avoid triggering
SQLAlchemy mapper configuration for the full model graph.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import text

from molabel.app.middleware.session import CurrentReviewer
from molabel.app.services.session import (
    COOKIE_HTTPONLY,
    COOKIE_NAME,
    COOKIE_PATH,
    COOKIE_SAMESITE,
    COOKIE_SECURE,
    create_session_token,
)
from molabel.app.utils import get_app_secret, get_engine, parse_bool

router = APIRouter(tags=["sessions"])


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------


class CreateSessionRequest(BaseModel):
    """Request body for creating a session (login / profile selection)."""

    reviewer_id: str = Field(
        ..., description="UUID of the reviewer profile to log in as"
    )


class SwitchSessionRequest(BaseModel):
    """Request body for switching to a different profile (SE-005)."""

    reviewer_id: str = Field(..., description="UUID of the target reviewer profile")


class SessionResponse(BaseModel):
    """Response model for session-related endpoints."""

    reviewer_id: uuid.UUID
    display_name: str
    avatar_color: str | None
    is_operator: bool
    message: str = "session_active"


class MeResponse(BaseModel):
    """Response model for GET /api/v1/me."""

    reviewer_id: uuid.UUID
    display_name: str
    avatar_color: str | None
    is_operator: bool
    is_active: bool
    created_at: datetime
    last_active_at: datetime | None
    preferences: dict[str, Any] | None


class NeedsSessionResponse(BaseModel):
    """Response indicating no valid session exists (SE-003)."""

    needs_session: bool = True
    profiles: list[ProfileSummary] = []


class ProfileSummary(BaseModel):
    """Lightweight profile info for the 'Who are you?' screen."""

    id: uuid.UUID
    display_name: str
    avatar_color: str | None

    model_config = {"from_attributes": True}


# Fix forward reference
NeedsSessionResponse.model_rebuild()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _set_session_cookie(response: Response, token: str) -> None:
    """Set the molabel_session cookie on the response (SE-002)."""
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        path=COOKIE_PATH,
        httponly=COOKIE_HTTPONLY,
        samesite=COOKIE_SAMESITE,
        secure=COOKIE_SECURE,
    )


_SELECT_COLUMNS = (
    "id, display_name, avatar_color, is_operator, is_active, "
    "preferences, created_at, last_active_at"
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/sessions", response_model=SessionResponse)
async def create_session(
    request: Request,
    response: Response,
    body: CreateSessionRequest,
) -> SessionResponse:
    """Create a new session by selecting a reviewer profile (SE-002).

    Sets the ``molabel_session`` cookie.  This is the primary "login"
    endpoint used from the "Who are you?" screen.
    """
    secret = get_app_secret(request)
    engine = get_engine(request)

    try:
        reviewer_uuid = uuid.UUID(body.reviewer_id)
    except ValueError:
        raise HTTPException(
            status_code=422, detail="reviewer_id is not a valid UUID"
        ) from None
    now = datetime.now(UTC).isoformat()

    with engine.connect() as conn:
        row = conn.execute(
            text(f"SELECT {_SELECT_COLUMNS} FROM reviewer_profiles WHERE id = :id"),
            {"id": str(reviewer_uuid)},
        ).first()

    if row is None or not parse_bool(row[4]):
        raise HTTPException(
            status_code=404, detail="Reviewer profile not found or inactive"
        )

    # Update last_active_at on login.
    with engine.connect() as conn:
        conn.execute(
            text("UPDATE reviewer_profiles SET last_active_at = :now WHERE id = :id"),
            {"now": now, "id": str(reviewer_uuid)},
        )
        conn.commit()

    token = create_session_token(reviewer_uuid, secret)
    _set_session_cookie(response, token)

    return SessionResponse(
        reviewer_id=reviewer_uuid,
        display_name=str(row[1]),
        avatar_color=str(row[2]) if row[2] else None,
        is_operator=parse_bool(row[3]),
        message="session_created",
    )


@router.delete("/sessions", status_code=204)
async def delete_session(response: Response) -> None:
    """Log out by clearing the session cookie."""
    response.delete_cookie(
        key=COOKIE_NAME,
        path=COOKIE_PATH,
        httponly=COOKIE_HTTPONLY,
        samesite=COOKIE_SAMESITE,
        secure=COOKIE_SECURE,
    )


@router.get("/me", response_model=MeResponse)
async def get_me(reviewer: CurrentReviewer) -> MeResponse:
    """Get current reviewer from the session cookie (SE-003).

    Returns the full reviewer profile for the currently logged-in user.
    Returns 401 if no valid session exists.
    """
    return MeResponse(
        reviewer_id=reviewer.id,
        display_name=reviewer.display_name,
        avatar_color=reviewer.avatar_color,
        is_operator=reviewer.is_operator,
        is_active=reviewer.is_active,
        created_at=reviewer.created_at,
        last_active_at=reviewer.last_active_at,
        preferences=reviewer.preferences,
    )


@router.post("/sessions/switch", response_model=SessionResponse)
async def switch_session(
    request: Request,
    response: Response,
    body: SwitchSessionRequest,
    _current_reviewer: CurrentReviewer,
) -> SessionResponse:
    """Switch to a different reviewer profile (SE-005).

    Replaces the session cookie.  The frontend should auto-save any
    in-progress drafts before calling this endpoint.  Active queue claims
    held by the old profile are NOT released (they expire naturally).
    """
    secret = get_app_secret(request)
    engine = get_engine(request)

    try:
        target_uuid = uuid.UUID(body.reviewer_id)
    except ValueError:
        raise HTTPException(
            status_code=422, detail="reviewer_id is not a valid UUID"
        ) from None
    now = datetime.now(UTC).isoformat()

    with engine.connect() as conn:
        row = conn.execute(
            text(f"SELECT {_SELECT_COLUMNS} FROM reviewer_profiles WHERE id = :id"),
            {"id": str(target_uuid)},
        ).first()

    if row is None or not parse_bool(row[4]):
        raise HTTPException(
            status_code=404, detail="Target reviewer profile not found or inactive"
        )

    with engine.connect() as conn:
        conn.execute(
            text("UPDATE reviewer_profiles SET last_active_at = :now WHERE id = :id"),
            {"now": now, "id": str(target_uuid)},
        )
        conn.commit()

    token = create_session_token(target_uuid, secret)
    _set_session_cookie(response, token)

    return SessionResponse(
        reviewer_id=target_uuid,
        display_name=str(row[1]),
        avatar_color=str(row[2]) if row[2] else None,
        is_operator=parse_bool(row[3]),
        message="session_switched",
    )

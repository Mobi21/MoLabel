"""Session middleware: FastAPI dependency for session validation (SE-004).

Provides the ``get_current_reviewer`` dependency that validates the
``molabel_session`` cookie on every protected API request.

Uses raw SQL queries to avoid triggering SQLAlchemy mapper configuration
for the full model graph.  This is necessary because some core models
have relationship annotations that cannot be resolved by the mapper in
all import orders.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Cookie, Depends, HTTPException, Request
from sqlalchemy import text

from molabel.app.services.session import (
    should_update_last_active,
    verify_session_token,
)
from molabel.app.utils import get_app_secret, get_engine, parse_bool, parse_datetime


@dataclass
class ReviewerSession:
    """Lightweight session data extracted from the database.

    Used instead of the SQLModel ReviewerProfile to avoid triggering
    mapper configuration across the full model graph.
    """

    id: uuid.UUID
    display_name: str
    avatar_color: str | None
    is_operator: bool
    is_active: bool
    created_at: datetime
    last_active_at: datetime | None
    preferences: dict[str, Any] | None
    workspace_id: uuid.UUID


async def get_current_reviewer(
    request: Request,
    molabel_session: Annotated[str | None, Cookie()] = None,
) -> ReviewerSession:
    """Validate the session cookie and return the current reviewer session.

    This is a FastAPI dependency that should be injected into any endpoint
    that requires an authenticated reviewer.

    Raises
    ------
    HTTPException(401)
        If the session cookie is missing, invalid, or references a
        non-existent / inactive reviewer profile.
    """
    if molabel_session is None:
        raise HTTPException(
            status_code=401,
            detail="No session cookie present. Please select a reviewer profile.",
            headers={"X-MoLabel-Auth": "needs_session"},
        )

    secret = get_app_secret(request)
    reviewer_id = verify_session_token(molabel_session, secret)
    if reviewer_id is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session cookie.",
            headers={"X-MoLabel-Auth": "needs_session"},
        )

    engine = get_engine(request)
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, display_name, avatar_color, is_operator, is_active, "
                "created_at, last_active_at, preferences, workspace_id "
                "FROM reviewer_profiles WHERE id = :id"
            ),
            {"id": str(reviewer_id)},
        ).first()

    if row is None or not parse_bool(row[4]):  # is_active
        raise HTTPException(
            status_code=401,
            detail="Reviewer profile not found or inactive.",
            headers={"X-MoLabel-Auth": "needs_session"},
        )

    profile = ReviewerSession(
        id=uuid.UUID(str(row[0])),
        display_name=str(row[1]),
        avatar_color=str(row[2]) if row[2] else None,
        is_operator=parse_bool(row[3]),
        is_active=parse_bool(row[4]),
        created_at=parse_datetime(row[5]) or datetime.now(UTC),
        last_active_at=parse_datetime(row[6]),
        preferences=None,  # JSON parsing skipped for session check
        workspace_id=uuid.UUID(str(row[8])),
    )

    # Debounced last_active_at update (SE-004)
    if should_update_last_active(reviewer_id):
        _update_last_active(engine, reviewer_id)

    return profile


def _update_last_active(engine, reviewer_id: uuid.UUID) -> None:
    """Write last_active_at to the database (debounced)."""
    now = datetime.now(UTC).isoformat()
    with engine.connect() as conn:
        conn.execute(
            text("UPDATE reviewer_profiles SET last_active_at = :now WHERE id = :id"),
            {"now": now, "id": str(reviewer_id)},
        )
        conn.commit()


# Type alias for cleaner dependency injection in endpoint signatures.
CurrentReviewer = Annotated[ReviewerSession, Depends(get_current_reviewer)]

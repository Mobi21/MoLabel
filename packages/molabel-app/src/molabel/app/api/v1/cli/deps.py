"""CLI-specific dependencies and auth helpers."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, Request
from sqlalchemy import text

from molabel.app.services.session import verify_session_token
from molabel.app.utils import get_app_secret, get_engine, parse_bool, parse_datetime


@dataclass
class CliRequestSession:
    """Authenticated reviewer session for CLI routes."""

    id: uuid.UUID
    display_name: str
    avatar_color: str | None
    is_operator: bool
    is_active: bool
    created_at: datetime
    last_active_at: datetime | None
    preferences: dict | None
    workspace_id: uuid.UUID


def _extract_cli_token(
    molabel_session: str | None,
    x_molabel_session: str | None,
    authorization: str | None,
) -> str | None:
    if molabel_session:
        return molabel_session
    if x_molabel_session:
        return x_molabel_session
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip() or None
    return None


async def get_cli_reviewer(
    request: Request,
    molabel_session: Annotated[str | None, Cookie()] = None,
    x_molabel_session: Annotated[str | None, Header(alias="X-MoLabel-Session")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> CliRequestSession:
    """Validate a CLI session token from cookie or header."""
    token = _extract_cli_token(molabel_session, x_molabel_session, authorization)
    if token is None:
        raise HTTPException(
            status_code=401,
            detail="No session token present.",
            headers={"X-MoLabel-Auth": "needs_session"},
        )

    secret = get_app_secret(request)
    reviewer_id = verify_session_token(token, secret)
    if reviewer_id is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session token.",
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

    if row is None or not parse_bool(row[4]):
        raise HTTPException(
            status_code=401,
            detail="Reviewer profile not found or inactive.",
            headers={"X-MoLabel-Auth": "needs_session"},
        )

    return CliRequestSession(
        id=uuid.UUID(str(row[0])),
        display_name=str(row[1]),
        avatar_color=str(row[2]) if row[2] else None,
        is_operator=parse_bool(row[3]),
        is_active=parse_bool(row[4]),
        created_at=parse_datetime(row[5]) or datetime.now(UTC),
        last_active_at=parse_datetime(row[6]),
        preferences=None,
        workspace_id=uuid.UUID(str(row[8])),
    )


CurrentCliReviewer = Annotated[CliRequestSession, Depends(get_cli_reviewer)]

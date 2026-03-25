"""Shared utility helpers for molabel-app.

Centralises common functions that were previously duplicated across
session middleware, API endpoint modules, and service layers.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException, Request


def get_engine(request: Request):
    """Extract the database engine from the application state.

    Raises
    ------
    HTTPException(500)
        If the engine has not been configured on the app state.
    """
    engine = getattr(request.app.state, "engine", None)
    if engine is None:
        raise HTTPException(
            status_code=500,
            detail="Database engine not configured",
        )
    return engine


def get_app_secret(request: Request) -> str:
    """Extract the application secret from the application state.

    Raises
    ------
    HTTPException(500)
        If the secret has not been configured on the app state.
    """
    secret = getattr(request.app.state, "app_secret", None)
    if secret is None:
        raise HTTPException(
            status_code=500,
            detail="Application secret not configured",
        )
    return secret


def parse_bool(value: Any) -> bool:
    """Convert a SQLite integer/bool value to Python bool."""
    if isinstance(value, bool):
        return value
    return bool(int(value)) if value is not None else False


def parse_datetime(value: Any) -> datetime | None:
    """Parse an ISO 8601 string or datetime value from SQLite."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None

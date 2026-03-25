"""Common Pydantic response models for the MoLabel API.

These models define the shared response envelopes, error types, and query
parameter conventions used across all API endpoints.  They follow the
contract in docs/architecture/api-specification.md.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


class PaginatedResponse[T](BaseModel):  # noqa: UP046
    """Cursor-based paginated response envelope.

    Clients must treat ``cursor`` as an opaque token — they should never
    parse or construct cursors themselves.
    """

    items: list[T]
    cursor: str | None = None
    has_more: bool = False


# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------


class ErrorDetail(BaseModel):
    """Single structured error description."""

    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    """Top-level error envelope returned for all error responses."""

    error: ErrorDetail


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------


class QueryParams(BaseModel):
    """Common query parameters for list endpoints (filtering / sorting).

    Designed to be used as a FastAPI ``Depends`` dependency.
    """

    cursor: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    sort_by: str | None = None
    sort_dir: Literal["asc", "desc"] = "desc"


# ---------------------------------------------------------------------------
# Mixins
# ---------------------------------------------------------------------------


class TimestampMixin(BaseModel):
    """Mixin providing standard created_at / updated_at timestamps."""

    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """Response model for the /health endpoint."""

    status: str

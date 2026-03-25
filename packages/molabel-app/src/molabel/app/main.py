"""MoLabel FastAPI application factory.

Module boundary rule (SC-006):
    This package (molabel.app) may only import from ``molabel.core``.
    It must NEVER import from ``molabel.plugins`` or ``molabel.depolarize``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from starlette.exceptions import HTTPException as StarletteHTTPException

from molabel.app.api.v1 import router as v1_router
from molabel.app.schemas import ErrorDetail, ErrorResponse, HealthResponse
from molabel.app.services.session import get_or_create_app_secret
from molabel.core.database import create_all_tables

# ---------------------------------------------------------------------------
# Network binding configuration (SE-012)
# ---------------------------------------------------------------------------

#: Host to bind to.  ``0.0.0.0`` (default) makes the server accessible on
#: the local network; ``127.0.0.1`` restricts to localhost only (single-user).
MOLABEL_HOST: str = os.environ.get("MOLABEL_HOST", "0.0.0.0")

#: Port for the API server.
MOLABEL_PORT: int = int(os.environ.get("MOLABEL_PORT", "8000"))


logger = logging.getLogger(__name__)


def _create_engine_from_env():
    """Create a SQLAlchemy engine from the MOLABEL_DB_URL environment variable.

    Defaults to a file-based SQLite database at ``molabel.db``.
    In-memory databases (used in tests) get a StaticPool so the same
    connection is reused across requests within a single process.
    """
    db_url = os.environ.get("MOLABEL_DB_URL", "sqlite:///molabel.db")
    # Normalise async driver URLs to their sync equivalents — the app uses
    # synchronous SQLAlchemy throughout.
    db_url = db_url.replace("sqlite+aiosqlite", "sqlite")
    in_memory = ":memory:" in db_url or db_url in {"sqlite://", "sqlite:///"}
    kwargs = {"connect_args": {"check_same_thread": False}}
    if in_memory:
        kwargs["poolclass"] = StaticPool  # type: ignore[assignment]
    return create_engine(db_url, **kwargs)  # type: ignore[arg-type]


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: initialise DB, app secret, and background tasks.

    DM-001: Engine creation from MOLABEL_DB_URL.
    SE-011: App secret auto-generation on startup.
    SE-007: Claim expiry background task.
    """
    engine = _create_engine_from_env()
    create_all_tables(engine)
    app.state.engine = engine
    app.state.app_secret = get_or_create_app_secret()

    claim_task: asyncio.Task[None] | None = None
    from molabel.app.tasks.claim_expiry import claim_expiry_loop

    claim_task = asyncio.create_task(claim_expiry_loop(engine))
    logger.info("Claim expiry background task started")

    yield

    if claim_task is not None:
        claim_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await claim_task
        logger.info("Claim expiry background task stopped")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""

    app = FastAPI(
        title="MoLabel API",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=_lifespan,
    )

    # ----- middleware -----
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # TODO: restrict in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ----- routers -----
    app.include_router(v1_router)

    # ----- exception handlers -----

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=ErrorResponse(
                error=ErrorDetail(
                    code="VALIDATION_ERROR",
                    message="Request validation failed",
                    details={"errors": exc.errors()},
                )
            ).model_dump(mode="json"),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        code_map: dict[int, str] = {
            400: "BAD_REQUEST",
            401: "UNAUTHORIZED",
            404: "NOT_FOUND",
            409: "CONFLICT",
            423: "LOCKED",
            500: "INTERNAL_ERROR",
        }
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error=ErrorDetail(
                    code=code_map.get(exc.status_code, "INTERNAL_ERROR"),
                    message=str(exc.detail),
                )
            ).model_dump(mode="json"),
        )

    # ----- health check -----

    @app.get("/health", tags=["system"])
    async def health() -> HealthResponse:
        return HealthResponse(status="ok")

    return app


# Module-level instance for ``uvicorn molabel.app.main:app`` (used by molabel-dev).
app: FastAPI = create_app()

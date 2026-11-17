"""MoLabel FastAPI application factory.

Module boundary rule (SC-006):
    This package (molabel.app) may only import from ``molabel.core``.
    It must NEVER import from ``molabel.plugins``.
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
from fastapi.routing import APIRoute
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from molabel.app.api.v1 import router as v1_router
from molabel.app.api.v1.cli.operations import (
    TemplateModelRequiredError,
    template_model_required_error_handler,
)
from molabel.app.api.v1.workflows import (
    UnresolvedModelError,
    unresolved_model_error_handler,
)
from molabel.app.schemas import ErrorDetail, ErrorResponse, HealthResponse
from molabel.app.server_state import (
    launch_folder_database,
    legacy_databases,
    server_db_url,
)
from molabel.app.services.session import get_or_create_app_secret
from molabel.app.workspace_paths import (
    WorkspacePathError,
    workspace_path_error_handler,
)
from molabel.core.database import engine_from_url
from molabel.core.migration_runner import upgrade_database

# ---------------------------------------------------------------------------
# Network binding configuration (SE-012)
# ---------------------------------------------------------------------------

#: Host to bind to. ``127.0.0.1`` (default) restricts the server to localhost
#: only; ``0.0.0.0`` exposes it to the local network when explicitly requested.
MOLABEL_HOST: str = os.environ.get("MOLABEL_HOST", "127.0.0.1")

#: Port for the API server.
MOLABEL_PORT: int = int(os.environ.get("MOLABEL_PORT", "8000"))

_DEFAULT_CORS_ORIGINS: tuple[str, ...] = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
)


logger = logging.getLogger(__name__)

#: SQLite's extended codes for a write that conflicts with rows already
#: stored. A repeated primary key reports "UNIQUE constraint failed" too.
_CONFLICT_ERRORS = frozenset(
    {
        "SQLITE_CONSTRAINT_FOREIGNKEY",
        "SQLITE_CONSTRAINT_UNIQUE",
        "SQLITE_CONSTRAINT_PRIMARYKEY",
    }
)


def _create_engine_from_env():
    """The server's engine for ``server_db_url()``, from the shared factory.

    ``molabel.core.database.engine_from_url`` sets WAL and foreign keys on
    every connection. In-memory databases (used in tests) get a StaticPool so
    the same connection is reused across requests within a single process.
    """
    return engine_from_url(server_db_url())


def _cors_origins_from_env() -> list[str]:
    """Return the allowed browser origins for the API.

    By default, MoLabel only permits the localhost origins used by the dev
    server and the bundled frontend. Set ``MOLABEL_CORS_ORIGINS`` to a
    comma-separated list to override that allowlist, or to an empty string to
    disable cross-origin browser access entirely.
    """
    raw = os.environ.get("MOLABEL_CORS_ORIGINS")
    if raw is None:
        return list(_DEFAULT_CORS_ORIGINS)
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: initialise DB, app secret, and background tasks.

    DM-001: Engine creation from MOLABEL_DB_URL.
    SE-011: App secret auto-generation on startup.
    SE-007: Claim expiry background task.
    """
    engine = _create_engine_from_env()
    try:
        upgrade_database(engine)
    except BaseException:
        # A refused database keeps only its own file: closing the pool lets
        # SQLite remove the WAL and shared-memory files it opened beside it.
        engine.dispose()
        raise
    for legacy in legacy_databases(engine, [launch_folder_database()]):
        logger.warning("LEGACY DATABASE NOT LOADED: %s", legacy.message)
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


def _operation_id(route: APIRoute) -> str:
    """Name each operation after its route function, for readable generated clients."""
    return route.name


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""

    app = FastAPI(
        title="MoLabel API",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=_lifespan,
        generate_unique_id_function=_operation_id,
    )

    # ----- middleware -----
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins_from_env(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ----- routers -----
    app.include_router(v1_router)

    # ----- exception handlers -----

    app.add_exception_handler(WorkspacePathError, workspace_path_error_handler)
    app.add_exception_handler(UnresolvedModelError, unresolved_model_error_handler)
    app.add_exception_handler(
        TemplateModelRequiredError, template_model_required_error_handler
    )

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

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(
        _request: Request, exc: IntegrityError
    ) -> JSONResponse:
        """A key to a missing row, or a repeated key, conflicts with the data.

        Any other refused write, such as a NOT NULL or CHECK failure, is a bug
        in the server, so it propagates as a 500 with its traceback.
        """
        if getattr(exc.orig, "sqlite_errorname", None) not in _CONFLICT_ERRORS:
            raise exc
        return JSONResponse(
            status_code=409,
            content=ErrorResponse(
                error=ErrorDetail(
                    code="CONFLICT",
                    message=f"The database refused the write: {exc.orig}",
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

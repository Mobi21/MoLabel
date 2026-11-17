"""Refuse browser requests that come from a page other than the server's own.

A web page the user has open can send requests to the local API, and the
browser stamps each with the page's ``Origin``. A request is refused with 403
unless its ``Origin`` is the server's own loopback origin on the port it
listens on, or one set in ``MOLABEL_ALLOWED_ORIGINS``. A request with no
``Origin``, such as the CLI's or curl's, goes through to the usual checks.
"""

from __future__ import annotations

import os
from collections.abc import Sequence

from fastapi.responses import JSONResponse
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from molabel.app.schemas import ErrorDetail, ErrorResponse

ALLOWED_ORIGINS_ENV = "MOLABEL_ALLOWED_ORIGINS"
_LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "[::1]")


def configured_origins() -> tuple[str, ...]:
    """``MOLABEL_ALLOWED_ORIGINS``, comma-separated, such as a dev frontend's origin."""
    raw = os.environ.get(ALLOWED_ORIGINS_ENV, "")
    return tuple(
        origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()
    )


def allowed_origins(port: int | None, configured: Sequence[str]) -> list[str]:
    """The server's loopback origins on *port*, then the *configured* ones."""
    own = [] if port is None else [f"http://{host}:{port}" for host in _LOOPBACK_HOSTS]
    return [*own, *configured]


class LocalOriginMiddleware:
    """Answer 403 ``ORIGIN_NOT_ALLOWED`` to a request from any other origin."""

    def __init__(self, app: ASGIApp, configured: Sequence[str]) -> None:
        self.app = app
        self.configured = tuple(configured)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        origin = Headers(scope=scope).get("origin") if scope["type"] == "http" else None
        if origin is not None:
            server = scope.get("server")
            allowed = allowed_origins(server[1] if server else None, self.configured)
            if origin not in allowed:
                refusal = JSONResponse(
                    status_code=403,
                    content=ErrorResponse(
                        error=ErrorDetail(
                            code="ORIGIN_NOT_ALLOWED",
                            message=(
                                f"Requests from {origin} are refused. The API "
                                f"takes browser requests only from "
                                f"{', '.join(allowed)}. {ALLOWED_ORIGINS_ENV} "
                                "adds origins."
                            ),
                            details={"origin": origin, "allowed_origins": allowed},
                        )
                    ).model_dump(mode="json"),
                )
                await refusal(scope, receive, send)
                return
        await self.app(scope, receive, send)

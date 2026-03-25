"""Async test client for E2E tests.

Uses httpx AsyncClient with ASGI transport — no real network needed.
Configures the in-memory SQLite DB via the MOLABEL_DB_URL environment
variable before calling create_app(), so the app reads the correct URL
from its environment at startup.
"""

from __future__ import annotations

import logging
import os
import time

import httpx

from tests.e2e.infrastructure.logging_config import TestContext


class E2EClient:
    """Async test client wrapping httpx + ASGI transport.

    Sets MOLABEL_DB_URL before creating the app so every test gets an
    isolated in-memory SQLite database.  create_app() reads the DB URL
    from the environment on startup.
    """

    def __init__(self, db_url: str = "sqlite+aiosqlite://") -> None:
        os.environ["MOLABEL_DB_URL"] = db_url
        from molabel.app.main import create_app

        self.app = create_app()
        self._client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://test",
            timeout=30.0,
        )
        self._session_cookie: str | None = None

    async def login(self, reviewer_id: str) -> None:
        resp = await self.post("/sessions", json={"reviewer_id": reviewer_id})
        self._session_cookie = resp.cookies.get("molabel_session")

    async def request(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        if self._session_cookie:
            kwargs.setdefault("cookies", {})["molabel_session"] = self._session_cookie  # type: ignore[index]
        return await self._client.request(method, path, **kwargs)

    async def get(self, path: str, **kw: object) -> httpx.Response:
        return await self.request("GET", path, **kw)

    async def post(self, path: str, **kw: object) -> httpx.Response:
        return await self.request("POST", path, **kw)

    async def put(self, path: str, **kw: object) -> httpx.Response:
        return await self.request("PUT", path, **kw)

    async def patch(self, path: str, **kw: object) -> httpx.Response:
        return await self.request("PATCH", path, **kw)

    async def delete(self, path: str, **kw: object) -> httpx.Response:
        return await self.request("DELETE", path, **kw)

    async def close(self) -> None:
        await self._client.aclose()


class InstrumentedClient(E2EClient):
    """E2E client that logs every API call to a TestContext.

    Wraps every request with timing, status logging, and TestContext
    recording so tests get full observability without boilerplate.
    """

    def __init__(self, ctx: TestContext, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.ctx = ctx
        self.logger = logging.getLogger("molabel.e2e.client")

    async def request(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        start = time.monotonic()
        resp = await super().request(method, path, **kwargs)
        duration_ms = (time.monotonic() - start) * 1000

        self.ctx.log_api_call(
            method=method,
            path=path,
            status=resp.status_code,
            duration_ms=round(duration_ms, 1),
            body=kwargs.get("json"),  # type: ignore[arg-type]
            summary=f"{resp.status_code} in {duration_ms:.0f}ms",
        )

        self.logger.info(
            f"{method} {path} -> {resp.status_code} ({duration_ms:.0f}ms)",
            extra={
                "test_id": self.ctx.test_id,
                "api_call": f"{method} {path}",
                "status_code": resp.status_code,
            },
        )
        return resp

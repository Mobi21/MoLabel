"""Async test client for E2E tests.

Uses httpx AsyncClient with ASGI transport — no real network needed.
Configures the in-memory SQLite DB via the MOLABEL_DB_URL environment
variable before calling create_app(), so the app reads the correct URL
from its environment at startup.
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
from pathlib import Path

import httpx

from tests.e2e.infrastructure.logging_config import TestContext


class E2EClient:
    """Async test client wrapping httpx + ASGI transport.

    Sets MOLABEL_DB_URL before creating the app so every test gets an
    isolated in-memory SQLite database.  create_app() reads the DB URL
    from the environment on startup.
    """

    def __init__(self, db_url: str = "sqlite:///:memory:") -> None:
        os.environ["MOLABEL_DB_URL"] = db_url
        from sqlalchemy import create_engine
        from sqlalchemy.pool import StaticPool

        from molabel.app.main import create_app
        from molabel.app.services.session import get_or_create_app_secret
        from molabel.core.migration_runner import upgrade_database

        self.app = create_app()

        # httpx ASGITransport does not fire ASGI lifespan events, so we
        # bootstrap the app state (engine + secret) manually here.
        engine = create_engine(
            db_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        upgrade_database(engine)
        self.app.state.engine = engine
        self.app.state.app_secret = get_or_create_app_secret()

        self._client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://test",
            timeout=30.0,
        )
        self._session_cookie: str | None = None
        self._workspace_dirs = tempfile.TemporaryDirectory(prefix="molabel-e2e-")

    async def login(self, reviewer_id: str) -> None:
        """Switch the active session to the given reviewer profile."""
        resp = await self.post("/api/v1/sessions", json={"reviewer_id": reviewer_id})
        cookie = resp.cookies.get("molabel_session")
        if cookie:
            self._session_cookie = cookie

    async def request(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        if self._session_cookie:
            kwargs.setdefault("cookies", {})["molabel_session"] = self._session_cookie  # type: ignore[index]
        resp = await self._client.request(method, path, **kwargs)
        # Auto-capture session cookie set by any endpoint (e.g. POST /workspaces).
        cookie = resp.cookies.get("molabel_session")
        if cookie:
            self._session_cookie = cookie
        return resp

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

    def workspace_dir(self, name: str) -> str:
        """A real folder to register as a workspace root; removed on close."""
        path = Path(self._workspace_dirs.name) / name
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    async def close(self) -> None:
        await self._client.aclose()
        self._workspace_dirs.cleanup()


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

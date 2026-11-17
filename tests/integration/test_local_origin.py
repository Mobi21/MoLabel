"""A web page may not drive the local API: browser requests must come from it.

The server listens on port 8000 here. A request whose ``Origin`` is the
server's own loopback origin, or one set in ``MOLABEL_ALLOWED_ORIGINS``, goes
through. Any other ``Origin`` is refused with 403 before a route runs. A
request with no ``Origin``, as the CLI and curl send, goes through.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from molabel.app.main import create_app
from molabel.core.database import engine_from_url
from molabel.core.migration_runner import upgrade_database

SERVER = "http://127.0.0.1:8000"
DEV_FRONTEND = "http://localhost:5173"


def _app():
    application = create_app()
    engine = engine_from_url("sqlite:///:memory:")
    upgrade_database(engine)
    application.state.engine = engine
    application.state.app_secret = "origin-secret"
    return application


@pytest_asyncio.fixture()
async def client(monkeypatch):
    monkeypatch.delenv("MOLABEL_ALLOWED_ORIGINS", raising=False)
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url=SERVER) as c:
        yield c


async def _register(client, path, origin: str | None):
    headers = {} if origin is None else {"Origin": origin}
    return await client.post(
        "/api/v1/workspaces", json={"path": str(path)}, headers=headers
    )


async def _registered(client) -> int:
    return len((await client.get("/api/v1/workspaces")).json()["items"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "origin",
    ["http://localhost:8000", "http://127.0.0.1:8000", "http://[::1]:8000"],
)
async def test_the_servers_own_loopback_origin_goes_through(client, tmp_path, origin):
    resp = await _register(client, tmp_path / "tickets", origin)

    assert resp.status_code == 201, resp.text
    assert await _registered(client) == 1


@pytest.mark.asyncio
async def test_a_request_without_an_origin_goes_through(client, tmp_path):
    resp = await _register(client, tmp_path / "tickets", None)

    assert resp.status_code == 201, resp.text
    assert await _registered(client) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:5173",
        "http://127.0.0.1:8001",
        "http://localhost",
        "https://localhost:8000",
        "http://evil.example",
        "https://evil.example:8000",
        "http://192.168.1.20:8000",
        "null",
    ],
    ids=[
        "other port",
        "loopback, other port",
        "no port",
        "other scheme",
        "remote host",
        "remote host, server port",
        "lan address",
        "null",
    ],
)
async def test_any_other_origin_is_refused_before_the_route_runs(
    client, tmp_path, origin
):
    resp = await _register(client, tmp_path / "tickets", origin)

    assert resp.status_code == 403
    error = resp.json()["error"]
    assert error["code"] == "ORIGIN_NOT_ALLOWED"
    assert error["details"]["origin"] == origin
    assert error["details"]["allowed_origins"] == [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://[::1]:8000",
    ]
    assert "access-control-allow-origin" not in resp.headers
    assert await _registered(client) == 0
    assert not (tmp_path / "tickets").exists()


@pytest.mark.asyncio
async def test_reads_from_another_origin_are_refused_too(client):
    resp = await client.get("/api/v1/workspaces", headers={"Origin": DEV_FRONTEND})

    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_a_configured_origin_goes_through_and_gets_cors_headers(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("MOLABEL_ALLOWED_ORIGINS", f"{DEV_FRONTEND}, https://lab.test/")
    async with AsyncClient(
        transport=ASGITransport(app=_app()), base_url=SERVER
    ) as client:
        preflight = await client.options(
            "/api/v1/workspaces",
            headers={
                "Origin": DEV_FRONTEND,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        created = await _register(client, tmp_path / "tickets", DEV_FRONTEND)
        refused = await _register(client, tmp_path / "other", "http://localhost:5174")

    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == DEV_FRONTEND
    assert created.status_code == 201, created.text
    assert created.headers["access-control-allow-origin"] == DEV_FRONTEND
    assert refused.status_code == 403
    assert refused.json()["error"]["details"]["allowed_origins"] == [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://[::1]:8000",
        DEV_FRONTEND,
        "https://lab.test",
    ]


@pytest.mark.asyncio
async def test_a_preflight_from_another_origin_is_refused(client):
    resp = await client.options(
        "/api/v1/workspaces",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert resp.status_code == 403
    assert "access-control-allow-origin" not in resp.headers

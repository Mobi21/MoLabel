"""Integration tests for export endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine

from molabel.app.main import create_app
from molabel.app.services.session import create_session_token

_SECRET = "export-test-secret"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def _db():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with eng.connect() as conn:
        conn.execute(
            text(
                "CREATE TABLE workspaces ("
                "id TEXT PRIMARY KEY, workspace_name TEXT, workspace_slug TEXT UNIQUE, "
                "core_version TEXT, root_path TEXT, manifest_path TEXT, "
                "created_at TEXT, updated_at TEXT)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE reviewer_profiles ("
                "id TEXT PRIMARY KEY, display_name TEXT, avatar_color TEXT, "
                "is_operator INTEGER DEFAULT 0, is_active INTEGER DEFAULT 1, "
                "preferences TEXT, created_at TEXT, last_active_at TEXT, "
                "workspace_id TEXT REFERENCES workspaces(id))"
            )
        )
        conn.commit()
    return eng


@pytest.fixture()
def _seed(_db):
    ws_id = str(uuid.uuid4())
    r_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    with _db.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO workspaces VALUES "
                "(:id,'Test','test','0.1.0','/tmp','/tmp/m.yaml',:now,:now)"
            ),
            {"id": ws_id, "now": now},
        )
        conn.execute(
            text(
                "INSERT INTO reviewer_profiles "
                "(id,display_name,avatar_color,is_operator,is_active,"
                "workspace_id,created_at,last_active_at) "
                "VALUES (:id,'Tester','#4A90D9',1,1,:ws,:now,:now)"
            ),
            {"id": r_id, "ws": ws_id, "now": now},
        )
        conn.commit()
    return ws_id, r_id


@pytest.fixture()
def _app(_db):
    application = create_app()
    application.state.engine = _db
    application.state.app_secret = _SECRET
    return application


@pytest_asyncio.fixture()
async def auth_client(_app, _seed):
    ws_id, r_id = _seed
    token = create_session_token(uuid.UUID(r_id), _SECRET)
    transport = ASGITransport(app=_app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        cookies={"molabel_session": token},
    ) as c:
        c.headers["X-Test-Workspace"] = ws_id
        yield c


def _ws(client: AsyncClient) -> str:
    return client.headers["X-Test-Workspace"]


# ===================================================================
# List exports
# ===================================================================


class TestListExports:
    @pytest.mark.asyncio
    async def test_returns_200(self, auth_client):
        resp = await auth_client.get(
            "/api/v1/exports",
            params={"workspace_id": _ws(auth_client)},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "has_more" in body
        assert isinstance(body["items"], list)

    @pytest.mark.asyncio
    async def test_requires_workspace_id(self, auth_client):
        resp = await auth_client.get("/api/v1/exports")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_requires_auth(self, _app):
        transport = ASGITransport(app=_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/api/v1/exports", params={"workspace_id": "any"})
            assert resp.status_code == 401


# ===================================================================
# Create export
# ===================================================================


class TestCreateExport:
    @pytest.mark.asyncio
    async def test_returns_202(self, auth_client):
        resp = await auth_client.post(
            "/api/v1/exports",
            json={
                "workspace_id": _ws(auth_client),
                "dataset_id": str(uuid.uuid4()),
                "name": "Test Export",
                "format": "jsonl",
                "include": {"record_data": True, "human_labels": True},
            },
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "pending"
        assert body["name"] == "Test Export"
        assert body["format"] == "jsonl"
        assert "export_id" in body

    @pytest.mark.asyncio
    async def test_validation_error(self, auth_client):
        resp = await auth_client.post("/api/v1/exports", json={})
        assert resp.status_code == 422


# ===================================================================
# Preview export
# ===================================================================


class TestPreviewExport:
    @pytest.mark.asyncio
    async def test_returns_200(self, auth_client):
        resp = await auth_client.post(
            "/api/v1/exports/preview",
            json={
                "workspace_id": _ws(auth_client),
                "dataset_id": str(uuid.uuid4()),
                "name": "Preview",
                "format": "jsonl",
                "include": {"record_data": True},
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "sample_records" in body
        assert "total_matching" in body
        assert "warnings" in body


# ===================================================================
# Get export detail
# ===================================================================


class TestGetExport:
    @pytest.mark.asyncio
    async def test_returns_404_for_missing(self, auth_client):
        resp = await auth_client.get(f"/api/v1/exports/{uuid.uuid4()}")
        assert resp.status_code == 404


# ===================================================================
# Validate export
# ===================================================================


class TestValidateExport:
    @pytest.mark.asyncio
    async def test_returns_200(self, auth_client):
        resp = await auth_client.post(f"/api/v1/exports/{uuid.uuid4()}/validate")
        assert resp.status_code == 200
        body = resp.json()
        assert "export_id" in body
        assert "status" in body
        assert "checks" in body
        assert "validated_at" in body


# ===================================================================
# Download export
# ===================================================================


class TestDownloadExport:
    @pytest.mark.asyncio
    async def test_returns_404_placeholder(self, auth_client):
        resp = await auth_client.post(f"/api/v1/exports/{uuid.uuid4()}/download")
        assert resp.status_code == 404
        body = resp.json()
        assert "detail" in body


# ===================================================================
# Push to Hugging Face
# ===================================================================


class TestPushHF:
    @pytest.mark.asyncio
    async def test_returns_202(self, auth_client):
        resp = await auth_client.post(
            f"/api/v1/exports/{uuid.uuid4()}/push-hf",
            json={"repo_id": "test-org/test-dataset"},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "pending"
        assert body["repo_id"] == "test-org/test-dataset"

    @pytest.mark.asyncio
    async def test_validation_error(self, auth_client):
        resp = await auth_client.post(
            f"/api/v1/exports/{uuid.uuid4()}/push-hf",
            json={},
        )
        assert resp.status_code == 422

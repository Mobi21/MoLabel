"""Integration tests for assistant endpoints."""

from __future__ import annotations

import json
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

_SECRET = "assistant-test-secret"


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


# ===================================================================
# POST /assistant/query — SSE streaming
# ===================================================================


class TestAssistantQuery:
    @pytest.mark.asyncio
    async def test_returns_sse_stream(self, auth_client):
        resp = await auth_client.post(
            "/api/v1/assistant/query",
            json={"query": "Help me label this", "screen": "review"},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

        # Parse SSE events from the response body
        lines = resp.text.strip().split("\n")
        data_lines = [ln for ln in lines if ln.startswith("data: ")]
        assert len(data_lines) >= 2  # at least one data event + [DONE]

        # First data line should be a valid JSON AssistantResponse
        first_data = data_lines[0].removeprefix("data: ")
        payload = json.loads(first_data)
        assert "response" in payload
        assert "context_used" in payload
        assert "suggested_actions" in payload
        assert "model_profile_id" in payload

        # Last data line should be [DONE]
        last_data = data_lines[-1].removeprefix("data: ")
        assert last_data == "[DONE]"

    @pytest.mark.asyncio
    async def test_requires_auth(self, _app):
        transport = ASGITransport(app=_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post(
                "/api/v1/assistant/query",
                json={"query": "test", "screen": "review"},
            )
            assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_validation_error(self, auth_client):
        resp = await auth_client.post("/api/v1/assistant/query", json={})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_accepts_optional_fields(self, auth_client):
        resp = await auth_client.post(
            "/api/v1/assistant/query",
            json={
                "query": "Explain this label",
                "screen": "review",
                "record_id": str(uuid.uuid4()),
                "model_profile_id": "gpt-4o",
            },
        )
        assert resp.status_code == 200
        lines = resp.text.strip().split("\n")
        data_lines = [ln for ln in lines if ln.startswith("data: ")]
        first_data = data_lines[0].removeprefix("data: ")
        payload = json.loads(first_data)
        assert payload["model_profile_id"] == "gpt-4o"


# ===================================================================
# GET /assistant/context
# ===================================================================


class TestAssistantContext:
    @pytest.mark.asyncio
    async def test_returns_200(self, auth_client):
        resp = await auth_client.get("/api/v1/assistant/context")
        assert resp.status_code == 200
        body = resp.json()
        assert "workspace_summary" in body
        assert "active_workflow" in body
        assert "queue_stats" in body
        assert "recent_agent_runs" in body
        assert "recent_validation_results" in body
        assert "context_token_count" in body

    @pytest.mark.asyncio
    async def test_requires_auth(self, _app):
        transport = ASGITransport(app=_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/api/v1/assistant/context")
            assert resp.status_code == 401

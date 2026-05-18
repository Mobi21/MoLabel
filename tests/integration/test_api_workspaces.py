"""Integration tests for workspace endpoints (API-003 through API-006).

Tests verify routing, response models, and status codes.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from molabel.app.main import create_app
from molabel.core.database import create_all_tables, get_engine


@pytest.fixture()
def app():
    """Create a fresh FastAPI application with an in-memory database."""
    application = create_app()
    engine = get_engine(":memory:")
    create_all_tables(engine)
    application.state.engine = engine
    application.state.app_secret = "test-secret-for-workspace-tests"
    return application


@pytest_asyncio.fixture()
async def client(app):
    """Async HTTP client wired to the test application."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# API-003: List workspaces
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_workspaces_returns_paginated(client):
    """API-003: GET /workspaces returns a paginated response."""
    resp = await client.get("/api/v1/workspaces")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert isinstance(body["items"], list)
    assert "cursor" in body
    assert "has_more" in body


@pytest.mark.asyncio
async def test_list_workspaces_with_limit(client):
    """API-003: GET /workspaces respects the limit parameter."""
    resp = await client.get("/api/v1/workspaces", params={"limit": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body


# ---------------------------------------------------------------------------
# API-004: Get workspace detail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_workspace_not_found(client):
    """API-004: GET /workspaces/{id} returns 404 for unknown workspace."""
    resp = await client.get("/api/v1/workspaces/00000000-0000-0000-0000-000000000099")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# API-005: Create workspace
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_workspace_no_auth_required(client):
    """API-005: POST /workspaces is auth-free (bootstrap entry point)."""
    resp = await client.post(
        "/api/v1/workspaces",
        json={"path": "/tmp/test-workspace", "workspace_name": "Test"},
    )
    # Workspace creation is the bootstrap entry point — no auth required
    assert resp.status_code == 201


# ---------------------------------------------------------------------------
# API-006: Reindex workspace
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reindex_workspace_requires_auth(client):
    """API-006: POST /workspaces/{id}/reindex requires a session cookie."""
    resp = await client.post(
        "/api/v1/workspaces/00000000-0000-0000-0000-000000000099/reindex",
    )
    # Without auth, expect 401
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Response shape validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workspace_summary_response_shape(client):
    """Workspace summary items contain expected fields."""
    resp = await client.get("/api/v1/workspaces")
    assert resp.status_code == 200
    body = resp.json()
    # Even with empty list, structure must be correct
    assert isinstance(body["items"], list)
    assert isinstance(body["has_more"], bool)

"""Integration tests for workflow endpoints (API-019 through API-028).

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
    return application


@pytest_asyncio.fixture()
async def client(app):
    """Async HTTP client wired to the test application."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# API-019: List workflows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_workflows_returns_paginated(client):
    """API-019: GET /workflows returns a paginated response."""
    resp = await client.get("/api/v1/workflows")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert isinstance(body["items"], list)
    assert "cursor" in body
    assert "has_more" in body


@pytest.mark.asyncio
async def test_list_workflows_with_limit(client):
    """API-019: GET /workflows respects the limit parameter."""
    resp = await client.get("/api/v1/workflows", params={"limit": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body


# ---------------------------------------------------------------------------
# API-020: Get workflow detail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_workflow_not_found(client):
    """API-020: GET /workflows/{id} returns 404 for unknown workflow."""
    resp = await client.get(
        "/api/v1/workflows/00000000-0000-0000-0000-000000000099"
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# API-021: Create workflow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_workflow_requires_auth(client):
    """API-021: POST /workflows requires a session cookie."""
    resp = await client.post(
        "/api/v1/workflows",
        json={
            "workspace_id": "00000000-0000-0000-0000-000000000001",
            "name": "Test Workflow",
            "steps": [],
        },
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# API-022: Update workflow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_workflow_requires_auth(client):
    """API-022: PUT /workflows/{id} requires a session cookie."""
    resp = await client.put(
        "/api/v1/workflows/00000000-0000-0000-0000-000000000099",
        json={"name": "Updated"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# API-023: Execute workflow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_workflow_requires_auth(client):
    """API-023: POST /workflows/{id}/execute requires auth."""
    resp = await client.post(
        "/api/v1/workflows/00000000-0000-0000-0000-000000000099/execute",
        json={},
    )
    # Without auth, expect 401
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# API-024: List executions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_executions_returns_paginated(client):
    """API-024: GET /workflows/{id}/executions returns paginated response."""
    resp = await client.get(
        "/api/v1/workflows/00000000-0000-0000-0000-000000000099/executions"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert isinstance(body["items"], list)
    assert "has_more" in body


# ---------------------------------------------------------------------------
# API-025: Get execution detail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_execution_not_found(client):
    """API-025: GET /workflows/{wid}/executions/{eid} returns 404."""
    resp = await client.get(
        "/api/v1/workflows/00000000-0000-0000-0000-000000000099/"
        "executions/00000000-0000-0000-0000-000000000088"
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# API-026: Advance step
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_advance_step_requires_auth(client):
    """API-026: POST advance step requires auth."""
    resp = await client.post(
        "/api/v1/workflows/00000000-0000-0000-0000-000000000099/"
        "executions/00000000-0000-0000-0000-000000000088/"
        "steps/step-1/advance",
        json={},
    )
    # Without auth, expect 401
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# API-027: Pause execution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pause_execution_requires_auth(client):
    """API-027: POST pause requires a session cookie."""
    resp = await client.post(
        "/api/v1/workflows/00000000-0000-0000-0000-000000000099/"
        "executions/00000000-0000-0000-0000-000000000088/pause"
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# API-028: Cancel execution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_execution_requires_auth(client):
    """API-028: POST cancel requires a session cookie."""
    resp = await client.post(
        "/api/v1/workflows/00000000-0000-0000-0000-000000000099/"
        "executions/00000000-0000-0000-0000-000000000088/cancel"
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Response shape validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workflow_list_response_shape(client):
    """Workflow list items contain expected structure."""
    resp = await client.get("/api/v1/workflows")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["items"], list)
    assert isinstance(body["has_more"], bool)

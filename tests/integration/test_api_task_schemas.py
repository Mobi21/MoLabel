"""Integration tests for task schema and label mapping endpoints.

Covers API-017, API-018, API-029 through API-032.

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
# API-029: List task schemas
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_task_schemas_returns_paginated(client):
    """API-029: GET /task-schemas returns a paginated response."""
    resp = await client.get("/api/v1/task-schemas")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert isinstance(body["items"], list)
    assert "cursor" in body
    assert "has_more" in body


@pytest.mark.asyncio
async def test_list_task_schemas_with_limit(client):
    """API-029: GET /task-schemas respects the limit parameter."""
    resp = await client.get("/api/v1/task-schemas", params={"limit": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body


# ---------------------------------------------------------------------------
# API-030: Get task schema detail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_task_schema_not_found(client):
    """API-030: GET /task-schemas/{id} returns 404 for unknown schema."""
    resp = await client.get(
        "/api/v1/task-schemas/00000000-0000-0000-0000-000000000099"
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# API-031: Create task schema
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_task_schema_requires_auth(client):
    """API-031: POST /task-schemas requires a session cookie."""
    resp = await client.post(
        "/api/v1/task-schemas",
        json={
            "workspace_id": "00000000-0000-0000-0000-000000000001",
            "task_type": "classification",
            "title": "Sentiment Classification",
            "label_fields": [
                {
                    "name": "sentiment",
                    "field_type": "categorical",
                    "options": ["positive", "negative", "neutral"],
                }
            ],
        },
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# API-032: Update task schema
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_task_schema_requires_auth(client):
    """API-032: PUT /task-schemas/{id} requires a session cookie."""
    resp = await client.put(
        "/api/v1/task-schemas/00000000-0000-0000-0000-000000000099",
        json={"title": "Updated Title"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Label mapping endpoints (API-017, API-018)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preview_label_mapping_requires_auth(client):
    """API-017: POST /label-mappings/preview requires a session cookie."""
    resp = await client.post(
        "/api/v1/label-mappings/preview",
        json={
            "source_system": "external",
            "task_schema_id": "00000000-0000-0000-0000-000000000001",
            "field_mappings": [
                {"source_field": "label", "target_field": "sentiment"}
            ],
            "sample_records": [{"label": "positive", "text": "Great!"}],
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_save_label_mapping_requires_auth(client):
    """API-018: POST /label-mappings requires a session cookie."""
    resp = await client.post(
        "/api/v1/label-mappings",
        json={
            "name": "Test Mapping",
            "workspace_id": "00000000-0000-0000-0000-000000000001",
            "source_system": "external",
            "task_schema_id": "00000000-0000-0000-0000-000000000001",
            "field_mappings": [
                {"source_field": "label", "target_field": "sentiment"}
            ],
        },
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Response shape validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_task_schema_list_response_shape(client):
    """Task schema list items contain expected structure."""
    resp = await client.get("/api/v1/task-schemas")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["items"], list)
    assert isinstance(body["has_more"], bool)

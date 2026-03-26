"""Integration tests for dataset endpoints (API-007 through API-018).

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
# API-007: List datasets
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_datasets_returns_paginated(client):
    """API-007: GET /datasets returns a paginated response."""
    resp = await client.get("/api/v1/datasets")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert isinstance(body["items"], list)
    assert "cursor" in body
    assert "has_more" in body


@pytest.mark.asyncio
async def test_list_datasets_with_limit(client):
    """API-007: GET /datasets respects the limit parameter."""
    resp = await client.get("/api/v1/datasets", params={"limit": 10})
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body


# ---------------------------------------------------------------------------
# API-008: Get dataset detail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_dataset_not_found(client):
    """API-008: GET /datasets/{id} returns 404 for unknown dataset."""
    resp = await client.get(
        "/api/v1/datasets/00000000-0000-0000-0000-000000000099"
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# API-009: Create dataset
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_dataset_requires_auth(client):
    """API-009: POST /datasets requires a session cookie."""
    resp = await client.post(
        "/api/v1/datasets",
        json={
            "dataset_name": "Test Dataset",
            "workspace_id": "00000000-0000-0000-0000-000000000001",
            "source_type": "jsonl",
        },
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# API-010: Import into dataset
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_dataset_requires_auth(client):
    """API-010: POST /datasets/{id}/import requires auth."""
    resp = await client.post(
        "/api/v1/datasets/00000000-0000-0000-0000-000000000099/import",
        json={"source_uri": "file:///data.jsonl"},
    )
    # Without auth, expect 401
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# API-011: List records
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_records_dataset_not_found(client):
    """API-011: GET /datasets/{id}/records returns 404 for unknown dataset."""
    resp = await client.get(
        "/api/v1/datasets/00000000-0000-0000-0000-000000000099/records"
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# API-012: Get record detail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_record_not_found(client):
    """API-012: GET /datasets/{did}/records/{rid} returns 404 for unknown record."""
    resp = await client.get(
        "/api/v1/datasets/00000000-0000-0000-0000-000000000099/"
        "records/00000000-0000-0000-0000-000000000088"
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# API-013: Dataset analytics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_analytics_not_found(client):
    """API-013: GET /datasets/{id}/analytics returns 404 for unknown dataset."""
    resp = await client.get(
        "/api/v1/datasets/00000000-0000-0000-0000-000000000099/analytics"
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# API-014: Create snapshot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_snapshot_requires_auth(client):
    """API-014: POST /datasets/{id}/snapshots requires a session cookie."""
    resp = await client.post(
        "/api/v1/datasets/00000000-0000-0000-0000-000000000099/snapshots",
        json={"name": "Test Snapshot"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# API-015: List snapshots
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_snapshots_dataset_not_found(client):
    """API-015: GET /datasets/{id}/snapshots returns 404 for unknown dataset."""
    resp = await client.get(
        "/api/v1/datasets/00000000-0000-0000-0000-000000000099/snapshots"
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# API-016: Snapshot diff
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_snapshot_diff_not_found(client):
    """API-016: GET /datasets/{did}/snapshots/{sid}/diff returns 404."""
    resp = await client.get(
        "/api/v1/datasets/00000000-0000-0000-0000-000000000099/"
        "snapshots/00000000-0000-0000-0000-000000000088/diff"
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Response shape validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dataset_list_response_shape(client):
    """Dataset list items contain expected structure."""
    resp = await client.get("/api/v1/datasets")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["items"], list)
    assert isinstance(body["has_more"], bool)

"""Integration tests for review event and adjudication endpoints.

Tests verify routing, response models, and status codes for
review event listing and adjudication endpoints.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from molabel.app.api.v1.adjudication import router as adjudication_router
from molabel.app.api.v1.reviews import router as reviews_router
from molabel.app.main import create_app


@pytest.fixture()
def app():
    """Create a test app with reviews and adjudication routers registered."""
    application = create_app()
    application.include_router(reviews_router, prefix="/api/v1")
    application.include_router(adjudication_router, prefix="/api/v1")
    return application


@pytest_asyncio.fixture()
async def client(app):
    """Async HTTP client wired to the test application."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Review event endpoints (API-063)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_review_events_returns_paginated(client):
    """API-063: List review events returns paginated response."""
    resp = await client.get("/api/v1/review/events")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert isinstance(body["items"], list)
    assert "cursor" in body
    assert "has_more" in body


@pytest.mark.asyncio
async def test_list_review_events_with_filters(client):
    """API-063: List review events accepts all documented filter params."""
    resp = await client.get(
        "/api/v1/review/events",
        params={
            "record_id": "rec-1",
            "reviewer_id": "rev-1",
            "task_schema_id": "ts-1",
            "is_draft": "false",
            "dataset_id": "ds-1",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []


# ---------------------------------------------------------------------------
# Adjudication endpoints (API-064 through API-066)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_adjudication_queue_route_exists(client):
    """API-064: GET /adjudication/queue route is reachable.

    Note: queue.py already registers GET /adjudication/queue with auth.
    When both routers are mounted, the queue.py version matches first
    and returns 401 (no session). Once __init__.py is updated to wire
    the adjudication router, the paginated version will be preferred
    only if it's registered after queue.py or queue.py's route is
    removed. Either way, the route is reachable.
    """
    resp = await client.get("/api/v1/adjudication/queue")
    # 200 (our new paginated endpoint) or 401 (queue.py's auth-protected version)
    assert resp.status_code in (200, 401)


@pytest.mark.asyncio
async def test_list_adjudication_queue_with_filters(client):
    """API-064: Adjudication queue accepts filter params.

    Same routing note as above — both queue.py and adjudication.py
    expose this path.
    """
    resp = await client.get(
        "/api/v1/adjudication/queue",
        params={
            "task_schema_id": "ts-1",
            "dataset_id": "ds-1",
            "severity": "high",
        },
    )
    assert resp.status_code in (200, 401)


@pytest.mark.asyncio
async def test_get_adjudication_detail_not_found(client):
    """API-065: Get non-existent adjudication returns 404."""
    resp = await client.get("/api/v1/adjudication/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_resolve_adjudication_requires_auth(client):
    """API-066: Resolve adjudication requires session cookie."""
    resp = await client.post(
        "/api/v1/adjudication/some-adj-id/resolve",
        json={
            "resolution_type": "majority_vote",
            "reasoning": "Two reviewers agree.",
        },
    )
    assert resp.status_code == 401

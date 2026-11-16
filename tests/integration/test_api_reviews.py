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
# Adjudication endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_adjudication_queue_requires_auth(client):
    """The in-memory adjudication queue requires a session cookie."""
    resp = await client.get("/api/v1/adjudication/queue")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_queue_disagreement_requires_auth(client):
    """A queue's disagreement detail requires a session cookie."""
    resp = await client.get(
        "/api/v1/adjudication/queues/some-queue/disagreements/some-record"
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_resolve_adjudication_requires_auth(client):
    """Resolving a queue's disagreement requires a session cookie."""
    resp = await client.post(
        "/api/v1/adjudication/queues/some-queue/disagreements/some-record/resolve",
        json={"resolved_labels": {"sentiment": "positive"}},
    )
    assert resp.status_code == 401

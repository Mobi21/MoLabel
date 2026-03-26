"""Integration tests for prompt and correction endpoints (API-053 through API-057).

Tests verify routing, response models, and status codes for all
prompt and correction endpoints.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from molabel.app.api.v1.corrections import router as corrections_router
from molabel.app.api.v1.prompts import router as prompts_router
from molabel.app.main import create_app


@pytest.fixture()
def app():
    """Create a test app with prompts and corrections routers registered."""
    application = create_app()
    application.include_router(prompts_router, prefix="/api/v1")
    application.include_router(corrections_router, prefix="/api/v1")
    return application


@pytest_asyncio.fixture()
async def client(app):
    """Async HTTP client wired to the test application."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Prompt endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_prompts_requires_workspace_id(client):
    """API-053: List prompts requires workspace_id query param."""
    resp = await client.get("/api/v1/prompts")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_prompts_returns_paginated(client):
    """API-053: List returns paginated response with correct shape."""
    resp = await client.get(
        "/api/v1/prompts",
        params={"workspace_id": "ws-1"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert isinstance(body["items"], list)
    assert "cursor" in body
    assert "has_more" in body


@pytest.mark.asyncio
async def test_list_prompts_with_filters(client):
    """API-053: List accepts agent_role and task_schema_id filters."""
    resp = await client.get(
        "/api/v1/prompts",
        params={
            "workspace_id": "ws-1",
            "agent_role": "labeler",
            "task_schema_id": "ts-1",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []


@pytest.mark.asyncio
async def test_get_prompt_not_found(client):
    """API-054: Get non-existent prompt returns 404."""
    resp = await client.get("/api/v1/prompts/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_prompt_requires_auth(client):
    """API-055: Create prompt requires session cookie."""
    resp = await client.post(
        "/api/v1/prompts",
        json={
            "workspace_id": "ws-1",
            "name": "Test Prompt",
            "agent_role": "labeler",
            "task_schema_id": "ts-1",
            "system_instructions": "Label the text.",
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_update_prompt_requires_auth(client):
    """API-056: Update prompt requires session cookie."""
    resp = await client.put(
        "/api/v1/prompts/some-prompt-id",
        json={"system_instructions": "Updated instructions."},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_prompt_diff_not_found(client):
    """API-057: Diff for non-existent prompt returns 404."""
    resp = await client.get(
        "/api/v1/prompts/nonexistent-id/diff",
        params={"v1": "v1", "v2": "v2"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_prompt_diff_requires_version_params(client):
    """API-057: Diff requires v1 and v2 query params."""
    resp = await client.get("/api/v1/prompts/some-id/diff")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Correction endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_correction_batches_returns_paginated(client):
    """List correction batches returns paginated response."""
    resp = await client.get("/api/v1/corrections")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert isinstance(body["items"], list)
    assert "cursor" in body
    assert "has_more" in body


@pytest.mark.asyncio
async def test_list_correction_batches_with_filters(client):
    """List correction batches accepts all filter params."""
    resp = await client.get(
        "/api/v1/corrections",
        params={
            "workspace_id": "ws-1",
            "task_schema_id": "ts-1",
            "prompt_template_id": "pt-1",
            "status": "ready",
        },
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_trigger_analysis_requires_auth(client):
    """Trigger analysis requires session cookie."""
    resp = await client.post(
        "/api/v1/corrections/analyze",
        json={"batch_id": "batch-1"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_refinement_not_found(client):
    """Get refinement for non-existent batch returns 404."""
    resp = await client.get("/api/v1/corrections/nonexistent-batch/refinement")
    assert resp.status_code == 404

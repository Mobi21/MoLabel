"""Integration tests for review event and adjudication endpoints.

Tests verify routing, response models, status codes, and that review event
listing reads only the session's workspace.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import text

from tests.integration.review_flow import (
    _as,
    _start_review,
    review_app,
    review_client,
)
from tests.integration.test_api_review_workspaces import _outsider


@pytest.fixture()
def app(tmp_path):
    return review_app(tmp_path)


@pytest_asyncio.fixture()
async def client(app):
    async with review_client(app) as c:
        yield c


def _filters_of(app, workspace_id):
    """A record, dataset, task schema and reviewer id of the workspace."""
    with app.state.engine.connect() as conn:
        record_id, dataset_id = conn.execute(
            text("SELECT id, dataset_id FROM records WHERE workspace_id = :w LIMIT 1"),
            {"w": workspace_id},
        ).one()
        task_schema_id, reviewer_id = (
            conn.execute(
                text(f"SELECT id FROM {table} WHERE workspace_id = :w LIMIT 1"),
                {"w": workspace_id},
            ).scalar_one()
            for table in ("task_schemas", "reviewer_profiles")
        )
    return {
        "record_id": record_id,
        "dataset_id": dataset_id,
        "task_schema_id": task_schema_id,
        "reviewer_id": reviewer_id,
    }


# ---------------------------------------------------------------------------
# Review event endpoints (API-063)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_listing_review_events_needs_a_session(client):
    resp = await client.get("/api/v1/review/events")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_review_events_returns_paginated(client, app, tmp_path):
    """API-063: List review events returns paginated response."""
    _, tokens, _ = await _start_review(client, app, tmp_path)

    resp = await client.get("/api/v1/review/events", headers=_as(tokens[0]))

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["items"], list)
    assert "cursor" in body
    assert "has_more" in body


@pytest.mark.asyncio
async def test_list_review_events_with_filters(client, app, tmp_path):
    """API-063: Every filter may name a row of the caller's workspace."""
    workspace_id, tokens, _ = await _start_review(client, app, tmp_path)

    resp = await client.get(
        "/api/v1/review/events",
        params={**_filters_of(app, workspace_id), "is_draft": "false"},
        headers=_as(tokens[0]),
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["items"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name", ["record_id", "dataset_id", "task_schema_id", "reviewer_id"]
)
async def test_a_filter_naming_another_workspace_answers_404(
    client, app, tmp_path, name
):
    workspace_id, _, _ = await _start_review(client, app, tmp_path)
    outsider = _outsider(app, tmp_path)

    resp = await client.get(
        "/api/v1/review/events",
        params={name: _filters_of(app, workspace_id)[name]},
        headers=_as(outsider),
    )

    assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# Adjudication endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_queue_disagreements_requires_auth(client):
    """A queue's disagreements require a session cookie."""
    resp = await client.get("/api/v1/adjudication/queues/some-queue/disagreements")
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

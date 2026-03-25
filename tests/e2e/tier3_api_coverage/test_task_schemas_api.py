"""Tier 3 — API Coverage: Task Schemas (T3-07).

Tests:
    T3-07: CRUD for categorical + JSON schema types
"""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SHARED_WORKSPACE

BASE = "/api/v1"


async def _setup_auth(client: InstrumentedClient) -> tuple[str, str]:
    """Return (reviewer_id, workspace_id) after login."""
    rp = await client.post(
        f"{BASE}/reviewer-profiles",
        json={
            "display_name": "TS Reviewer",
            "workspace_id": "00000000-0000-0000-0000-000000000001",
        },
    )
    assert rp.status_code == 201
    reviewer_id = rp.json()["id"]
    login = await client.post(f"{BASE}/sessions", json={"reviewer_id": reviewer_id})
    assert login.status_code == 200
    client._session_cookie = login.cookies.get("molabel_session")

    ws = await client.post(
        f"{BASE}/workspaces",
        json={"path": "/tmp/ws-schemas", "workspace_name": "Schema WS"},
    )
    assert ws.status_code == 201
    workspace_id = ws.json()["workspace_id"]
    return reviewer_id, workspace_id


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier3
async def test_task_schema_crud_categorical_and_json(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T3-07: CRUD for categorical and JSON schema task types."""

    _, workspace_id = await _setup_auth(client)

    cat_schema_id: str = ""
    with checkpoint(ctx, "create_categorical_schema"):
        resp = await client.post(
            f"{BASE}/task-schemas",
            json={
                "workspace_id": workspace_id,
                "task_type": "text_classification",
                "title": "Sentiment Classification",
                "instructions": "Classify the sentiment of the text.",
                "label_fields": [
                    {
                        "name": "sentiment",
                        "field_type": "categorical",
                        "required": True,
                        "options": ["positive", "negative", "neutral"],
                    }
                ],
                "required_fields": ["sentiment"],
                "blind_review_policy": "hide_agent_outputs_by_default",
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["task_type"] == "text_classification"
        assert body["title"] == "Sentiment Classification"
        assert len(body["label_fields"]) == 1
        cat_schema_id = body["task_schema_id"]

    with checkpoint(ctx, "get_categorical_schema"):
        resp = await client.get(f"{BASE}/task-schemas/{cat_schema_id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["task_schema_id"] == cat_schema_id
        assert body["label_fields"][0]["name"] == "sentiment"

    with checkpoint(ctx, "update_categorical_schema"):
        resp = await client.put(
            f"{BASE}/task-schemas/{cat_schema_id}",
            json={
                "title": "Updated Sentiment Schema",
                "instructions": "Updated instructions.",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["title"] == "Updated Sentiment Schema"

    json_schema_id: str = ""
    with checkpoint(ctx, "create_json_schema"):
        resp = await client.post(
            f"{BASE}/task-schemas",
            json={
                "workspace_id": workspace_id,
                "task_type": "structured_extraction",
                "title": "Invoice Extraction",
                "label_fields": [
                    {
                        "name": "extracted_data",
                        "field_type": "json",
                        "required": True,
                    }
                ],
                "required_fields": ["extracted_data"],
                "blind_review_policy": "show_agent_outputs",
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["task_type"] == "structured_extraction"
        json_schema_id = body["task_schema_id"]

    with checkpoint(ctx, "list_task_schemas"):
        resp = await client.get(f"{BASE}/task-schemas")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "items" in body
        ids = [s["task_schema_id"] for s in body["items"]]
        assert cat_schema_id in ids
        assert json_schema_id in ids

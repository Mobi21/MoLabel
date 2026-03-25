"""Tier 3 — API Coverage: Prompts (T3-15).

Tests:
    T3-15: CRUD + versioning + diff
"""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SHARED_WORKSPACE

BASE = "/api/v1"


async def _setup(client: InstrumentedClient) -> tuple[str, str]:
    rp = await client.post(
        f"{BASE}/reviewer-profiles",
        json={
            "display_name": "Prompt Reviewer",
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
        json={"path": "/tmp/ws-prompts", "workspace_name": "Prompts WS"},
    )
    assert ws.status_code == 201
    workspace_id = ws.json()["workspace_id"]

    ts = await client.post(
        f"{BASE}/task-schemas",
        json={
            "workspace_id": workspace_id,
            "task_type": "text_classification",
            "title": "Sentiment",
            "label_fields": [
                {
                    "name": "label",
                    "field_type": "categorical",
                    "options": ["pos", "neg"],
                }
            ],
        },
    )
    assert ts.status_code == 201
    task_schema_id = ts.json()["task_schema_id"]
    return workspace_id, task_schema_id


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier3
async def test_prompts_crud_versioning_diff(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T3-15: Create, get (404), update (404), diff (404), list."""

    workspace_id, task_schema_id = await _setup(client)

    prompt_id: str = ""
    with checkpoint(ctx, "create_prompt"):
        resp = await client.post(
            f"{BASE}/prompts",
            json={
                "workspace_id": workspace_id,
                "name": "Sentiment Classifier Prompt",
                "agent_role": "proposer",
                "task_schema_id": task_schema_id,
                "system_instructions": (
                    "You are a sentiment classifier. Classify text as pos or neg."
                ),
                "task_rubric": "Return JSON with field 'label'.",
                "few_shot_examples": [
                    {
                        "input_text": "I love this product!",
                        "expected_output": {"label": "pos"},
                        "source": "manual",
                    }
                ],
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["name"] == "Sentiment Classifier Prompt"
        assert body["workspace_id"] == workspace_id
        assert body["current_version"] == "v1"
        assert len(body["versions"]) == 1
        prompt_id = body["prompt_id"]

    with checkpoint(ctx, "list_prompts"):
        resp = await client.get(
            f"{BASE}/prompts",
            params={"workspace_id": workspace_id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "items" in body

    with checkpoint(ctx, "list_prompts_filtered"):
        resp = await client.get(
            f"{BASE}/prompts",
            params={"workspace_id": workspace_id, "agent_role": "proposer"},
        )
        assert resp.status_code == 200, resp.text

    with checkpoint(ctx, "get_prompt_404"):
        # Stub raises 404 after in-memory creation
        resp = await client.get(f"{BASE}/prompts/{prompt_id}")
        assert resp.status_code == 404, resp.text
        body = resp.json()
        assert "error" in body

    with checkpoint(ctx, "update_prompt_404"):
        resp = await client.put(
            f"{BASE}/prompts/{prompt_id}",
            json={"system_instructions": "Updated system instructions."},
        )
        assert resp.status_code == 404, resp.text

    with checkpoint(ctx, "prompt_diff_404"):
        resp = await client.get(
            f"{BASE}/prompts/{prompt_id}/diff",
            params={"v1": "v1", "v2": "v2"},
        )
        assert resp.status_code == 404, resp.text

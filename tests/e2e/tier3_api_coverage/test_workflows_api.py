"""Tier 3 — API Coverage: Workflows (T3-08).

Tests:
    T3-08: Full CRUD + execute (202) + pause + cancel lifecycle
"""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SHARED_WORKSPACE

BASE = "/api/v1"


async def _setup_auth_and_workspace(client: InstrumentedClient) -> str:
    rp = await client.post(
        f"{BASE}/reviewer-profiles",
        json={
            "display_name": "WF Reviewer",
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
        json={"path": "/tmp/ws-wf", "workspace_name": "WF Workspace"},
    )
    assert ws.status_code == 201
    return ws.json()["workspace_id"]


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier3
async def test_workflows_crud_execute_pause_cancel(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T3-08: Create, read, list, update workflow; execute; pause; cancel."""

    workspace_id = await _setup_auth_and_workspace(client)

    workflow_id: str = ""
    with checkpoint(ctx, "create_workflow"):
        resp = await client.post(
            f"{BASE}/workflows",
            json={
                "workspace_id": workspace_id,
                "name": "T3 Classification Pipeline",
                "description": "E2E test workflow",
                "steps": [
                    {
                        "step_id": "ingest",
                        "step_type": "data_ingest",
                        "label": "Ingest Data",
                        "config": {},
                    },
                    {
                        "step_id": "agent",
                        "step_type": "agent_run",
                        "label": "Run Agent",
                        "config": {},
                    },
                ],
                "edges": [{"source_step_id": "ingest", "target_step_id": "agent"}],
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["name"] == "T3 Classification Pipeline"
        assert len(body["steps"]) == 2
        workflow_id = body["workflow_id"]

    with checkpoint(ctx, "get_workflow"):
        resp = await client.get(f"{BASE}/workflows/{workflow_id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["workflow_id"] == workflow_id

    with checkpoint(ctx, "list_workflows"):
        resp = await client.get(f"{BASE}/workflows")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "items" in body
        ids = [w["workflow_id"] for w in body["items"]]
        assert workflow_id in ids

    with checkpoint(ctx, "update_workflow"):
        resp = await client.put(
            f"{BASE}/workflows/{workflow_id}",
            json={"description": "Updated description"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["description"] == "Updated description"

    execution_id: str = ""
    with checkpoint(ctx, "execute_workflow"):
        resp = await client.post(
            f"{BASE}/workflows/{workflow_id}/execute",
            json={"context": {"run_label": "t3-test"}},
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["workflow_definition_id"] == workflow_id
        assert body["status"] in ("pending", "running")
        execution_id = body["execution_id"]

    with checkpoint(ctx, "list_executions"):
        resp = await client.get(f"{BASE}/workflows/{workflow_id}/executions")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "items" in body
        exec_ids = [e["execution_id"] for e in body["items"]]
        assert execution_id in exec_ids

    with checkpoint(ctx, "get_execution_detail"):
        resp = await client.get(
            f"{BASE}/workflows/{workflow_id}/executions/{execution_id}"
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["execution_id"] == execution_id

    with checkpoint(ctx, "pause_execution"):
        resp = await client.post(
            f"{BASE}/workflows/{workflow_id}/executions/{execution_id}/pause"
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "paused"

    with checkpoint(ctx, "cancel_execution"):
        resp = await client.post(
            f"{BASE}/workflows/{workflow_id}/executions/{execution_id}/cancel"
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "cancelled"

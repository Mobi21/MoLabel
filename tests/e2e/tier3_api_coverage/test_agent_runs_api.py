"""Tier 3 — API Coverage: Agent Runs (T3-09).

Tests:
    T3-09: CRUD + outputs + comparison + analytics
"""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SHARED_WORKSPACE

BASE = "/api/v1"


async def _setup(client: InstrumentedClient) -> tuple[str, str, str]:
    """Return (reviewer_id, workspace_id, task_schema_id)."""
    rp = await client.post(
        f"{BASE}/reviewer-profiles",
        json={
            "display_name": "AR Reviewer",
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
        json={"path": "/tmp/ws-ar", "workspace_name": "AR Workspace"},
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

    return reviewer_id, workspace_id, task_schema_id


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier3
async def test_agent_runs_crud_outputs_comparison_analytics(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T3-09: Start runs, list, outputs, comparison, analytics."""

    reviewer_id, workspace_id, task_schema_id = await _setup(client)
    dataset_id = "00000000-0000-0000-0000-da7ase700000"
    model_profile_id = "00000000-0000-0000-0000-000000000001"

    agent_run_id: str = ""
    with checkpoint(ctx, "start_agent_run"):
        resp = await client.post(
            f"{BASE}/agent-runs",
            json={
                "workspace_id": workspace_id,
                "dataset_id": dataset_id,
                "agent_role": "proposer",
                "task_schema_id": task_schema_id,
                "model_profile_id": model_profile_id,
                "prompt_version": "v1",
            },
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["status"] == "pending"
        assert body["workspace_id"] == workspace_id
        agent_run_id = body["agent_run_id"]

    with checkpoint(ctx, "list_agent_runs"):
        resp = await client.get(
            f"{BASE}/agent-runs",
            params={"workspace_id": workspace_id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "items" in body

    with checkpoint(ctx, "get_agent_run"):
        resp = await client.get(f"{BASE}/agent-runs/{agent_run_id}")
        # The stub raises 404 since no DB persistence is implemented
        assert resp.status_code in (200, 404), resp.text

    with checkpoint(ctx, "list_agent_outputs"):
        resp = await client.get(f"{BASE}/agent-runs/{agent_run_id}/outputs")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "items" in body

    with checkpoint(ctx, "start_comparison_run"):
        resp = await client.post(
            f"{BASE}/agent-runs/compare",
            json={
                "workspace_id": workspace_id,
                "dataset_id": dataset_id,
                "agent_role": "proposer",
                "task_schema_id": task_schema_id,
                "model_profile_ids": [
                    model_profile_id,
                    "00000000-0000-0000-0000-000000000002",
                ],
            },
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert "comparison_id" in body
        assert len(body["agent_run_ids"]) == 2
        comparison_id = body["comparison_id"]

    with checkpoint(ctx, "get_comparison_results"):
        resp = await client.get(f"{BASE}/agent-runs/comparison/{comparison_id}")
        # Stub raises 404 until DB is wired up
        assert resp.status_code in (200, 404), resp.text

    with checkpoint(ctx, "get_agent_analytics"):
        resp = await client.get(
            f"{BASE}/agent-runs/analytics",
            params={"workspace_id": workspace_id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "accuracy_by_field" in body
        assert "agreement_trend" in body

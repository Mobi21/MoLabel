"""Integration tests for agent run endpoints (API-041 through API-052).

Tests verify routing, response models, and status codes for all
agent-run endpoints. Mutation endpoints require auth (401 without cookie).
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine

from molabel.app.api.v1.agent_runs import router as agent_runs_router
from molabel.app.main import create_app
from molabel.core.database import create_all_tables


@pytest.fixture()
def app(tmp_path):
    """Create a test app with agent-runs router registered."""
    application = create_app()
    # Register the router under the v1 prefix so it's reachable.
    application.include_router(agent_runs_router, prefix="/api/v1")
    engine = create_engine(
        f"sqlite:///{tmp_path / 'agent-runs.db'}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    create_all_tables(engine)
    application.state.engine = engine
    application.state.app_secret = "agent-runs-test-secret"
    return application


@pytest_asyncio.fixture()
async def client(app):
    """Async HTTP client wired to the test application."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# GET endpoints (no auth required for reads)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_agent_runs_requires_workspace_id(client):
    """API-041: List agent runs requires workspace_id query param."""
    resp = await client.get("/api/v1/agent-runs")
    assert resp.status_code == 422  # validation error: missing workspace_id


@pytest.mark.asyncio
async def test_list_agent_runs_returns_paginated(client):
    """API-041: List returns paginated response with correct shape."""
    resp = await client.get(
        "/api/v1/agent-runs",
        params={"workspace_id": "ws-1"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert isinstance(body["items"], list)
    assert "cursor" in body
    assert "has_more" in body


@pytest.mark.asyncio
async def test_list_agent_runs_with_filters(client):
    """API-041: List accepts all documented filter params."""
    resp = await client.get(
        "/api/v1/agent-runs",
        params={
            "workspace_id": "ws-1",
            "dataset_id": "ds-1",
            "status": "completed",
            "agent_role": "labeler",
            "model_profile_id": "mp-1",
            "comparison_id": "cmp-1",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []


@pytest.mark.asyncio
async def test_get_agent_run_not_found(client):
    """API-042: Get non-existent agent run returns 404."""
    resp = await client.get("/api/v1/agent-runs/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_agent_run_returns_failure_envelope(client, app):
    """API-042: Failed runs expose classified recovery metadata."""
    workspace_id = str(uuid.uuid4())
    dataset_id = str(uuid.uuid4())
    task_schema_id = str(uuid.uuid4())
    model_profile_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    now = "2026-05-16T12:00:00+00:00"

    with app.state.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO workspaces ("
                "id, workspace_name, workspace_slug, core_version, root_path, "
                "manifest_path, created_at, updated_at"
                ") VALUES ("
                ":id, 'Workspace', 'workspace', '0.1.0', '/tmp/workspace', "
                "'workbench.project.yaml', :now, :now)"
            ),
            {"id": workspace_id, "now": now},
        )
        conn.execute(
            text(
                "INSERT INTO datasets ("
                "id, dataset_name, dataset_slug, source_type, canonical_id_strategy, "
                "indexing_mode, record_count, labeled_count, workspace_id, "
                "created_at, updated_at"
                ") VALUES ("
                ":id, 'Dataset', 'dataset', 'file', 'external_id', "
                "'full', 2, 0, :workspace_id, :now, :now)"
            ),
            {"id": dataset_id, "workspace_id": workspace_id, "now": now},
        )
        conn.execute(
            text(
                "INSERT INTO task_schemas ("
                "id, task_schema_slug, version, task_type, title, label_fields, "
                "blind_review_policy, is_active, is_frozen, workspace_id, "
                "created_at, updated_at"
                ") VALUES ("
                ":id, 'schema', 1, 'classification', 'Schema', '{}', "
                "'show_agent_outputs', 1, 0, :workspace_id, :now, :now)"
            ),
            {"id": task_schema_id, "workspace_id": workspace_id, "now": now},
        )
        conn.execute(
            text(
                "INSERT INTO model_profiles ("
                "id, model_profile_slug, provider_type, provider_name, "
                "model_identifier, "
                "transport, workspace_id, created_at, updated_at"
                ") VALUES ("
                ":id, 'minimax', 'anthropic', 'MiniMax', "
                "'MiniMax-M2.7-highspeed', 'anthropic_sdk', "
                ":workspace_id, :now, :now)"
            ),
            {"id": model_profile_id, "workspace_id": workspace_id, "now": now},
        )
        conn.execute(
            text(
                "INSERT INTO agent_runs ("
                "id, dataset_id, task_schema_id, model_profile_id, prompt_version, "
                "agent_role, adapter_plugin, status, config, total_records, "
                "completed_records, failed_records, retry_count, error_summary, "
                "started_at, completed_at, created_at, updated_at, workspace_id"
                ") VALUES ("
                ":id, :dataset_id, :task_schema_id, :model_profile_id, 'v1', "
                "'proposer', 'builtin.anthropic', 'failed', '{}', 2, "
                "0, 2, 1, :error_summary, :now, :now, :now, :now, :workspace_id)"
            ),
            {
                "id": run_id,
                "dataset_id": dataset_id,
                "task_schema_id": task_schema_id,
                "model_profile_id": model_profile_id,
                "workspace_id": workspace_id,
                "error_summary": "Provider login failure: missing X-Api-Key",
                "now": now,
            },
        )

    resp = await client.get(f"/api/v1/agent-runs/{run_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["agent_run_id"] == run_id
    assert body["model_identifier"] == "MiniMax-M2.7-highspeed"
    assert body["records_failed"] == 2
    assert body["failure_envelope"]["schema"] == "molabel.run.failure_envelope"
    assert body["failure_envelope"]["category"] == "provider_auth"
    assert body["failure_envelope"]["retryable"] is False
    assert body["failure_envelope"]["affected_records"] == 2
    assert (
        "molabel provider health"
        in body["failure_envelope"]["recommended_repair_commands"][1]
    )


@pytest.mark.asyncio
async def test_get_analytics_requires_workspace_id(client):
    """API-052: Analytics requires workspace_id query param."""
    resp = await client.get("/api/v1/agent-runs/analytics")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_analytics_returns_correct_shape(client):
    """API-052: Analytics returns the expected response shape."""
    resp = await client.get(
        "/api/v1/agent-runs/analytics",
        params={"workspace_id": "ws-1"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "accuracy_by_field" in body
    assert "accuracy_by_label_value" in body
    assert "accuracy_overall" in body
    assert "agreement_trend" in body
    assert "error_patterns" in body
    assert "confidence_calibration" in body
    assert "prompt_version_comparison" in body


@pytest.mark.asyncio
async def test_get_comparison_results_not_found(client):
    """API-050: Get non-existent comparison returns 404."""
    resp = await client.get("/api/v1/agent-runs/comparison/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_agent_outputs_returns_paginated(client):
    """API-047: List outputs returns empty paginated response."""
    resp = await client.get("/api/v1/agent-runs/run-1/outputs")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert body["items"] == []


@pytest.mark.asyncio
async def test_list_agent_outputs_with_normalization_filter(client):
    """API-047: List outputs accepts normalization_status filter."""
    resp = await client.get(
        "/api/v1/agent-runs/run-1/outputs",
        params={"normalization_status": "normalized"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_agent_output_for_record_not_found(client):
    """API-048: Get output for non-existent record returns 404."""
    resp = await client.get("/api/v1/agent-runs/run-1/outputs/record-1")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST endpoints (require auth — verify 401 without session)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_agent_run_requires_auth(client):
    """API-043: Start agent run requires session cookie."""
    resp = await client.post(
        "/api/v1/agent-runs",
        json={
            "workspace_id": "ws-1",
            "dataset_id": "ds-1",
            "agent_role": "labeler",
            "task_schema_id": "ts-1",
            "model_profile_id": "mp-1",
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_start_comparison_run_requires_auth(client):
    """API-044: Comparison run requires session cookie."""
    resp = await client.post(
        "/api/v1/agent-runs/compare",
        json={
            "workspace_id": "ws-1",
            "dataset_id": "ds-1",
            "agent_role": "labeler",
            "task_schema_id": "ts-1",
            "model_profile_ids": ["mp-1", "mp-2"],
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_cancel_agent_run_requires_auth(client):
    """API-045: Cancel agent run requires session cookie."""
    resp = await client.post("/api/v1/agent-runs/some-run-id/cancel")
    assert resp.status_code == 401

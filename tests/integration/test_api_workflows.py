"""Integration tests for workflow endpoints (API-019 through API-028).

Tests verify routing, response models, and status codes.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from molabel.app.main import create_app
from molabel.app.services.session import create_session_token
from molabel.core.database import create_all_tables, get_engine

TEST_SECRET = "workflow-test-secret"


@pytest.fixture()
def app(tmp_path):
    """Create a fresh FastAPI application with an in-memory database."""
    application = create_app()
    engine = get_engine(tmp_path / "workflows.db")
    create_all_tables(engine)
    application.state.engine = engine
    application.state.app_secret = TEST_SECRET
    application.state.test_workspace_root = tmp_path
    return application


@pytest_asyncio.fixture()
async def client(app):
    """Async HTTP client wired to the test application."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _seed_workspace(engine, root_path):
    workspace_id = uuid.uuid4()
    now = datetime.now(UTC).isoformat()
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO workspaces "
                "(id, workspace_name, workspace_slug, core_version, root_path, "
                "manifest_path, created_at, updated_at) "
                "VALUES (:id, :name, :slug, :version, :root_path, :manifest, "
                ":now, :now)"
            ),
            {
                "id": str(workspace_id),
                "name": "Workflow Fixture",
                "slug": "workflow-fixture",
                "version": "0.1.0",
                "root_path": str(root_path),
                "manifest": str(root_path / "workbench.project.yaml"),
                "now": now,
            },
        )
        conn.commit()
    return workspace_id


def _seed_reviewer(engine, workspace_id):
    reviewer_id = uuid.uuid4()
    now = datetime.now(UTC).isoformat()
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO reviewer_profiles "
                "(id, display_name, avatar_color, is_operator, is_active, "
                "workspace_id, created_at) "
                "VALUES (:id, :name, :color, 1, 1, :wid, :now)"
            ),
            {
                "id": str(reviewer_id),
                "name": "Workflow Reviewer",
                "color": "#2255AA",
                "wid": str(workspace_id),
                "now": now,
            },
        )
        conn.commit()
    return create_session_token(reviewer_id, TEST_SECRET)


def _seed_task_schema(engine, workspace_id):
    task_schema_id = uuid.uuid4()
    now = datetime.now(UTC).isoformat()
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO task_schemas "
                "(id, task_schema_slug, version, task_type, title, instructions, "
                "record_selector, label_fields, required_fields, optional_fields, "
                "blind_review_policy, overlap_policy, adjudication_policy, "
                "supported_agent_roles, default_model_profile_id, export_mapping, "
                "is_active, is_frozen, file_path, created_at, updated_at, "
                "workspace_id) "
                "VALUES (:id, :slug, 1, 'classification', :title, :instructions, "
                "NULL, :label_fields, '[]', '[]', 'show_agent_outputs', NULL, NULL, "
                "'[]', NULL, NULL, 1, 0, :file_path, :now, :now, :wid)"
            ),
            {
                "id": str(task_schema_id),
                "slug": "sentiment-demo-v1",
                "title": "Sentiment Demo",
                "instructions": "Review the AI sentiment label.",
                "label_fields": json.dumps(
                    [
                        {
                            "name": "sentiment",
                            "field_type": "categorical",
                            "required": True,
                            "options": ["positive", "negative", "neutral"],
                        }
                    ]
                ),
                "file_path": "workbench/config/task-schemas/sentiment-demo-v1.yaml",
                "now": now,
                "wid": str(workspace_id),
            },
        )
        conn.commit()
    return task_schema_id


def _seed_workflow(engine, workspace_id, *, include_export: bool = False):
    workflow_id = uuid.uuid4()
    now = datetime.now(UTC).isoformat()
    steps = [
        {
            "step_id": "ingest",
            "step_type": "data_ingest",
            "config": {"source": "data/reviews.jsonl"},
        },
        {
            "step_id": "agent_label",
            "step_type": "agent_run",
            "config": {
                "model": "heuristic-agent",
                "prompt_ref": "prompts/sentiment-demo-v1",
            },
        },
        {
            "step_id": "review",
            "step_type": "human_review",
            "config": {},
        },
    ]
    if include_export:
        steps.append(
            {
                "step_id": "export_results",
                "step_type": "export",
                "config": {
                    "format": "jsonl",
                    "destination": "workbench/exports/sentiment-demo",
                },
            }
        )
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO workflow_definitions "
                "(id, workflow_slug, version, name, steps, description, "
                "is_template, template_source, file_path, is_active, "
                "workspace_id, created_at, updated_at) "
                "VALUES (:id, :slug, 1, :name, :steps, :description, "
                "0, NULL, :file_path, 1, :wid, :now, :now)"
            ),
            {
                "id": str(workflow_id),
                "slug": "basic-agentic-review",
                "name": "Basic Agentic Review",
                "steps": json.dumps(steps),
                "description": "Run agent labeling then pause for review.",
                "file_path": "workbench/workflows/basic-agentic-review.yaml",
                "wid": str(workspace_id),
                "now": now,
            },
        )
        conn.commit()
    return workflow_id


def _write_demo_reviews(root_path):
    (root_path / "data").mkdir(parents=True, exist_ok=True)
    (root_path / "data" / "reviews.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"id": "r1", "text": "I love how fast this is."}),
                json.dumps({"id": "r2", "text": "This was slow and bad."}),
                json.dumps({"id": "r3", "text": "It is okay, nothing special."}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# API-019: List workflows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_workflows_returns_paginated(client):
    """API-019: GET /workflows returns a paginated response."""
    resp = await client.get("/api/v1/workflows")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert isinstance(body["items"], list)
    assert "cursor" in body
    assert "has_more" in body


@pytest.mark.asyncio
async def test_list_workflows_with_limit(client):
    """API-019: GET /workflows respects the limit parameter."""
    resp = await client.get("/api/v1/workflows", params={"limit": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body


# ---------------------------------------------------------------------------
# API-020: Get workflow detail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_workflow_not_found(client):
    """API-020: GET /workflows/{id} returns 404 for unknown workflow."""
    resp = await client.get("/api/v1/workflows/00000000-0000-0000-0000-000000000099")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# API-021: Create workflow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_workflow_requires_auth(client):
    """API-021: POST /workflows requires a session cookie."""
    resp = await client.post(
        "/api/v1/workflows",
        json={
            "workspace_id": "00000000-0000-0000-0000-000000000001",
            "name": "Test Workflow",
            "steps": [],
        },
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# API-022: Update workflow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_workflow_requires_auth(client):
    """API-022: PUT /workflows/{id} requires a session cookie."""
    resp = await client.put(
        "/api/v1/workflows/00000000-0000-0000-0000-000000000099",
        json={"name": "Updated"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# API-023: Execute workflow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_workflow_requires_auth(client):
    """API-023: POST /workflows/{id}/execute requires auth."""
    resp = await client.post(
        "/api/v1/workflows/00000000-0000-0000-0000-000000000099/execute",
        json={},
    )
    # Without auth, expect 401
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_execute_workflow_reaches_review_queue(client, app, tmp_path):
    workspace_id = _seed_workspace(app.state.engine, tmp_path)
    token = _seed_reviewer(app.state.engine, workspace_id)
    _seed_task_schema(app.state.engine, workspace_id)
    workflow_id = _seed_workflow(app.state.engine, workspace_id)

    _write_demo_reviews(tmp_path)

    resp = await client.post(
        f"/api/v1/workflows/{workflow_id}/execute",
        json={},
        headers={"Cookie": f"molabel_session={token}"},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "paused"
    assert body["current_step_id"] == "review"

    detail_resp = await client.get(
        f"/api/v1/workflows/{workflow_id}/executions/{body['execution_id']}"
    )
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    states = {item["step_id"]: item["status"] for item in detail["step_states"]}
    assert states["ingest"] == "completed"
    assert states["agent_label"] == "completed"
    assert states["review"] == "waiting_for_human"

    with app.state.engine.connect() as conn:
        queue_count = conn.execute(
            text("SELECT count(*) FROM review_tasks WHERE workspace_id = :wid"),
            {"wid": str(workspace_id)},
        ).first()
        output_count = conn.execute(
            text("SELECT count(*) FROM agent_outputs WHERE workspace_id = :wid"),
            {"wid": str(workspace_id)},
        ).first()

    assert queue_count is not None and int(queue_count[0]) == 3
    assert output_count is not None and int(output_count[0]) == 3


@pytest.mark.asyncio
async def test_review_queue_must_complete_before_advance_and_export(
    client, app, tmp_path
):
    workspace_id = _seed_workspace(app.state.engine, tmp_path)
    token = _seed_reviewer(app.state.engine, workspace_id)
    _seed_task_schema(app.state.engine, workspace_id)
    workflow_id = _seed_workflow(app.state.engine, workspace_id, include_export=True)
    _write_demo_reviews(tmp_path)

    execute_resp = await client.post(
        f"/api/v1/workflows/{workflow_id}/execute",
        json={},
        headers={"Cookie": f"molabel_session={token}"},
    )
    assert execute_resp.status_code == 202
    execution = execute_resp.json()

    with app.state.engine.connect() as conn:
        queue_row = conn.execute(
            text(
                "SELECT DISTINCT queue_id FROM review_tasks WHERE workspace_id = :wid"
            ),
            {"wid": str(workspace_id)},
        ).first()
    assert queue_row is not None
    queue_id = str(queue_row[0])

    blocked_resp = await client.post(
        f"/api/v1/workflows/{workflow_id}/executions/{execution['execution_id']}/"
        "steps/review/advance",
        json={},
        headers={"Cookie": f"molabel_session={token}"},
    )
    assert blocked_resp.status_code == 409
    assert "not complete" in blocked_resp.json()["error"]["message"]

    claim_resp = await client.post(
        f"/api/v1/queues/{queue_id}/claim",
        headers={"Cookie": f"molabel_session={token}"},
    )
    assert claim_resp.status_code == 200
    claimed = claim_resp.json()
    assert claimed["queue_empty"] is False
    task = claimed["task"]
    assert task is not None
    assert task["agent_output"] is not None

    while task is not None:
        submit_resp = await client.post(
            f"/api/v1/review-tasks/{task['id']}/submit",
            json={
                "labels": {},
                "decision": "accept_ai",
                "rationale": "Accepting agent label for benchmark flow.",
                "auto_claim_next": True,
            },
            headers={"Cookie": f"molabel_session={token}"},
        )
        assert submit_resp.status_code == 200
        submit_body = submit_resp.json()
        task = submit_body["next_task"]
        if task is not None:
            assert task["agent_output"] is not None

    advance_resp = await client.post(
        f"/api/v1/workflows/{workflow_id}/executions/{execution['execution_id']}/"
        "steps/review/advance",
        json={},
        headers={"Cookie": f"molabel_session={token}"},
    )
    assert advance_resp.status_code == 200
    detail = advance_resp.json()
    assert detail["status"] == "completed"
    step_states = {item["step_id"]: item["status"] for item in detail["step_states"]}
    assert step_states["review"] == "completed"
    assert step_states["export_results"] == "completed"
    export_bundle_ids = detail["context"]["export_bundle_ids"]
    assert export_bundle_ids

    export_path = (
        tmp_path
        / "workbench"
        / "exports"
        / "sentiment-demo"
        / f"{export_bundle_ids[0]}.jsonl"
    )
    assert export_path.is_file()

    exported_rows = [
        json.loads(line)
        for line in export_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(exported_rows) == 3
    assert all(
        row["labels"]["sentiment"] in {"positive", "negative", "neutral"}
        for row in exported_rows
    )

    with app.state.engine.connect() as conn:
        record_rows = conn.execute(
            text(
                "SELECT latest_label, label_count FROM records "
                "WHERE workspace_id = :wid"
            ),
            {"wid": str(workspace_id)},
        ).fetchall()

    assert len(record_rows) == 3
    assert all(row[0] is not None for row in record_rows)
    assert all(int(row[1]) == 1 for row in record_rows)


@pytest.mark.asyncio
async def test_review_completion_is_required_before_advancing_and_export_runs(
    client, app, tmp_path
):
    workspace_id = _seed_workspace(app.state.engine, tmp_path)
    token = _seed_reviewer(app.state.engine, workspace_id)
    _seed_task_schema(app.state.engine, workspace_id)
    workflow_id = _seed_workflow(
        app.state.engine,
        workspace_id,
        include_export=True,
    )

    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "reviews.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"id": "r1", "text": "I love how fast this is."}),
                json.dumps({"id": "r2", "text": "This was slow and bad."}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    execute_resp = await client.post(
        f"/api/v1/workflows/{workflow_id}/execute",
        json={},
        headers={"Cookie": f"molabel_session={token}"},
    )
    assert execute_resp.status_code == 202
    execution_id = execute_resp.json()["execution_id"]

    blocked_resp = await client.post(
        f"/api/v1/workflows/{workflow_id}/executions/{execution_id}/steps/review/advance",
        headers={"Cookie": f"molabel_session={token}"},
    )
    assert blocked_resp.status_code == 409
    assert "not complete" in blocked_resp.json()["error"]["message"]

    with app.state.engine.connect() as conn:
        queue_row = conn.execute(
            text("SELECT queue_id FROM review_tasks WHERE workspace_id = :wid LIMIT 1"),
            {"wid": str(workspace_id)},
        ).first()
    assert queue_row is not None
    queue_id = str(queue_row[0])

    next_task_id: str | None = None
    while True:
        if next_task_id is None:
            claim_resp = await client.post(
                f"/api/v1/queues/{queue_id}/claim",
                headers={"Cookie": f"molabel_session={token}"},
            )
            assert claim_resp.status_code == 200
            claim_body = claim_resp.json()
            if claim_body["queue_empty"]:
                break
            next_task_id = claim_body["task"]["id"]

        submit_resp = await client.post(
            f"/api/v1/review-tasks/{next_task_id}/submit",
            json={
                "labels": {},
                "decision": "accept_ai",
                "auto_claim_next": True,
            },
            headers={"Cookie": f"molabel_session={token}"},
        )
        assert submit_resp.status_code == 200
        submit_body = submit_resp.json()
        next_task = submit_body["next_task"]
        next_task_id = None if next_task is None else next_task["id"]
        if submit_body["queue_empty"]:
            break

    complete_resp = await client.post(
        f"/api/v1/workflows/{workflow_id}/executions/{execution_id}/steps/review/advance",
        headers={"Cookie": f"molabel_session={token}"},
    )
    assert complete_resp.status_code == 200
    complete_body = complete_resp.json()
    assert complete_body["status"] == "completed"

    detail_resp = await client.get(
        f"/api/v1/workflows/{workflow_id}/executions/{execution_id}"
    )
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    states = {item["step_id"]: item["status"] for item in detail["step_states"]}
    assert states["review"] == "completed"
    assert states["export_results"] == "completed"

    export_bundle_ids = detail["context"]["export_bundle_ids"]
    assert len(export_bundle_ids) == 1
    export_path = (
        tmp_path
        / "workbench"
        / "exports"
        / "sentiment-demo"
        / f"{export_bundle_ids[0]}.jsonl"
    )
    assert export_path.is_file()
    exported_rows = [
        json.loads(line)
        for line in export_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(exported_rows) == 2
    assert all(row["labels"] for row in exported_rows)

    with app.state.engine.connect() as conn:
        record_rows = conn.execute(
            text(
                "SELECT latest_label, label_count FROM records "
                "WHERE workspace_id = :wid ORDER BY sequence_index"
            ),
            {"wid": str(workspace_id)},
        ).fetchall()

    assert len(record_rows) == 2
    assert all(row[0] is not None for row in record_rows)
    assert all(int(row[1]) == 1 for row in record_rows)


# ---------------------------------------------------------------------------
# API-024: List executions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_executions_returns_paginated(client):
    """API-024: GET /workflows/{id}/executions returns paginated response."""
    resp = await client.get(
        "/api/v1/workflows/00000000-0000-0000-0000-000000000099/executions"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert isinstance(body["items"], list)
    assert "has_more" in body


# ---------------------------------------------------------------------------
# API-025: Get execution detail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_execution_not_found(client):
    """API-025: GET /workflows/{wid}/executions/{eid} returns 404."""
    resp = await client.get(
        "/api/v1/workflows/00000000-0000-0000-0000-000000000099/"
        "executions/00000000-0000-0000-0000-000000000088"
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# API-026: Advance step
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_advance_step_requires_auth(client):
    """API-026: POST advance step requires auth."""
    resp = await client.post(
        "/api/v1/workflows/00000000-0000-0000-0000-000000000099/"
        "executions/00000000-0000-0000-0000-000000000088/"
        "steps/step-1/advance",
        json={},
    )
    # Without auth, expect 401
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# API-027: Pause execution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pause_execution_requires_auth(client):
    """API-027: POST pause requires a session cookie."""
    resp = await client.post(
        "/api/v1/workflows/00000000-0000-0000-0000-000000000099/"
        "executions/00000000-0000-0000-0000-000000000088/pause"
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# API-028: Cancel execution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_execution_requires_auth(client):
    """API-028: POST cancel requires a session cookie."""
    resp = await client.post(
        "/api/v1/workflows/00000000-0000-0000-0000-000000000099/"
        "executions/00000000-0000-0000-0000-000000000088/cancel"
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Response shape validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workflow_list_response_shape(client):
    """Workflow list items contain expected structure."""
    resp = await client.get("/api/v1/workflows")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["items"], list)
    assert isinstance(body["has_more"], bool)

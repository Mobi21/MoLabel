"""Integration tests for workflow endpoints (API-019 through API-028).

Tests verify routing, response models, and status codes.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
import yaml
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from molabel.app.api.v1.workflows import _ensure_model_profile, _LlmAgentRunner
from molabel.app.main import create_app
from molabel.app.services.session import create_session_token
from molabel.core.database import get_engine
from molabel.core.migration_runner import upgrade_database
from molabel.core.providers import (
    AnthropicAdapter,
    OllamaAdapter,
    OpenAIAdapter,
    OpenRouterAdapter,
)
from molabel.core.providers.base import ProviderError
from molabel.core.providers.detection import DiscoveredProvider, ProviderDetector
from molabel.core.types import CompletionResult, HealthStatus
from molabel.core.workflow.templates import get_template_yaml, list_templates

TEST_SECRET = "workflow-test-secret"


@pytest.fixture()
def app(tmp_path):
    """Create a fresh FastAPI application with an in-memory database."""
    application = create_app()
    engine = get_engine(tmp_path / "workflows.db")
    upgrade_database(engine)
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


def _seed_workflow(
    engine,
    workspace_id,
    *,
    include_export: bool = False,
    ingest_config: dict | None = None,
    agent_config: dict | None = None,
    agent_step_type: str = "agent_run",
):
    workflow_id = uuid.uuid4()
    now = datetime.now(UTC).isoformat()
    steps = [
        {
            "step_id": "ingest",
            "step_type": "data_ingest",
            "config": ingest_config or {"source": "data/reviews.jsonl"},
        },
        {
            "step_id": "agent_label",
            "step_type": agent_step_type,
            "config": agent_config
            or {
                "model": "offline-heuristic",
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
async def test_execute_failed_step_reports_same_status_as_detail(client, app, tmp_path):
    workspace_id = _seed_workspace(app.state.engine, tmp_path)
    token = _seed_reviewer(app.state.engine, workspace_id)
    _seed_task_schema(app.state.engine, workspace_id)
    workflow_id = _seed_workflow(app.state.engine, workspace_id)

    resp = await client.post(
        f"/api/v1/workflows/{workflow_id}/execute",
        json={},
        headers={"Cookie": f"molabel_session={token}"},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["current_step_id"] == "ingest"
    assert "Data source not found" in body["error_summary"]

    detail_resp = await client.get(
        f"/api/v1/workflows/{workflow_id}/executions/{body['execution_id']}"
    )
    detail = detail_resp.json()
    assert body["status"] == detail["status"] == "paused"
    states = {item["step_id"]: item["status"] for item in detail["step_states"]}
    assert states["ingest"] == "failed"


@pytest.mark.asyncio
async def test_execute_ingests_an_imported_dataset_by_id(client, app, tmp_path):
    workspace_id = _seed_workspace(app.state.engine, tmp_path)
    token = _seed_reviewer(app.state.engine, workspace_id)
    _seed_task_schema(app.state.engine, workspace_id)
    headers = {"Cookie": f"molabel_session={token}"}
    dataset_resp = await client.post(
        "/api/v1/datasets",
        json={
            "workspace_id": str(workspace_id),
            "dataset_name": "Imported reviews",
            "source_type": "jsonl",
        },
        headers=headers,
    )
    assert dataset_resp.status_code == 201, dataset_resp.text
    dataset_id = dataset_resp.json()["dataset_id"]
    import_resp = await client.post(
        f"/api/v1/datasets/{dataset_id}/import",
        json={
            "records": [
                {"id": "r1", "text": "I love how fast this is."},
                {"id": "r2", "text": "This was slow and bad."},
            ]
        },
        headers=headers,
    )
    assert import_resp.status_code == 202, import_resp.text
    workflow_id = _seed_workflow(
        app.state.engine, workspace_id, ingest_config={"dataset_id": dataset_id}
    )

    resp = await client.post(
        f"/api/v1/workflows/{workflow_id}/execute", json={}, headers=headers
    )

    assert resp.status_code == 202
    body = resp.json()
    assert body["error_summary"] is None
    assert body["current_step_id"] == "review"
    with app.state.engine.connect() as conn:
        queued = conn.execute(
            text("SELECT count(*), min(dataset_id) FROM review_tasks")
        ).first()
    assert int(queued[0]) == 2
    assert str(queued[1]) == dataset_id


@pytest.mark.asyncio
async def test_execute_reports_an_empty_dataset_as_a_failed_ingest(
    client, app, tmp_path
):
    workspace_id = _seed_workspace(app.state.engine, tmp_path)
    token = _seed_reviewer(app.state.engine, workspace_id)
    _seed_task_schema(app.state.engine, workspace_id)
    headers = {"Cookie": f"molabel_session={token}"}
    dataset_resp = await client.post(
        "/api/v1/datasets",
        json={
            "workspace_id": str(workspace_id),
            "dataset_name": "Empty",
            "source_type": "jsonl",
        },
        headers=headers,
    )
    dataset_id = dataset_resp.json()["dataset_id"]
    workflow_id = _seed_workflow(
        app.state.engine, workspace_id, ingest_config={"dataset_id": dataset_id}
    )

    resp = await client.post(
        f"/api/v1/workflows/{workflow_id}/execute", json={}, headers=headers
    )

    body = resp.json()
    assert body["current_step_id"] == "ingest"
    assert "has no records" in body["error_summary"]


@pytest.mark.asyncio
async def test_execute_reports_an_agent_step_that_labels_no_records(
    client, app, tmp_path, monkeypatch
):
    workspace_id = _seed_workspace(app.state.engine, tmp_path)
    token = _seed_reviewer(app.state.engine, workspace_id)
    _seed_task_schema(app.state.engine, workspace_id)
    workflow_id = _seed_workflow(
        app.state.engine,
        workspace_id,
        agent_config={
            "model": "claude-sonnet-4-20250514",
            "prompt_ref": "prompts/default.yaml",
        },
    )
    _write_demo_reviews(tmp_path)

    def reject_missing_key(self, **_kwargs):
        raise ProviderError("Anthropic API error: 401 x-api-key header is required")

    monkeypatch.setattr(_LlmAgentRunner, "_label_record", reject_missing_key)

    resp = await client.post(
        f"/api/v1/workflows/{workflow_id}/execute",
        json={},
        headers={"Cookie": f"molabel_session={token}"},
    )

    assert resp.status_code == 202
    body = resp.json()
    assert body["current_step_id"] == "agent_label"
    assert "x-api-key header is required" in body["error_summary"]


PROVIDER_KEYS = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "MINIMAX_API_KEY",
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("key", "names_the_offline_switch"), [(None, True), ("sk-test", False)]
)
async def test_a_keyless_agent_step_fails_and_names_the_offline_switch(
    client, app, tmp_path, monkeypatch, key, names_the_offline_switch
):
    for name in PROVIDER_KEYS:
        monkeypatch.delenv(name, raising=False)
    if key is not None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", key)
    workspace_id = _seed_workspace(app.state.engine, tmp_path)
    token = _seed_reviewer(app.state.engine, workspace_id)
    _seed_task_schema(app.state.engine, workspace_id)
    workflow_id = _seed_workflow(
        app.state.engine,
        workspace_id,
        agent_config={
            "model": "claude-sonnet-4-20250514",
            "prompt_ref": "prompts/default.yaml",
        },
    )
    _write_demo_reviews(tmp_path)

    def reject_missing_key(self, **_kwargs):
        raise ProviderError(
            "Anthropic API error: 401 x-api-key header is required", status_code=401
        )

    monkeypatch.setattr(_LlmAgentRunner, "_label_record", reject_missing_key)

    resp = await client.post(
        f"/api/v1/workflows/{workflow_id}/execute",
        json={},
        headers={"Cookie": f"molabel_session={token}"},
    )

    body = resp.json()
    assert body["current_step_id"] == "agent_label"
    assert "x-api-key header is required" in body["error_summary"]
    hint = (
        "ANTHROPIC_API_KEY is not set. To label without an API key, recreate the "
        "workflow with `molabel workflow create --template <template-id> "
        "--provider offline`, or set `provider_type: offline` in this "
        "agent_run step's config"
    )
    assert (hint in body["error_summary"]) is names_the_offline_switch
    with app.state.engine.connect() as conn:
        adapters = conn.execute(
            text("SELECT adapter_plugin FROM agent_runs WHERE workspace_id = :wid"),
            {"wid": str(workspace_id)},
        ).fetchall()
    assert [row[0] for row in adapters] == ["builtin.anthropic"]


LOCAL_ENDPOINT = {
    "model": "llama3.1",
    "provider_type": "openai_compatible",
    "base_url": "http://localhost:1234/v1",
}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("step_config", "failure"),
    [
        (
            LOCAL_ENDPOINT,
            ProviderError("OpenAI API error: 500 model is not loaded", status_code=500),
        ),
        (
            LOCAL_ENDPOINT,
            ProviderError("OpenAI HTTP error: All connection attempts failed"),
        ),
        (
            LOCAL_ENDPOINT,
            ProviderError("OpenAI API error: 401 invalid token", status_code=401),
        ),
        (
            {"model": "gpt-4o"},
            ProviderError("OpenAI API error: 503 overloaded", status_code=503),
        ),
    ],
    ids=["local-server-error", "local-unreachable", "local-401", "hosted-non-auth"],
)
async def test_a_failure_that_is_not_a_missing_key_gets_no_key_hint(
    client, app, tmp_path, monkeypatch, hosted_calls, step_config, failure
):
    def fail(self, messages, model, **_kwargs):
        raise failure

    monkeypatch.setattr(OpenAIAdapter, "complete", fail)
    workspace_id = _seed_workspace(app.state.engine, tmp_path)

    resp = await _execute_sentiment_workflow(
        client, app, tmp_path, workspace_id, step_config
    )

    error_summary = resp.json()["error_summary"]
    assert str(failure) in error_summary
    assert "To label without an API key" not in error_summary


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "agent_config",
    [
        {"model": "offline-heuristic"},
        {"provider_type": "offline"},
        {"model": "claude-sonnet-4-20250514", "provider_type": "offline"},
    ],
    ids=["offline-model", "offline-provider", "offline-provider-over-claude-profile"],
)
async def test_an_offline_workflow_reaches_review_without_a_key(
    client, app, tmp_path, monkeypatch, agent_config
):
    for name in PROVIDER_KEYS:
        monkeypatch.delenv(name, raising=False)
    workspace_id = _seed_workspace(app.state.engine, tmp_path)
    token = _seed_reviewer(app.state.engine, workspace_id)
    _seed_task_schema(app.state.engine, workspace_id)
    with app.state.engine.connect() as conn:
        _ensure_model_profile(
            conn,
            workspace_id=str(workspace_id),
            model_identifier="claude-sonnet-4-20250514",
        )
        conn.commit()
    workflow_id = _seed_workflow(
        app.state.engine,
        workspace_id,
        agent_config={**agent_config, "prompt_ref": "prompts/default.yaml"},
    )
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "reviews.jsonl").write_text(
        "\n".join(
            json.dumps({"id": record_id, "text": text_value})
            for record_id, text_value in [
                ("r1", "A Negative experience overall."),
                ("r2", "Mostly neutral, a bit negative."),
                ("r3", "No opinion."),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    resp = await client.post(
        f"/api/v1/workflows/{workflow_id}/execute",
        json={},
        headers={"Cookie": f"molabel_session={token}"},
    )

    body = resp.json()
    assert body["error_summary"] is None
    assert body["status"] == "paused"
    assert body["current_step_id"] == "review"
    with app.state.engine.connect() as conn:
        outputs = conn.execute(
            text(
                "SELECT r.external_id, o.labels, o.raw_response, "
                "o.composite_confidence, a.adapter_plugin, p.provider_type "
                "FROM agent_outputs o "
                "JOIN records r ON r.id = o.record_id "
                "JOIN agent_runs a ON a.id = o.agent_run_id "
                "JOIN model_profiles p ON p.id = a.model_profile_id "
                "WHERE o.workspace_id = :wid ORDER BY r.external_id"
            ),
            {"wid": str(workspace_id)},
        ).fetchall()
        task_count = conn.execute(
            text("SELECT count(*) FROM review_tasks WHERE workspace_id = :wid"),
            {"wid": str(workspace_id)},
        ).scalar()

    assert task_count == 3
    assert [(row[0], json.loads(row[1])) for row in outputs] == [
        ("r1", {"sentiment": "negative"}),
        ("r2", {"sentiment": "negative"}),
        ("r3", {"sentiment": "positive"}),
    ]
    for _external_id, _labels, raw_response, confidence, adapter, provider in outputs:
        provenance = json.loads(raw_response)
        assert provenance["strategy"] == "offline-heuristic"
        assert provenance["provider_type"] == "offline"
        assert provenance["model"] == "offline-heuristic"
        assert confidence == 0.0
        assert adapter == "builtin.offline"
        assert provider == "offline"


SHARED_PROFILE_WORKSPACE = "00000000-0000-0000-0000-000000000001"


@pytest.fixture()
def hosted_calls(monkeypatch):
    for name in PROVIDER_KEYS:
        monkeypatch.delenv(name, raising=False)
    calls: list[tuple[str, str]] = []

    def complete(self, messages, model, **_kwargs):
        calls.append((self.provider_type, model))
        labels = {"sentiment": "neutral"}
        return CompletionResult(
            content=json.dumps(labels), parsed=labels, model_id=model
        )

    for adapter in (AnthropicAdapter, OpenAIAdapter, OpenRouterAdapter, OllamaAdapter):
        monkeypatch.setattr(adapter, "complete", complete)
    return calls


def _seed_other_workspace(engine, root_path, workspace_id):
    now = datetime.now(UTC).isoformat()
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO workspaces "
                "(id, workspace_name, workspace_slug, core_version, root_path, "
                "manifest_path, created_at, updated_at) "
                "VALUES (:id, 'Other', :slug, '0.1.0', :root_path, :manifest, "
                ":now, :now)"
            ),
            {
                "id": workspace_id,
                "slug": f"other-{workspace_id}",
                "root_path": str(root_path),
                "manifest": str(root_path / "workbench.project.yaml"),
                "now": now,
            },
        )
        conn.commit()


def _seed_model_profile(engine, workspace_id, *, provider_type, model, slug=None):
    profile_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO model_profiles "
                "(id, model_profile_slug, provider_type, provider_name, "
                "model_identifier, transport, auth_ref, supports_structured_output, "
                "supports_tool_use, is_available, created_at, updated_at, "
                "workspace_id) "
                "VALUES (:id, :slug, :provider_type, 'Seeded', :model, 'https', "
                "'ANTHROPIC_API_KEY', 1, 0, 1, :now, :now, :wid)"
            ),
            {
                "id": profile_id,
                "slug": slug or model,
                "provider_type": provider_type,
                "model": model,
                "now": now,
                "wid": str(workspace_id),
            },
        )
        conn.commit()
    return profile_id


def _agent_run_profiles(engine, workspace_id):
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT p.id, p.provider_type, p.workspace_id FROM agent_runs a "
                "JOIN model_profiles p ON p.id = a.model_profile_id "
                "WHERE a.workspace_id = :wid"
            ),
            {"wid": str(workspace_id)},
        ).fetchall()
    return [(str(row[0]), str(row[1]), str(row[2])) for row in rows]


async def _execute_sentiment_workflow(
    client, app, tmp_path, workspace_id, agent_config, agent_step_type="agent_run"
):
    token = _seed_reviewer(app.state.engine, workspace_id)
    _seed_task_schema(app.state.engine, workspace_id)
    workflow_id = _seed_workflow(
        app.state.engine,
        workspace_id,
        agent_config={**agent_config, "prompt_ref": "prompts/default.yaml"},
        agent_step_type=agent_step_type,
    )
    _write_demo_reviews(tmp_path)
    resp = await client.post(
        f"/api/v1/workflows/{workflow_id}/execute",
        json={},
        headers={"Cookie": f"molabel_session={token}"},
    )
    return resp


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("profile_provider", "model", "step_provider"),
    [
        ("anthropic", "offline-heuristic", "offline"),
        ("offline", "claude-sonnet-4-20250514", "anthropic"),
    ],
    ids=["offline-step-over-anthropic-profile", "anthropic-step-over-offline-profile"],
)
async def test_an_explicit_provider_never_reuses_a_profile_of_another_provider(
    client, app, tmp_path, hosted_calls, profile_provider, model, step_provider
):
    workspace_id = _seed_workspace(app.state.engine, tmp_path)
    _seed_model_profile(
        app.state.engine, workspace_id, provider_type=profile_provider, model=model
    )

    resp = await _execute_sentiment_workflow(
        client,
        app,
        tmp_path,
        workspace_id,
        {"model": model, "provider_type": step_provider},
    )

    assert resp.json()["error_summary"] is None
    assert [
        provider
        for _id, provider, _wid in _agent_run_profiles(app.state.engine, workspace_id)
    ] == [step_provider]
    expected_calls = [] if step_provider == "offline" else [(step_provider, model)] * 3
    assert hosted_calls == expected_calls


@pytest.mark.asyncio
async def test_a_step_that_pins_a_profile_of_another_provider_fails(
    client, app, tmp_path, hosted_calls, usable_providers
):
    workspace_id = _seed_workspace(app.state.engine, tmp_path)
    profile_id = _seed_model_profile(
        app.state.engine,
        workspace_id,
        provider_type="offline",
        model="claude-sonnet-4-20250514",
    )

    resp = await _execute_sentiment_workflow(
        client,
        app,
        tmp_path,
        workspace_id,
        {"model": profile_id, "provider_type": "anthropic"},
    )

    assert resp.status_code == 400, resp.text
    error = resp.json()["error"]
    assert error["code"] == "MODEL_UNRESOLVED"
    assert (
        f"Model profile {profile_id} uses provider offline, but the step sets "
        "provider_type anthropic"
    ) in error["message"]
    assert _execution_count(app.state.engine, workspace_id) == 0
    assert hosted_calls == []


@pytest.mark.asyncio
async def test_a_profile_from_another_workspace_is_never_reused(
    client, app, tmp_path, hosted_calls
):
    other_workspace = str(uuid.uuid4())
    _seed_other_workspace(app.state.engine, tmp_path / "other", other_workspace)
    _seed_model_profile(
        app.state.engine,
        other_workspace,
        provider_type="offline",
        model="claude-sonnet-4-20250514",
    )
    workspace_id = _seed_workspace(app.state.engine, tmp_path)

    resp = await _execute_sentiment_workflow(
        client, app, tmp_path, workspace_id, {"model": "claude-sonnet-4-20250514"}
    )

    assert resp.json()["error_summary"] is None
    [(_id, provider, profile_workspace)] = _agent_run_profiles(
        app.state.engine, workspace_id
    )
    assert (provider, profile_workspace) == ("anthropic", str(workspace_id))
    assert hosted_calls == [("anthropic", "claude-sonnet-4-20250514")] * 3


@pytest.mark.asyncio
@pytest.mark.parametrize("names_the_profile_by", ["slug", "id"])
async def test_a_profile_in_the_shared_profile_workspace_is_reused(
    client, app, tmp_path, hosted_calls, names_the_profile_by
):
    _seed_other_workspace(
        app.state.engine, tmp_path / "shared", SHARED_PROFILE_WORKSPACE
    )
    profile_id = _seed_model_profile(
        app.state.engine,
        SHARED_PROFILE_WORKSPACE,
        provider_type="anthropic",
        model="claude-sonnet-4-20250514",
        slug="team-claude",
    )
    workspace_id = _seed_workspace(app.state.engine, tmp_path)

    step_config = (
        {"model": "team-claude"}
        if names_the_profile_by == "slug"
        else {"model_profile_id": profile_id}
    )

    resp = await _execute_sentiment_workflow(
        client, app, tmp_path, workspace_id, step_config
    )

    assert resp.json()["error_summary"] is None
    assert _agent_run_profiles(app.state.engine, workspace_id) == [
        (profile_id, "anthropic", SHARED_PROFILE_WORKSPACE)
    ]
    assert hosted_calls == [("anthropic", "claude-sonnet-4-20250514")] * 3


@pytest.fixture()
def usable_providers(monkeypatch, hosted_calls):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    async def ollama_with_one_model(self):
        return DiscoveredProvider(
            provider_type="ollama",
            name="Ollama (local)",
            health=HealthStatus(is_healthy=True),
            base_url="http://localhost:11434",
            suggested_models=["llama3.2"],
        )

    monkeypatch.setattr(ProviderDetector, "_check_ollama", ollama_with_one_model)
    return [
        {
            "provider_type": "offline",
            "name": "Offline heuristic (no LLM)",
            "models": ["offline-heuristic"],
        },
        {"provider_type": "ollama", "name": "Ollama (local)", "models": ["llama3.2"]},
        {
            "provider_type": "anthropic",
            "name": "Anthropic",
            "models": ["claude-sonnet-4-20250514", "claude-3-5-haiku-20241022"],
        },
    ]


def _execution_count(engine, workspace_id):
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT count(*) FROM workflow_executions WHERE workspace_id = :wid"),
            {"wid": str(workspace_id)},
        ).scalar()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("step_config", "agent_step_type", "leftover_custom_profile", "unresolved"),
    [
        ({"model": "llama3.1"}, "agent_run", False, {"model": "llama3.1"}),
        ({"model": "gtp-4o"}, "agent_run", False, {"model": "gtp-4o"}),
        ({"model": "llama3.1"}, "agent_run", True, {"model": "llama3.1"}),
        (
            {"model": "gpt-4o", "provider_type": "openai"},
            "agent_run",
            False,
            {"model": "gpt-4o", "provider_type": "openai"},
        ),
        (
            {"models": ["offline-heuristic", "llama3.1"]},
            "agent_compare",
            False,
            {"model": "llama3.1"},
        ),
    ],
    ids=[
        "unknown-model",
        "typo",
        "custom-profile",
        "unknown-provider",
        "compare-model",
    ],
)
async def test_an_unresolvable_model_fails_before_any_step_runs(
    client,
    app,
    tmp_path,
    hosted_calls,
    usable_providers,
    step_config,
    agent_step_type,
    leftover_custom_profile,
    unresolved,
):
    workspace_id = _seed_workspace(app.state.engine, tmp_path)
    if leftover_custom_profile:
        _seed_model_profile(
            app.state.engine, workspace_id, provider_type="custom", model="llama3.1"
        )

    resp = await _execute_sentiment_workflow(
        client, app, tmp_path, workspace_id, step_config, agent_step_type
    )

    assert resp.status_code == 400, resp.text
    error = resp.json()["error"]
    assert error["code"] == "MODEL_UNRESOLVED"
    assert "agent_label" in error["message"]
    assert error["details"] == {
        "step_id": "agent_label",
        "model": unresolved["model"],
        "provider_type": unresolved.get("provider_type"),
        "usable_providers": usable_providers,
    }
    assert _execution_count(app.state.engine, workspace_id) == 0
    assert _agent_run_profiles(app.state.engine, workspace_id) == []
    assert hosted_calls == []


def _models_templates_ship():
    for template in list_templates():
        definition = yaml.safe_load(get_template_yaml(template["id"]))
        for step in definition["steps"]:
            config = step.get("config") or {}
            models = {
                "agent_run": [config.get("model")],
                "agent_compare": config.get("models") or [],
            }.get(step["type"], [])
            settings = {
                key: config[key]
                for key in ("provider_type", "provider_name", "base_url", "auth_ref")
                if key in config
            }
            for model in models:
                if model is not None:
                    yield pytest.param(
                        {"model": model, **settings}, id=f"{template['id']}:{model}"
                    )


@pytest.mark.asyncio
@pytest.mark.parametrize("agent_config", list(_models_templates_ship()))
async def test_every_model_a_template_ships_runs(
    client, app, tmp_path, hosted_calls, agent_config
):
    workspace_id = _seed_workspace(app.state.engine, tmp_path)

    resp = await _execute_sentiment_workflow(
        client, app, tmp_path, workspace_id, agent_config
    )

    assert resp.status_code == 202, resp.text
    assert resp.json()["error_summary"] is None


PINNING_STEPS = [
    pytest.param("agent_run", "model", id="agent_run-model"),
    pytest.param("agent_run", "model_profile_id", id="agent_run-model_profile_id"),
    pytest.param("agent_labeling", "model", id="agent_labeling-model"),
    pytest.param(
        "agent_labeling", "model_profile_id", id="agent_labeling-model_profile_id"
    ),
    pytest.param("agent_compare", "models", id="agent_compare-models"),
]


def _pinning(pin_key, profile_id):
    return {pin_key: [profile_id, profile_id] if pin_key == "models" else profile_id}


@pytest.mark.asyncio
@pytest.mark.parametrize(("agent_step_type", "pin_key"), PINNING_STEPS)
@pytest.mark.parametrize("pinned_profile", ["custom", "missing"])
async def test_a_pinned_profile_id_that_cannot_run_is_never_sent_as_a_model(
    client,
    app,
    tmp_path,
    hosted_calls,
    usable_providers,
    agent_step_type,
    pin_key,
    pinned_profile,
):
    workspace_id = _seed_workspace(app.state.engine, tmp_path)
    profile_id = (
        _seed_model_profile(
            app.state.engine, workspace_id, provider_type="custom", model="llama3.1"
        )
        if pinned_profile == "custom"
        else str(uuid.uuid4())
    )

    resp = await _execute_sentiment_workflow(
        client,
        app,
        tmp_path,
        workspace_id,
        {**_pinning(pin_key, profile_id), "provider_type": "anthropic"},
        agent_step_type,
    )

    assert resp.status_code == 400, resp.text
    error = resp.json()["error"]
    assert error["code"] == "MODEL_UNRESOLVED"
    assert error["details"] == {
        "step_id": "agent_label",
        "model": profile_id,
        "provider_type": "anthropic",
        "usable_providers": usable_providers,
    }
    assert _execution_count(app.state.engine, workspace_id) == 0
    assert _agent_run_profiles(app.state.engine, workspace_id) == []
    assert hosted_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(("agent_step_type", "pin_key"), PINNING_STEPS)
async def test_an_offline_step_that_pins_a_hosted_profile_fails(
    client, app, tmp_path, hosted_calls, usable_providers, agent_step_type, pin_key
):
    workspace_id = _seed_workspace(app.state.engine, tmp_path)
    profile_id = _seed_model_profile(
        app.state.engine,
        workspace_id,
        provider_type="anthropic",
        model="claude-sonnet-4-20250514",
    )

    resp = await _execute_sentiment_workflow(
        client,
        app,
        tmp_path,
        workspace_id,
        {**_pinning(pin_key, profile_id), "provider_type": "offline"},
        agent_step_type,
    )

    assert resp.status_code == 400, resp.text
    error = resp.json()["error"]
    assert error["code"] == "MODEL_UNRESOLVED"
    assert (
        f"Model profile {profile_id} uses provider anthropic, but the step sets "
        "provider_type offline"
    ) in error["message"]
    assert error["details"] == {
        "step_id": "agent_label",
        "model": profile_id,
        "provider_type": "offline",
        "usable_providers": usable_providers,
    }
    assert _execution_count(app.state.engine, workspace_id) == 0
    assert _agent_run_profiles(app.state.engine, workspace_id) == []
    assert hosted_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(("agent_step_type", "pin_key"), PINNING_STEPS)
async def test_an_offline_step_runs_on_the_offline_profile_it_pins(
    client, app, tmp_path, hosted_calls, agent_step_type, pin_key
):
    workspace_id = _seed_workspace(app.state.engine, tmp_path)
    profile_id = _seed_model_profile(
        app.state.engine, workspace_id, provider_type="offline", model="team-offline"
    )

    resp = await _execute_sentiment_workflow(
        client,
        app,
        tmp_path,
        workspace_id,
        {**_pinning(pin_key, profile_id), "provider_type": "offline"},
        agent_step_type,
    )

    assert resp.json()["error_summary"] is None
    run_count = 2 if agent_step_type == "agent_compare" else 1
    assert (
        _agent_run_profiles(app.state.engine, workspace_id)
        == [(profile_id, "offline", str(workspace_id))] * run_count
    )
    assert hosted_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(("agent_step_type", "pin_key"), PINNING_STEPS)
async def test_a_model_name_shaped_like_a_profile_id_runs_as_that_model(
    client, app, tmp_path, hosted_calls, agent_step_type, pin_key
):
    workspace_id = _seed_workspace(app.state.engine, tmp_path)
    model = str(uuid.uuid4())
    profile_id = _seed_model_profile(
        app.state.engine,
        workspace_id,
        provider_type="openai_compatible",
        model=model,
        slug="uuid-named-model",
    )

    resp = await _execute_sentiment_workflow(
        client,
        app,
        tmp_path,
        workspace_id,
        {**_pinning(pin_key, model), "provider_type": "openai_compatible"},
        agent_step_type,
    )

    assert resp.status_code == 202, resp.text
    assert resp.json()["error_summary"] is None
    run_count = 2 if agent_step_type == "agent_compare" else 1
    assert (
        _agent_run_profiles(app.state.engine, workspace_id)
        == [(profile_id, "openai_compatible", str(workspace_id))] * run_count
    )
    assert hosted_calls == [("openai_compatible", model)] * 3 * run_count


@pytest.mark.asyncio
@pytest.mark.parametrize(("agent_step_type", "pin_key"), PINNING_STEPS)
@pytest.mark.parametrize(
    "spell",
    [
        str.upper,
        lambda profile_id: uuid.UUID(profile_id).hex,
        lambda profile_id: f"{{{profile_id}}}",
        lambda profile_id: uuid.UUID(profile_id).urn,
    ],
    ids=["uppercase", "unhyphenated", "braced", "urn"],
)
async def test_a_pinned_profile_id_runs_its_profile_in_any_uuid_spelling(
    client, app, tmp_path, hosted_calls, agent_step_type, pin_key, spell
):
    workspace_id = _seed_workspace(app.state.engine, tmp_path)
    profile_id = _seed_model_profile(
        app.state.engine,
        workspace_id,
        provider_type="anthropic",
        model="claude-sonnet-4-20250514",
    )

    resp = await _execute_sentiment_workflow(
        client,
        app,
        tmp_path,
        workspace_id,
        _pinning(pin_key, spell(profile_id)),
        agent_step_type,
    )

    assert resp.status_code == 202, resp.text
    assert resp.json()["error_summary"] is None
    run_count = 2 if agent_step_type == "agent_compare" else 1
    assert (
        _agent_run_profiles(app.state.engine, workspace_id)
        == [(profile_id, "anthropic", str(workspace_id))] * run_count
    )
    assert hosted_calls == [("anthropic", "claude-sonnet-4-20250514")] * 3 * run_count


def _model_beside_profile_id(agent_step_type, model, profile_id, provider_type):
    model_key = "models" if agent_step_type == "agent_compare" else "model"
    config = {**_pinning(model_key, model), "model_profile_id": profile_id}
    return {**config, "provider_type": provider_type} if provider_type else config


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "agent_step_type", ["agent_run", "agent_labeling", "agent_compare"]
)
@pytest.mark.parametrize(
    ("pinned_provider", "step_provider"),
    [("anthropic", "offline"), ("offline", None)],
    ids=["hosted-pin-on-an-offline-step", "offline-pin-beside-a-hosted-model"],
)
async def test_a_model_profile_id_beside_a_model_of_another_provider_fails(
    client,
    app,
    tmp_path,
    hosted_calls,
    usable_providers,
    agent_step_type,
    pinned_provider,
    step_provider,
):
    workspace_id = _seed_workspace(app.state.engine, tmp_path)
    profile_id = _seed_model_profile(
        app.state.engine, workspace_id, provider_type=pinned_provider, model="team"
    )

    resp = await _execute_sentiment_workflow(
        client,
        app,
        tmp_path,
        workspace_id,
        _model_beside_profile_id(
            agent_step_type, "claude-sonnet-4-20250514", profile_id, step_provider
        ),
        agent_step_type,
    )

    assert resp.status_code == 400, resp.text
    error = resp.json()["error"]
    assert error["code"] == "MODEL_UNRESOLVED"
    assert error["details"] == {
        "step_id": "agent_label",
        "model": profile_id,
        "provider_type": step_provider,
        "usable_providers": usable_providers,
    }
    assert _execution_count(app.state.engine, workspace_id) == 0
    assert _agent_run_profiles(app.state.engine, workspace_id) == []
    assert hosted_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "agent_step_type", ["agent_run", "agent_labeling", "agent_compare"]
)
@pytest.mark.parametrize(
    ("pinned_provider", "step_provider"),
    [("offline", "offline"), ("anthropic", None)],
    ids=["offline", "hosted"],
)
async def test_a_model_profile_id_beside_a_model_of_its_provider_runs(
    client, app, tmp_path, hosted_calls, agent_step_type, pinned_provider, step_provider
):
    workspace_id = _seed_workspace(app.state.engine, tmp_path)
    profile_id = _seed_model_profile(
        app.state.engine, workspace_id, provider_type=pinned_provider, model="team"
    )
    model = "claude-sonnet-4-20250514"

    resp = await _execute_sentiment_workflow(
        client,
        app,
        tmp_path,
        workspace_id,
        _model_beside_profile_id(agent_step_type, model, profile_id, step_provider),
        agent_step_type,
    )

    assert resp.status_code == 202, resp.text
    assert resp.json()["error_summary"] is None
    run_count = 2 if agent_step_type == "agent_compare" else 1
    assert [
        provider
        for _id, provider, _wid in _agent_run_profiles(app.state.engine, workspace_id)
    ] == [pinned_provider] * run_count
    expected_calls = [] if pinned_provider == "offline" else [(pinned_provider, model)]
    assert hosted_calls == expected_calls * 3 * run_count


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
                "decision": "accept",
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
        decisions = conn.execute(
            text("SELECT decision FROM review_events WHERE workspace_id = :wid"),
            {"wid": str(workspace_id)},
        ).fetchall()

    assert len(record_rows) == 3
    assert all(row[0] is not None for row in record_rows)
    assert all(int(row[1]) == 1 for row in record_rows)
    assert [row[0] for row in decisions] == ["accept", "accept", "accept"]


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
                "decision": "accept",
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

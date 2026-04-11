"""Integration tests for CLI-specific additive endpoints."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from molabel.app.main import create_app
from molabel.app.services.session import create_session_token
from molabel.core.database import create_all_tables
from molabel.core.models import Dataset, DatasetSnapshot, Record

TEST_SECRET = "test-secret-for-cli-tests"


@pytest.fixture()
def app(tmp_path):
    application = create_app()
    engine = create_engine(
        f"sqlite:///{tmp_path / 'cli-tests.db'}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    create_all_tables(engine)
    application.state.engine = engine
    application.state.app_secret = TEST_SECRET
    application.state.test_workspace_root = tmp_path
    return application


@pytest_asyncio.fixture()
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _seed_workspace(engine, root_path: Path, *, workspace_id: uuid.UUID | None = None):
    wid = workspace_id or uuid.uuid4()
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
                "id": str(wid),
                "name": "CLI Test Workspace",
                "slug": "cli-test-workspace",
                "version": "0.1.0",
                "root_path": str(root_path),
                "manifest": str(root_path / "workbench.project.yaml"),
                "now": now,
            },
        )
        conn.commit()
    return wid


def _seed_reviewer(engine, workspace_id: uuid.UUID) -> str:
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
                "name": "CLI Reviewer",
                "color": "#4A90D9",
                "wid": str(workspace_id),
                "now": now,
            },
        )
        conn.commit()
    return create_session_token(reviewer_id, TEST_SECRET)


@pytest.mark.asyncio
async def test_status_reports_workspace_detection(client, tmp_path):
    manifest = tmp_path / "workbench.project.yaml"
    manifest.write_text(
        "workspace_id: 123e4567-e89b-12d3-a456-426614174000\n"
        "workspace_name: Example Workspace\n"
        "core_version: 0.1.0\n",
        encoding="utf-8",
    )

    resp = await client.get("/api/v1/cli/status", params={"path": str(tmp_path)})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["workspace_detected"] is True
    assert body["manifest_path"].endswith("workbench.project.yaml")


@pytest.mark.asyncio
async def test_detect_workspace_returns_project_info(client, tmp_path):
    (tmp_path / "workbench.project.yaml").write_text(
        "workspace_id: 123e4567-e89b-12d3-a456-426614174000\n"
        "workspace_name: Example Workspace\n"
        "core_version: 0.1.0\n",
        encoding="utf-8",
    )

    resp = await client.post(
        "/api/v1/cli/workspaces/detect",
        json={"path": str(tmp_path)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_project"] is True
    assert body["detection_mode"] in {"manifest", "heuristic"}


@pytest.mark.asyncio
async def test_bootstrap_workspace_creates_manifest_and_db_row(client, app, tmp_path):
    resp = await client.post(
        "/api/v1/cli/workspaces/bootstrap",
        json={"path": str(tmp_path), "workspace_name": "Bootstrap Workspace"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["workspace_name"] == "Bootstrap Workspace"
    assert (tmp_path / "workbench.project.yaml").exists()

    with app.state.engine.connect() as conn:
        row = conn.execute(
            text("SELECT workspace_name, root_path FROM workspaces WHERE id = :id"),
            {"id": body["workspace_id"]},
        ).first()
    assert row is not None
    assert row[0] == "Bootstrap Workspace"
    assert row[1] == str(tmp_path)


@pytest.mark.asyncio
async def test_workflow_templates_are_listable_and_fetchable(client):
    resp = await client.get("/api/v1/cli/workflow-templates")
    assert resp.status_code == 200
    templates = resp.json()
    assert any(
        template["template_id"] == "quick_agentic_label" for template in templates
    )

    resp = await client.get("/api/v1/cli/workflow-templates/quick_agentic_label")
    assert resp.status_code == 200
    body = resp.json()
    assert body["template_id"] == "quick_agentic_label"
    assert "yaml" in body and "steps" in body["yaml"]


@pytest.mark.asyncio
async def test_selector_resolve_and_artifact_round_trip(client, app, tmp_path):
    workspace_id = _seed_workspace(app.state.engine, tmp_path)
    token = _seed_reviewer(app.state.engine, workspace_id)

    workflow_path = tmp_path / "workbench" / "workflows" / "demo.yaml"
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.write_text("name: Demo\nsteps: []\n", encoding="utf-8")

    with app.state.engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO workflow_definitions "
                "(id, workflow_slug, version, name, steps, description, "
                "is_template, template_source, file_path, is_active, "
                "workspace_id, created_at, updated_at) "
                "VALUES (:id, :slug, 1, :name, :steps, NULL, 0, NULL, :file_path, 1, "
                ":wid, :now, :now)"
            ),
            {
                "id": str(uuid.uuid4()),
                "slug": "demo",
                "name": "Demo Workflow",
                "steps": json.dumps([]),
                "file_path": str(workflow_path.relative_to(tmp_path)),
                "wid": str(workspace_id),
                "now": datetime.now(UTC).isoformat(),
            },
        )
        conn.commit()

    resolve_resp = await client.post(
        "/api/v1/cli/selectors/resolve",
        json={
            "kind": "workflow",
            "selector": "demo",
            "workspace_id": str(workspace_id),
            "workspace_root": str(tmp_path),
        },
    )
    assert resolve_resp.status_code == 200
    resolved = resolve_resp.json()
    assert resolved["resolved"] is True
    assert resolved["resolved_path"].endswith("workbench/workflows/demo.yaml")

    read_resp = await client.post(
        "/api/v1/cli/artifacts/read",
        json={
            "kind": "workflow",
            "selector": "demo",
            "workspace_id": str(workspace_id),
            "workspace_root": str(tmp_path),
        },
    )
    assert read_resp.status_code == 200
    read_body = read_resp.json()
    assert read_body["exists"] is True
    assert "Demo" in read_body["content"]

    diff_resp = await client.post(
        "/api/v1/cli/artifacts/diff",
        json={
            "kind": "workflow",
            "selector": "demo",
            "content": "name: Demo Updated\nsteps: []\n",
            "workspace_id": str(workspace_id),
            "workspace_root": str(tmp_path),
            "expected_hash": read_body["content_hash"],
        },
    )
    assert diff_resp.status_code == 200
    diff_body = diff_resp.json()
    assert diff_body["has_conflict"] is False
    assert "Demo Updated" in diff_body["diff"]

    write_resp = await client.post(
        "/api/v1/cli/artifacts/write",
        headers={"X-MoLabel-Session": token},
        json={
            "kind": "workflow",
            "selector": "demo",
            "content": "name: Demo Updated\nsteps: []\n",
            "workspace_id": str(workspace_id),
            "workspace_root": str(tmp_path),
            "expected_hash": read_body["content_hash"],
        },
    )
    assert write_resp.status_code == 200
    assert "Demo Updated" in workflow_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_artifact_write_creates_new_task_schema_at_canonical_path(
    client, app, tmp_path
):
    workspace_id = _seed_workspace(app.state.engine, tmp_path)
    token = _seed_reviewer(app.state.engine, workspace_id)

    write_resp = await client.post(
        "/api/v1/cli/artifacts/write",
        headers={"X-MoLabel-Session": token},
        json={
            "kind": "task_schema",
            "selector": "sentiment-demo-v2",
            "content": "task_slug: sentiment_demo_v2\n",
            "workspace_id": str(workspace_id),
            "workspace_root": str(tmp_path),
        },
    )
    assert write_resp.status_code == 200
    body = write_resp.json()
    assert body["resolved_path"].endswith(
        "workbench/config/task-schemas/sentiment-demo-v2.yaml"
    )
    assert (
        tmp_path / "workbench" / "config" / "task-schemas" / "sentiment-demo-v2.yaml"
    ).read_text(encoding="utf-8") == "task_slug: sentiment_demo_v2\n"


@pytest.mark.asyncio
async def test_snapshot_restore_updates_dataset_and_records(client, app, tmp_path):
    workspace_id = _seed_workspace(app.state.engine, tmp_path)
    token = _seed_reviewer(app.state.engine, workspace_id)
    dataset_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()
    record_id = uuid.uuid4()
    membership = {
        "health_status": "healthy",
        "record_states": {
            str(record_id): {
                "latest_label": {"label": "restored"},
                "composite_confidence": 0.9,
                "export_eligible": 1,
                "flags": ["restored"],
                "label_count": 1,
            }
        },
    }

    with Session(app.state.engine) as session:
        session.add(
            Dataset(
                id=dataset_id,
                dataset_name="Dataset",
                dataset_slug="dataset",
                source_type="file",
                canonical_id_strategy="external_id",
                indexing_mode="full",
                record_count=1,
                labeled_count=0,
                workspace_id=workspace_id,
            )
        )
        session.add(
            Record(
                id=record_id,
                stable_fields={"text": "hello"},
                label_count=0,
                export_eligible=False,
                workspace_id=workspace_id,
                dataset_id=dataset_id,
            )
        )
        session.add(
            DatasetSnapshot(
                id=snapshot_id,
                dataset_id=dataset_id,
                name="Snapshot",
                snapshot_type="full",
                record_count=1,
                labeled_count=1,
                dataset_membership=membership,
                workspace_id=workspace_id,
            )
        )
        session.commit()

    resp = await client.post(
        f"/api/v1/cli/datasets/{dataset_id}/snapshots/{snapshot_id}/restore",
        headers={"X-MoLabel-Session": token},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["records_restored"] == 1
    assert body["labels_restored"] == 1

    with Session(app.state.engine) as session:
        record = session.get(Record, record_id)
    assert record is not None
    assert record.label_count == 1
    assert bool(record.export_eligible) is True
    assert record.latest_label == {"label": "restored"}

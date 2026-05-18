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
    assert body["version"] == "1.0.0"
    assert body["task_family"] == "general_labeling"
    assert "agent_labeling" in body["capabilities"]
    assert "yaml" in body and "steps" in body["yaml"]


@pytest.mark.asyncio
async def test_benchmark_run_facts_returns_persisted_queue_counts(
    client, app, tmp_path
):
    workspace_id = _seed_workspace(app.state.engine, tmp_path)
    token = _seed_reviewer(app.state.engine, workspace_id)
    queue_id = str(uuid.uuid4())
    workflow_execution_id = uuid.uuid4()
    workflow_definition_id = uuid.uuid4()
    dataset_id = uuid.uuid4()
    task_schema_id = uuid.uuid4()
    record_ids = [uuid.uuid4() for _ in range(3)]
    task_ids = [uuid.uuid4() for _ in range(3)]
    now = datetime.now(UTC).isoformat()

    artifact_dir = tmp_path / "workbench" / "benchmarks" / "runs" / "live-operator"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "summary.json").write_text(
        '{"submitted_count": 2}\n',
        encoding="utf-8",
    )
    (artifact_dir / "report.md").write_text("# report\n", encoding="utf-8")

    context = {
        "review_queue_ids": [queue_id],
        "step_outputs": {
            "human_review": {
                "summary": {
                    "queue_id": queue_id,
                    "total_items": 3,
                }
            }
        },
    }

    with Session(app.state.engine) as session:
        session.add(
            Dataset(
                id=dataset_id,
                dataset_name="CLI Benchmark Dataset",
                dataset_slug="cli-benchmark-dataset",
                source_type="fixture",
                canonical_id_strategy="external_id",
                indexing_mode="full",
                record_count=len(record_ids),
                labeled_count=0,
                workspace_id=workspace_id,
            )
        )
        for index, record_id in enumerate(record_ids):
            session.add(
                Record(
                    id=record_id,
                    external_id=f"record-{index}",
                    stable_fields={"record_id": f"record-{index}"},
                    payload={"text": f"record {index}"},
                    export_eligible=False,
                    workspace_id=workspace_id,
                    dataset_id=dataset_id,
                )
            )
        session.commit()

    with app.state.engine.connect() as conn:
        conn.execute(
            text(
                """
                INSERT INTO workflow_executions (
                    id, workflow_definition_id, workflow_version, status,
                    current_step_id, step_execution_count, context,
                    started_at, created_at, updated_at, workspace_id
                ) VALUES (
                    :id, :workflow_definition_id, 1, 'paused',
                    'human_review', 4, :context,
                    :now, :now, :now, :workspace_id
                )
                """
            ),
            {
                "id": str(workflow_execution_id),
                "workflow_definition_id": str(workflow_definition_id),
                "context": json.dumps(context),
                "now": now,
                "workspace_id": str(workspace_id),
            },
        )
        for index, (task_id, record_id) in enumerate(
            zip(task_ids, record_ids, strict=True)
        ):
            status = "submitted" if index < 2 else "available"
            submitted_at = now if status == "submitted" else None
            agent_output_ids = None
            if index < 2:
                agent_output_id = uuid.uuid4()
                agent_output_ids = json.dumps([str(agent_output_id)])
                conn.execute(
                    text(
                        """
                        INSERT INTO agent_outputs (
                            id, agent_run_id, record_id, task_schema_id, output_type,
                            labels, validation_passed, retry_attempt,
                            is_visible_for_review, created_at, workspace_id
                        ) VALUES (
                            :id, :agent_run_id, :record_id, :task_schema_id, 'labels',
                            :labels, 1, 0, 1, :created_at, :workspace_id
                        )
                        """
                    ),
                    {
                        "id": str(agent_output_id),
                        "agent_run_id": str(uuid.uuid4()),
                        "record_id": str(record_id),
                        "task_schema_id": str(task_schema_id),
                        "labels": json.dumps(
                            {"stance_label": ("normal" if index == 0 else "agent-only")}
                        ),
                        "created_at": now,
                        "workspace_id": str(workspace_id),
                    },
                )
            conn.execute(
                text(
                    """
                    INSERT INTO review_tasks (
                        id, queue_id, record_id, task_schema_id, status, priority,
                        claim_expired_count, is_overlap, is_calibration, ai_revealed,
                        agent_output_ids, created_at, updated_at, submitted_at,
                        workspace_id, dataset_id
                    ) VALUES (
                        :id, :queue_id, :record_id, :task_schema_id, :status, :priority,
                        0, 0, 0, 0, :agent_output_ids,
                        :created_at, :updated_at, :submitted_at,
                        :workspace_id, :dataset_id
                    )
                    """
                ),
                {
                    "id": str(task_id),
                    "queue_id": queue_id,
                    "record_id": str(record_id),
                    "task_schema_id": str(task_schema_id),
                    "status": status,
                    "priority": index,
                    "agent_output_ids": agent_output_ids,
                    "created_at": now,
                    "updated_at": now,
                    "submitted_at": submitted_at,
                    "workspace_id": str(workspace_id),
                    "dataset_id": str(dataset_id),
                },
            )
        for task_id, record_id, decision in (
            (task_ids[0], record_ids[0], "accept"),
            (task_ids[1], record_ids[1], "accept"),
        ):
            conn.execute(
                text(
                    """
                    INSERT INTO review_events (
                        id, review_task_id, record_id, task_schema_id,
                        task_schema_version,
                        reviewer_id, source, decision, labels, ai_was_revealed,
                        created_at, workspace_id
                    ) VALUES (
                        :id, :review_task_id, :record_id, :task_schema_id, 1,
                        :reviewer_id, 'human', :decision, :labels, 0,
                        :created_at, :workspace_id
                    )
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "review_task_id": str(task_id),
                    "record_id": str(record_id),
                    "task_schema_id": str(task_schema_id),
                    "reviewer_id": str(uuid.uuid4()),
                    "decision": decision,
                    "labels": json.dumps({"stance_label": "normal"}),
                    "created_at": now,
                    "workspace_id": str(workspace_id),
                },
            )
        conn.commit()

    resp = await client.get(
        f"/api/v1/cli/benchmark-run-facts/{workflow_execution_id}",
        headers={"X-MoLabel-Session": token},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["workflow_execution_id"] == str(workflow_execution_id)
    assert body["queue_id"] == queue_id
    assert body["record_count"] == 3
    assert body["submitted_count"] == 2
    assert body["available_count"] == 1
    assert body["claimed_count"] == 0
    assert body["review_event_count"] == 2
    assert body["decision_counts"]["accept"] == 2
    assert body["semantic_decision_counts"]["accept_ai"] == 1
    assert body["semantic_decision_counts"]["edit_ai"] == 1
    assert body["queue_empty"] is False
    assert body["review_completion_rate"] == pytest.approx(2 / 3)
    assert body["summary_path"].endswith("summary.json")
    assert body["report_path"].endswith("report.md")


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
async def test_artifact_proposal_accept_and_reject_are_persisted(client, app, tmp_path):
    workspace_id = _seed_workspace(app.state.engine, tmp_path)
    token = _seed_reviewer(app.state.engine, workspace_id)
    workflow_path = tmp_path / "workbench" / "workflows" / "proposal-demo.yaml"
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.write_text("name: Proposal Demo\nsteps: []\n", encoding="utf-8")

    read_resp = await client.post(
        "/api/v1/cli/artifacts/read",
        json={
            "kind": "workflow",
            "selector": "proposal-demo",
            "workspace_id": str(workspace_id),
            "workspace_root": str(tmp_path),
        },
    )
    assert read_resp.status_code == 200
    original_hash = read_resp.json()["content_hash"]

    propose_resp = await client.post(
        "/api/v1/cli/artifacts/proposals",
        headers={"X-MoLabel-Session": token},
        json={
            "kind": "workflow",
            "selector": "proposal-demo",
            "content": "name: Proposal Demo Accepted\nsteps: []\n",
            "workspace_id": str(workspace_id),
            "workspace_root": str(tmp_path),
            "expected_hash": original_hash,
            "title": "Rename proposal demo",
            "rationale": "Prove semantic diff accept flow.",
        },
    )
    assert propose_resp.status_code == 200, propose_resp.text
    proposal = propose_resp.json()
    assert proposal["status"] == "proposed"
    assert "Proposal Demo Accepted" in proposal["diff"]
    assert (tmp_path / "workbench" / "proposals" / "artifacts").exists()

    accept_resp = await client.post(
        f"/api/v1/cli/artifacts/proposals/{proposal['proposal_id']}/decision",
        headers={"X-MoLabel-Session": token},
        json={
            "decision": "accept",
            "workspace_id": str(workspace_id),
            "workspace_root": str(tmp_path),
            "notes": "Accepted in integration test.",
        },
    )
    assert accept_resp.status_code == 200, accept_resp.text
    accepted = accept_resp.json()
    assert accepted["status"] == "accepted"
    assert accepted["write_result"]["success"] is True
    assert "Proposal Demo Accepted" in workflow_path.read_text(encoding="utf-8")
    trace_resp = await client.get(
        f"/api/v1/cli/artifacts/proposals/{proposal['proposal_id']}/trace",
        params={
            "workspace_id": str(workspace_id),
            "workspace_root": str(tmp_path),
        },
    )
    assert trace_resp.status_code == 200
    trace_body = trace_resp.json()
    trace = trace_body["trace"]
    assert trace["schema"] == "molabel.artifact.trace"
    assert trace["proposal_id"] == proposal["proposal_id"]
    assert trace["source_hash"] == original_hash
    assert trace["proposed_hash"] == proposal["new_hash"]
    assert trace["current_hash"] == proposal["new_hash"]
    assert trace["hashes_match_proposal"] is True
    assert trace["target_path"] == str(workflow_path)
    assert trace["audit_event_ids"]
    audit_resp = await client.get(
        "/api/v1/audit",
        cookies={"molabel_session": token},
        params={
            "workspace_id": str(workspace_id),
            "object_id": proposal["proposal_id"],
        },
    )
    assert audit_resp.status_code == 200
    audit_types = {item["event_type"] for item in audit_resp.json()["items"]}
    assert "artifact_proposed" in audit_types
    assert "artifact_proposal_accepted" in audit_types

    reject_resp = await client.post(
        "/api/v1/cli/artifacts/proposals",
        headers={"X-MoLabel-Session": token},
        json={
            "kind": "workflow",
            "selector": "proposal-demo",
            "content": "name: Proposal Demo Rejected\nsteps: []\n",
            "workspace_id": str(workspace_id),
            "workspace_root": str(tmp_path),
        },
    )
    assert reject_resp.status_code == 200
    rejected_id = reject_resp.json()["proposal_id"]
    decision_resp = await client.post(
        f"/api/v1/cli/artifacts/proposals/{rejected_id}/decision",
        headers={"X-MoLabel-Session": token},
        json={
            "decision": "reject",
            "workspace_id": str(workspace_id),
            "workspace_root": str(tmp_path),
            "notes": "Rejected in integration test.",
        },
    )
    assert decision_resp.status_code == 200
    assert decision_resp.json()["status"] == "rejected"
    assert "Proposal Demo Rejected" not in workflow_path.read_text(encoding="utf-8")

    stale_read_resp = await client.post(
        "/api/v1/cli/artifacts/read",
        json={
            "kind": "workflow",
            "selector": "proposal-demo",
            "workspace_id": str(workspace_id),
            "workspace_root": str(tmp_path),
        },
    )
    assert stale_read_resp.status_code == 200
    stale_base_hash = stale_read_resp.json()["content_hash"]
    stale_propose_resp = await client.post(
        "/api/v1/cli/artifacts/proposals",
        headers={"X-MoLabel-Session": token},
        json={
            "kind": "workflow",
            "selector": "proposal-demo",
            "content": "name: Proposal Demo Stale Accept\nsteps: []\n",
            "workspace_id": str(workspace_id),
            "workspace_root": str(tmp_path),
            "expected_hash": stale_base_hash,
        },
    )
    assert stale_propose_resp.status_code == 200
    stale_id = stale_propose_resp.json()["proposal_id"]
    workflow_path.write_text(
        "name: Proposal Demo External Edit\nsteps: []\n",
        encoding="utf-8",
    )
    stale_accept_resp = await client.post(
        f"/api/v1/cli/artifacts/proposals/{stale_id}/decision",
        headers={"X-MoLabel-Session": token},
        json={
            "decision": "accept",
            "workspace_id": str(workspace_id),
            "workspace_root": str(tmp_path),
        },
    )
    assert stale_accept_resp.status_code == 409
    assert "External Edit" in workflow_path.read_text(encoding="utf-8")
    stale_payload = json.loads(
        (
            tmp_path / "workbench" / "proposals" / "artifacts" / f"{stale_id}.json"
        ).read_text(encoding="utf-8")
    )
    assert stale_payload["status"] == "conflicted"
    assert stale_payload["has_conflict"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "selector", "relative_path", "content"),
    [
        (
            "workflow",
            "guarded-workflow",
            "workbench/workflows/guarded-workflow.yaml",
            "name: Guarded\nsteps: []\n",
        ),
        (
            "prompt",
            "guarded-prompt",
            "workbench/prompts/guarded-prompt.yaml",
            "name: Guarded Prompt\nbody: hi\n",
        ),
        (
            "task_schema",
            "guarded-schema",
            "workbench/config/task-schemas/guarded-schema.yaml",
            "task_slug: guarded_schema\nfields: []\n",
        ),
        (
            "workspace_manifest",
            "ignored",
            "workbench.project.yaml",
            "workspace_name: Guarded\n",
        ),
    ],
)
async def test_artifact_write_rejects_blind_overwrite_for_canonical_namespaces(
    client,
    app,
    tmp_path,
    kind,
    selector,
    relative_path,
    content,
):
    workspace_id = _seed_workspace(app.state.engine, tmp_path)
    token = _seed_reviewer(app.state.engine, workspace_id)
    path = tmp_path / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

    response = await client.post(
        "/api/v1/cli/artifacts/write",
        headers={"X-MoLabel-Session": token},
        json={
            "kind": kind,
            "selector": selector,
            "content": content + "# edited\n",
            "workspace_id": str(workspace_id),
            "workspace_root": str(tmp_path),
        },
    )

    assert response.status_code == 409
    assert "expected_hash is required" in response.text
    assert path.read_text(encoding="utf-8") == content


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

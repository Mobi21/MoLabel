"""Request-supplied paths must stay inside a registered workspace."""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine

from molabel.app import workspace_paths
from molabel.app.main import create_app
from molabel.app.services.session import create_session_token
from molabel.core.migration_runner import upgrade_database

SECRET = "path-guard-secret"


@pytest.fixture()
def layout(tmp_path: Path) -> dict[str, Path]:
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    (workspace / "data").mkdir(parents=True)
    outside.mkdir()
    (workspace / "data" / "rows.jsonl").write_text(
        json.dumps({"id": "r1", "text": "inside"}) + "\n", encoding="utf-8"
    )
    (outside / "secret.jsonl").write_text(
        json.dumps({"id": "s1", "text": "outside"}) + "\n", encoding="utf-8"
    )
    (outside / "secret.yaml").write_text("secret: true\n", encoding="utf-8")
    return {"workspace": workspace, "outside": outside}


@pytest.fixture()
def app(layout: dict[str, Path]):
    application = create_app()
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    upgrade_database(engine)
    application.state.engine = engine
    application.state.app_secret = SECRET
    workspace_id = str(uuid.uuid4())
    reviewer_id = uuid.uuid4()
    now = datetime.now(UTC).isoformat()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO workspaces (id, workspace_name, workspace_slug, "
                "core_version, root_path, manifest_path, created_at, updated_at) "
                "VALUES (:id, 'Guarded', 'guarded', '0.1.0', :root, "
                "'workbench.project.yaml', :now, :now)"
            ),
            {"id": workspace_id, "root": str(layout["workspace"]), "now": now},
        )
        conn.execute(
            text(
                "INSERT INTO reviewer_profiles (id, display_name, avatar_color, "
                "is_operator, is_active, workspace_id, created_at) "
                "VALUES (:id, 'Guard', '#4A90D9', 1, 1, :wid, :now)"
            ),
            {"id": str(reviewer_id), "wid": workspace_id, "now": now},
        )
    application.state.test_workspace_id = workspace_id
    application.state.test_token = create_session_token(reviewer_id, SECRET)
    return application


@pytest_asyncio.fixture()
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-MoLabel-Session": app.state.test_token},
        cookies={"molabel_session": app.state.test_token},
    ) as c:
        yield c


def _error(resp) -> tuple[int, str]:
    return resp.status_code, resp.json()["error"]["code"]


@pytest.mark.asyncio
async def test_artifact_read_rejects_traversal_in_workspace_root(client, layout):
    resp = await client.post(
        "/api/v1/cli/artifacts/read",
        json={
            "kind": "workspace_manifest",
            "selector": "workspace",
            "workspace_root": f"{layout['workspace']}/../outside",
        },
    )
    assert _error(resp) == (400, "PATH_TRAVERSAL")


@pytest.mark.asyncio
async def test_artifact_read_rejects_an_unregistered_workspace_root(client, layout):
    resp = await client.post(
        "/api/v1/cli/artifacts/read",
        json={
            "kind": "prompt",
            "selector": "secret.yaml",
            "workspace_root": str(layout["outside"]),
        },
    )
    assert _error(resp) == (403, "PATH_OUTSIDE_WORKSPACE")


@pytest.mark.asyncio
async def test_artifact_read_requires_a_workspace(client):
    resp = await client.post(
        "/api/v1/cli/artifacts/read",
        json={"kind": "workspace_manifest", "selector": "workspace"},
    )
    assert _error(resp) == (400, "WORKSPACE_REQUIRED")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("selector", "expected"),
    [
        ("../outside/secret.yaml", (400, "PATH_TRAVERSAL")),
        ("OUTSIDE_ABSOLUTE", (403, "PATH_OUTSIDE_WORKSPACE")),
    ],
)
async def test_artifact_read_rejects_selectors_that_leave_the_workspace(
    client, layout, selector, expected
):
    if selector == "OUTSIDE_ABSOLUTE":
        selector = str(layout["outside"] / "secret.yaml")
    resp = await client.post(
        "/api/v1/cli/artifacts/read",
        json={
            "kind": "prompt",
            "selector": selector,
            "workspace_root": str(layout["workspace"]),
        },
    )
    assert _error(resp) == expected
    assert "secret: true" not in resp.text


def _link_folder(link: Path, target: Path) -> None:
    """Make *link* a directory symlink to *target*, or a junction on Windows."""
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError:
        if sys.platform != "win32":
            raise
        import _winapi

        _winapi.CreateJunction(str(target), str(link))


def _link_file(link: Path, target: Path) -> None:
    try:
        os.symlink(target, link)
    except OSError as exc:
        pytest.skip(f"cannot create a file symlink here: {exc}")


def _outside_files(layout: dict[str, Path]) -> list[str]:
    outside = layout["outside"]
    return sorted(p.relative_to(outside).as_posix() for p in outside.rglob("*"))


@pytest.mark.asyncio
async def test_artifact_read_rejects_a_symlink_out_of_the_workspace(client, layout):
    _link_folder(layout["workspace"] / "linked", layout["outside"])
    resp = await client.post(
        "/api/v1/cli/artifacts/read",
        json={
            "kind": "prompt",
            "selector": "linked/secret.yaml",
            "workspace_root": str(layout["workspace"]),
        },
    )
    assert _error(resp) == (403, "PATH_OUTSIDE_WORKSPACE")


@pytest.mark.asyncio
async def test_artifact_write_outside_the_workspace_writes_nothing(client, layout):
    target = layout["outside"] / "planted.yaml"
    resp = await client.post(
        "/api/v1/cli/artifacts/write",
        json={
            "kind": "workflow",
            "selector": str(target),
            "content": "planted: true\n",
            "workspace_root": str(layout["workspace"]),
        },
    )
    assert _error(resp) == (403, "PATH_OUTSIDE_WORKSPACE")
    assert not target.exists()


@pytest.mark.asyncio
async def test_artifact_proposal_in_an_unregistered_root_writes_nothing(client, layout):
    resp = await client.post(
        "/api/v1/cli/artifacts/proposals",
        json={
            "kind": "workflow",
            "selector": "demo",
            "content": "name: Demo\n",
            "workspace_root": str(layout["outside"]),
        },
    )
    assert _error(resp) == (403, "PATH_OUTSIDE_WORKSPACE")
    assert list(layout["outside"].rglob("*.json")) == []


async def _create_dataset(client, app) -> str:
    resp = await client.post(
        "/api/v1/datasets",
        json={
            "workspace_id": app.state.test_workspace_id,
            "dataset_name": "rows",
            "source_type": "jsonl",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["dataset_id"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source_uri", "expected"),
    [
        ("../outside/secret.jsonl", (400, "PATH_TRAVERSAL")),
        ("OUTSIDE_ABSOLUTE", (403, "PATH_OUTSIDE_WORKSPACE")),
    ],
)
async def test_dataset_import_rejects_files_outside_the_workspace(
    client, app, layout, source_uri, expected
):
    if source_uri == "OUTSIDE_ABSOLUTE":
        source_uri = str(layout["outside"] / "secret.jsonl")
    dataset_id = await _create_dataset(client, app)

    resp = await client.post(
        f"/api/v1/datasets/{dataset_id}/import", json={"source_uri": source_uri}
    )

    assert _error(resp) == expected
    records = await client.get(f"/api/v1/datasets/{dataset_id}/records")
    assert records.json()["items"] == []


@pytest.mark.asyncio
async def test_dataset_import_reads_a_file_inside_the_workspace(client, app):
    dataset_id = await _create_dataset(client, app)

    resp = await client.post(
        f"/api/v1/datasets/{dataset_id}/import",
        json={"source_uri": "data/rows.jsonl"},
    )

    assert resp.status_code == 202, resp.text
    assert resp.json()["records_imported"] == 1


async def _run_workflow(client, app, steps: list[dict]) -> dict:
    created = await client.post(
        "/api/v1/workflows",
        json={
            "workspace_id": app.state.test_workspace_id,
            "name": f"guard-{uuid.uuid4().hex[:8]}",
            "steps": steps,
        },
    )
    assert created.status_code == 201, created.text
    workflow_id = created.json()["workflow_id"]
    executed = await client.post(f"/api/v1/workflows/{workflow_id}/execute", json={})
    assert executed.status_code == 202, executed.text
    execution_id = executed.json()["execution_id"]
    detail = await client.get(
        f"/api/v1/workflows/{workflow_id}/executions/{execution_id}"
    )
    return detail.json()


@pytest.mark.asyncio
async def test_workflow_data_source_outside_the_workspace_fails_the_step(
    client, app, layout
):
    detail = await _run_workflow(
        client,
        app,
        [
            {
                "step_id": "ingest",
                "step_type": "data_ingest",
                "config": {"source": str(layout["outside"] / "secret.jsonl")},
            }
        ],
    )

    states = {s["step_id"]: s for s in detail["step_states"]}
    assert states["ingest"]["status"] == "failed"
    assert "outside the workspace" in states["ingest"]["error_summary"]


@pytest.mark.asyncio
async def test_workflow_export_outside_the_workspace_writes_nothing(
    client, app, layout
):
    detail = await _run_workflow(
        client,
        app,
        [
            {
                "step_id": "ingest",
                "step_type": "data_ingest",
                "config": {"source": "data/rows.jsonl"},
            },
            {
                "step_id": "export_results",
                "step_type": "export",
                "config": {"format": "jsonl", "destination": str(layout["outside"])},
            },
        ],
    )

    states = {s["step_id"]: s for s in detail["step_states"]}
    assert states["export_results"]["status"] == "failed"
    assert "outside the workspace" in states["export_results"]["error_summary"]
    assert sorted(p.name for p in layout["outside"].iterdir()) == [
        "secret.jsonl",
        "secret.yaml",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("relative/workspace", (400, "PATH_NOT_ABSOLUTE")),
        ("TRAVERSAL", (400, "PATH_TRAVERSAL")),
    ],
)
async def test_bootstrap_requires_an_absolute_path_without_traversal(
    client, layout, path, expected
):
    if path == "TRAVERSAL":
        path = f"{layout['workspace']}/../elsewhere"
    resp = await client.post("/api/v1/cli/workspaces/bootstrap", json={"path": path})
    assert _error(resp) == expected
    assert not (layout["workspace"].parent / "elsewhere").exists()


@pytest.mark.asyncio
async def test_proposal_through_a_linked_proposals_folder_writes_nothing(
    client, layout
):
    _link_folder(layout["workspace"] / "workbench" / "proposals", layout["outside"])

    resp = await client.post(
        "/api/v1/cli/artifacts/proposals",
        json={
            "kind": "workflow",
            "selector": "demo",
            "content": "name: Demo\n",
            "workspace_root": str(layout["workspace"]),
        },
    )

    assert _error(resp) == (403, "PATH_OUTSIDE_WORKSPACE")
    assert _outside_files(layout) == ["secret.jsonl", "secret.yaml"]


@pytest.mark.asyncio
async def test_workspace_manifest_read_refuses_a_link_out_of_the_workspace(
    client, layout
):
    manifest = layout["workspace"] / "workbench.project.yaml"
    _link_file(manifest, layout["outside"] / "secret.yaml")

    resp = await client.post(
        "/api/v1/cli/artifacts/read",
        json={
            "kind": "workspace_manifest",
            "selector": "workspace",
            "workspace_root": str(layout["workspace"]),
        },
    )

    assert _error(resp) == (403, "PATH_OUTSIDE_WORKSPACE")
    assert "secret: true" not in resp.text


async def _create_release(client, app, **fields) -> object:
    return await client.post(
        "/api/v1/releases",
        json={
            "workspace_id": app.state.test_workspace_id,
            "name": "Guarded",
            "version": "1.0.0",
            "export_ids": [],
            **fields,
        },
    )


@pytest.mark.asyncio
async def test_release_through_a_linked_releases_folder_writes_nothing(
    client, app, layout
):
    _link_folder(layout["workspace"] / "workbench" / "releases", layout["outside"])

    resp = await _create_release(client, app)

    assert _error(resp) == (403, "PATH_OUTSIDE_WORKSPACE")
    assert _outside_files(layout) == ["secret.jsonl", "secret.yaml"]


@pytest.mark.asyncio
async def test_release_gate_reads_no_benchmark_summary_through_a_link(
    client, app, layout
):
    run = layout["outside"] / "run-1"
    run.mkdir()
    (run / "summary.json").write_text(
        json.dumps({"run_id": "run-1", "overall_score": 1.0}), encoding="utf-8"
    )
    _link_folder(
        layout["workspace"] / "workbench" / "benchmarks" / "runs", layout["outside"]
    )

    resp = await _create_release(client, app, benchmark_run_ids=["run-1"])

    assert _error(resp) == (403, "PATH_OUTSIDE_WORKSPACE")


@pytest.mark.asyncio
async def test_release_gate_reads_the_summary_it_checked_when_a_link_is_swapped(
    client, app, layout, monkeypatch
):
    def summary_in(folder: Path, benchmark_id: str) -> Path:
        folder.mkdir(parents=True)
        (folder / "summary.json").write_text(
            json.dumps({"run_id": "run-1", "benchmark_id": benchmark_id}),
            encoding="utf-8",
        )
        return folder

    inside = summary_in(layout["workspace"] / "data" / "run-1", "inside")
    outside = summary_in(layout["outside"] / "run-1", "outside")
    link = layout["workspace"] / "workbench" / "benchmarks" / "runs" / "linked"
    _link_folder(link, inside)

    check = workspace_paths.resolve_in_workspace

    def swap_the_link_after_its_check(root: Path, raw: str) -> Path:
        resolved = check(root, raw)
        if Path(raw) == link / "summary.json":
            os.rmdir(link) if link.is_junction() else link.unlink()
            _link_folder(link, outside)
        return resolved

    monkeypatch.setattr(
        workspace_paths, "resolve_in_workspace", swap_the_link_after_its_check
    )

    resp = await _create_release(client, app, benchmark_run_ids=["run-1"])

    assert resp.status_code == 201, resp.text
    [gate] = resp.json()["validation_report"]["gates"]
    assert (gate["details"]["benchmark_id"], gate["details"]["summary_path"]) == (
        "inside",
        str(link / "summary.json"),
    )


def _completed_execution(app) -> str:
    execution_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    with app.state.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO workflow_executions (id, workflow_definition_id, "
                "workflow_version, status, context, workspace_id, created_at, "
                "updated_at) VALUES (:id, :wf, 1, 'completed', '{}', :wid, "
                ":now, :now)"
            ),
            {
                "id": execution_id,
                "wf": str(uuid.uuid4()),
                "wid": app.state.test_workspace_id,
                "now": now,
            },
        )
    return execution_id


@pytest.mark.asyncio
async def test_benchmark_run_facts_list_no_files_through_a_link(client, app, layout):
    _link_folder(
        layout["workspace"] / "workbench" / "benchmarks" / "runs" / "live-operator",
        layout["outside"],
    )
    execution_id = _completed_execution(app)

    resp = await client.get(f"/api/v1/cli/benchmark-run-facts/{execution_id}")

    assert _error(resp) == (403, "PATH_OUTSIDE_WORKSPACE")
    assert "secret.jsonl" not in resp.text


@pytest.mark.asyncio
async def test_benchmark_run_facts_list_files_through_a_link_inside_the_workspace(
    client, app, layout
):
    reports = layout["workspace"] / "data" / "shared-reports"
    reports.mkdir()
    (reports / "report.md").write_text("inside", encoding="utf-8")
    run = layout["workspace"] / "workbench" / "benchmarks" / "runs" / "live-operator"
    run.mkdir(parents=True)
    (run / "summary.json").write_text("{}", encoding="utf-8")
    _link_folder(run / "reports", reports)
    execution_id = _completed_execution(app)

    resp = await client.get(f"/api/v1/cli/benchmark-run-facts/{execution_id}")

    assert resp.status_code == 200, resp.text
    assert resp.json()["artifact_files"] == [
        str(Path("reports", "report.md")),
        "summary.json",
    ]


@pytest.mark.asyncio
async def test_config_write_refuses_a_manifest_linked_out_of_the_workspace(
    client, app, layout
):
    outside_manifest = layout["outside"] / "workbench.project.yaml"
    elsewhere = (
        "workspace_id: 00000000-0000-0000-0000-000000000002\n"
        "workspace_name: Elsewhere\n"
        "core_version: 0.1.0\n"
    )
    outside_manifest.write_text(elsewhere, encoding="utf-8")
    _link_file(layout["workspace"] / "workbench.project.yaml", outside_manifest)

    resp = await client.post(
        "/api/v1/task-schemas",
        json={
            "workspace_id": app.state.test_workspace_id,
            "task_type": "text_classification",
            "title": "Guarded",
        },
    )

    assert _error(resp) == (403, "PATH_OUTSIDE_WORKSPACE")
    assert outside_manifest.read_text(encoding="utf-8") == elsewhere


@pytest.mark.asyncio
async def test_bootstrap_refuses_a_manifest_linked_out_of_the_folder(
    client, layout, tmp_path
):
    folder = tmp_path / "linked-manifest"
    folder.mkdir()
    outside_manifest = layout["outside"] / "workbench.project.yaml"
    outside_manifest.write_text(
        "workspace_id: 00000000-0000-0000-0000-000000000001\n"
        "workspace_name: Elsewhere\n"
        "core_version: 0.1.0\n",
        encoding="utf-8",
    )
    _link_file(folder / "workbench.project.yaml", outside_manifest)

    resp = await client.post(
        "/api/v1/cli/workspaces/bootstrap", json={"path": str(folder)}
    )

    assert _error(resp) == (403, "PATH_OUTSIDE_WORKSPACE")
    workspaces = await client.get("/api/v1/workspaces")
    names = [w["workspace_name"] for w in workspaces.json()["items"]]
    assert "Elsewhere" not in names

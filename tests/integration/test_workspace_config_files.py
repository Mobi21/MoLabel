"""Task schemas, prompts and workflows are files; their database rows index them."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import pytest_asyncio
import yaml
from httpx import ASGITransport, AsyncClient
from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine

from molabel.app.main import create_app
from molabel.core.migration_runner import upgrade_database

SCHEMA = {
    "task_schema_slug": "sentiment",
    "task_type": "text_classification",
    "title": "Sentiment",
    "label_fields": [
        {
            "name": "sentiment",
            "field_type": "categorical",
            "options": ["positive", "negative"],
        }
    ],
}
WORKFLOW = {
    "name": "Label reviews",
    "workflow_slug": "label-reviews",
    "steps": [
        {
            "step_id": "ingest",
            "step_type": "data_ingest",
            "config": {"source": "data/reviews.jsonl"},
        }
    ],
}


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    (root / "data").mkdir(parents=True)
    (root / "data" / "reviews.jsonl").write_text(
        json.dumps({"id": "r1", "text": "Great"}) + "\n", encoding="utf-8"
    )
    return root


@pytest_asyncio.fixture()
async def client(workspace: Path):
    app = create_app()
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    upgrade_database(engine)
    app.state.engine = engine
    app.state.app_secret = "config-files-secret"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        c.workspace_id = await _bootstrap(c, workspace)
        yield c


async def _bootstrap(client: AsyncClient, root: Path) -> str:
    resp = await client.post(
        "/api/v1/cli/workspaces/bootstrap", json={"path": str(root)}
    )
    assert resp.status_code == 201, resp.text
    client.cookies.set("molabel_session", resp.cookies["molabel_session"])
    return resp.json()["workspace_id"]


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


async def _create(client: AsyncClient, route: str, body: dict) -> dict:
    resp = await client.post(route, json={**body, "workspace_id": client.workspace_id})
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_creating_config_writes_files_listed_in_the_manifest(client, workspace):
    schema = await _create(client, "/api/v1/task-schemas", SCHEMA)
    await _create(
        client,
        "/api/v1/prompts",
        {
            "name": "Sentiment proposer",
            "agent_role": "proposer",
            "task_schema_id": schema["task_schema_id"],
            "system_instructions": "Label the sentiment.",
        },
    )
    await _create(client, "/api/v1/workflows", WORKFLOW)
    dataset = await _create(
        client,
        "/api/v1/datasets",
        {"dataset_name": "reviews", "source_type": "jsonl", "record_kind": "text"},
    )
    imported = await client.post(
        f"/api/v1/datasets/{dataset['dataset_id']}/import",
        json={"source_uri": "data/reviews.jsonl"},
    )
    assert imported.status_code == 202, imported.text

    schema_file = workspace / "workbench/config/task-schemas/sentiment.yaml"
    prompt_file = workspace / "workbench/prompts/sentiment-proposer.yaml"
    workflow_file = workspace / "workbench/workflows/label-reviews.yaml"
    assert _yaml(schema_file)["label_fields"][0]["options"] == ["positive", "negative"]
    assert _yaml(prompt_file)["system_instructions"] == "Label the sentiment."
    assert _yaml(workflow_file)["steps"][0]["config"] == {
        "source": "data/reviews.jsonl"
    }

    manifest = _yaml(workspace / "workbench.project.yaml")
    assert manifest["task_schemas"] == [
        {
            "task_schema_id": "sentiment",
            "task_type_plugin": None,
            "definition_path": "workbench/config/task-schemas/sentiment.yaml",
        }
    ]
    assert manifest["prompts"] == [
        {
            "prompt_id": "sentiment-proposer",
            "definition_path": "workbench/prompts/sentiment-proposer.yaml",
        }
    ]
    assert manifest["workflows"] == [
        {
            "workflow_id": "label-reviews",
            "definition_path": "workbench/workflows/label-reviews.yaml",
        }
    ]
    datasets = {d["dataset_id"]: d["source_paths"] for d in manifest["datasets"]}
    assert datasets["reviews"] == ["data/reviews.jsonl"]
    assert all("\\" not in path for paths in datasets.values() for path in paths)


@pytest.mark.asyncio
async def test_updates_rewrite_the_file(client, workspace):
    schema = await _create(client, "/api/v1/task-schemas", SCHEMA)
    workflow = await _create(client, "/api/v1/workflows", WORKFLOW)

    schema_resp = await client.put(
        f"/api/v1/task-schemas/{schema['task_schema_id']}",
        json={"title": "Review sentiment"},
    )
    workflow_resp = await client.put(
        f"/api/v1/workflows/{workflow['workflow_id']}",
        json={"description": "Ingest and label."},
    )

    assert schema_resp.status_code == 200, schema_resp.text
    assert workflow_resp.status_code == 200, workflow_resp.text
    schema_file = workspace / "workbench/config/task-schemas/sentiment.yaml"
    workflow_file = workspace / "workbench/workflows/label-reviews.yaml"
    assert _yaml(schema_file)["title"] == "Review sentiment"
    assert _yaml(workflow_file)["description"] == "Ingest and label."


@pytest.mark.asyncio
async def test_the_file_wins_when_bootstrap_reindexes(client, workspace):
    schema = await _create(client, "/api/v1/task-schemas", SCHEMA)
    workflow = await _create(client, "/api/v1/workflows", WORKFLOW)
    schema_file = workspace / "workbench/config/task-schemas/sentiment.yaml"
    workflow_file = workspace / "workbench/workflows/label-reviews.yaml"
    edited_schema = {**_yaml(schema_file), "title": "Edited by hand"}
    schema_file.write_text(yaml.safe_dump(edited_schema), encoding="utf-8")
    edited_workflow = _yaml(workflow_file)
    edited_workflow["steps"][0]["config"]["source"] = "data/other.jsonl"
    workflow_file.write_text(yaml.safe_dump(edited_workflow), encoding="utf-8")

    before = await client.get(f"/api/v1/task-schemas/{schema['task_schema_id']}")
    assert before.json()["title"] == "Sentiment"

    await _bootstrap(client, workspace)

    after = await client.get(f"/api/v1/task-schemas/{schema['task_schema_id']}")
    assert after.json()["title"] == "Edited by hand"
    workflow_after = await client.get(f"/api/v1/workflows/{workflow['workflow_id']}")
    assert workflow_after.json()["steps"][0]["config"] == {"source": "data/other.jsonl"}


@pytest.mark.asyncio
async def test_create_registers_an_existing_file_without_rewriting_it(
    client, workspace
):
    schema_file = workspace / "workbench/config/task-schemas/intent.yaml"
    schema_file.parent.mkdir(parents=True)
    authored = "# written by a person\ntask_type: text_classification\ntitle: Intent\n"
    schema_file.write_text(authored, encoding="utf-8")

    await _create(
        client,
        "/api/v1/task-schemas",
        {
            "task_type": "text_classification",
            "title": "Intent",
            "file_path": "workbench/config/task-schemas/intent.yaml",
        },
    )

    assert schema_file.read_text(encoding="utf-8") == authored
    manifest = _yaml(workspace / "workbench.project.yaml")
    assert [e["definition_path"] for e in manifest["task_schemas"]] == [
        "workbench/config/task-schemas/intent.yaml"
    ]


@pytest.mark.asyncio
async def test_config_for_a_workspace_without_a_folder_is_refused(
    client, tmp_path: Path
):
    missing = tmp_path / "never-created"
    registered = await client.post(
        "/api/v1/workspaces", json={"path": str(missing), "workspace_name": "Gone"}
    )
    assert registered.status_code == 201, registered.text

    resp = await client.post(
        "/api/v1/task-schemas",
        json={**SCHEMA, "workspace_id": registered.json()["workspace_id"]},
    )

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "WORKSPACE_FOLDER_MISSING"
    assert not missing.exists()

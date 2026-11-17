"""Task schemas, prompts and workflows are files; their database rows index them."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import pytest
import pytest_asyncio
import yaml
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event

from molabel.app.main import create_app
from molabel.core.database import engine_from_url
from molabel.core.migration_runner import upgrade_database
from molabel.core.workflow.parser import parse_workflow_yaml

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
    engine = engine_from_url("sqlite:///:memory:")
    upgrade_database(engine)
    app.state.engine = engine
    app.state.app_secret = "config-files-secret"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        c.engine = engine
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


def _tree(workspace: Path) -> list[str]:
    return sorted(
        p.relative_to(workspace).as_posix()
        for p in workspace.rglob("*")
        if ".molabel" not in p.parts
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("route", "body"),
    [
        ("/api/v1/task-schemas", {**SCHEMA, "task_schema_slug": "Con"}),
        ("/api/v1/task-schemas", {**SCHEMA, "task_schema_slug": "nul.v2"}),
        (
            "/api/v1/task-schemas",
            {**SCHEMA, "file_path": "workbench/config/task-schemas/sentiment.yaml "},
        ),
        (
            "/api/v1/task-schemas",
            {**SCHEMA, "file_path": "workbench/config./sentiment.yaml"},
        ),
        ("/api/v1/workflows", {**WORKFLOW, "workflow_slug": "com1"}),
    ],
)
async def test_config_with_a_name_windows_cannot_hold_is_refused(
    client, workspace, route, body
):
    before = _tree(workspace)

    resp = await client.post(route, json={**body, "workspace_id": client.workspace_id})

    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "PATH_NOT_PORTABLE"
    assert "Windows" in resp.json()["error"]["message"]
    assert _tree(workspace) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("slug", ["com0", "lpt0", "COM0"])
async def test_config_named_com0_or_lpt0_is_written_as_windows_holds_it(
    client, workspace, slug
):
    created = await client.post(
        "/api/v1/task-schemas",
        json={**SCHEMA, "task_schema_slug": slug, "workspace_id": client.workspace_id},
    )
    refused = await client.post(
        "/api/v1/task-schemas",
        json={
            **SCHEMA,
            "task_schema_slug": "com1",
            "workspace_id": client.workspace_id,
        },
    )

    assert created.status_code == 201, created.text
    written = workspace / f"workbench/config/task-schemas/{slug}.yaml"
    assert _yaml(written)["task_schema_slug"] == slug
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["code"] == "PATH_NOT_PORTABLE"


@pytest.mark.asyncio
async def test_a_prompt_named_like_a_windows_device_is_refused(client, workspace):
    schema = await _create(client, "/api/v1/task-schemas", SCHEMA)
    before = _tree(workspace)

    resp = await client.post(
        "/api/v1/prompts",
        json={
            "workspace_id": client.workspace_id,
            "name": "AUX",
            "agent_role": "proposer",
            "task_schema_id": schema["task_schema_id"],
            "system_instructions": "Label the sentiment.",
        },
    )

    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "PATH_NOT_PORTABLE"
    assert _tree(workspace) == before


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


HAND_WRITTEN_SCHEMA = """\
# Sentiment schema, reviewed by the labeling lead.
title: Sentiment
task_type: text_classification  # set once, never changes
task_schema_slug: sentiment

# One categorical field.
label_fields:
  - name: sentiment
    field_type: categorical
    required: true
    options:
      - "yes"
      - "no"
    description: ""
required_fields: []
optional_fields: []
blind_review_policy: hide_agent_outputs_by_default
supported_agent_roles: []
"""

HAND_WRITTEN_MANIFEST = """\
# Workspace manifest, edited by hand.
workspace_name: Reviews
workspace_id: {workspace_id}  # do not change
core_version: "0.1.0"
enabled_plugins: []

# Datasets are imported with the CLI.
datasets: []
task_schemas: []
prompts: []
workflows: []
export_targets: []
validation_gates: []
"""


def _comments(text: str) -> list[str]:
    return [line.partition("#")[2] for line in text.splitlines() if "#" in line]


@pytest.mark.asyncio
async def test_config_writes_keep_hand_written_comments_and_key_order(
    client, workspace
):
    manifest_file = workspace / "workbench.project.yaml"
    manifest_text = HAND_WRITTEN_MANIFEST.format(workspace_id=client.workspace_id)
    manifest_file.write_text(manifest_text, encoding="utf-8")
    schema_file = workspace / "workbench/config/task-schemas/sentiment.yaml"
    schema_file.parent.mkdir(parents=True)
    schema_file.write_text(HAND_WRITTEN_SCHEMA, encoding="utf-8")
    manifest_keys = list(_yaml(manifest_file))

    schema = await _create(
        client,
        "/api/v1/task-schemas",
        {
            **yaml.safe_load(HAND_WRITTEN_SCHEMA),
            "file_path": schema_file.relative_to(workspace).as_posix(),
        },
    )

    created = manifest_file.read_text(encoding="utf-8")
    assert _comments(created) == _comments(manifest_text)
    assert list(_yaml(manifest_file)) == manifest_keys
    assert _yaml(manifest_file)["task_schemas"] == [
        {
            "task_schema_id": "sentiment",
            "task_type_plugin": None,
            "definition_path": "workbench/config/task-schemas/sentiment.yaml",
        }
    ]

    resp = await client.put(
        f"/api/v1/task-schemas/{schema['task_schema_id']}",
        json={"title": "Review sentiment"},
    )

    assert resp.status_code == 200, resp.text
    assert schema_file.read_text(encoding="utf-8") == HAND_WRITTEN_SCHEMA.replace(
        "title: Sentiment\n", "title: Review sentiment\n"
    )
    assert _yaml(schema_file)["label_fields"][0]["options"] == ["yes", "no"]
    assert manifest_file.read_text(encoding="utf-8") == created


@pytest.mark.asyncio
async def test_config_writes_keep_keys_added_to_the_manifest_by_hand(client, workspace):
    schema = await _create(client, "/api/v1/task-schemas", SCHEMA)
    manifest_file = workspace / "workbench.project.yaml"
    manifest = _yaml(manifest_file)
    owner = {"team": "research", "reviewed_on": date(2026, 11, 1)}
    manifest["owner"] = owner
    manifest["task_schemas"][0]["reviewed_by"] = "alice"
    manifest_file.write_text(yaml.safe_dump(manifest, sort_keys=False), "utf-8")

    await _create(client, "/api/v1/workflows", WORKFLOW)
    after_create = _yaml(manifest_file)
    resp = await client.put(
        f"/api/v1/task-schemas/{schema['task_schema_id']}",
        json={"title": "Review sentiment"},
    )
    assert resp.status_code == 200, resp.text
    after_update = _yaml(manifest_file)

    for written in (after_create, after_update):
        assert written["owner"] == owner
        assert written["task_schemas"][0]["reviewed_by"] == "alice"
    assert [w["workflow_id"] for w in after_update["workflows"]] == ["label-reviews"]


@pytest.mark.parametrize(
    "broken",
    ["title: Sentiment\ntitle: Twice\n", "title: [never closed\n"],
    ids=["duplicate-key", "unparseable"],
)
@pytest.mark.asyncio
async def test_an_update_rewrites_a_hand_edited_file_it_cannot_round_trip(
    client, workspace, broken
):
    schema = await _create(client, "/api/v1/task-schemas", SCHEMA)
    schema_file = workspace / "workbench/config/task-schemas/sentiment.yaml"
    schema_file.write_text(broken, encoding="utf-8")

    resp = await client.put(
        f"/api/v1/task-schemas/{schema['task_schema_id']}",
        json={"title": "Review sentiment"},
    )

    assert resp.status_code == 200, resp.text
    assert _yaml(schema_file)["title"] == "Review sentiment"
    assert _yaml(schema_file)["label_fields"][0]["options"] == ["positive", "negative"]


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


def _files(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file()
    }


class CommitRefused(Exception):
    """The database refused to commit."""


@contextmanager
def _commits_refused(engine):
    def refuse(_conn) -> None:
        raise CommitRefused

    event.listen(engine, "commit", refuse)
    try:
        yield
    finally:
        event.remove(engine, "commit", refuse)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        "update task schema",
        "update workflow",
        "create task schema",
        "create workflow",
        "create dataset",
    ],
)
async def test_a_refused_commit_leaves_the_workspace_files_as_they_were(
    client, workspace, change
):
    schema = await _create(client, "/api/v1/task-schemas", SCHEMA)
    workflow = await _create(client, "/api/v1/workflows", WORKFLOW)
    requests = {
        "update task schema": (
            "PUT",
            f"/api/v1/task-schemas/{schema['task_schema_id']}",
            {"title": "Never saved"},
        ),
        "update workflow": (
            "PUT",
            f"/api/v1/workflows/{workflow['workflow_id']}",
            {"description": "Never saved"},
        ),
        "create task schema": (
            "POST",
            "/api/v1/task-schemas",
            {
                **SCHEMA,
                "task_schema_slug": "unsaved",
                "workspace_id": client.workspace_id,
            },
        ),
        "create workflow": (
            "POST",
            "/api/v1/workflows",
            {
                **WORKFLOW,
                "workflow_slug": "unsaved",
                "workspace_id": client.workspace_id,
            },
        ),
        "create dataset": (
            "POST",
            "/api/v1/datasets",
            {
                "dataset_name": "unsaved",
                "source_type": "jsonl",
                "workspace_id": client.workspace_id,
            },
        ),
    }
    method, route, body = requests[change]
    before = _files(workspace)

    with _commits_refused(client.engine), pytest.raises(CommitRefused):
        await client.request(method, route, json=body)

    assert _files(workspace) == before


@pytest.mark.asyncio
async def test_a_read_only_manifest_refuses_the_update_and_keeps_the_file(
    client, workspace
):
    schema = await _create(client, "/api/v1/task-schemas", SCHEMA)
    manifest = workspace / "workbench.project.yaml"
    before = _files(workspace)
    manifest.chmod(stat.S_IREAD)
    try:
        resp = await client.put(
            f"/api/v1/task-schemas/{schema['task_schema_id']}",
            json={"title": "Never saved"},
        )
    finally:
        manifest.chmod(stat.S_IREAD | stat.S_IWRITE)

    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "WORKSPACE_FILE_NOT_WRITABLE"
    assert resp.json()["error"]["details"]["path"] == "workbench.project.yaml"
    assert _files(workspace) == before
    after = await client.get(f"/api/v1/task-schemas/{schema['task_schema_id']}")
    assert after.json()["title"] == SCHEMA["title"]


_CREATE_SCHEMAS_WHEN_TOLD = """
import sys, time, uuid
from pathlib import Path
from fastapi.testclient import TestClient
from molabel.app.main import create_app
from molabel.app.services.session import create_session_token

workspace_id, reviewer_id, worker, count = sys.argv[1:5]
ready, go = Path(sys.argv[5]), Path(sys.argv[6])
app = create_app()
with TestClient(app) as client:
    client.cookies.set(
        "molabel_session",
        create_session_token(uuid.UUID(reviewer_id), app.state.app_secret),
    )
    ready.touch()
    while not go.exists():
        time.sleep(0.005)
    for n in range(int(count)):
        resp = client.post(
            "/api/v1/task-schemas",
            json={
                "workspace_id": workspace_id,
                "task_schema_slug": f"w{worker}-{n}",
                "task_type": "text_classification",
                "title": f"Worker {worker} schema {n}",
            },
        )
        assert resp.status_code == 201, resp.text
"""


def test_servers_writing_one_manifest_together_keep_every_entry(
    tmp_path: Path, workspace: Path, monkeypatch: pytest.MonkeyPatch
):
    db_url = f"sqlite:///{(tmp_path / 'server.db').as_posix()}"
    env = {
        **os.environ,
        "MOLABEL_DB_URL": db_url,
        "MOLABEL_DATA_DIR": str(tmp_path / "data"),
    }
    monkeypatch.setenv("MOLABEL_DB_URL", env["MOLABEL_DB_URL"])
    monkeypatch.setenv("MOLABEL_DATA_DIR", env["MOLABEL_DATA_DIR"])
    with TestClient(create_app()) as setup:
        booted = setup.post(
            "/api/v1/cli/workspaces/bootstrap", json={"path": str(workspace)}
        ).json()
    workers, per_worker = 4, 8
    go = tmp_path / "go"
    ready = [tmp_path / f"ready-{n}" for n in range(workers)]
    servers = [
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                _CREATE_SCHEMAS_WHEN_TOLD,
                booted["workspace_id"],
                booted["reviewer_id"],
                str(n),
                str(per_worker),
                str(flag),
                str(go),
            ],
            env=env,
            stderr=subprocess.PIPE,
            text=True,
        )
        for n, flag in enumerate(ready)
    ]
    deadline = time.monotonic() + 60
    while not all(flag.exists() for flag in ready):
        assert time.monotonic() < deadline, "servers did not start"
        assert all(s.poll() is None for s in servers), [
            s.communicate()[1] for s in servers if s.poll() is not None
        ]
        time.sleep(0.01)
    go.touch()

    errors = [server.communicate(timeout=180)[1] for server in servers]

    assert [server.returncode for server in servers] == [0] * workers, errors
    listed = {
        e["task_schema_id"]
        for e in _yaml(workspace / "workbench.project.yaml")["task_schemas"]
    }
    expected = {f"w{w}-{n}" for w in range(workers) for n in range(per_worker)}
    assert listed == expected


@pytest.mark.asyncio
async def test_a_read_only_manifest_refuses_the_import_and_keeps_no_records(
    client, workspace
):
    dataset = await _create(
        client,
        "/api/v1/datasets",
        {"dataset_name": "reviews", "source_type": "jsonl", "record_kind": "text"},
    )
    manifest = workspace / "workbench.project.yaml"
    before = _files(workspace)
    manifest.chmod(stat.S_IREAD)
    try:
        resp = await client.post(
            f"/api/v1/datasets/{dataset['dataset_id']}/import",
            json={"source_uri": "data/reviews.jsonl"},
        )
    finally:
        manifest.chmod(stat.S_IREAD | stat.S_IWRITE)

    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "WORKSPACE_FILE_NOT_WRITABLE"
    assert _files(workspace) == before
    records = await client.get(f"/api/v1/datasets/{dataset['dataset_id']}/records")
    assert records.json()["items"] == []


@pytest.fixture()
def threaded(tmp_path: Path, workspace: Path):
    """An app on a database file, so requests on separate threads overlap."""
    engine = engine_from_url(f"sqlite:///{(tmp_path / 'threaded.db').as_posix()}")
    upgrade_database(engine)
    app = create_app()
    app.state.engine = engine
    app.state.app_secret = "config-files-secret"
    booted = TestClient(app).post(
        "/api/v1/cli/workspaces/bootstrap", json={"path": str(workspace)}
    )
    assert booted.status_code == 201, booted.text
    app.state.workspace_id = booted.json()["workspace_id"]
    app.state.session = booted.cookies["molabel_session"]
    yield app
    engine.dispose()


def _client(app) -> TestClient:
    return TestClient(app, cookies={"molabel_session": app.state.session})


def _during_a_rolled_back_schema_create(app, action):
    """Run *action* while a task schema create has written its files.

    The create then fails its database insert and puts its files back. It
    waits briefly for *action* first, so an action that does not wait for the
    workspace lock lands inside the create.
    """
    in_flight, acted = threading.Event(), threading.Event()

    def fail_the_first_insert(_conn, _cursor, statement, *_args) -> None:
        if statement.startswith("INSERT INTO task_schemas") and not in_flight.is_set():
            in_flight.set()
            acted.wait(0.5)
            raise CommitRefused

    engine = app.state.engine
    event.listen(engine, "before_cursor_execute", fail_the_first_insert)
    try:
        with ThreadPoolExecutor(1) as pool:
            create = pool.submit(
                _client(app).post,
                "/api/v1/task-schemas",
                json={**SCHEMA, "workspace_id": app.state.workspace_id},
            )
            assert in_flight.wait(10), "the create never reached its insert"
            result = action(_client(app))
            acted.set()
            with pytest.raises(CommitRefused):
                create.result(timeout=30)
    finally:
        event.remove(engine, "before_cursor_execute", fail_the_first_insert)
    return result


AGENT_EDIT = "# An agent's edit\n"


def _manifest_edit(workspace: Path, workspace_id: str) -> dict:
    manifest = workspace / "workbench.project.yaml"
    return {
        "kind": "workspace_manifest",
        "selector": "workspace",
        "workspace_id": workspace_id,
        "content": manifest.read_text(encoding="utf-8") + AGENT_EDIT,
        "expected_hash": hashlib.sha256(manifest.read_bytes()).hexdigest(),
    }


def _write(client: TestClient, edit: dict):
    return client.post("/api/v1/cli/artifacts/write", json=edit)


def _propose_and_accept(client: TestClient, edit: dict):
    proposal = client.post("/api/v1/cli/artifacts/proposals", json=edit)
    assert proposal.status_code == 200, proposal.text
    return client.post(
        f"/api/v1/cli/artifacts/proposals/{proposal.json()['proposal_id']}/decision",
        json={"decision": "accept", "workspace_id": edit["workspace_id"]},
    )


@pytest.mark.parametrize(
    "apply", [_write, _propose_and_accept], ids=["write", "accepted proposal"]
)
def test_an_artifact_edit_during_a_rolled_back_config_write_conflicts(
    threaded, workspace, apply
):
    resp = _during_a_rolled_back_schema_create(
        threaded,
        lambda client: apply(
            client, _manifest_edit(workspace, threaded.state.workspace_id)
        ),
    )

    manifest = (workspace / "workbench.project.yaml").read_text(encoding="utf-8")
    assert (resp.status_code, AGENT_EDIT in manifest) == (409, False)


def _schema_edit(path: Path, workspace_id: str, *, expected_hash: str | None) -> dict:
    return {
        "kind": "task_schema",
        "selector": path.stem,
        "workspace_id": workspace_id,
        "content": "task_slug: sentiment\n" + AGENT_EDIT,
        "expected_hash": expected_hash,
    }


@pytest.mark.parametrize(
    "apply", [_write, _propose_and_accept], ids=["write", "accepted proposal"]
)
def test_an_edit_to_a_file_a_rolled_back_create_removed_conflicts(
    threaded, workspace, apply
):
    schema = workspace / "workbench" / "config" / "task-schemas" / "sentiment.yaml"

    def edit_the_new_schema(client: TestClient):
        seen = hashlib.sha256(schema.read_bytes()).hexdigest()
        return apply(
            client,
            _schema_edit(schema, threaded.state.workspace_id, expected_hash=seen),
        )

    resp = _during_a_rolled_back_schema_create(threaded, edit_the_new_schema)

    assert (resp.status_code, schema.exists()) == (409, False)


@pytest.mark.parametrize(
    "apply", [_write, _propose_and_accept], ids=["write", "accepted proposal"]
)
def test_an_edit_without_an_expected_hash_creates_a_new_file(
    threaded, workspace, apply
):
    schema = workspace / "workbench" / "config" / "task-schemas" / "fresh.yaml"

    resp = apply(
        _client(threaded),
        _schema_edit(schema, threaded.state.workspace_id, expected_hash=None),
    )

    assert resp.status_code == 200, resp.text
    assert AGENT_EDIT in schema.read_text(encoding="utf-8")


def test_bootstrap_during_a_rolled_back_config_write_indexes_none_of_it(
    threaded, workspace
):
    resp = _during_a_rolled_back_schema_create(
        threaded,
        lambda client: client.post(
            "/api/v1/cli/workspaces/bootstrap", json={"path": str(workspace)}
        ),
    )

    assert resp.status_code == 201, resp.text
    schemas = _client(threaded).get("/api/v1/task-schemas").json()["items"]
    assert [s["task_schema_slug"] for s in schemas] == []


def test_an_import_and_a_config_write_at_once_both_succeed(threaded, workspace):
    client = TestClient(
        threaded,
        cookies={"molabel_session": threaded.state.session},
        raise_server_exceptions=False,
    )
    dataset = client.post(
        "/api/v1/datasets",
        json={
            "workspace_id": threaded.state.workspace_id,
            "dataset_name": "reviews",
            "source_type": "jsonl",
        },
    )
    assert dataset.status_code == 201, dataset.text
    import_wrote, config_writing = threading.Event(), threading.Event()

    def overlap(_conn, _cursor, statement, *_args) -> None:
        if statement.lstrip().startswith("UPDATE datasets"):
            import_wrote.set()
            config_writing.wait(1)
        elif statement.startswith("INSERT INTO task_schemas"):
            config_writing.set()

    engine = threaded.state.engine
    event.listen(engine, "before_cursor_execute", overlap)
    try:
        with ThreadPoolExecutor(2) as pool:
            imported = pool.submit(
                client.post,
                f"/api/v1/datasets/{dataset.json()['dataset_id']}/import",
                json={"source_uri": "data/reviews.jsonl"},
            )
            assert import_wrote.wait(10), "the import never wrote its records"
            created = pool.submit(
                client.post,
                "/api/v1/task-schemas",
                json={**SCHEMA, "workspace_id": threaded.state.workspace_id},
            )
            statuses = (
                imported.result(timeout=30).status_code,
                created.result(timeout=30).status_code,
            )
    finally:
        event.remove(engine, "before_cursor_execute", overlap)

    assert statuses == (202, 201)
    manifest = _yaml(workspace / "workbench.project.yaml")
    assert [e["task_schema_id"] for e in manifest["task_schemas"]] == ["sentiment"]
    datasets = {d["dataset_id"]: d["source_paths"] for d in manifest["datasets"]}
    assert datasets["reviews"] == ["data/reviews.jsonl"]


NATIVE_WORKFLOW = """\
name: Native review
description: Written by hand in the core format.
steps:
  - id: ingest
    type: data_ingest
    config:
      source: data/reviews.jsonl
  - id: review
    type: human_review
    config:
      sample_strategy: all
"""


async def _bootstrap_conflicts(client: AsyncClient, root: Path) -> list[dict]:
    resp = await client.post(
        "/api/v1/cli/workspaces/bootstrap", json={"path": str(root)}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["conflicts"]


def _steps(workflow: dict) -> list[tuple[str, str, dict]]:
    return [(s["step_id"], s["step_type"], s["config"]) for s in workflow["steps"]]


@pytest.mark.asyncio
async def test_a_workflow_written_by_the_api_parses_and_reindexes(client, workspace):
    workflow = await _create(client, "/api/v1/workflows", WORKFLOW)
    workflow_file = workspace / "workbench/workflows/label-reviews.yaml"

    parsed = parse_workflow_yaml(workflow_file)
    conflicts = await _bootstrap_conflicts(client, workspace)
    reindexed = await client.get(f"/api/v1/workflows/{workflow['workflow_id']}")

    assert parsed.name == WORKFLOW["name"]
    assert [(s.id, s.type, s.config) for s in parsed.steps] == [
        ("ingest", "data_ingest", {"source": "data/reviews.jsonl"})
    ]
    assert conflicts == []
    assert _steps(reindexed.json()) == _steps(workflow)


@pytest.mark.asyncio
async def test_a_native_workflow_file_reindexes_into_its_row(client, workspace):
    workflow_file = workspace / "workbench/workflows/native-review.yaml"
    workflow_file.parent.mkdir(parents=True)
    workflow_file.write_text(NATIVE_WORKFLOW, encoding="utf-8")
    registered = await _create(
        client,
        "/api/v1/workflows",
        {
            "name": "Native review",
            "workflow_slug": "native-review",
            "file_path": "workbench/workflows/native-review.yaml",
        },
    )

    conflicts = await _bootstrap_conflicts(client, workspace)
    reindexed = await client.get(f"/api/v1/workflows/{registered['workflow_id']}")

    assert conflicts == []
    assert _steps(reindexed.json()) == [
        ("ingest", "data_ingest", {"source": "data/reviews.jsonl"}),
        ("review", "human_review", {"sample_strategy": "all"}),
    ]
    assert workflow_file.read_text(encoding="utf-8") == NATIVE_WORKFLOW


API_FIELDS_WORKFLOW = """\
workflow_slug: older-review
name: Older review
steps:
- step_id: ingest
  step_type: data_ingest
  label: Intake
  config:
    source: data/reviews.jsonl
"""


@pytest.mark.asyncio
async def test_a_workflow_file_with_api_step_fields_still_reindexes(client, workspace):
    workflow_file = workspace / "workbench/workflows/older-review.yaml"
    workflow_file.parent.mkdir(parents=True)
    workflow_file.write_text(API_FIELDS_WORKFLOW, encoding="utf-8")
    registered = await _create(
        client,
        "/api/v1/workflows",
        {
            "name": "Older review",
            "workflow_slug": "older-review",
            "file_path": "workbench/workflows/older-review.yaml",
        },
    )

    conflicts = await _bootstrap_conflicts(client, workspace)
    reindexed = await client.get(f"/api/v1/workflows/{registered['workflow_id']}")
    updated = await client.put(
        f"/api/v1/workflows/{registered['workflow_id']}",
        json={"description": "Rewritten by the API."},
    )

    assert conflicts == []
    assert [
        (s["step_id"], s["step_type"], s["label"], s["config"])
        for s in reindexed.json()["steps"]
    ] == [("ingest", "data_ingest", "Intake", {"source": "data/reviews.jsonl"})]
    assert updated.status_code == 200, updated.text
    assert [(s.id, s.type) for s in parse_workflow_yaml(workflow_file).steps] == [
        ("ingest", "data_ingest")
    ]

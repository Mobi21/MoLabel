"""Ids that JSON and text columns hold are hyphenated by revision 006 (#29)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from pathlib import Path

import pytest
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from sqlalchemy import text
from sqlmodel import SQLModel

import molabel.core
import molabel.core.models  # noqa: F401
from molabel.core.data.snapshot_service import SnapshotService
from molabel.core.database import HyphenatedUuid, get_engine
from molabel.core.migration_runner import upgrade_database
from tests.integration.review_flow import (
    _as,
    _review_all,
    _review_both,
    _start_review,
    review_app,
    review_client,
)
from tests.integration.test_api_workflows import (
    OFFLINE_SENTIMENT,
    SENTIMENT_RECORDS,
    _insert_workflow,
    _seed_reviewer,
    _seed_task_schema,
    _seed_workspace,
    _write_demo_reviews,
)

MIGRATIONS_DIR = Path(molabel.core.__file__).resolve().parent / "migrations"

UUID_COLUMNS = [
    (table.name, column.name)
    for table in SQLModel.metadata.sorted_tables
    for column in table.columns
    if isinstance(column.type, HyphenatedUuid)
]


def _db_path(app) -> Path:
    return Path(app.state.engine.url.database)


def _hex(value: str) -> str:
    return uuid.UUID(value).hex


def _as_written_before_005(db_path: Path) -> None:
    """Every UUID column in hex and the database at 004, as the ORM left it."""
    with sqlite3.connect(db_path) as conn:
        for table, column in UUID_COLUMNS:
            conn.execute(f"UPDATE {table} SET {column} = replace({column}, '-', '')")
        conn.execute("UPDATE alembic_version SET version_num = '004'")


def _context(db_path: Path, execution_id: str) -> dict:
    with sqlite3.connect(db_path) as conn:
        (raw,) = conn.execute(
            "SELECT context FROM workflow_executions WHERE id IN (?, ?)",
            (execution_id, _hex(execution_id)),
        ).fetchone()
    return json.loads(raw)


def _set_context(db_path: Path, execution_id: str, context: dict) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE workflow_executions SET context = ? WHERE id IN (?, ?)",
            (json.dumps(context), execution_id, _hex(execution_id)),
        )


def _with_hex_database_ids(context: dict) -> dict:
    """The context as a workflow wrote it while the database held hex ids.

    The workflow copied the workspace, dataset and record ids it read from
    the database into the context, in the spelling the database held.
    """
    return {
        **context,
        "workspace_id": _hex(context["workspace_id"]),
        "datasets": {
            _hex(key): {**ref, "dataset_id": _hex(ref["dataset_id"])}
            for key, ref in context["datasets"].items()
        },
        "record_sets": {
            step: {**records, "record_ids": [_hex(r) for r in records["record_ids"]]}
            for step, records in context["record_sets"].items()
        },
    }


INGEST_GATE_EXPORT = [
    {
        "step_id": "ingest",
        "step_type": "data_ingest",
        "config": {"source": "data/reviews.jsonl"},
    },
    {"step_id": "approve", "step_type": "gate", "config": {}},
    {
        "step_id": "export_results",
        "step_type": "export",
        "config": {"format": "jsonl", "destination": "workbench/exports/resumed"},
    },
]


async def _paused_at_gate(client, app, tmp_path):
    engine = app.state.engine
    workspace_id = _seed_workspace(engine, tmp_path)
    token = _seed_reviewer(engine, workspace_id)
    _write_demo_reviews(tmp_path)
    workflow_id = _insert_workflow(engine, workspace_id, INGEST_GATE_EXPORT)
    started = await client.post(
        f"/api/v1/workflows/{workflow_id}/execute", json={}, headers=_as(token)
    )
    assert started.json()["current_step_id"] == "approve", started.text
    return workflow_id, started.json()["execution_id"], token


async def _advance(client, workflow_id, execution_id, step_id, token) -> dict:
    advanced = await client.post(
        f"/api/v1/workflows/{workflow_id}/executions/{execution_id}/"
        f"steps/{step_id}/advance",
        json={},
        headers=_as(token),
    )
    assert advanced.status_code == 200, advanced.text
    return advanced.json()


def _exported(tmp_path: Path, execution: dict) -> list[dict]:
    assert execution["status"] == "completed", execution["error_summary"]
    (bundle_id,) = execution["context"]["export_bundle_ids"]
    export = tmp_path / "workbench" / "exports" / "resumed" / f"{bundle_id}.jsonl"
    return [json.loads(line) for line in export.read_text().splitlines()]


@pytest.mark.asyncio
async def test_a_paused_workflow_exports_every_record_after_the_migration(tmp_path):
    app = review_app(tmp_path)
    async with review_client(app) as client:
        workflow_id, execution_id, token = await _paused_at_gate(client, app, tmp_path)
        db_path = _db_path(app)
        record_ids = _context(db_path, execution_id)["record_sets"]["ingest"][
            "record_ids"
        ]
        _as_written_before_005(db_path)
        _set_context(
            db_path,
            execution_id,
            _with_hex_database_ids(_context(db_path, execution_id)),
        )

        upgrade_database(app.state.engine)
        resumed = await _advance(client, workflow_id, execution_id, "approve", token)

    rows = _exported(tmp_path, resumed)

    assert len(record_ids) == 3
    assert [row["record_id"] for row in rows] == record_ids
    assert [row["external_id"] for row in rows] == ["r1", "r2", "r3"]


A, B, C, D, E, F, G = (uuid.uuid4() for _ in range(7))
HASH = hashlib.md5(b"a payload, not an id").hexdigest()

STEP_SUMMARY = {
    "dataset_id": "id:C",
    "task_schema_id": HASH,
    "agent_run_ids": ["id:E"],
    "per_model_results": [{"agent_run_id": "id:E", "model": HASH}],
    "snapshot_id": "id:G",
    "queue_id": HASH,
    "content_hash": HASH,
}

CONTAINERS = {
    "workflow context": (
        "workflow_executions",
        "context",
        {
            "workspace_id": "id:A",
            "workflow_execution_id": "id:B",
            "workflow_version": 1,
            "datasets": {
                "id:C": {"dataset_id": "id:C", "dataset_name": HASH, "record_count": 1}
            },
            "record_sets": {
                "ingest": {
                    "record_ids": ["id:D"],
                    "record_count": 1,
                    "description": HASH,
                }
            },
            "active_record_set_id": "ingest",
            "agent_run_ids": ["id:E"],
            "agent_outputs": {"id:E": {"agent_run_id": "id:E", "model_id": HASH}},
            "review_queue_ids": [HASH],
            "export_bundle_ids": ["id:F"],
            "snapshot_ids": ["id:G"],
            "step_outputs": {"agent": {"step_id": "agent", "summary": STEP_SUMMARY}},
            "variables": {"checksum": HASH},
        },
    ),
    "workflow step result": (
        "workflow_step_executions",
        "result",
        {"status": "completed", "summary": STEP_SUMMARY, "warnings": [HASH]},
    ),
    "review task agent outputs": (
        "review_tasks",
        "agent_output_ids",
        ["id:A", "id:B"],
    ),
    "adjudication event ids": (
        "adjudications",
        "conflicting_event_ids",
        ["id:A", "id:B"],
    ),
    "adjudication metadata": (
        "adjudications",
        "metadata",
        {"queue_id": HASH, "review_event_id": "id:C"},
    ),
    "snapshot membership": (
        "dataset_snapshots",
        "dataset_membership",
        {
            "health_status": "healthy",
            "record_states": {"id:A": {"latest_label": {"hash": HASH}}},
        },
    ),
    "saved view filters": (
        "saved_views",
        "filters",
        {
            "dataset_id": "id:A",
            "parent_subset_id": "id:B",
            "selection_criteria": {
                "include_record_ids": ["id:C"],
                "exclude_record_ids": ["id:D"],
                "content_hash": HASH,
            },
            "tags": [HASH],
        },
    ),
    "dataset source config": (
        "datasets",
        "source_config",
        {"source_dataset_id": "id:A", "source_subset_id": "id:B", "sha": HASH},
    ),
    "agent event payload": (
        "agent_events",
        "payload",
        {
            "workspace_id": "id:A",
            "dataset_id": "id:B",
            "task_schema_id": "id:C",
            "model_profile_id": "id:D",
            "record_ids": ["id:E", "id:F"],
            "response_hash": HASH,
        },
    ),
}
"""A JSON document per id container; ``id:X`` marks where the id ``X`` sits."""

TEXT_CONTAINERS = {
    "audit event": ("audit_events", {"workspace_id": A, "actor": B, "object_id": C})
}

IDS = dict(zip("ABCDEFG", (A, B, C, D, E, F, G), strict=True))


def _spelled(document, spell):
    """``document`` with each ``id:X`` marker replaced by ``spell(X)``."""
    if isinstance(document, dict):
        return {_spelled(k, spell): _spelled(v, spell) for k, v in document.items()}
    if isinstance(document, list):
        return [_spelled(item, spell) for item in document]
    if isinstance(document, str) and document.startswith("id:"):
        return spell(IDS[document[3:]])
    return document


_FILLER = {"INTEGER": 0, "BOOLEAN": 0, "FLOAT": 0.0, "JSON": "{}"}


def _insert(conn: sqlite3.Connection, table: str, values: dict) -> None:
    """A row of ``table`` with ``values`` and a placeholder in each required column."""
    row = {"id": str(uuid.uuid4()), **values}
    for _, name, sql_type, not_null, default, _ in conn.execute(
        f"PRAGMA table_info({table})"
    ):
        if not_null and default is None and name not in row:
            row[name] = (
                str(uuid.uuid4())
                if sql_type == "CHAR(32)"
                else _FILLER.get(sql_type, "x")
            )
    conn.execute(
        f"INSERT INTO {table} ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
        tuple(row.values()),
    )


ROW_IDS = {name: str(uuid.uuid4()) for name in [*CONTAINERS, *TEXT_CONTAINERS]}
"""The id of the row that holds each container."""


def _database_at_005_with_hex_ids(db_path: Path) -> None:
    engine = get_engine(db_path)
    upgrade_database(engine)
    engine.dispose()
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE alembic_version SET version_num = '005'")
        for name, (table, column, document) in CONTAINERS.items():
            hex_document = _spelled(document, lambda value: value.hex)
            _insert(
                conn, table, {"id": ROW_IDS[name], column: json.dumps(hex_document)}
            )
        for name, (table, columns) in TEXT_CONTAINERS.items():
            values = {column: value.hex for column, value in columns.items()}
            _insert(conn, table, {"id": ROW_IDS[name], **values})
        _insert(conn, "records", {"content_hash": HASH, "payload": json.dumps([HASH])})


def _upgrade(db_path: Path) -> None:
    engine = get_engine(db_path)
    try:
        upgrade_database(engine)
    finally:
        engine.dispose()


def _stored(db_path: Path) -> dict:
    with sqlite3.connect(db_path) as conn:

        def row(name, table, columns):
            sql = f"SELECT {', '.join(columns)} FROM {table} WHERE id = ?"
            return conn.execute(sql, (ROW_IDS[name],)).fetchone()

        stored = {
            name: json.loads(row(name, table, [column])[0])
            for name, (table, column, _) in CONTAINERS.items()
        }
        for name, (table, columns) in TEXT_CONTAINERS.items():
            stored[name] = dict(zip(columns, row(name, table, columns), strict=True))
    return stored


@pytest.mark.parametrize("name", [*CONTAINERS, *TEXT_CONTAINERS])
def test_each_id_container_is_rewritten_hyphenated(tmp_path, name):
    db_path = tmp_path / "legacy.db"
    _database_at_005_with_hex_ids(db_path)

    _upgrade(db_path)

    if name in CONTAINERS:
        expected = _spelled(CONTAINERS[name][2], str)
    else:
        expected = {
            column: str(value) for column, value in TEXT_CONTAINERS[name][1].items()
        }
    assert _stored(db_path)[name] == expected


def test_a_hash_beside_the_ids_is_left_as_it_is(tmp_path):
    db_path = tmp_path / "legacy.db"
    _database_at_005_with_hex_ids(db_path)
    with sqlite3.connect(db_path) as conn:
        before = "\n".join(conn.iterdump()).count(HASH)

    _upgrade(db_path)

    with sqlite3.connect(db_path) as conn:
        dump = "\n".join(conn.iterdump())
        content_hash, payload = conn.execute(
            "SELECT content_hash, payload FROM records"
        ).fetchone()
    assert before >= 20
    assert dump.count(HASH) == before
    assert (content_hash, json.loads(payload)) == (HASH, [HASH])


def test_downgrading_to_005_and_upgrading_again_changes_nothing(tmp_path):
    db_path = tmp_path / "legacy.db"
    _database_at_005_with_hex_ids(db_path)
    _upgrade(db_path)
    migrated = _stored(db_path)
    cfg = AlembicConfig()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")

    for _ in range(2):
        alembic_command.downgrade(cfg, "005")
        _upgrade(db_path)
        assert _stored(db_path) == migrated

    assert migrated["workflow context"] == _spelled(
        CONTAINERS["workflow context"][2], str
    )


AGENT_REVIEW_AGREEMENT_EXPORT = [
    INGEST_GATE_EXPORT[0],
    INGEST_GATE_EXPORT[1],
    {
        "step_id": "agent_label",
        "step_type": "agent_run",
        "config": {"provider_type": "offline", "prompt_ref": "prompts/default.yaml"},
    },
    {"step_id": "check", "step_type": "gate", "config": {}},
    {"step_id": "review", "step_type": "human_review", "config": {}},
    {
        "step_id": "agreement",
        "step_type": "agreement_analysis",
        "config": {"analysis_type": "human_agent"},
    },
    INGEST_GATE_EXPORT[2],
]


@pytest.mark.asyncio
async def test_hex_ids_left_in_a_context_reach_every_later_step(tmp_path):
    app = review_app(tmp_path)
    engine = app.state.engine
    db_path = _db_path(app)
    workspace_id = _seed_workspace(engine, tmp_path)
    token = _seed_reviewer(engine, workspace_id)
    _seed_task_schema(engine, workspace_id)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "reviews.jsonl").write_text(
        "".join(
            json.dumps({"id": record_id, "text": SENTIMENT_RECORDS[record_id]}) + "\n"
            for record_id in ("r1", "r2", "r3")
        )
    )
    workflow_id = _insert_workflow(engine, workspace_id, AGENT_REVIEW_AGREEMENT_EXPORT)
    async with review_client(app) as client:
        started = await client.post(
            f"/api/v1/workflows/{workflow_id}/execute", json={}, headers=_as(token)
        )
        execution_id = started.json()["execution_id"]
        context = _context(db_path, execution_id)
        _set_context(db_path, execution_id, _with_hex_database_ids(context))

        labelled = await _advance(client, workflow_id, execution_id, "approve", token)
        assert labelled["current_step_id"] == "check", labelled["error_summary"]
        context = _context(db_path, execution_id)
        agent_run_ids = [_hex(run_id) for run_id in context["agent_run_ids"]]
        _set_context(db_path, execution_id, {**context, "agent_run_ids": agent_run_ids})
        reviewing = await _advance(client, workflow_id, execution_id, "check", token)
        assert reviewing["current_step_id"] == "review", reviewing["error_summary"]
        (queue_id,) = reviewing["context"]["review_queue_ids"]
        await _review_all(client, queue_id, token, OFFLINE_SENTIMENT)
        done = await _advance(client, workflow_id, execution_id, "review", token)
        report = await client.get(
            "/api/v1/quality/agreement",
            params={"workspace_id": str(workspace_id), "queue_id": queue_id},
            headers=_as(token),
        )

    results = {state["step_id"]: state["result"] for state in done["step_states"]}
    sentiment = results["agreement"]["summary"]["fields"]["sentiment"]
    assert (sentiment["comparisons"], sentiment["agreements"]) == (3, 3)
    bound = report.json()["human_agent"]["fields"]["sentiment"]
    assert (bound["comparisons"], bound["agreements"]) == (3, 3)
    rows = _exported(tmp_path, done)
    assert [row["external_id"] for row in rows] == ["r1", "r2", "r3"]
    assert all(row["labels"] is not None for row in rows)


async def _imported_dataset(client, workspace_id, token) -> str:
    created = await client.post(
        "/api/v1/datasets",
        json={
            "workspace_id": str(workspace_id),
            "dataset_name": "Imported reviews",
            "source_type": "jsonl",
        },
        headers=_as(token),
    )
    assert created.status_code == 201, created.text
    dataset_id = created.json()["dataset_id"]
    imported = await client.post(
        f"/api/v1/datasets/{dataset_id}/import",
        json={
            "records": [{"id": "r1", "text": "Fast."}, {"id": "r2", "text": "Slow."}]
        },
        headers=_as(token),
    )
    assert imported.status_code == 202, imported.text
    return dataset_id


@pytest.mark.asyncio
async def test_a_workflow_may_name_its_dataset_and_task_schema_by_hex_id(tmp_path):
    app = review_app(tmp_path)
    engine = app.state.engine
    workspace_id = _seed_workspace(engine, tmp_path)
    token = _seed_reviewer(engine, workspace_id)
    other_schema_id = _seed_task_schema(engine, workspace_id)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE task_schemas SET task_schema_slug = 'other' WHERE id = :id"),
            {"id": str(other_schema_id)},
        )
    schema_id = _seed_task_schema(engine, workspace_id)
    async with review_client(app) as client:
        dataset_id = await _imported_dataset(client, workspace_id, token)
        workflow_id = _insert_workflow(
            engine,
            workspace_id,
            [
                {
                    "step_id": "ingest",
                    "step_type": "data_ingest",
                    "config": {"dataset_id": _hex(dataset_id)},
                },
                {
                    "step_id": "review",
                    "step_type": "human_review",
                    "config": {"task_schema_id": schema_id.hex},
                },
            ],
        )
        started = await client.post(
            f"/api/v1/workflows/{workflow_id}/execute", json={}, headers=_as(token)
        )

    assert started.json()["current_step_id"] == "review", started.text
    with engine.connect() as conn:
        queued = conn.execute(text("SELECT task_schema_id FROM review_tasks")).all()
    assert [row[0] for row in queued] == [str(schema_id)] * 2


@pytest.mark.asyncio
async def test_a_resolution_stored_with_hex_event_ids_stays_resolved(tmp_path):
    app = review_app(tmp_path)
    async with review_client(app) as client:
        _, tokens, queue = await _start_review(client, app, tmp_path)
        await _review_both(client, queue["queue_id"], tokens)
        base = f"/api/v1/adjudication/queues/{queue['queue_id']}/disagreements"
        (item,) = (await client.get(base, headers=_as(tokens[0]))).json()["items"]
        path = f"{base}/{item['record_id']}"
        shown = (await client.get(path, headers=_as(tokens[0]))).json()
        resolved = await client.post(
            f"{path}/resolve",
            json={
                "resolved_labels": {"sentiment": "neutral"},
                "rationale": "Hedged.",
                "review_event_ids": [
                    labels["review_event_id"] for labels in shown["reviewer_labels"]
                ],
            },
            headers=_as(tokens[0]),
        )
        assert resolved.status_code == 200, resolved.text
        with sqlite3.connect(_db_path(app)) as conn:
            (raw,) = conn.execute(
                "SELECT conflicting_event_ids FROM adjudications"
            ).fetchone()
            hex_ids = [_hex(event_id) for event_id in json.loads(raw)]
            conn.execute(
                "UPDATE adjudications SET conflicting_event_ids = ?",
                (json.dumps(hex_ids),),
            )

        listed = (await client.get(base, headers=_as(tokens[1]))).json()

    assert (listed["unresolved"], listed["items"][0]["status"]) == (0, "resolved")


def _set_labels(db_path: Path, labels: dict) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE records SET latest_label = ?, label_count = 1",
            (json.dumps(labels),),
        )


def _labels(db_path: Path) -> list:
    with sqlite3.connect(db_path) as conn:
        return [
            json.loads(raw)
            for (raw,) in conn.execute("SELECT latest_label FROM records").fetchall()
        ]


@pytest.mark.asyncio
@pytest.mark.parametrize("restorer", ["cli route", "snapshot service"])
async def test_a_snapshot_keyed_by_hex_record_ids_restores_its_records(
    tmp_path, restorer
):
    app = review_app(tmp_path)
    engine = app.state.engine
    db_path = _db_path(app)
    workspace_id = _seed_workspace(engine, tmp_path)
    token = _seed_reviewer(engine, workspace_id)
    async with review_client(app) as client:
        dataset_id = await _imported_dataset(client, workspace_id, token)
        _set_labels(db_path, {"sentiment": "positive"})
        snapshot = SnapshotService().create_snapshot(
            engine,
            workspace_id=workspace_id,
            dataset_id=uuid.UUID(dataset_id),
            name="Before",
        )
        snapshot_id = str(snapshot.snapshot_id)
        with sqlite3.connect(db_path) as conn:
            (raw,) = conn.execute(
                "SELECT dataset_membership FROM dataset_snapshots WHERE id = ?",
                (snapshot_id,),
            ).fetchone()
            membership = json.loads(raw)
            membership["record_states"] = {
                _hex(key): state for key, state in membership["record_states"].items()
            }
            conn.execute(
                "UPDATE dataset_snapshots SET dataset_membership = ? WHERE id = ?",
                (json.dumps(membership), snapshot_id),
            )
        _set_labels(db_path, {"sentiment": "negative"})

        if restorer == "cli route":
            restored = await client.post(
                f"/api/v1/cli/datasets/{dataset_id}/snapshots/{snapshot_id}/restore",
                headers={"X-MoLabel-Session": token},
            )
            assert restored.status_code == 200, restored.text
        else:
            SnapshotService().restore_snapshot(
                engine, workspace_id=workspace_id, snapshot_id=snapshot.snapshot_id
            )

    assert len(membership["record_states"]) == 2
    assert _labels(db_path) == [{"sentiment": "positive"}] * 2

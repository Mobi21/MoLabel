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
from sqlmodel import SQLModel

import molabel.core
import molabel.core.models  # noqa: F401
from molabel.core.database import HyphenatedUuid, get_engine
from molabel.core.migration_runner import upgrade_database
from tests.integration.review_flow import _as, review_app, review_client
from tests.integration.test_api_workflows import (
    _insert_workflow,
    _seed_reviewer,
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


async def _resume_into_export(client, tmp_path, workflow_id, execution_id, token):
    resumed = await client.post(
        f"/api/v1/workflows/{workflow_id}/executions/{execution_id}/"
        "steps/approve/advance",
        json={},
        headers=_as(token),
    )
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["status"] == "completed", resumed.text
    (bundle_id,) = resumed.json()["context"]["export_bundle_ids"]
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
        rows = await _resume_into_export(
            client, tmp_path, workflow_id, execution_id, token
        )

    assert len(record_ids) == 3
    assert [row["record_id"] for row in rows] == record_ids
    assert [row["external_id"] for row in rows] == ["r1", "r2", "r3"]


A, B, C, D, E, F, G = (uuid.uuid4() for _ in range(7))
HASH = hashlib.md5(b"a payload, not an id").hexdigest()

STEP_SUMMARY = {
    "dataset_id": "id:C",
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

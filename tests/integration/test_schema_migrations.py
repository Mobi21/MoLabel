"""The server database schema is created and upgraded by Alembic only."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest
from alembic import command as alembic_command
from alembic.autogenerate import compare_metadata
from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel, select

import molabel.core
import molabel.core.models  # noqa: F401
from molabel.app.main import create_app
from molabel.app.services.session import create_session_token
from molabel.core.database import foreign_key_violations, get_engine
from molabel.core.migration_runner import IncompleteBaselineError
from molabel.core.models import Dataset, DatasetSnapshot, Record

REPO_ROOT = Path(__file__).resolve().parents[2]
LEGACY_FIXTURES = REPO_ROOT / "fixtures" / "migrations"
MIGRATIONS_DIR = Path(molabel.core.__file__).resolve().parent / "migrations"
HEAD = ScriptDirectory(str(MIGRATIONS_DIR)).get_current_head()


def _start_server(monkeypatch: pytest.MonkeyPatch, db_path: Path) -> None:
    monkeypatch.setenv("MOLABEL_DB_URL", f"sqlite:///{db_path.as_posix()}")
    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200


def _revision_and_drift(db_path: Path) -> tuple[tuple[str, ...], list]:
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn, opts={"compare_type": True})
            return ctx.get_current_heads(), compare_metadata(ctx, SQLModel.metadata)
    finally:
        engine.dispose()


def test_fresh_database_at_head_matches_the_models(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "fresh.db"

    _start_server(monkeypatch, db_path)

    revision, drift = _revision_and_drift(db_path)
    assert revision == (HEAD,)
    assert drift == []


@pytest.mark.parametrize(
    "routes_created_audit_events",
    [None, "audit_or_release_route", "artifact_route"],
)
def test_database_created_before_alembic_is_stamped_and_upgraded(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    routes_created_audit_events: str | None,
) -> None:
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        (LEGACY_FIXTURES / "pre-alembic-create-all.sql").read_text(encoding="utf-8")
    )
    if routes_created_audit_events:
        conn.executescript(
            (LEGACY_FIXTURES / "pre-alembic-audit-events.sql").read_text(
                encoding="utf-8"
            )
        )
        if routes_created_audit_events == "artifact_route":
            conn.execute("DROP INDEX idx_audit_events_workspace_id")
        conn.execute(
            "INSERT INTO audit_events (id, workspace_id, event_type, actor, "
            "object_type, object_id, summary, details, created_at) "
            "VALUES ('a1', 'w1', 'release_created', 'r1', 'release', 'x', "
            "'kept', '{}', '2026-01-01T00:00:00')"
        )
    conn.execute(
        "INSERT INTO workspaces (id, workspace_name, workspace_slug, core_version, "
        "root_path, manifest_path, created_at, updated_at) VALUES ('w1', 'Old', "
        "'old', '0.1.0', '/old', 'workbench.project.yaml', '2026-01-01', "
        "'2026-01-01')"
    )
    conn.commit()
    conn.close()

    _start_server(monkeypatch, db_path)

    revision, drift = _revision_and_drift(db_path)
    assert revision == (HEAD,)
    assert drift == []
    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT workspace_name FROM workspaces").fetchall() == [
        ("Old",)
    ]
    kept = conn.execute("SELECT summary FROM audit_events").fetchall()
    conn.close()
    assert kept == ([("kept",)] if routes_created_audit_events else [])


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {row[0] for row in rows}


def test_backup_of_a_wal_database_holds_its_uncheckpointed_tables(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "legacy.db"
    writer = sqlite3.connect(db_path)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("PRAGMA wal_autocheckpoint=0")
    writer.executescript(
        (LEGACY_FIXTURES / "pre-alembic-create-all.sql").read_text(encoding="utf-8")
    )
    writer.commit()
    legacy_tables = _table_names(writer)
    try:
        _start_server(monkeypatch, db_path)
    finally:
        writer.close()

    backups = list(tmp_path.glob("legacy.backup.*.sqlite"))
    assert len(backups) == 1
    backup = sqlite3.connect(backups[0])
    try:
        assert _table_names(backup) == legacy_tables
    finally:
        backup.close()


def test_database_missing_part_of_the_baseline_is_refused_and_left_alone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "partial.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        (LEGACY_FIXTURES / "pre-alembic-create-all.sql").read_text(encoding="utf-8")
    )
    conn.execute("DROP TABLE saved_views")
    conn.execute("ALTER TABLE workspaces DROP COLUMN reference_app")
    conn.commit()
    tables_before = _table_names(conn)
    conn.close()

    with pytest.raises(IncompleteBaselineError) as refused:
        _start_server(monkeypatch, db_path)

    assert "saved_views" in str(refused.value)
    assert "workspaces.reference_app" in str(refused.value)
    conn = sqlite3.connect(db_path)
    try:
        assert _table_names(conn) == tables_before
    finally:
        conn.close()
    assert sorted(
        p.name for p in tmp_path.iterdir() if not p.name.endswith(".migrate.lock")
    ) == ["partial.db"]


_UPGRADE_WHEN_TOLD = """
import sys, time
from pathlib import Path
from sqlalchemy import create_engine
from molabel.core.migration_runner import upgrade_database

url, ready, go = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
ready.touch()
while not go.exists():
    time.sleep(0.005)
upgrade_database(create_engine(url))
"""


def test_servers_starting_together_on_a_fresh_database_all_start(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "fresh.db"
    url = f"sqlite:///{db_path.as_posix()}"
    go = tmp_path / "go"
    ready = [tmp_path / f"ready-{n}" for n in range(4)]
    starts = [
        subprocess.Popen(
            [sys.executable, "-c", _UPGRADE_WHEN_TOLD, url, str(flag), str(go)],
            stderr=subprocess.PIPE,
            text=True,
        )
        for flag in ready
    ]
    deadline = time.monotonic() + 60
    while not all(flag.exists() for flag in ready):
        assert time.monotonic() < deadline, "upgrade processes did not start"
        time.sleep(0.01)
    go.touch()

    errors = [start.communicate(timeout=120)[1] for start in starts]

    assert [start.returncode for start in starts] == [0, 0, 0, 0], errors
    revision, drift = _revision_and_drift(db_path)
    assert revision == (HEAD,)
    assert drift == []


MIXED_ROWS = (
    "workspace",
    "reviewer",
    "schema",
    "dataset",
    "record",
    "snapshot",
    "task",
)


def _legacy_mixed_database(db_path: Path) -> dict[str, uuid.UUID]:
    """A pre-Alembic database with route rows hyphenated and ORM rows in hex.

    The workspace, reviewer, task schema and review task are route rows. The
    dataset, its record and its snapshot are ORM rows, stored as hex, and the
    review task names the record and dataset by their hyphenated spelling, as
    the routes did (#29). Before the rewrite, no row of one kind references a
    row of the other.
    """
    ids = {name: uuid.uuid4() for name in MIXED_ROWS}
    route = {name: str(value) for name, value in ids.items()}
    orm = {name: value.hex for name, value in ids.items()}
    now = "2026-01-01T00:00:00"
    membership = {
        "health_status": "healthy",
        "record_states": {
            route["record"]: {
                "latest_label": {"label": "restored"},
                "composite_confidence": 0.9,
                "export_eligible": 1,
                "flags": ["restored"],
                "label_count": 1,
            }
        },
    }
    conn = sqlite3.connect(db_path)
    conn.executescript(
        (LEGACY_FIXTURES / "pre-alembic-create-all.sql").read_text(encoding="utf-8")
    )
    conn.execute(
        "INSERT INTO workspaces (id, workspace_name, workspace_slug, core_version, "
        "root_path, manifest_path, created_at, updated_at) VALUES (?, 'Mixed', "
        "'mixed', '0.1.0', '/mixed', 'workbench.project.yaml', ?, ?)",
        (route["workspace"], now, now),
    )
    conn.execute(
        "INSERT INTO reviewer_profiles (id, display_name, is_operator, is_active, "
        "created_at, workspace_id) VALUES (?, 'Reviewer', 1, 1, ?, ?)",
        (route["reviewer"], now, route["workspace"]),
    )
    conn.execute(
        "INSERT INTO task_schemas (id, task_schema_slug, version, task_type, title, "
        "label_fields, blind_review_policy, is_active, is_frozen, created_at, "
        "updated_at, workspace_id) VALUES (?, 'schema', 1, 'classification', "
        "'Schema', '[]', 'show_agent_outputs', 1, 0, ?, ?, ?)",
        (route["schema"], now, now, route["workspace"]),
    )
    conn.execute(
        "INSERT INTO datasets (id, dataset_name, dataset_slug, source_type, "
        "canonical_id_strategy, indexing_mode, record_count, labeled_count, "
        "created_at, updated_at, workspace_id) VALUES (?, 'Dataset', 'dataset', "
        "'file', 'external_id', 'full', 1, 0, ?, ?, ?)",
        (orm["dataset"], now, now, orm["workspace"]),
    )
    conn.execute(
        "INSERT INTO records (id, stable_fields, export_eligible, label_count, "
        "created_at, updated_at, workspace_id, dataset_id) VALUES (?, "
        '\'{"text": "hello"}\', 0, 0, ?, ?, ?, ?)',
        (orm["record"], now, now, orm["workspace"], orm["dataset"]),
    )
    conn.execute(
        "INSERT INTO dataset_snapshots (id, dataset_id, name, snapshot_type, "
        "record_count, labeled_count, dataset_membership, created_at, "
        "workspace_id) VALUES (?, ?, 'Snapshot', 'full', 1, 1, ?, ?, ?)",
        (
            orm["snapshot"],
            orm["dataset"],
            json.dumps(membership),
            now,
            orm["workspace"],
        ),
    )
    conn.execute(
        "INSERT INTO review_tasks (id, queue_id, record_id, task_schema_id, status, "
        "priority, claim_expired_count, is_overlap, is_calibration, ai_revealed, "
        "created_at, updated_at, workspace_id, dataset_id) VALUES (?, 'queue-1', "
        "?, ?, 'available', 0, 0, 0, 0, 0, ?, ?, ?, ?)",
        (
            route["task"],
            route["record"],
            route["schema"],
            now,
            now,
            route["workspace"],
            route["dataset"],
        ),
    )
    conn.commit()
    conn.close()
    return ids


def _stored_ids(db_path: Path) -> dict[str, tuple[str, ...]]:
    """The id and foreign key values of the rows the mixed database holds."""
    queries = {
        "workspaces": "SELECT id FROM workspaces",
        "reviewer_profiles": "SELECT id, workspace_id FROM reviewer_profiles",
        "task_schemas": "SELECT id, workspace_id FROM task_schemas",
        "datasets": "SELECT id, workspace_id FROM datasets",
        "records": "SELECT id, workspace_id, dataset_id FROM records",
        "dataset_snapshots": (
            "SELECT id, dataset_id, workspace_id FROM dataset_snapshots"
        ),
        "review_tasks": (
            "SELECT id, record_id, task_schema_id, workspace_id, dataset_id "
            "FROM review_tasks"
        ),
    }
    conn = sqlite3.connect(db_path)
    try:
        return {table: conn.execute(sql).fetchone() for table, sql in queries.items()}
    finally:
        conn.close()


def _hyphenated_ids(ids: dict[str, uuid.UUID]) -> dict[str, tuple[str, ...]]:
    h = {name: str(value) for name, value in ids.items()}
    return {
        "workspaces": (h["workspace"],),
        "reviewer_profiles": (h["reviewer"], h["workspace"]),
        "task_schemas": (h["schema"], h["workspace"]),
        "datasets": (h["dataset"], h["workspace"]),
        "records": (h["record"], h["workspace"], h["dataset"]),
        "dataset_snapshots": (h["snapshot"], h["dataset"], h["workspace"]),
        "review_tasks": (
            h["task"],
            h["record"],
            h["schema"],
            h["workspace"],
            h["dataset"],
        ),
    }


def _violations(db_path: Path) -> list[tuple[str, str, int]]:
    engine = get_engine(db_path)
    try:
        return [(v.table, v.parent, v.rows) for v in foreign_key_violations(engine)]
    finally:
        engine.dispose()


def test_a_mixed_format_legacy_database_is_rewritten_hyphenated(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "legacy.db"
    ids = _legacy_mixed_database(db_path)
    assert _violations(db_path) == [
        ("dataset_snapshots", "workspaces", 1),
        ("datasets", "workspaces", 1),
        ("records", "workspaces", 1),
        ("review_tasks", "datasets", 1),
        ("review_tasks", "records", 1),
    ]

    _start_server(monkeypatch, db_path)

    revision, drift = _revision_and_drift(db_path)
    assert revision == (HEAD,)
    assert drift == []
    assert _stored_ids(db_path) == _hyphenated_ids(ids)
    assert _violations(db_path) == []
    engine = get_engine(db_path)
    try:
        with Session(engine) as session:
            dataset = session.get(Dataset, ids["dataset"])
            assert dataset is not None
            assert dataset.workspace.id == ids["workspace"]
            assert [record.id for record in dataset.records] == [ids["record"]]
            assert [s.id for s in dataset.dataset_snapshots] == [ids["snapshot"]]
    finally:
        engine.dispose()


def test_the_uuid_rewrite_leaves_hyphenated_data_as_it_is(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "legacy.db"
    _legacy_mixed_database(db_path)
    _start_server(monkeypatch, db_path)
    rewritten = _stored_ids(db_path)
    cfg = AlembicConfig()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    alembic_command.downgrade(cfg, "004")
    assert _revision_and_drift(db_path)[0] == ("004",)

    _start_server(monkeypatch, db_path)

    assert _revision_and_drift(db_path)[0] == (HEAD,)
    assert _stored_ids(db_path) == rewritten
    assert _violations(db_path) == []


def test_a_snapshot_restores_on_a_migrated_mixed_format_database(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "legacy.db"
    ids = _legacy_mixed_database(db_path)
    monkeypatch.setenv("MOLABEL_DB_URL", f"sqlite:///{db_path.as_posix()}")

    with TestClient(create_app()) as client:
        token = create_session_token(ids["reviewer"], client.app.state.app_secret)
        resp = client.post(
            f"/api/v1/cli/datasets/{ids['dataset']}/snapshots/{ids['snapshot']}/restore",
            headers={"X-MoLabel-Session": token},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["records_restored"] == 1
    assert resp.json()["labels_restored"] == 1
    engine = get_engine(db_path)
    try:
        with Session(engine) as session:
            record = session.get(Record, ids["record"])
            assert record is not None
            assert record.latest_label == {"label": "restored"}
            assert record.label_count == 1
            snapshots = session.exec(select(DatasetSnapshot)).all()
        assert {s.name for s in snapshots} == {
            "Snapshot",
            "Pre-restore safety snapshot",
        }
        assert {s.workspace_id for s in snapshots} == {ids["workspace"]}
    finally:
        engine.dispose()
    assert _violations(db_path) == []

"""Every engine the factory builds runs SQLite with WAL and foreign keys on."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from molabel.app.main import create_app
from molabel.core.database import (
    engine_from_url,
    foreign_key_violations,
    get_engine,
)
from molabel.core.migration_runner import upgrade_database

ORPHAN_EVENT = text(
    "INSERT INTO review_events (id, record_id, task_schema_id, "
    "task_schema_version, source, labels, created_at, workspace_id) "
    "VALUES (:id, :record_id, :task_schema_id, 1, 'human', '{}', "
    "'2026-01-01T00:00:00', :workspace_id)"
)


def _orphan() -> dict[str, str]:
    return {
        "id": str(uuid.uuid4()),
        "record_id": str(uuid.uuid4()),
        "task_schema_id": str(uuid.uuid4()),
        "workspace_id": str(uuid.uuid4()),
    }


def _pragmas(engine: Engine) -> tuple[str, int]:
    with engine.connect() as conn:
        journal = conn.exec_driver_sql("PRAGMA journal_mode").scalar()
        foreign_keys = conn.exec_driver_sql("PRAGMA foreign_keys").scalar()
    return str(journal), int(foreign_keys)


def test_a_fresh_server_connection_runs_wal_with_foreign_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "server.db"
    monkeypatch.setenv("MOLABEL_DB_URL", f"sqlite:///{db_path.as_posix()}")

    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200
        engine = client.app.state.engine
        engine.dispose()

        assert _pragmas(engine) == ("wal", 1)


def test_a_write_to_a_missing_workspace_answers_409(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "server.db"
    monkeypatch.setenv("MOLABEL_DB_URL", f"sqlite:///{db_path.as_posix()}")

    with TestClient(create_app()) as client:
        resp = client.post(
            "/api/v1/reviewer-profiles",
            json={"display_name": "Nobody", "workspace_id": str(uuid.uuid4())},
        )

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CONFLICT"
    assert "FOREIGN KEY" in resp.json()["error"]["message"]


def test_a_row_whose_foreign_key_points_nowhere_is_refused(tmp_path: Path) -> None:
    engine = get_engine(tmp_path / "enforced.db")
    upgrade_database(engine)

    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(ORPHAN_EVENT, _orphan())

    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM review_events")).scalar() == 0


def test_an_in_memory_url_shares_one_connection_with_foreign_keys_on() -> None:
    engine = engine_from_url("sqlite://")
    upgrade_database(engine)

    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO workspaces (id, workspace_name, workspace_slug, "
                "core_version, root_path, manifest_path, created_at, updated_at) "
                "VALUES (:id, 'w', 'w', '0.1.0', '/w', '/w/m.yaml', "
                "'2026-01-01T00:00:00', '2026-01-01T00:00:00')"
            ),
            {"id": str(uuid.uuid4())},
        )
        conn.commit()

    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM workspaces")).scalar() == 1
    assert _pragmas(engine) == ("memory", 1)


def test_rows_written_before_enforcement_are_reported_not_deleted(
    tmp_path: Path,
) -> None:
    engine = get_engine(tmp_path / "orphans.db")
    upgrade_database(engine)
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        conn.execute(ORPHAN_EVENT, [_orphan(), _orphan()])
        conn.commit()
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")

    violations = foreign_key_violations(engine)

    assert [(v.table, v.parent, v.rows) for v in violations] == [
        ("review_events", "records", 2),
        ("review_events", "task_schemas", 2),
        ("review_events", "workspaces", 2),
    ]
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM review_events")).scalar() == 2

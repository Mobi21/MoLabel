"""``molabel status`` and ``molabel doctor`` list rows whose foreign keys dangle."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from molabel.app.main import create_app


def test_status_lists_dangling_foreign_keys_per_table_and_parent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "server.db"
    monkeypatch.setenv("MOLABEL_DB_URL", f"sqlite:///{db_path.as_posix()}")

    with TestClient(create_app()) as client:
        clean = client.get("/api/v1/cli/status")
        assert clean.status_code == 200
        assert clean.json()["foreign_key_violations"] == []

        engine = client.app.state.engine
        with engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
            conn.execute(
                text(
                    "INSERT INTO review_events (id, record_id, task_schema_id, "
                    "task_schema_version, source, labels, created_at, "
                    "workspace_id) VALUES (:id, :record_id, :task_schema_id, 1, "
                    "'human', '{}', '2026-01-01T00:00:00', :workspace_id)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "record_id": str(uuid.uuid4()),
                    "task_schema_id": str(uuid.uuid4()),
                    "workspace_id": str(uuid.uuid4()),
                },
            )
            conn.commit()
            conn.exec_driver_sql("PRAGMA foreign_keys=ON")

        dangling = client.get("/api/v1/cli/status")

    assert dangling.status_code == 200
    assert dangling.json()["foreign_key_violations"] == [
        {"table": "review_events", "parent": "records", "rows": 1},
        {"table": "review_events", "parent": "task_schemas", "rows": 1},
        {"table": "review_events", "parent": "workspaces", "rows": 1},
    ]

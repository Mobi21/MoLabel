"""The server database schema is created and upgraded by Alembic only."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlmodel import SQLModel

import molabel.core
import molabel.core.models  # noqa: F401
from molabel.app.main import create_app

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


def test_no_application_code_creates_tables_outside_migrations() -> None:
    offenders = []
    for path in sorted((REPO_ROOT / "packages").glob("*/src/**/*.py")):
        if "migrations" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        if "CREATE TABLE" in source or ".create_all(" in source:
            offenders.append(path.relative_to(REPO_ROOT).as_posix())
    assert offenders == []

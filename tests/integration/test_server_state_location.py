"""Where the server keeps its own database and secret."""

from __future__ import annotations

import logging
import sqlite3
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from molabel.app.main import create_app


@pytest.fixture()
def fresh_user(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """A user with an empty home, launching the server from an empty folder."""
    home = tmp_path / "home"
    home.mkdir()
    for var in ("MOLABEL_DB_URL", "MOLABEL_DATA_DIR"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("LOCALAPPDATA", str(home / "AppData" / "Local"))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / ".local" / "share"))
    launch = tmp_path / "launch"
    launch.mkdir()
    monkeypatch.chdir(launch)
    return home, launch


def test_server_start_writes_nothing_into_the_launch_folder(
    fresh_user: tuple[Path, Path],
) -> None:
    home, launch = fresh_user

    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/v1/cli/status").status_code == 200

    assert list(launch.iterdir()) == []
    assert len(list(home.rglob("molabel.db"))) == 1
    assert len(list(home.rglob("app_secret"))) == 1


def test_bootstrap_records_the_workspace_in_the_server_database(
    fresh_user: tuple[Path, Path], tmp_path: Path
) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "data").mkdir(parents=True)
    (workspace / "data" / "items.jsonl").write_text('{"id": "1", "text": "hi"}\n')

    with TestClient(create_app()) as client:
        resp = client.post(
            "/api/v1/cli/workspaces/bootstrap", json={"path": str(workspace)}
        )
        assert resp.status_code == 201, resp.text
        datasets = client.get("/api/v1/datasets").json()["items"]

    assert [d["dataset_slug"] for d in datasets] == ["data"]
    files = sorted(
        p.relative_to(workspace).as_posix()
        for p in workspace.rglob("*")
        if p.relative_to(workspace).parts[0] != ".molabel"
    )
    assert files == ["data", "data/items.jsonl", "workbench.project.yaml"]
    assert (workspace / ".molabel" / ".gitignore").read_text() == "*\n"


LEGACY_SCHEMA = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "migrations"
    / "pre-alembic-create-all.sql"
)


def _legacy_database(path: Path, workspace_name: str) -> Path:
    """A database the server made before it kept its state in the data dir."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(LEGACY_SCHEMA.read_text(encoding="utf-8"))
    conn.execute(
        "INSERT INTO workspaces (id, workspace_name, workspace_slug, core_version, "
        "root_path, manifest_path, created_at, updated_at) VALUES (?, ?, ?, "
        "'0.1.0', '/old', 'workbench.project.yaml', '2026-01-01', '2026-01-01')",
        (uuid.uuid4().hex, workspace_name, workspace_name.lower()),
    )
    conn.commit()
    conn.close()
    return path.resolve()


def test_a_launch_folder_database_is_reported_while_the_server_has_no_workspace(
    fresh_user: tuple[Path, Path], tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _home, launch = fresh_user
    legacy = _legacy_database(launch / "molabel.db", "Old")
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with caplog.at_level(logging.WARNING), TestClient(create_app()) as client:
        before = client.get("/api/v1/cli/status").json()["legacy_databases"]
        booted = client.post(
            "/api/v1/cli/workspaces/bootstrap", json={"path": str(workspace)}
        ).json()["legacy_databases"]
        after = client.get("/api/v1/cli/status").json()["legacy_databases"]

    assert [notice["path"] for notice in before] == [str(legacy)]
    assert before[0]["adopt"] == f"MOLABEL_DB_URL=sqlite:///{legacy.as_posix()}"
    assert booted == before
    assert after == []
    assert any(str(legacy) in record.getMessage() for record in caplog.records)


def test_a_workspace_database_from_the_old_bootstrap_is_reported_at_bootstrap(
    fresh_user: tuple[Path, Path], tmp_path: Path
) -> None:
    workspace = tmp_path / "workspace"
    legacy = _legacy_database(workspace / "workbench" / "molabel.db", "Workspace")

    with TestClient(create_app()) as client:
        booted = client.post(
            "/api/v1/cli/workspaces/bootstrap", json={"path": str(workspace)}
        ).json()["legacy_databases"]

    assert [notice["path"] for notice in booted] == [str(legacy)]


def test_the_adopt_setting_in_a_notice_serves_the_legacy_database(
    fresh_user: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _home, launch = fresh_user
    _legacy_database(launch / "molabel.db", "Old")
    with TestClient(create_app()) as client:
        (notice,) = client.get("/api/v1/cli/status").json()["legacy_databases"]

    name, value = notice["adopt"].split("=", 1)
    monkeypatch.setenv(name, value)
    with TestClient(create_app()) as client:
        names = [
            w["workspace_name"]
            for w in client.get("/api/v1/workspaces").json()["items"]
        ]
        notices = client.get("/api/v1/cli/status").json()["legacy_databases"]

    assert names == ["Old"]
    assert notices == []

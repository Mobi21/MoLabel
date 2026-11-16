"""Where the server keeps its own database and secret."""

from __future__ import annotations

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
    files = sorted(p.relative_to(workspace).as_posix() for p in workspace.rglob("*"))
    assert files == ["data", "data/items.jsonl", "workbench.project.yaml"]

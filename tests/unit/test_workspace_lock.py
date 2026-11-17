import shutil
import subprocess
from pathlib import Path

import pytest
from filelock import Timeout

from molabel.app.workspace_config import workspace_lock


def test_writers_with_different_data_dirs_share_one_workspace_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    monkeypatch.setenv("MOLABEL_DATA_DIR", str(tmp_path / "data-a"))
    server_lock = workspace_lock(workspace)
    monkeypatch.setenv("MOLABEL_DATA_DIR", str(tmp_path / "data-b"))
    cli_lock = workspace_lock(workspace)

    with server_lock, pytest.raises(Timeout):
        cli_lock.acquire(timeout=0)
    with cli_lock:
        assert cli_lock.is_locked


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_the_workspace_lock_leaves_git_status_clean(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)

    with workspace_lock(workspace):
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=workspace,
            check=True,
            capture_output=True,
            text=True,
        ).stdout

    assert status == ""

import shutil
import subprocess
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from molabel.app.workspace_config import workspace_lock


def test_writers_with_different_data_dirs_share_one_workspace_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    events = []

    def cli_write() -> None:
        with workspace_lock(workspace):
            events.append("cli wrote")

    monkeypatch.setenv("MOLABEL_DATA_DIR", str(tmp_path / "data-a"))
    with workspace_lock(workspace):
        monkeypatch.setenv("MOLABEL_DATA_DIR", str(tmp_path / "data-b"))
        cli = threading.Thread(target=cli_write)
        cli.start()
        cli.join(timeout=0.5)
        events.append("server released")
    cli.join()

    assert events == ["server released", "cli wrote"]


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


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_writers_racing_for_the_lock_all_get_it_and_leave_git_status_clean(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    ignore = workspace / ".molabel" / ".gitignore"
    ignore.parent.mkdir(parents=True)
    ignore.write_bytes(b"")
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
    writers, turns = 16, 100
    start = threading.Barrier(writers)

    def take_turns() -> list[Exception]:
        start.wait()
        errors = []
        for _ in range(turns):
            try:
                with workspace_lock(workspace):
                    pass
            except Exception as exc:
                errors.append(exc)
        return errors

    with ThreadPoolExecutor(writers) as pool:
        results = [pool.submit(take_turns) for _ in range(writers)]
    failed = Counter(type(e).__name__ for r in results for e in r.result())
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    assert failed == {}, f"{failed.total()} of {writers * turns} turns raised"
    assert ignore.read_bytes() == b"*\n"
    assert status == ""


WRITE_CONFIG_AND_DIE = """
import os, sys, uuid
from pathlib import Path
from molabel.app.workspace_config import TASK_SCHEMA, WorkspaceFolder, workspace_files

replace = os.replace
def replace_or_die(src, dst):
    if os.path.basename(dst) == "sentiment.yaml":
        os._exit(17)
    replace(src, dst)
os.replace = replace_or_die
folder = WorkspaceFolder(str(uuid.uuid4()), "Workspace", Path(sys.argv[1]))
with workspace_files(folder) as files:
    files.write_config(TASK_SCHEMA, slug="sentiment",
                       document={"task_schema_slug": "sentiment"},
                       file_path=None, overwrite=True)
"""


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
@pytest.mark.parametrize("ignore_before", [None, b"", b"*.lock\n"])
def test_a_config_write_killed_before_its_replace_leaves_git_status_clean(
    tmp_path: Path, ignore_before: bytes | None
) -> None:
    workspace = tmp_path / "workspace"
    ignore = workspace / ".molabel" / ".gitignore"
    workspace.mkdir()
    if ignore_before is not None:
        ignore.parent.mkdir()
        ignore.write_bytes(ignore_before)
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)

    killed = subprocess.run(
        [sys.executable, "-c", WRITE_CONFIG_AND_DIE, str(workspace)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    assert killed.returncode == 17, killed.stderr
    assert status == ""
    assert ignore.read_bytes() == b"*\n"

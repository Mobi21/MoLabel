"""A workspace root may be registered only inside an allowed parent folder.

Runs on the real OS: drive and share roots, the home folder, an allowed parent
itself, a folder outside every allowed parent, and a junction (Windows) or
symlink (POSIX) inside home that points outside are all refused, through both
workspace create and CLI bootstrap.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from molabel.app.main import create_app
from molabel.core.database import engine_from_url
from molabel.core.migration_runner import upgrade_database

CREATE = "/api/v1/workspaces"
BOOTSTRAP = "/api/v1/cli/workspaces/bootstrap"
ROOTS_ENV = "MOLABEL_ALLOWED_WORKSPACE_ROOTS"


@pytest.fixture()
def folders(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """A home folder and a lab folder that are allowed, and a folder outside both."""
    home, labs, outside = (tmp_path / name for name in ("home", "labs", "outside"))
    for folder in (home, labs, outside):
        folder.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv(ROOTS_ENV, os.pathsep.join([str(home), str(labs)]))
    return {"home": home, "labs": labs, "outside": outside}


@pytest.fixture()
def app():
    application = create_app()
    engine = engine_from_url("sqlite:///:memory:")
    upgrade_database(engine)
    application.state.engine = engine
    application.state.app_secret = "registration-secret"
    return application


@pytest_asyncio.fixture()
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


def _junction(link: Path, target: Path) -> None:
    """Make *link* a junction to *target* on Windows, a folder symlink elsewhere."""
    link.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            check=True,
            capture_output=True,
        )
    else:
        os.symlink(target, link, target_is_directory=True)


async def _registered_roots(client) -> list[str]:
    return [w["path"] for w in (await client.get(CREATE)).json()["items"]]


def _filesystem_roots(tmp_path: Path) -> list[str]:
    if sys.platform == "win32":
        return [tmp_path.anchor, "\\\\localhost\\molabel-no-such-share"]
    return ["/"]


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", [CREATE, BOOTSTRAP])
@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("filesystem_root", "filesystem_root"),
        ("home", "home_folder"),
        ("allowed_parent", "allowed_parent"),
        ("outside", "outside_allowed_parents"),
        ("new_folder_outside", "outside_allowed_parents"),
        ("link_in_home_to_outside", "outside_allowed_parents"),
    ],
)
async def test_registration_is_refused_outside_the_allowed_parents(
    client, folders, tmp_path, endpoint, case, reason
):
    new_folder = folders["outside"] / "not-yet"
    if case == "link_in_home_to_outside":
        _junction(folders["home"] / "linked", folders["outside"])
    paths = {
        "filesystem_root": _filesystem_roots(tmp_path),
        "home": [str(folders["home"])],
        "allowed_parent": [str(folders["labs"])],
        "outside": [str(folders["outside"])],
        "new_folder_outside": [str(new_folder)],
        "link_in_home_to_outside": [str(folders["home"] / "linked")],
    }[case]

    for path in paths:
        resp = await client.post(endpoint, json={"path": path})

        assert resp.status_code == 403, resp.text
        error = resp.json()["error"]
        assert error["code"] == "WORKSPACE_ROOT_NOT_ALLOWED"
        assert error["details"]["reason"] == reason
        assert error["details"]["allowed_parents"] == [
            str(folders["home"].resolve()),
            str(folders["labs"].resolve()),
        ]
        assert str(folders["labs"].resolve()) in error["message"]
    assert await _registered_roots(client) == []
    assert not new_folder.exists()
    assert list(folders["outside"].iterdir()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", [CREATE, BOOTSTRAP])
@pytest.mark.parametrize("parent", ["home", "labs"])
async def test_a_folder_inside_an_allowed_parent_is_registered(
    client, folders, endpoint, parent
):
    root = folders[parent] / "projects" / "tickets"
    root.mkdir(parents=True)

    resp = await client.post(endpoint, json={"path": str(root)})

    assert resp.status_code == 201, resp.text
    assert await _registered_roots(client) == [str(root.resolve())]


@pytest.mark.asyncio
async def test_without_the_setting_only_folders_inside_home_are_allowed(
    client, folders, monkeypatch
):
    monkeypatch.delenv(ROOTS_ENV)
    inside = folders["home"] / "tickets"
    inside.mkdir()

    refused = await client.post(BOOTSTRAP, json={"path": str(folders["labs"])})
    allowed = await client.post(BOOTSTRAP, json={"path": str(inside)})

    assert refused.status_code == 403
    assert refused.json()["error"]["details"]["allowed_parents"] == [
        str(folders["home"].resolve())
    ]
    assert allowed.status_code == 201, allowed.text


@pytest.mark.asyncio
async def test_a_workspace_registered_before_the_limit_keeps_working_with_a_warning(
    client, folders, monkeypatch
):
    legacy = folders["outside"] / "legacy"
    legacy.mkdir()
    monkeypatch.setenv(ROOTS_ENV, str(folders["outside"]))
    booted = await client.post(
        BOOTSTRAP, json={"path": str(legacy), "workspace_name": "Legacy"}
    )
    assert booted.status_code == 201, booted.text
    monkeypatch.setenv(
        ROOTS_ENV, os.pathsep.join([str(folders["home"]), str(folders["labs"])])
    )

    status = (await client.get("/api/v1/cli/status")).json()
    manifest = await client.post(
        "/api/v1/cli/artifacts/read",
        json={
            "kind": "workspace_manifest",
            "selector": "workspace",
            "workspace_root": str(legacy),
        },
    )
    rebooted = await client.post(BOOTSTRAP, json={"path": str(legacy)})

    (warning,) = status["workspace_roots_not_allowed"]
    assert warning["workspace_id"] == booted.json()["workspace_id"]
    assert warning["workspace_name"] == "Legacy"
    assert warning["root_path"] == str(legacy.resolve())
    assert warning["reason"] == "outside_allowed_parents"
    assert str(folders["labs"].resolve()) in warning["message"]
    assert ROOTS_ENV in warning["message"]
    assert manifest.status_code == 200, manifest.text
    assert rebooted.status_code == 403
    assert rebooted.json()["error"]["code"] == "WORKSPACE_ROOT_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_status_lists_no_warning_for_workspaces_inside_the_allowed_parents(
    client, folders
):
    root = folders["home"] / "tickets"
    root.mkdir()
    assert (await client.post(BOOTSTRAP, json={"path": str(root)})).status_code == 201

    status = (await client.get("/api/v1/cli/status")).json()

    assert status["workspace_roots_not_allowed"] == []

"""Session-wide test isolation."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True, scope="session")
def _isolated_server_data_dir(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[None]:
    """Keep the server database and secret out of the developer's data dir.

    Test workspaces live in the temp folder, which on CI is outside the home
    folder, so the session allows workspace roots under it instead of home.
    """
    settings = {
        "MOLABEL_DATA_DIR": str(tmp_path_factory.mktemp("molabel-data")),
        "MOLABEL_ALLOWED_WORKSPACE_ROOTS": tempfile.gettempdir(),
    }
    previous = {name: os.environ.get(name) for name in settings}
    os.environ.update(settings)
    yield
    for name, value in previous.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value

"""Session-wide test isolation."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True, scope="session")
def _isolated_server_data_dir(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[None]:
    """Keep the server database and secret out of the developer's data dir."""
    previous = os.environ.get("MOLABEL_DATA_DIR")
    os.environ["MOLABEL_DATA_DIR"] = str(tmp_path_factory.mktemp("molabel-data"))
    yield
    if previous is None:
        os.environ.pop("MOLABEL_DATA_DIR", None)
    else:
        os.environ["MOLABEL_DATA_DIR"] = previous

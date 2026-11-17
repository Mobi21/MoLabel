"""Which resolved folders may be workspace roots, in POSIX and Windows forms."""

from __future__ import annotations

from pathlib import PurePath, PurePosixPath, PureWindowsPath

import pytest

from molabel.app.workspace_paths import RootPolicy, RootRefusal

POSIX = RootPolicy(
    home=PurePosixPath("/home/ada"),
    allowed_parents=(PurePosixPath("/home/ada"), PurePosixPath("/srv/labs")),
)
WINDOWS = RootPolicy(
    home=PureWindowsPath(r"C:\Users\Ada"),
    allowed_parents=(
        PureWindowsPath(r"C:\Users\Ada"),
        PureWindowsPath(r"D:\Labs"),
        PureWindowsPath(r"\\fileserver\team\labels"),
    ),
)


@pytest.mark.parametrize(
    ("root", "expected"),
    [
        ("/", RootRefusal.FILESYSTEM_ROOT),
        ("/home/ada", RootRefusal.HOME_FOLDER),
        ("/srv/labs", RootRefusal.ALLOWED_PARENT),
        ("/srv", RootRefusal.OUTSIDE_ALLOWED_PARENTS),
        ("/etc/ssh", RootRefusal.OUTSIDE_ALLOWED_PARENTS),
        ("/home/adam/tickets", RootRefusal.OUTSIDE_ALLOWED_PARENTS),
        ("/home/ada/projects/tickets", None),
        ("/srv/labs/tickets", None),
    ],
)
def test_posix_roots(root: str, expected: RootRefusal | None) -> None:
    assert POSIX.refusal(PurePosixPath(root)) == expected


@pytest.mark.parametrize(
    ("root", "expected"),
    [
        ("C:\\", RootRefusal.FILESYSTEM_ROOT),
        ("D:\\", RootRefusal.FILESYSTEM_ROOT),
        ("z:/", RootRefusal.FILESYSTEM_ROOT),
        (r"\\fileserver\team", RootRefusal.FILESYSTEM_ROOT),
        ("\\\\fileserver\\team\\", RootRefusal.FILESYSTEM_ROOT),
        ("\\\\?\\C:\\", RootRefusal.FILESYSTEM_ROOT),
        (r"C:\Users\Ada", RootRefusal.HOME_FOLDER),
        (r"c:\users\ADA", RootRefusal.HOME_FOLDER),
        (r"D:\Labs", RootRefusal.ALLOWED_PARENT),
        (r"\\fileserver\team\labels", RootRefusal.ALLOWED_PARENT),
        (r"C:\Users", RootRefusal.OUTSIDE_ALLOWED_PARENTS),
        (r"C:\Windows\System32", RootRefusal.OUTSIDE_ALLOWED_PARENTS),
        (r"C:\Users\Adam\tickets", RootRefusal.OUTSIDE_ALLOWED_PARENTS),
        (r"E:\Labs\tickets", RootRefusal.OUTSIDE_ALLOWED_PARENTS),
        (r"\\fileserver\team\other", RootRefusal.OUTSIDE_ALLOWED_PARENTS),
        (r"C:\Users\Ada\projects\tickets", None),
        (r"c:\USERS\ada\Projects", None),
        (r"D:\Labs\tickets", None),
        (r"\\fileserver\team\labels\tickets", None),
    ],
)
def test_windows_roots(root: str, expected: RootRefusal | None) -> None:
    assert WINDOWS.refusal(PureWindowsPath(root)) == expected


@pytest.mark.parametrize(
    ("policy", "home"),
    [
        (
            RootPolicy(
                home=PurePosixPath("/home/ada"),
                allowed_parents=(PurePosixPath("/srv/labs"),),
            ),
            PurePosixPath("/home/ada"),
        ),
        (
            RootPolicy(
                home=PureWindowsPath(r"C:\Users\Ada"),
                allowed_parents=(PureWindowsPath("C:\\Users"),),
            ),
            PureWindowsPath(r"C:\Users\Ada"),
        ),
    ],
)
def test_home_is_refused_even_when_no_allowed_parent_is_home(
    policy: RootPolicy, home: PurePath
) -> None:
    assert policy.refusal(home) == RootRefusal.HOME_FOLDER

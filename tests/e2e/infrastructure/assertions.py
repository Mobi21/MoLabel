"""Reusable checkpoint assertion helpers.

The ``checkpoint`` context manager wraps a block of assertions as a named
phase within a test.  It records pass/fail status, duration, and any error
details into the TestContext so the E2EReporter can include per-checkpoint
breakdowns in the run report.

Usage::

    with checkpoint(ctx, "workspace_setup"):
        resp = await client.post("/workspaces", json={"workspace_name": "Test"})
        assert resp.status_code == 201
        ws_id = resp.json()["workspace_id"]
"""

from __future__ import annotations

import time
from collections.abc import Generator
from contextlib import contextmanager

from tests.e2e.infrastructure.logging_config import TestContext


@contextmanager
def checkpoint(ctx: TestContext, name: str) -> Generator[None, None, None]:
    """Independently assertable test phase with timing and error tracking.

    Logs the checkpoint result into ``ctx`` regardless of whether it passes
    or fails.  On failure the AssertionError is re-raised so pytest still
    marks the test as failed; the error message is also appended to
    ``ctx.errors`` for the run report.

    Args:
        ctx: The TestContext for the current test.
        name: A short identifier for this checkpoint, e.g. ``"workspace_setup"``.
    """
    start = time.monotonic()
    passed_count = 0
    failed_count = 0
    details: list[str] = []
    try:
        yield
        passed_count += 1
    except AssertionError as e:
        failed_count += 1
        details.append(str(e))
        ctx.errors.append(f"Checkpoint '{name}': {e}")
        raise
    finally:
        duration_ms = (time.monotonic() - start) * 1000
        ctx.log_checkpoint(
            name=name,
            passed=failed_count == 0,
            duration_ms=round(duration_ms, 1),
            passed_count=passed_count,
            failed_count=failed_count,
            details=details,
        )

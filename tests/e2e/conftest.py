"""Shared fixtures and hooks for the MoLabel E2E test suite.

Every E2E test automatically gets:
- A fresh in-memory SQLite database (via InstrumentedClient)
- A TestContext tracking all API calls, checkpoints, and timings
- VCR cassette management for deterministic LLM tests
- Lifecycle logging via LoggingHook
- Registration with the session-level E2EReporter

Session-level fixtures (run_id, e2e_logger, reporter) are created once per
pytest session. Per-test fixtures (ctx, client, cassette) are re-created
for each test function.
"""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

import pytest

from tests.e2e.infrastructure.cassettes import CassetteManager
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.hooks import LoggingHook
from tests.e2e.infrastructure.logging_config import TestContext, setup_logging
from tests.e2e.infrastructure.reporter import E2EReporter

# ── Session-scoped fixtures ──────────────────────────────────────────────────


@pytest.fixture(scope="session")
def run_id() -> str:
    """Unique identifier for this test run, shared across the entire session."""
    return f"{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"


@pytest.fixture(scope="session")
def e2e_logger(run_id: str):
    """Structured logger for the full session; writes JSONL to logs/."""
    return setup_logging(run_id)


@pytest.fixture(scope="session")
def reporter(run_id: str) -> E2EReporter:
    """Session-level reporter that accumulates all test contexts."""
    return E2EReporter(run_id)


# ── Per-test fixtures ────────────────────────────────────────────────────────


@pytest.fixture
async def ctx(request) -> TestContext:
    """Per-test observability context, auto-populated from pytest markers.

    Extracts tier number from tier* markers and test_id from callspec
    (parametrized tests) or node name (non-parametrized).
    """
    markers = {m.name for m in request.node.iter_markers()}
    tier = next((int(m[4:]) for m in markers if m.startswith("tier")), 0)
    callspec = getattr(request.node, "callspec", None)
    test_id = callspec.id if callspec is not None else request.node.name
    return TestContext(test_id=test_id, tier=tier, name=request.node.name)


@pytest.fixture
async def client(ctx: TestContext) -> InstrumentedClient:
    """Instrumented async client backed by a fresh in-memory SQLite DB.

    Each test gets its own isolated database; no state leaks between tests.
    """
    c = InstrumentedClient(ctx)
    yield c
    await c.close()


@pytest.fixture
def cassette(request) -> CassetteManager:
    """VCR cassette manager — replay pre-recorded LLM calls by default.

    Set E2E_RECORD_CASSETTES=1 to record new cassettes from real LLM calls.
    Cassette name is derived from the test node name.
    """
    scenario_id = request.node.name
    record = os.environ.get("E2E_RECORD_CASSETTES") == "1"
    mgr = CassetteManager(scenario_id, record=record)
    mgr.load()
    yield mgr
    mgr.save()


# ── Autouse lifecycle hook ───────────────────────────────────────────────────


@pytest.fixture(autouse=True)
async def log_test_lifecycle(ctx, e2e_logger, reporter, request):
    """Log test start/end and register the context with the session reporter.

    This fixture runs for every test automatically. It fires on_test_start
    at the beginning and on_test_end at teardown, using the rep_call attribute
    set by the pytest_runtest_makereport hook to determine pass/fail status.
    """
    hook = LoggingHook(e2e_logger)
    await hook.on_test_start(ctx.test_id, ctx.name)
    yield
    # rep_call is attached by pytest_runtest_makereport below
    rep_call = getattr(request.node, "rep_call", None)
    passed = (not rep_call.failed) if rep_call is not None else (len(ctx.errors) == 0)
    await hook.on_test_end(ctx.test_id, passed, ctx.summary())
    reporter.add(ctx)


# ── pytest hooks ────────────────────────────────────────────────────────────


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Attach the test call result to the node so log_test_lifecycle can read it.

    Only the 'call' phase is captured; setup/teardown failures are not
    tracked here (they would prevent ctx from being available anyway).
    """
    outcome = yield
    rep = outcome.get_result()
    if rep.when == "call":
        item.rep_call = rep


def pytest_configure(config):
    """Attach a fresh E2EReporter to the pytest config for session-level access.

    This reporter is used by pytest_sessionfinish to write the final report.
    The run_id here is independent of the fixture run_id (fixtures are not
    available in session hooks), but uses the same format.
    """
    run_id = f"{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    config._e2e_reporter = E2EReporter(run_id=run_id)


def pytest_sessionfinish(session, exitstatus):
    """Write the final JSON and Markdown reports at the end of the session."""
    reporter = getattr(session.config, "_e2e_reporter", None)
    if reporter:
        reporter.write_report(Path("tests/e2e/logs"))

"""Pre/post test hooks for agent integration.

The E2EHook protocol defines the full lifecycle event surface.  Any object
implementing these async methods can be registered with the E2ERunner.
LoggingHook is the default implementation that forwards all events to a
standard Python logger.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class E2EHook(Protocol):
    """Protocol for E2E test lifecycle hooks.

    Implement this to react to test events — for example, posting results
    to a dashboard, opening issues on failures, or driving a feedback loop.
    All methods are async.
    """

    async def on_run_start(self, run_id: str, total_tests: int) -> None: ...

    async def on_tier_start(self, tier: int, test_count: int) -> None: ...

    async def on_test_start(self, test_id: str, name: str) -> None: ...

    async def on_checkpoint(
        self, test_id: str, checkpoint: str, passed: bool
    ) -> None: ...

    async def on_test_end(
        self, test_id: str, passed: bool, summary: dict[str, Any]
    ) -> None: ...

    async def on_tier_end(self, tier: int, passed: int, failed: int) -> None: ...

    async def on_run_end(self, report: dict[str, Any]) -> None: ...

    async def on_failure(
        self, test_id: str, error: str, context: dict[str, Any]
    ) -> None: ...


class LoggingHook:
    """Default hook that logs all lifecycle events to a Python logger.

    This is registered automatically in conftest.py for every test.
    """

    def __init__(self, logger: logging.Logger) -> None:
        self.logger = logger

    async def on_run_start(self, run_id: str, total_tests: int) -> None:
        self.logger.info(f"E2E run {run_id} starting — {total_tests} tests")

    async def on_tier_start(self, tier: int, test_count: int) -> None:
        self.logger.info(f"Tier {tier} starting — {test_count} tests")

    async def on_test_start(self, test_id: str, name: str) -> None:
        self.logger.info(f"[{test_id}] Starting: {name}")

    async def on_checkpoint(self, test_id: str, checkpoint: str, passed: bool) -> None:
        status = "PASS" if passed else "FAIL"
        self.logger.info(f"[{test_id}] Checkpoint {checkpoint}: {status}")

    async def on_test_end(
        self, test_id: str, passed: bool, summary: dict[str, Any]
    ) -> None:
        status = "PASSED" if passed else "FAILED"
        duration = summary.get("total_duration_ms", 0)
        api_calls = summary.get("api_calls", 0)
        self.logger.info(
            f"[{test_id}] {status} ({duration:.0f}ms, {api_calls} API calls)"
        )

    async def on_tier_end(self, tier: int, passed: int, failed: int) -> None:
        self.logger.info(f"Tier {tier} complete — {passed} passed, {failed} failed")

    async def on_run_end(self, report: dict[str, Any]) -> None:
        total = report["total_tests"]
        passed = report["passed"]
        duration_s = report["total_duration_ms"] / 1000
        self.logger.info(
            f"E2E run complete — {passed}/{total} passed in {duration_s:.1f}s"
        )

    async def on_failure(
        self, test_id: str, error: str, context: dict[str, Any]
    ) -> None:
        self.logger.error(f"[{test_id}] FAILURE: {error}")

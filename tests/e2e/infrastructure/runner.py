"""Programmatic E2E test runner for agent integration.

The E2ERunner exposes an async API that an agent skill or external process
can call to run the full suite or subsets of it.  It delegates to pytest
under the hood, passing appropriate ``-k`` / ``-m`` / tier-path filters,
and aggregates results via the E2EReporter.

Example usage from an agent skill::

    runner = E2ERunner(hooks=[LoggingHook(logger)], api_key="sk-...")
    report = await runner.run_tier(2, parallel=True)
    runner.reporter.write_report(Path("tests/e2e/logs"))
"""

from __future__ import annotations

import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from tests.e2e.infrastructure.hooks import E2EHook
from tests.e2e.infrastructure.reporter import E2EReporter


def _generate_run_id() -> str:
    return f"{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"


_TIER_PATHS: dict[int, str] = {
    1: "tests/e2e/tier1_pipeline",
    2: "tests/e2e/tier2_workflows",
    3: "tests/e2e/tier3_api_coverage",
    4: "tests/e2e/tier4_queue_review",
    5: "tests/e2e/tier5_agent_llm",
    6: "tests/e2e/tier6_quality",
    7: "tests/e2e/tier7_data_management",
    8: "tests/e2e/tier8_resilience",
    9: "tests/e2e/tier9_cross_cutting",
}


def _run_pytest(args: list[str]) -> int:
    """Run pytest with the given arguments and return the exit code."""
    result = subprocess.run(["uv", "run", "pytest", *args], check=False)
    return result.returncode


class E2ERunner:
    """Programmatic E2E test runner for agent integration.

    Wraps pytest invocations and exposes high-level async methods that an
    agent skill can call.  All heavy work is delegated to pytest; the runner
    coordinates hooks and collects the final report.
    """

    def __init__(
        self,
        hooks: list[E2EHook] | None = None,
        api_key: str | None = None,
    ) -> None:
        self.hooks: list[E2EHook] = hooks or []
        self.api_key = api_key
        self.reporter = E2EReporter(run_id=_generate_run_id())

    async def run_all(
        self, parallel: bool = True, skip_real_llm: bool = False
    ) -> dict[str, Any]:
        """Run all E2E tests and return the report dict."""
        args = ["tests/e2e/", "-v", "--tb=short"]
        if parallel:
            args += ["-n", "4", "--dist", "loadgroup"]
        if skip_real_llm:
            args += ["-m", "not real_llm"]
        _run_pytest(args)
        return self.get_report()

    async def run_tier(self, tier: int, parallel: bool = True) -> dict[str, Any]:
        """Run all tests in a specific tier (1–9)."""
        if tier not in _TIER_PATHS:
            raise ValueError(f"Invalid tier: {tier}. Must be 1–9.")
        path = _TIER_PATHS[tier]
        args = [path, "-v", "--tb=short"]
        if parallel:
            args += ["-n", "4", "--dist", "loadgroup"]
        _run_pytest(args)
        return self.get_report()

    async def run_scenario(self, scenario_id: str) -> dict[str, Any]:
        """Run a single scenario by its ID, e.g. 'T2-20'."""
        args = ["tests/e2e/", "-k", scenario_id, "-v", "--tb=short"]
        _run_pytest(args)
        return self.get_report()

    async def run_tags(self, tags: list[str], parallel: bool = True) -> dict[str, Any]:
        """Run all tests matching any of the given pytest marker tags."""
        marker_expr = " or ".join(tags)
        args = ["tests/e2e/", "-m", marker_expr, "-v", "--tb=short"]
        if parallel:
            args += ["-n", "4", "--dist", "loadgroup"]
        _run_pytest(args)
        return self.get_report()

    def get_report(self) -> dict[str, Any]:
        """Return the current run report dict."""
        return self.reporter.generate_report()

    def write_report(self, output_dir: Path) -> None:
        """Write JSON + Markdown reports to output_dir."""
        self.reporter.write_report(output_dir)

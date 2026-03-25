"""Test run reporter.

Aggregates TestContext results from all tests into a structured run report,
then writes two output formats:

- JSON: machine-readable full report with per-test breakdowns
- Markdown: human-readable summary table with tier breakdown and failures
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from tests.e2e.infrastructure.logging_config import TestContext

# Tier names for the markdown report table
_TIER_NAMES: dict[int, str] = {
    1: "Pipeline",
    2: "Workflows",
    3: "API Coverage",
    4: "Queue/Review",
    5: "Agent/LLM",
    6: "Quality",
    7: "Data Mgmt",
    8: "Resilience",
    9: "Cross-Cut",
}


class E2EReporter:
    """Aggregates all TestContext results into a run report.

    Attach one E2EReporter to the pytest session; add each test's context
    via ``add()`` after the test completes; call ``write_report()`` in
    ``pytest_sessionfinish`` to persist the output files.
    """

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.contexts: list[TestContext] = []

    def add(self, ctx: TestContext) -> None:
        """Register a completed test context."""
        self.contexts.append(ctx)

    def generate_report(self) -> dict:
        """Produce the full report dict from all registered contexts."""
        by_tier: dict[int, list[TestContext]] = {}
        for ctx in self.contexts:
            by_tier.setdefault(ctx.tier, []).append(ctx)

        return {
            "run_id": self.run_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "total_tests": len(self.contexts),
            "passed": sum(1 for c in self.contexts if not c.errors),
            "failed": sum(1 for c in self.contexts if c.errors),
            "total_duration_ms": sum(c.elapsed_ms() for c in self.contexts),
            "total_api_calls": sum(len(c.api_calls) for c in self.contexts),
            "total_llm_calls": sum(c.llm_calls for c in self.contexts),
            "total_real_llm_calls": sum(c.real_llm_calls for c in self.contexts),
            "by_tier": {
                tier: {
                    "total": len(ctxs),
                    "passed": sum(1 for c in ctxs if not c.errors),
                    "failed": sum(1 for c in ctxs if c.errors),
                    "duration_ms": sum(c.elapsed_ms() for c in ctxs),
                }
                for tier, ctxs in sorted(by_tier.items())
            },
            "tests": [c.summary() for c in self.contexts],
        }

    def write_report(self, output_dir: Path) -> None:
        """Write JSON and Markdown reports to output_dir."""
        output_dir.mkdir(parents=True, exist_ok=True)
        report = self.generate_report()

        json_path = output_dir / f"e2e_report_{self.run_id}.json"
        json_path.write_text(json.dumps(report, indent=2))

        md_path = output_dir / f"e2e_report_{self.run_id}.md"
        md_path.write_text(self._render_markdown(report))

    def _render_markdown(self, report: dict) -> str:
        lines = [
            f"# E2E Test Report — {report['run_id']}",
            "",
            f"**Date**: {report['timestamp']}",
            f"**Total**: {report['total_tests']} tests | "
            f"**Passed**: {report['passed']} | **Failed**: {report['failed']}",
            f"**Duration**: {report['total_duration_ms'] / 1000:.1f}s | "
            f"**API calls**: {report['total_api_calls']} | "
            f"**LLM calls**: {report['total_llm_calls']} "
            f"({report['total_real_llm_calls']} real)",
            "",
            "## By Tier",
            "",
            "| Tier | Tests | Passed | Failed | Duration |",
            "|------|-------|--------|--------|----------|",
        ]
        for tier, data in report["by_tier"].items():
            tier_name = _TIER_NAMES.get(int(tier), "")
            lines.append(
                f"| {tier}. {tier_name} | {data['total']} | "
                f"{data['passed']} | {data['failed']} | "
                f"{data['duration_ms'] / 1000:.1f}s |"
            )

        failed_tests = [t for t in report["tests"] if t["errors"] > 0]
        if failed_tests:
            lines.extend(["", "## Failures", ""])
            for t in failed_tests:
                lines.append(
                    f"- **{t['test_id']}** {t['name']} — {t['errors']} error(s)"
                )

        return "\n".join(lines)

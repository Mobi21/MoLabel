"""CLI entry point for the MoLabel E2E test suite.

Run with::

    python -m tests.e2e [options]

or via the uv workspace shortcut::

    uv run python -m tests.e2e --tier 2 --parallel

This wraps E2ERunner with a full argument parser so agents and CI scripts
can drive the test pipeline programmatically with structured output.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from tests.e2e.infrastructure.hooks import LoggingHook
from tests.e2e.infrastructure.logging_config import setup_logging
from tests.e2e.infrastructure.runner import E2ERunner


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="MoLabel E2E Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m tests.e2e                          Run all tests (parallel)
  python -m tests.e2e --tier 2                 Run only Tier 2 workflow tests
  python -m tests.e2e --scenario T2-20         Run a single scenario
  python -m tests.e2e --tags tier1 tier3       Run tests matching tier1 or tier3
  python -m tests.e2e --skip-real-llm          Skip tests requiring real LLM
  python -m tests.e2e --record-cassettes ...   Record new VCR cassettes
        """,
    )
    parser.add_argument(
        "--tier",
        type=int,
        choices=range(1, 10),
        metavar="TIER",
        help="Run only tests in a specific tier (1–9)",
    )
    parser.add_argument(
        "--scenario",
        type=str,
        metavar="ID",
        help="Run a single scenario by ID (e.g. T2-20)",
    )
    parser.add_argument(
        "--tags",
        nargs="+",
        metavar="TAG",
        help="Run tests matching any of the given pytest marker tags",
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        default=True,
        help="Run tests in parallel using pytest-xdist (default: True)",
    )
    parser.add_argument(
        "--no-parallel",
        dest="parallel",
        action="store_false",
        help="Disable parallel execution",
    )
    parser.add_argument(
        "--skip-real-llm",
        action="store_true",
        default=False,
        help="Skip tests that require a real LLM API call",
    )
    parser.add_argument(
        "--record-cassettes",
        action="store_true",
        default=False,
        help="Record new VCR cassettes instead of replaying existing ones",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        metavar="KEY",
        help="API key for real LLM tests (MiniMax, Anthropic, etc.)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="tests/e2e/logs",
        metavar="DIR",
        help="Directory for report output (default: tests/e2e/logs)",
    )
    args = parser.parse_args()

    import os

    if args.record_cassettes:
        os.environ["E2E_RECORD_CASSETTES"] = "1"

    runner = E2ERunner(api_key=args.api_key)
    # Wire up logging hook after runner creates its reporter
    logger = setup_logging(runner.reporter.run_id)
    runner.hooks = [LoggingHook(logger)]

    if args.scenario:
        report = await runner.run_scenario(args.scenario)
    elif args.tier:
        report = await runner.run_tier(args.tier, parallel=args.parallel)
    elif args.tags:
        report = await runner.run_tags(args.tags, parallel=args.parallel)
    else:
        report = await runner.run_all(
            parallel=args.parallel,
            skip_real_llm=args.skip_real_llm,
        )

    runner.reporter.write_report(Path(args.output_dir))
    passed = report.get("passed", 0)
    total = report.get("total_tests", 0)
    duration_s = report.get("total_duration_ms", 0) / 1000
    print(f"\nResults: {passed}/{total} passed in {duration_s:.1f}s")
    print(f"Report written to {args.output_dir}/")


if __name__ == "__main__":
    asyncio.run(main())

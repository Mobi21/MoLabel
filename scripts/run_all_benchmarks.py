#!/usr/bin/env python3
"""Run all live grounded operator benchmarks in parallel and save full logs.

Runs the real LLM operator-mode benchmark tests (one per scenario) each as a
separate pytest process so they execute concurrently.  Each scenario launches
a Claude Code / Codex agent, so the default timeout is 40 minutes per process.

Requires ANTHROPIC_API_KEY in .env or environment.

Usage:
    uv run python scripts/run_all_benchmarks.py
    uv run python scripts/run_all_benchmarks.py --report-dir reports/my-run
    uv run python scripts/run_all_benchmarks.py --workers 4
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

OPERATOR_TEST = (
    "tests/e2e/tier1_pipeline/test_live_grounded_operator_benchmarks_real_llm.py"
)

SCENARIOS = ["clinc150", "hatexplain", "feverous", "banking77", "goemotions", "scifact"]

# Each entry: (display_name, test_file, pytest_k_filter)
BENCHMARKS: list[tuple[str, str, str]] = [
    (scenario, OPERATOR_TEST, scenario) for scenario in SCENARIOS
]


def _load_dotenv() -> dict[str, str]:
    """Load .env into a dict to pass to subprocesses."""
    import os

    env = dict(os.environ)
    dotenv_path = REPO_ROOT / ".env"
    if dotenv_path.exists():
        for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :].strip()
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            env.setdefault(key.strip(), value.strip().strip("'").strip('"'))
    return env


def run_single_benchmark(args: tuple[str, str, str]) -> dict:
    """Run one benchmark and capture all output."""
    name, test_file, k_filter = args
    abs_path = str(REPO_ROOT / test_file)
    env = _load_dotenv()

    cmd = [
        "uv",
        "run",
        "pytest",
        abs_path,
        "-v",
        "-s",
        "--tb=long",
        "--no-header",
        "--timeout=2400",
        "-k",
        k_filter,
    ]

    start = time.monotonic()
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=env,
        timeout=2400,
    )
    elapsed = time.monotonic() - start

    return {
        "benchmark": name,
        "test_file": test_file,
        "k_filter": k_filter,
        "command": " ".join(cmd),
        "exit_code": result.returncode,
        "passed": result.returncode == 0,
        "duration_seconds": round(elapsed, 2),
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def write_report(report_dir: Path, entry: dict) -> Path:
    """Write one benchmark's full log to a JSON file."""
    out = report_dir / f"{entry['benchmark']}.json"
    out.write_text(json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def write_summary(report_dir: Path, results: list[dict], wall_time: float) -> None:
    """Write a summary table as both JSON and Markdown."""
    passed = [r for r in results if r["passed"]]
    failed = [r for r in results if not r["passed"]]

    summary = {
        "timestamp": datetime.now(UTC).isoformat(),
        "total": len(results),
        "passed": len(passed),
        "failed": len(failed),
        "wall_time_seconds": round(wall_time, 2),
        "benchmarks": [
            {
                "benchmark": r["benchmark"],
                "passed": r["passed"],
                "duration_seconds": r["duration_seconds"],
                "exit_code": r["exit_code"],
            }
            for r in sorted(results, key=lambda r: r["benchmark"])
        ],
    }

    (report_dir / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    # Markdown summary
    lines = [
        f"# Operator Benchmark Report — {summary['timestamp']}",
        "",
        f"**{summary['passed']}/{summary['total']} passed** | "
        f"Wall time: {summary['wall_time_seconds']}s",
        "",
        "| Benchmark | Status | Duration |",
        "|-----------|--------|----------|",
    ]
    for b in summary["benchmarks"]:
        status = "PASS" if b["passed"] else "FAIL"
        lines.append(f"| {b['benchmark']} | {status} | {b['duration_seconds']}s |")

    if failed:
        lines += ["", "## Failures", ""]
        for r in sorted(failed, key=lambda r: r["benchmark"]):
            lines += [
                f"### {r['benchmark']}",
                "",
                "**stdout** (last 3000 chars):",
                "```",
                r["stdout"][-3000:] if len(r["stdout"]) > 3000 else r["stdout"],
                "```",
                "",
                "**stderr** (last 1000 chars):",
                "```",
                r["stderr"][-1000:] if len(r["stderr"]) > 1000 else r["stderr"],
                "```",
                "",
            ]

    (report_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run all live grounded operator benchmarks in parallel"
    )
    parser.add_argument(
        "--report-dir",
        default=None,
        help="Directory for reports (default: reports/bench-<timestamp>)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Max parallel workers (default: number of benchmarks)",
    )
    args = parser.parse_args()

    if args.report_dir:
        report_dir = Path(args.report_dir)
    else:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        report_dir = REPO_ROOT / "reports" / f"bench-{ts}"
    report_dir.mkdir(parents=True, exist_ok=True)

    workers = args.workers or len(BENCHMARKS)
    print(f"Running {len(BENCHMARKS)} operator benchmarks with {workers} workers")
    print(f"Reports → {report_dir}\n")

    wall_start = time.monotonic()
    results: list[dict] = []

    benchmark_args = [(name, tf, kf) for name, tf, kf in BENCHMARKS]

    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(run_single_benchmark, ba): ba[0] for ba in benchmark_args
        }
        for future in as_completed(futures):
            entry = future.result()
            status = "PASS" if entry["passed"] else "FAIL"
            print(f"  [{status}] {entry['benchmark']} ({entry['duration_seconds']}s)")
            write_report(report_dir, entry)
            results.append(entry)

    wall_time = time.monotonic() - wall_start
    write_summary(report_dir, results, wall_time)

    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])
    print(f"\nDone: {passed} passed, {failed} failed in {wall_time:.1f}s")
    print(f"Reports: {report_dir}")
    print("  summary.md / summary.json + one .json per benchmark")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

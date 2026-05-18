#!/usr/bin/env python3
"""Run live grounded operator benchmarks and write structured batch reports.

Runs the real LLM grounded operator benchmark test one benchmark at a time in
separate pytest processes. Each benchmark may be repeated multiple times, while
paper-direct baselines are cached per benchmark inside the batch report
directory to avoid repeating identical maintainer-side setup work.

Requires ANTHROPIC_API_KEY in .env or environment.

Usage:
    uv run python scripts/run_all_benchmarks.py
    uv run python scripts/run_all_benchmarks.py --report-dir reports/my-run
    uv run python scripts/run_all_benchmarks.py --workers 4
    uv run python scripts/run_all_benchmarks.py --repeats 5
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

OPERATOR_TEST = (
    "tests/e2e/tier1_pipeline/test_live_grounded_operator_benchmarks_real_llm.py"
)

SCENARIOS = ["clinc150", "hatexplain", "feverous", "banking77", "goemotions", "scifact"]
DEFAULT_WORKERS = 1
DEFAULT_REPEATS = 1
DEFAULT_MODE = "open"
DEFAULT_COOLDOWN_SECONDS = 0.0

INFRA_SIGNAL_FIELDS = (
    "rate_limit_retries",
    "timeout_count",
    "adapter_error_count",
    "enforcer_timeout_count",
    "enforcer_validation_failures",
)


def resolve_worker_count(requested_workers: int | None, benchmark_count: int) -> int:
    """Return a safe worker count for the current benchmark batch."""
    if benchmark_count <= 0:
        return 1
    if requested_workers is None:
        return min(DEFAULT_WORKERS, benchmark_count)
    return max(1, min(requested_workers, benchmark_count))


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


def build_benchmarks(mode: str) -> list[tuple[str, str, str, str]]:
    modes = ["open", "preset"] if mode == "both" else [mode]
    return [
        (scenario, OPERATOR_TEST, scenario, benchmark_mode)
        for benchmark_mode in modes
        for scenario in SCENARIOS
    ]


def _artifact_path(
    report_dir: Path,
    benchmark: str,
    mode: str,
    repeat_index: int,
) -> Path:
    filename = f"{benchmark}-{mode}-repeat-{repeat_index:02d}.json"
    return report_dir / "artifacts" / filename


def _repeat_log_path(
    report_dir: Path,
    benchmark: str,
    mode: str,
    repeat_index: int,
) -> Path:
    filename = f"{benchmark}-{mode}-repeat-{repeat_index:02d}.json"
    return report_dir / "repeats" / filename


def run_single_benchmark(
    args: tuple[str, str, str, str, str, int],
) -> dict[str, Any]:
    """Run one benchmark repeat and capture structured output when available."""

    name, test_file, k_filter, benchmark_mode, report_dir_str, repeat_index = args
    report_dir = Path(report_dir_str)
    abs_path = str(REPO_ROOT / test_file)
    env = _load_dotenv()
    artifact_path = _artifact_path(report_dir, name, benchmark_mode, repeat_index)
    env["MOLABEL_BATCH_ARTIFACT_PATH"] = str(artifact_path)
    env["MOLABEL_BATCH_BASELINE_CACHE_DIR"] = str(report_dir / "baseline-cache")
    env["MOLABEL_BENCHMARK_REPEAT_INDEX"] = str(repeat_index)
    env["MOLABEL_BENCHMARK_MODE"] = benchmark_mode

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
    artifact = None
    if artifact_path.exists():
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    return {
        "benchmark": name,
        "test_file": test_file,
        "k_filter": k_filter,
        "mode": benchmark_mode,
        "repeat_index": repeat_index,
        "command": " ".join(cmd),
        "exit_code": result.returncode,
        "passed": result.returncode == 0,
        "duration_seconds": round(elapsed, 2),
        "stdout": result.stdout,
        "stderr": result.stderr,
        "artifact": artifact,
    }


def write_repeat_report(report_dir: Path, entry: dict[str, Any]) -> Path:
    """Write one benchmark repeat's full log to JSON."""

    out = _repeat_log_path(
        report_dir,
        entry["benchmark"],
        entry["mode"],
        entry["repeat_index"],
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def _fallback_artifact_from_logs(entry: dict[str, Any]) -> dict[str, Any]:
    combined = f"{entry.get('stdout', '')}\n{entry.get('stderr', '')}"
    lower = combined.lower()
    attempts = [int(value) for value in re.findall(r"attempts=(\d+)", combined)]
    api_calls_match = re.search(r"FAILED \(([\d.]+)ms, (\d+) API calls\)", combined)
    api_calls_total = int(api_calls_match.group(2)) if api_calls_match else 0
    timeout_count = 1 if "timeouterror" in lower or "timed out" in lower else 0
    rate_limit_count = lower.count("rate_limit_error") + lower.count(
        "usage limit exceeded"
    )
    no_submission_exit = (
        "submit review labels through molabel" in lower
        or "no review submissions" in lower
    )
    validation_failures = lower.count("validation_errors")

    return {
        "benchmark_id": entry["benchmark"],
        "mode": entry.get("mode", DEFAULT_MODE),
        "review_submission_count": 0,
        "operator_label_score": None,
        "operator_checklist_score": None,
        "operator_overall_score": None,
        "thresholds": {
            "acceptable_operator_label_score": None,
            "acceptable_checklist_score": None,
        },
        "named_lifts": {},
        "taxes": {},
        "stages": {},
        "truthfulness_ok": False,
        "provider_pressure": {
            "api_calls_total": api_calls_total,
            "api_calls_agent": api_calls_total,
            "api_calls_paper_direct": 0,
            "rate_limit_retries": rate_limit_count,
            "timeout_count": timeout_count,
            "adapter_error_count": 0,
            "budget_spent_usd": 0.0,
            "budget_exhausted": (
                "error_max_budget_usd" in lower or "usage limit exceeded" in lower
            ),
            "enforcer_attempts_total": sum(attempts),
            "enforcer_attempts_max": max(attempts or [0]),
            "enforcer_validation_failures": validation_failures,
            "enforcer_timeout_count": timeout_count if attempts else 0,
            "no_submission_exit": no_submission_exit,
        },
    }


def _record_repeat_entry(
    report_dir: Path,
    entry: dict[str, Any],
    repeat_entries: list[dict[str, Any]],
) -> None:
    repeat_outcome = classify_repeat(entry)
    status = "PASS" if entry["passed"] else "FAIL"
    print(
        f"  [{status}] {entry['benchmark']} "
        f"(repeat {entry['repeat_index']}, {entry['duration_seconds']}s, "
        f"{repeat_outcome})"
    )
    write_repeat_report(report_dir, entry)
    repeat_entries.append(entry)


def _artifact_for_entry(entry: dict[str, Any]) -> dict[str, Any]:
    artifact = entry.get("artifact")
    if isinstance(artifact, dict):
        return artifact
    return _fallback_artifact_from_logs(entry)


def _safe_mean(values: list[float]) -> float | None:
    return mean(values) if values else None


def _safe_stddev(values: list[float]) -> float:
    return pstdev(values) if len(values) > 1 else 0.0


def _round_or_none(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def _infer_no_submission_exit(entry: dict[str, Any]) -> bool:
    artifact = _artifact_for_entry(entry)
    pressure = artifact.get("provider_pressure") or {}
    if "no_submission_exit" in pressure:
        return bool(pressure["no_submission_exit"])
    if artifact.get("review_submission_count") == 0:
        return True
    combined = f"{entry.get('stdout', '')}\n{entry.get('stderr', '')}".lower()
    return "submit review labels through molabel" in combined


def _has_infra_signal(provider_pressure: dict[str, Any]) -> bool:
    if not provider_pressure:
        return False
    if provider_pressure.get("budget_exhausted"):
        return True
    return any(
        float(provider_pressure.get(field, 0) or 0) > 0 for field in INFRA_SIGNAL_FIELDS
    )


def classify_repeat(entry: dict[str, Any]) -> str:
    """Classify a single repeat outcome before benchmark-level aggregation."""

    artifact = _artifact_for_entry(entry)
    provider_pressure = artifact.get("provider_pressure") or {}
    review_submission_count = int(artifact.get("review_submission_count") or 0)
    operator_label_score = artifact.get("operator_label_score")
    if operator_label_score is not None and review_submission_count > 0:
        return "scored"
    if _has_infra_signal(provider_pressure) or entry["exit_code"] != 0:
        return "infra-failed"
    if _infer_no_submission_exit(entry):
        return "operator-incomplete"
    return "infra-failed"


def _aggregate_float_fields(
    payloads: list[dict[str, Any]],
) -> dict[str, float]:
    values_by_key: dict[str, list[float]] = defaultdict(list)
    for payload in payloads:
        for key, value in payload.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                values_by_key[key].append(float(value))
    return {
        key: round(mean(values), 4)
        for key, values in sorted(values_by_key.items())
        if values
    }


def _aggregate_stage_scores(artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    stages: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for artifact in artifacts:
        for stage, payload in (artifact.get("stages") or {}).items():
            if isinstance(payload, dict):
                stages[stage].append(payload)
    aggregated: dict[str, Any] = {}
    for stage, payloads in sorted(stages.items()):
        metric_payloads = [payload.get("metrics") or {} for payload in payloads]
        overall_scores = [
            float(payload["overall_score"])
            for payload in payloads
            if payload.get("overall_score") is not None
        ]
        aggregated[stage] = {
            "record_count": payloads[0].get("record_count"),
            "overall_score": _round_or_none(_safe_mean(overall_scores)),
            "metrics": _aggregate_float_fields(metric_payloads),
        }
    return aggregated


def _aggregate_provider_pressure(artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    aggregated: dict[str, Any] = {
        "api_calls_total": 0,
        "api_calls_agent": 0,
        "api_calls_paper_direct": 0,
        "rate_limit_retries": 0,
        "timeout_count": 0,
        "adapter_error_count": 0,
        "budget_spent_usd": 0.0,
        "budget_exhausted": False,
        "enforcer_attempts_total": 0,
        "enforcer_attempts_max": 0,
        "enforcer_validation_failures": 0,
        "enforcer_timeout_count": 0,
        "no_submission_exit": False,
    }
    for artifact in artifacts:
        pressure = artifact.get("provider_pressure") or {}
        for key in (
            "api_calls_total",
            "api_calls_agent",
            "api_calls_paper_direct",
            "rate_limit_retries",
            "timeout_count",
            "adapter_error_count",
            "enforcer_attempts_total",
            "enforcer_validation_failures",
            "enforcer_timeout_count",
        ):
            aggregated[key] += int(pressure.get(key, 0) or 0)
        aggregated["budget_spent_usd"] += float(
            pressure.get("budget_spent_usd", 0.0) or 0.0
        )
        aggregated["budget_exhausted"] = aggregated["budget_exhausted"] or bool(
            pressure.get("budget_exhausted")
        )
        aggregated["no_submission_exit"] = aggregated["no_submission_exit"] or bool(
            pressure.get("no_submission_exit")
        )
        aggregated["enforcer_attempts_max"] = max(
            aggregated["enforcer_attempts_max"],
            int(pressure.get("enforcer_attempts_max", 0) or 0),
        )
    aggregated["budget_spent_usd"] = round(aggregated["budget_spent_usd"], 4)
    return aggregated


def aggregate_benchmark_results(
    benchmark: str,
    mode: str,
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate repeat entries into the per-benchmark report contract."""

    entries = sorted(entries, key=lambda item: item["repeat_index"])
    repeat_outcomes = [
        {
            "repeat_index": entry["repeat_index"],
            "outcome": classify_repeat(entry),
            "duration_seconds": entry["duration_seconds"],
            "exit_code": entry["exit_code"],
        }
        for entry in entries
    ]
    artifacts = [_artifact_for_entry(entry) for entry in entries]
    scored_artifacts = [
        artifact
        for artifact in artifacts
        if artifact.get("operator_label_score") is not None
        and int(artifact.get("review_submission_count") or 0) > 0
    ]

    label_scores = [
        float(artifact["operator_label_score"]) for artifact in scored_artifacts
    ]
    checklist_scores = [
        float(artifact["operator_checklist_score"]) for artifact in scored_artifacts
    ]
    overall_scores = [
        float(artifact["operator_overall_score"]) for artifact in scored_artifacts
    ]
    acceptable_label_threshold = next(
        (
            artifact.get("thresholds", {}).get("acceptable_operator_label_score")
            for artifact in artifacts
            if artifact.get("thresholds", {}).get("acceptable_operator_label_score")
            is not None
        ),
        None,
    )
    acceptable_checklist_threshold = next(
        (
            artifact.get("thresholds", {}).get("acceptable_checklist_score")
            for artifact in artifacts
            if artifact.get("thresholds", {}).get("acceptable_checklist_score")
            is not None
        ),
        None,
    )
    operator_label_score = _safe_mean(label_scores)
    operator_checklist_score = _safe_mean(checklist_scores)
    operator_overall_score = _safe_mean(overall_scores)

    if scored_artifacts:
        checklist_ok = True
        if (
            acceptable_checklist_threshold is not None
            and operator_checklist_score is not None
        ):
            checklist_ok = operator_checklist_score >= float(
                acceptable_checklist_threshold
            )
        label_ok = True
        if acceptable_label_threshold is not None and operator_label_score is not None:
            label_ok = operator_label_score >= float(acceptable_label_threshold)
        outcome = (
            "scored-acceptable-quality"
            if checklist_ok and label_ok
            else "scored-low-quality"
        )
    elif any(repeat["outcome"] == "infra-failed" for repeat in repeat_outcomes):
        outcome = "infra-failed"
    else:
        outcome = "operator-incomplete"

    stage_scores = _aggregate_stage_scores(scored_artifacts)
    provider_pressure = _aggregate_provider_pressure(artifacts)
    named_lifts = _aggregate_float_fields(
        [artifact.get("named_lifts") or {} for artifact in scored_artifacts]
    )
    taxes = _aggregate_float_fields(
        [artifact.get("taxes") or {} for artifact in scored_artifacts]
    )
    artifact_truthfulness_failed = sum(
        int(not artifact.get("truthfulness_ok", False)) for artifact in scored_artifacts
    )
    slice_size = None
    operator_stage = stage_scores.get("operator_reviewed")
    if operator_stage is not None:
        slice_size = operator_stage.get("record_count")

    distribution = {
        "operator_label_score": {
            "raw": [round(value, 4) for value in label_scores],
            "mean": _round_or_none(operator_label_score),
            "min": _round_or_none(min(label_scores) if label_scores else None),
            "max": _round_or_none(max(label_scores) if label_scores else None),
            "stdev": round(_safe_stddev(label_scores), 4),
        },
        "operator_checklist_score": {
            "raw": [round(value, 4) for value in checklist_scores],
            "mean": _round_or_none(operator_checklist_score),
            "min": _round_or_none(min(checklist_scores) if checklist_scores else None),
            "max": _round_or_none(max(checklist_scores) if checklist_scores else None),
            "stdev": round(_safe_stddev(checklist_scores), 4),
        },
        "operator_overall_score": {
            "raw": [round(value, 4) for value in overall_scores],
            "mean": _round_or_none(operator_overall_score),
            "min": _round_or_none(min(overall_scores) if overall_scores else None),
            "max": _round_or_none(max(overall_scores) if overall_scores else None),
            "stdev": round(_safe_stddev(overall_scores), 4),
        },
        "infra_invalid_count": sum(
            int(repeat["outcome"] == "infra-failed") for repeat in repeat_outcomes
        ),
        "repeat_outcomes": repeat_outcomes,
    }

    return {
        "benchmark": benchmark,
        "mode": mode,
        "test_file": entries[0]["test_file"],
        "k_filter": entries[0]["k_filter"],
        "repeats": len(entries),
        "duration_seconds": round(
            sum(entry["duration_seconds"] for entry in entries), 2
        ),
        "outcome": outcome,
        "passed": outcome == "scored-acceptable-quality",
        "slice_size": slice_size,
        "operator_label_score": _round_or_none(operator_label_score),
        "operator_checklist_score": _round_or_none(operator_checklist_score),
        "operator_overall_score": _round_or_none(operator_overall_score),
        "thresholds": {
            "acceptable_operator_label_score": acceptable_label_threshold,
            "acceptable_checklist_score": acceptable_checklist_threshold,
        },
        "model_lift_vs_paper": named_lifts.get("model_lift_vs_paper"),
        "autorun_lift_vs_model": named_lifts.get("autorun_lift_vs_model"),
        "review_lift_in_workflow": named_lifts.get("review_lift_in_workflow"),
        "operator_review_delta": named_lifts.get("operator_review_delta"),
        "workflow_pipeline_delta": named_lifts.get("workflow_pipeline_delta"),
        "headline_review_lift": named_lifts.get("headline_review_lift"),
        "scores": {
            "stages": stage_scores,
            "taxes": taxes,
            "named_lifts": named_lifts,
        },
        "provider_pressure": provider_pressure,
        "artifact_truthfulness_failed_repeats": artifact_truthfulness_failed,
        "distribution": distribution,
        "repeat_logs": [
            {
                "repeat_index": entry["repeat_index"],
                "exit_code": entry["exit_code"],
                "duration_seconds": entry["duration_seconds"],
                "outcome": classify_repeat(entry),
            }
            for entry in entries
        ],
        "raw_repeats": entries,
    }


def write_benchmark_report(report_dir: Path, benchmark_summary: dict[str, Any]) -> Path:
    """Write the aggregated per-benchmark JSON report."""

    filename = f"{benchmark_summary['benchmark']}-{benchmark_summary['mode']}.json"
    out = report_dir / filename
    out.write_text(
        json.dumps(benchmark_summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return out


def write_summary(
    report_dir: Path,
    results: list[dict[str, Any]],
    wall_time: float,
    repeats: int,
    mode: str,
) -> None:
    """Write batch summary JSON and Markdown."""

    results = sorted(results, key=lambda item: (item["mode"], item["benchmark"]))
    outcome_counts: dict[str, int] = defaultdict(int)
    for result in results:
        outcome_counts[result["outcome"]] += 1

    provider_and_enforcer_pressure = {
        "api_calls_total": sum(
            result["provider_pressure"]["api_calls_total"] for result in results
        ),
        "api_calls_agent": sum(
            result["provider_pressure"]["api_calls_agent"] for result in results
        ),
        "api_calls_paper_direct": sum(
            result["provider_pressure"]["api_calls_paper_direct"] for result in results
        ),
        "rate_limit_retries": sum(
            result["provider_pressure"]["rate_limit_retries"] for result in results
        ),
        "timeout_count": sum(
            result["provider_pressure"]["timeout_count"] for result in results
        ),
        "adapter_error_count": sum(
            result["provider_pressure"]["adapter_error_count"] for result in results
        ),
        "budget_spent_usd": round(
            sum(result["provider_pressure"]["budget_spent_usd"] for result in results),
            4,
        ),
        "budget_exhausted_runs": sum(
            int(result["provider_pressure"]["budget_exhausted"]) for result in results
        ),
        "enforcer_attempts_total": sum(
            result["provider_pressure"]["enforcer_attempts_total"] for result in results
        ),
        "enforcer_attempts_max": max(
            [result["provider_pressure"]["enforcer_attempts_max"] for result in results]
            or [0]
        ),
        "enforcer_validation_failures": sum(
            result["provider_pressure"]["enforcer_validation_failures"]
            for result in results
        ),
        "enforcer_timeout_count": sum(
            result["provider_pressure"]["enforcer_timeout_count"] for result in results
        ),
        "no_submission_exit_runs": sum(
            int(result["provider_pressure"]["no_submission_exit"]) for result in results
        ),
    }

    summary = {
        "timestamp": datetime.now(UTC).isoformat(),
        "total": len(results),
        "repeats": repeats,
        "mode": mode,
        "wall_time_seconds": round(wall_time, 2),
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "provider_and_enforcer_pressure": provider_and_enforcer_pressure,
        "benchmarks": [
            {
                key: result[key]
                for key in (
                    "benchmark",
                    "mode",
                    "slice_size",
                    "operator_label_score",
                    "operator_checklist_score",
                    "operator_overall_score",
                    "headline_review_lift",
                    "outcome",
                    "duration_seconds",
                )
            }
            for result in results
        ],
    }

    (report_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    lines = [
        f"# Operator Benchmark Report — {summary['timestamp']}",
        "",
        f"Modes: `{mode}`",
        "",
        (
            f"Repeats: `{repeats}` | Wall time: `{summary['wall_time_seconds']}s` | "
            + ", ".join(
                f"`{outcome}`={count}"
                for outcome, count in sorted(outcome_counts.items())
            )
        ),
        "",
        (
            "| Mode | Benchmark | Slice | Label Score | Checklist Score | Combined | "
            "Headline Review Lift | Outcome |"
        ),
        "|------|-----------|-------|-------------|-----------------|----------|----------------------|---------|",
    ]
    for benchmark in summary["benchmarks"]:
        label_score = (
            f"{benchmark['operator_label_score']:.4f}"
            if benchmark["operator_label_score"] is not None
            else "—"
        )
        checklist_score = (
            f"{benchmark['operator_checklist_score']:.4f}"
            if benchmark["operator_checklist_score"] is not None
            else "—"
        )
        combined_score = (
            f"{benchmark['operator_overall_score']:.4f}"
            if benchmark["operator_overall_score"] is not None
            else "—"
        )
        headline_review_lift = (
            f"{benchmark['headline_review_lift']:+.4f}"
            if benchmark["headline_review_lift"] is not None
            else "—"
        )
        slice_size = (
            benchmark["slice_size"] if benchmark["slice_size"] is not None else "—"
        )
        lines.append(
            f"| {benchmark['mode']} | {benchmark['benchmark']} | {slice_size} | "
            f"{label_score} | "
            f"{checklist_score} | {combined_score} | {headline_review_lift} | "
            f"{benchmark['outcome']} |"
        )

    lines.extend(
        [
            "",
            "## Provider And Enforcer Pressure",
            "",
            (
                f"- `api_calls_total`: "
                f"`{provider_and_enforcer_pressure['api_calls_total']}`"
            ),
            (
                f"- `api_calls_agent`: "
                f"`{provider_and_enforcer_pressure['api_calls_agent']}`"
            ),
            (
                f"- `api_calls_paper_direct`: "
                f"`{provider_and_enforcer_pressure['api_calls_paper_direct']}`"
            ),
            (
                f"- `rate_limit_retries`: "
                f"`{provider_and_enforcer_pressure['rate_limit_retries']}`"
            ),
            f"- `timeout_count`: `{provider_and_enforcer_pressure['timeout_count']}`",
            (
                f"- `adapter_error_count`: "
                f"`{provider_and_enforcer_pressure['adapter_error_count']}`"
            ),
            (
                f"- `budget_spent_usd`: "
                f"${provider_and_enforcer_pressure['budget_spent_usd']:.4f}"
            ),
            (
                f"- `budget_exhausted_runs`: "
                f"`{provider_and_enforcer_pressure['budget_exhausted_runs']}`"
            ),
            (
                f"- `enforcer_attempts_total`: "
                f"`{provider_and_enforcer_pressure['enforcer_attempts_total']}`"
            ),
            (
                f"- `enforcer_attempts_max`: "
                f"`{provider_and_enforcer_pressure['enforcer_attempts_max']}`"
            ),
            (
                f"- `enforcer_validation_failures`: "
                f"`{provider_and_enforcer_pressure['enforcer_validation_failures']}`"
            ),
            (
                f"- `enforcer_timeout_count`: "
                f"`{provider_and_enforcer_pressure['enforcer_timeout_count']}`"
            ),
            (
                f"- `no_submission_exit_runs`: "
                f"`{provider_and_enforcer_pressure['no_submission_exit_runs']}`"
            ),
        ]
    )

    (report_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run all live grounded operator benchmarks"
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
        help=(
            "Max parallel workers "
            f"(default: {DEFAULT_WORKERS}, capped to benchmark count)"
        ),
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=DEFAULT_REPEATS,
        help=f"Independent repeats per benchmark (default: {DEFAULT_REPEATS})",
    )
    parser.add_argument(
        "--mode",
        choices=("open", "preset", "both"),
        default=DEFAULT_MODE,
        help=f"Benchmark workflow mode to run (default: {DEFAULT_MODE})",
    )
    parser.add_argument(
        "--cooldown-seconds",
        type=float,
        default=DEFAULT_COOLDOWN_SECONDS,
        help=(
            "Seconds to wait between sequential benchmark repeats. "
            "Useful for live provider rate limits when --workers=1."
        ),
    )
    args = parser.parse_args()

    if args.repeats < 1:
        raise SystemExit("--repeats must be at least 1")
    if args.cooldown_seconds < 0:
        raise SystemExit("--cooldown-seconds must be non-negative")

    benchmarks = build_benchmarks(args.mode)
    if args.report_dir:
        report_dir = Path(args.report_dir)
    else:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        report_dir = REPO_ROOT / "reports" / f"bench-{ts}"
    report_dir.mkdir(parents=True, exist_ok=True)

    workers = resolve_worker_count(args.workers, len(benchmarks))
    print(
        f"Running {len(benchmarks)} operator benchmarks with {workers} workers, "
        f"{args.repeats} repeat(s), mode={args.mode}"
    )
    print(f"Reports -> {report_dir}\n")

    wall_start = time.monotonic()
    repeat_entries: list[dict[str, Any]] = []
    benchmark_args = [
        (name, test_file, k_filter, benchmark_mode, str(report_dir), repeat_index)
        for name, test_file, k_filter, benchmark_mode in benchmarks
        for repeat_index in range(1, args.repeats + 1)
    ]

    if workers == 1:
        for index, benchmark_arg in enumerate(benchmark_args):
            entry = run_single_benchmark(benchmark_arg)
            _record_repeat_entry(report_dir, entry, repeat_entries)
            if args.cooldown_seconds and index < len(benchmark_args) - 1:
                print(
                    f"  [WAIT] cooldown {args.cooldown_seconds:.1f}s before next repeat"
                )
                time.sleep(args.cooldown_seconds)
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(run_single_benchmark, benchmark_arg): benchmark_arg
                for benchmark_arg in benchmark_args
            }
            for future in as_completed(futures):
                entry = future.result()
                _record_repeat_entry(report_dir, entry, repeat_entries)

    grouped_entries: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for entry in repeat_entries:
        grouped_entries[(entry["benchmark"], entry["mode"])].append(entry)

    results = [
        aggregate_benchmark_results(
            benchmark,
            benchmark_mode,
            grouped_entries[(benchmark, benchmark_mode)],
        )
        for benchmark, benchmark_mode in sorted(grouped_entries)
    ]
    for result in results:
        write_benchmark_report(report_dir, result)

    wall_time = time.monotonic() - wall_start
    write_summary(report_dir, results, wall_time, args.repeats, args.mode)

    acceptable = sum(
        1 for result in results if result["outcome"] == "scored-acceptable-quality"
    )
    failed = sum(
        1
        for result in results
        if result["outcome"] in {"infra-failed", "operator-incomplete"}
    )
    print(
        f"\nDone: {acceptable} acceptable, {failed} infra/incomplete "
        f"in {wall_time:.1f}s"
    )
    print(f"Reports: {report_dir}")
    print("  summary.md / summary.json + one aggregated .json per benchmark")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

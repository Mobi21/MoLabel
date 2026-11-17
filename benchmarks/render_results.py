#!/usr/bin/env python3
"""Render the path x size table in docs/performance.md from result files.

Reads the JSON files ``bench_hot_paths.py`` writes, in the order given, and
prints one Markdown row per path with the median and p95 at each size. A
later file overrides an earlier one for the same path and size, so a clean
rerun of one path replaces its earlier numbers.

    uv run python benchmarks/render_results.py benchmarks/results/baseline-*.json
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

PATH_ORDER = [
    "ingest_api_jsonl",
    "ingest_loader_jsonl",
    "ingest_loader_csv",
    "query_datasets",
    "query_records",
    "query_queues",
    "query_queue_status",
    "query_my_tasks",
    "agreement_service_inter_annotator",
    "agreement_service_human_agent",
    "agreement_api",
    "benchmark_clinc150",
    "benchmark_banking77",
    "export_orchestrator_jsonl",
    "export_workflow_step",
]


def cell(row: dict[str, Any] | None) -> str:
    if row is None:
        return "not run"
    if row["errors"]:
        return f"error ({row['errors']}/{row['runs']} runs)"
    text = f"{row['median_s']:.3f} / {row['p95_s']:.3f}"
    if row["runs"] != 7:
        text += f" ({row['runs']} run{'s' if row['runs'] != 1 else ''})"
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args(argv)

    by_path: dict[str, dict[int, dict[str, Any]]] = defaultdict(dict)
    sizes: set[int] = set()
    for file in args.files:
        for row in json.loads(file.read_text(encoding="utf-8"))["timings"]:
            by_path[row["path"]][row["size"]] = row
            sizes.add(row["size"])
    ordered_sizes = sorted(sizes)

    header = "| path | " + " | ".join(f"n={size:,}" for size in ordered_sizes) + " |"
    print(header)
    print("|---|" + "---:|" * len(ordered_sizes))
    for path in PATH_ORDER + sorted(set(by_path) - set(PATH_ORDER)):
        if path not in by_path:
            continue
        cells = [cell(by_path[path].get(size)) for size in ordered_sizes]
        print(f"| {path} | " + " | ".join(cells) + " |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

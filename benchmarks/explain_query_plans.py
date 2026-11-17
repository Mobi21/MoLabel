#!/usr/bin/env python3
"""Print SQLite's query plan and the time of the queue queries the GUI runs.

Seeds a synthetic reviewed workspace at each ``--sizes`` entry with
``bench_hot_paths``, then calls the queue services the endpoints call
(``list_queues``, ``reviewer_queue_tasks`` and ``get_queue_status``) with a
hook that captures the SQL each one sends. Each captured statement is run
through ``EXPLAIN QUERY PLAN`` on the same database with the same parameters,
and timed once, so a plan that scans or re-runs a subquery per row shows up
next to the seconds it costs.

    uv run python benchmarks/explain_query_plans.py --sizes 1000,10000

Everything generated lives in a temp directory.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import tempfile
import time
import uuid
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

from sqlalchemy import event

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from benchmarks.bench_hot_paths import BenchServer, seed_reviewed_dataset  # noqa: E402


def captured_statements(engine: Any, call: Callable[[], Any]) -> list[tuple[str, Any]]:
    """The (statement, parameters) pairs ``call`` sends through ``engine``."""
    seen: list[tuple[str, Any]] = []

    def capture(
        _conn: Any, _cursor: Any, statement: str, parameters: Any, *_: Any
    ) -> None:
        seen.append((statement, parameters))

    event.listen(engine, "before_cursor_execute", capture)
    try:
        call()
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    return seen


def explain(db_path: Path, statement: str, parameters: Any) -> tuple[list[str], float]:
    with sqlite3.connect(db_path) as conn:
        plan = [
            "  " * int(row[1] > 0) + str(row[3])
            for row in conn.execute(f"EXPLAIN QUERY PLAN {statement}", parameters)
        ]
        start = time.perf_counter()
        conn.execute(statement, parameters).fetchall()
        seconds = time.perf_counter() - start
    return plan, seconds


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", default="1000,10000")
    args = parser.parse_args(argv)
    sizes = [int(s) for s in args.sizes.split(",") if s]

    from molabel.app.services.claims import (
        get_queue_status,
        list_queues,
        reviewer_queue_tasks,
    )

    tmp = Path(tempfile.mkdtemp(prefix="molabel-explain-"))
    try:
        with BenchServer(tmp) as server:
            for size in sizes:
                data = seed_reviewed_dataset(server, size)
                workspace_id = uuid.UUID(data.workspace.id)
                reviewer_id = uuid.UUID(data.reviewer_ids[0])
                calls = {
                    "list_queues": partial(
                        list_queues, server.engine, workspace_id, reviewer_id
                    ),
                    "reviewer_queue_tasks": partial(
                        reviewer_queue_tasks,
                        server.engine,
                        data.queue_id,
                        reviewer_id,
                        500,
                    ),
                    "get_queue_status": partial(
                        get_queue_status, server.engine, data.queue_id
                    ),
                }
                for name, call in calls.items():
                    print(f"\n=== {name} at n={size} (tasks={size * 3}) ===")
                    for statement, parameters in captured_statements(
                        server.engine, call
                    ):
                        plan, seconds = explain(server.db_path, statement, parameters)
                        first_line = " ".join(statement.split())[:110]
                        print(f"-- {seconds:9.4f}s  {first_line}")
                        for line in plan:
                            print(f"     {line}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

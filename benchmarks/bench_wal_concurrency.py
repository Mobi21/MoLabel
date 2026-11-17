#!/usr/bin/env python3
"""Measure what SQLite's journal mode does to concurrent reads and writes.

The server answers requests from a thread pool, so one reviewer submitting
while others read is threads sharing one SQLite file. This runs that shape
on a synthetic reviewed workspace (seeded by ``bench_hot_paths``) twice, with
the rollback journal (``journal_mode=DELETE``, what the server used before
issue #16) and with the write-ahead log (``journal_mode=WAL``), alternating
sides for ``--rounds`` rounds so drift favours neither.

Each round runs one writer thread that submits ``--writes`` reviews, each in
its own transaction the way ``submit_review`` writes them, while ``--readers``
threads read the queue status and the writer's task list through the
services the endpoints call. It reports writer throughput, reader latency
(median and p95 over every read in the round), and the errors each side saw.

    uv run python benchmarks/bench_wal_concurrency.py
    uv run python benchmarks/bench_wal_concurrency.py --size 10000 --readers 8

Everything generated lives in a temp directory.
"""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event, text

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from benchmarks.bench_hot_paths import (  # noqa: E402
    RESULTS_DIR,
    BenchServer,
    ReviewedDataset,
    machine_info,
    seed_reviewed_dataset,
)


def engine_with_journal(db_path: Path, journal_mode: str) -> Engine:
    """An engine like the server's, pinned to one journal mode on every connection."""
    engine = create_engine(
        f"sqlite:///{db_path.as_posix()}", connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine, "connect")
    def _pin_journal(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute(f"PRAGMA journal_mode={journal_mode}")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


@dataclass
class SideResult:
    journal_mode: str
    writer_seconds: float
    writes: int
    write_errors: int
    reads: int
    read_errors: int
    read_latencies: list[float] = field(default_factory=list)

    def row(self) -> dict[str, Any]:
        ordered = sorted(self.read_latencies)
        rank = max(1, int(-(-0.95 * len(ordered) // 1))) if ordered else 0
        return {
            "journal_mode": self.journal_mode,
            "writer_seconds": round(self.writer_seconds, 3),
            "writes_per_second": round(self.writes / self.writer_seconds, 1),
            "writes": self.writes,
            "write_errors": self.write_errors,
            "reads": self.reads,
            "read_errors": self.read_errors,
            "read_median_ms": round(statistics.median(ordered) * 1000, 2)
            if ordered
            else None,
            "read_p95_ms": round(ordered[rank - 1] * 1000, 2) if ordered else None,
            "read_max_ms": round(ordered[-1] * 1000, 2) if ordered else None,
        }


def run_side(
    engine: Engine, data: ReviewedDataset, *, writes: int, readers: int
) -> SideResult:
    from molabel.app.services.claims import get_queue_status, reviewer_queue_tasks

    with engine.connect() as conn:
        available = conn.execute(
            text(
                "SELECT id, record_id FROM review_tasks WHERE queue_id = :queue "
                "AND status = 'available' ORDER BY priority LIMIT :limit"
            ),
            {"queue": data.queue_id, "limit": writes},
        ).fetchall()
    assert len(available) == writes, f"only {len(available)} available tasks"
    reviewer_id = data.reviewer_ids[0]
    stop = threading.Event()
    result = SideResult(
        journal_mode="",
        writer_seconds=0.0,
        writes=0,
        write_errors=0,
        reads=0,
        read_errors=0,
    )
    lock = threading.Lock()

    def writer() -> None:
        now = datetime.now(UTC).isoformat()
        start = time.perf_counter()
        for task_id, record_id in available:
            try:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            "UPDATE review_tasks SET status = 'submitted', "
                            "claimed_by = :reviewer, submitted_at = :now, "
                            "updated_at = :now WHERE id = :id"
                        ),
                        {"reviewer": reviewer_id, "now": now, "id": task_id},
                    )
                    conn.execute(
                        text(
                            "INSERT INTO review_events (id, review_task_id, record_id, "
                            "task_schema_id, task_schema_version, reviewer_id, source, "
                            "decision, labels, ai_was_revealed, created_at, "
                            "workspace_id) VALUES (:id, :task, :record, :schema, 1, "
                            ":reviewer, 'human', 'accept', '{}', 1, :now, :workspace)"
                        ),
                        {
                            "id": str(uuid.uuid4()),
                            "task": task_id,
                            "record": record_id,
                            "schema": data.task_schema_id,
                            "reviewer": reviewer_id,
                            "now": now,
                            "workspace": data.workspace.id,
                        },
                    )
                    conn.execute(
                        text(
                            "UPDATE records SET label_count = label_count + 1, "
                            "updated_at = :now WHERE id = :id"
                        ),
                        {"now": now, "id": record_id},
                    )
                result.writes += 1
            except Exception:
                result.write_errors += 1
        result.writer_seconds = time.perf_counter() - start
        stop.set()

    def reader() -> None:
        latencies: list[float] = []
        reads = errors = 0
        while not stop.is_set():
            for call in (
                lambda: get_queue_status(engine, data.queue_id),
                lambda: reviewer_queue_tasks(
                    engine, data.queue_id, uuid.UUID(reviewer_id), 50
                ),
            ):
                start = time.perf_counter()
                try:
                    call()
                except Exception:
                    errors += 1
                latencies.append(time.perf_counter() - start)
                reads += 1
        with lock:
            result.read_latencies.extend(latencies)
            result.reads += reads
            result.read_errors += errors

    threads = [threading.Thread(target=reader) for _ in range(readers)]
    writer_thread = threading.Thread(target=writer)
    for thread in threads:
        thread.start()
    writer_thread.start()
    writer_thread.join()
    for thread in threads:
        thread.join()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--size", type=int, default=10000)
    parser.add_argument("--writes", type=int, default=300)
    parser.add_argument("--readers", type=int, default=4)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--label", default="wal-concurrency")
    args = parser.parse_args(argv)

    tmp = Path(tempfile.mkdtemp(prefix="molabel-wal-"))
    try:
        with BenchServer(tmp) as server:
            data = seed_reviewed_dataset(server, args.size)
            seeded = server.db_path
        sides: dict[str, list[SideResult]] = {"DELETE": [], "WAL": []}
        for round_index in range(args.rounds):
            order = ("DELETE", "WAL") if round_index % 2 == 0 else ("WAL", "DELETE")
            for mode in order:
                db_path = tmp / f"{mode.lower()}-{round_index}.db"
                shutil.copyfile(seeded, db_path)
                engine = engine_with_journal(db_path, mode)
                try:
                    result = run_side(
                        engine, data, writes=args.writes, readers=args.readers
                    )
                finally:
                    engine.dispose()
                result.journal_mode = mode
                sides[mode].append(result)
                row = result.row()
                print(
                    f"  round {round_index} {mode:<6} "
                    f"writer {row['writer_seconds']:7.3f}s "
                    f"({row['writes_per_second']} w/s) reads={row['reads']} "
                    f"median={row['read_median_ms']}ms p95={row['read_p95_ms']}ms "
                    f"errors w={row['write_errors']} r={row['read_errors']}",
                    flush=True,
                )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    def summary(results: list[SideResult]) -> dict[str, Any]:
        rows = [r.row() for r in results]
        return {
            "rounds": rows,
            "writer_seconds_median": statistics.median(
                r["writer_seconds"] for r in rows
            ),
            "writes_per_second_median": statistics.median(
                r["writes_per_second"] for r in rows
            ),
            "read_median_ms_median": statistics.median(
                r["read_median_ms"] for r in rows
            ),
            "read_p95_ms_median": statistics.median(r["read_p95_ms"] for r in rows),
            "read_errors": sum(r["read_errors"] for r in rows),
            "write_errors": sum(r["write_errors"] for r in rows),
        }

    report = {
        "label": args.label,
        "generated_at": datetime.now(UTC).isoformat(),
        "machine": machine_info(),
        "args": vars(args),
        "sides": {mode: summary(results) for mode, results in sides.items()},
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"{args.label}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwrote {out.relative_to(REPO)}")
    print(
        "\n| journal | writes/s (median of rounds) | read median ms "
        "| read p95 ms | read errors |"
    )
    print("|---|---:|---:|---:|---:|")
    for mode, side in report["sides"].items():
        print(
            f"| {mode} | {side['writes_per_second_median']} | "
            f"{side['read_median_ms_median']} | {side['read_p95_ms_median']} | "
            f"{side['read_errors']} |"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

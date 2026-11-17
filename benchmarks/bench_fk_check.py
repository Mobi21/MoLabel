#!/usr/bin/env python3
"""Time the dangling-foreign-key check that molabel doctor runs.

Seeds a synthetic reviewed workspace with ``bench_hot_paths`` at ``--size``
records, then times ``molabel.core.database.foreign_key_violations`` on it
``--runs`` times. The check is ``PRAGMA foreign_key_check``, which visits
every row of every table that declares a foreign key, so its cost grows
with the database, and this says what a doctor call costs at scale.

    uv run python benchmarks/bench_fk_check.py --size 100000

Everything generated lives in a temp directory.
"""

from __future__ import annotations

import argparse
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from benchmarks.bench_hot_paths import (  # noqa: E402
    RESULTS_DIR,
    BenchServer,
    machine_info,
    seed_reviewed_dataset,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=100000)
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args(argv)

    from sqlalchemy import text

    from molabel.core.database import foreign_key_violations

    tmp = Path(tempfile.mkdtemp(prefix="molabel-fkcheck-"))
    try:
        with BenchServer(tmp) as server:
            seed_reviewed_dataset(server, args.size)
            with server.engine.connect() as conn:
                tables = [
                    name
                    for (name,) in conn.execute(
                        text("SELECT name FROM sqlite_master WHERE type = 'table'")
                    )
                ]
                rows = sum(
                    conn.execute(text(f"SELECT count(*) FROM {table}")).scalar()
                    for table in tables
                )
            seconds: list[float] = []
            for _ in range(args.runs):
                start = time.perf_counter()
                violations = foreign_key_violations(server.engine)
                seconds.append(time.perf_counter() - start)
            db_bytes = server.db_path.stat().st_size
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    lines = [
        f"machine: {machine_info()}",
        f"size={args.size} records, {rows} rows in {len(tables)} tables, "
        f"{db_bytes / 1e6:.0f} MB",
        f"foreign_key_violations: median {statistics.median(seconds):.3f} s, "
        f"max {max(seconds):.3f} s over {args.runs} runs; violations={violations}",
    ]
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"fk-check-{args.size // 1000}k.txt"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"wrote {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

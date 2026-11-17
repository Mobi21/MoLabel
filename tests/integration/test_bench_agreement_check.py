"""The agreement benchmark counts a run that compares fewer rater pairs as an error."""

from __future__ import annotations

import importlib.util
import os
import sqlite3
import sys
from pathlib import Path
from types import ModuleType

import pytest

BENCH_SCRIPT = Path(__file__).resolve().parents[2] / "benchmarks" / "bench_hot_paths.py"
SIZE = 12


@pytest.fixture()
def bench(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ModuleType:
    for name in list(os.environ):
        if name.endswith(("_API_KEY", "_AUTH_TOKEN")):
            monkeypatch.delenv(name)
    monkeypatch.setenv("MOLABEL_DB_URL", "")
    monkeypatch.setenv("MOLABEL_DATA_DIR", str(tmp_path))
    spec = importlib.util.spec_from_file_location("bench_hot_paths", BENCH_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def _errors(bench: ModuleType, tmp_path: Path, tamper_sql: str | None) -> dict:
    ctx = bench.Context(
        runs=1,
        warmup=0,
        profile=False,
        largest=SIZE,
        out_dir=tmp_path,
        max_run_seconds=60.0,
    )
    with bench.BenchServer(tmp_path / "bench") as server:
        data = bench.seed_reviewed_dataset(server, SIZE)
        if tamper_sql is not None:
            with sqlite3.connect(server.db_path) as conn:
                conn.execute(tamper_sql, {"rater": data.reviewer_ids[1]})
        bench.bench_agreement(server, {SIZE: data}, [SIZE], ctx)
    return {timing.path: timing.errors for timing in ctx.timings}


def test_a_full_agreement_run_counts_no_errors(
    bench: ModuleType, tmp_path: Path
) -> None:
    assert _errors(bench, tmp_path, None) == {
        "agreement_service_inter_annotator": 0,
        "agreement_service_human_agent": 0,
        "agreement_api": 0,
    }


@pytest.mark.parametrize(
    "tamper_sql",
    [
        "DELETE FROM agent_outputs",
        "DELETE FROM review_events WHERE reviewer_id = :rater",
    ],
    ids=["no-agent-proposals", "one-rater-missing"],
)
def test_an_endpoint_that_compares_fewer_pairs_counts_an_error(
    bench: ModuleType, tmp_path: Path, tamper_sql: str
) -> None:
    assert _errors(bench, tmp_path, tamper_sql)["agreement_api"] == 1


def test_a_service_run_that_compares_fewer_pairs_counts_an_error(
    bench: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    full = bench.agreement_records

    def first_record_rated_once(size: int) -> list:
        records = full(size)
        records[0].annotations = records[0].annotations[:1]
        return records

    monkeypatch.setattr(bench, "agreement_records", first_record_rated_once)
    ctx = bench.Context(
        runs=1,
        warmup=0,
        profile=False,
        largest=SIZE,
        out_dir=tmp_path,
        max_run_seconds=60.0,
    )

    bench.bench_agreement(None, {}, [SIZE], ctx)

    assert {timing.path: timing.errors for timing in ctx.timings} == {
        "agreement_service_inter_annotator": 1,
        "agreement_service_human_agent": 1,
    }

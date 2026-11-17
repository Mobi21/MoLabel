#!/usr/bin/env python3
"""Time MoLabel's hot paths on synthetic data, through the real code paths.

Paths, each run through the code a user's request runs:

- ingest: ``POST /api/v1/datasets/{id}/import`` on a JSONL file in the
  workspace (what ``molabel dataset import`` calls), and the JSONL and CSV
  loader plugins. CSV has no API import path today, so the CSV number is the
  plugin's ``load_records`` alone.
- query: ``GET /api/v1/datasets``, ``GET /api/v1/datasets/{id}/records``,
  ``GET /api/v1/queues``, ``GET /api/v1/queues/{id}/status`` and
  ``GET /api/v1/queues/{id}/my-tasks``.
- agreement: ``AgreementMetricsService.analyze`` on in-memory records, and
  ``GET /api/v1/quality/agreement`` from stored review events.
- benchmark: ``score_grounded_stage`` with the clinc150 and banking77
  authority packs on synthetic gold and predictions.
- export: ``ExportOrchestrator.export`` with the JSONL packager, and the
  workflow ``export`` step with the server's exporter service.

Each size gets its own server and database, so a timing at one size never
runs against another size's tables. Every path gets ``--warmup`` untimed
runs, then ``--runs`` timed runs per size. The report gives the median, the
p95 (nearest rank; with 7 runs that is the slowest run), the work each run
did (rows imported, items returned, comparisons counted, records exported)
and the errors it saw. ``--profile`` adds one cProfile run per path at the
largest size, not counted in the timings, and writes the top frames beside
the results. ``--no-seed`` skips the reviewed-dataset seed, which leaves the
in-memory paths and the ingest endpoint for sizes too large to seed.

    uv run python benchmarks/bench_hot_paths.py --sizes 1000,10000,100000
    uv run python benchmarks/bench_hot_paths.py --paths agreement --profile

The data is synthetic. Records are numbered sentences of random words, labels
come from a seeded generator, the second rater disagrees with the first at a
fixed rate, and the agent proposal disagrees at another. None of it is gold.
Generated files and the database live in a temp directory, never in the repo.
"""

from __future__ import annotations

import argparse
import cProfile
import csv
import io
import json
import os
import platform
import pstats
import random
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
RESULTS_DIR = REPO / "benchmarks" / "results"
GROUNDED_FIXTURES = REPO / "fixtures" / "benchmarks-grounded"

WORDS = [
    "alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel",
    "india", "juliet", "kilo", "lima", "mike", "november", "oscar", "papa",
    "quebec", "romeo", "sierra", "tango", "uniform", "victor", "whiskey",
]  # fmt: skip
LABEL_OPTIONS = [f"option_{letter}" for letter in "abcdefgh"]
FIELD_COUNT = 3
RATER_COUNT = 2
OVERLAP = 3
RATER_DISAGREEMENT = 0.2
AGENT_DISAGREEMENT = 0.1
SEED = 7


# ---------------------------------------------------------------------------
# Synthetic data
# ---------------------------------------------------------------------------


def synthetic_rows(size: int) -> list[dict[str, Any]]:
    rng = random.Random(SEED)
    return [
        {
            "id": f"synthetic-{index:07d}",
            "text": f"synthetic ticket {index}: "
            + " ".join(rng.choice(WORDS) for _ in range(16)),
            "source": "synthetic",
        }
        for index in range(size)
    ]


def gold_labels(rng: random.Random) -> dict[str, str]:
    return {f"label_{k}": rng.choice(LABEL_OPTIONS) for k in range(FIELD_COUNT)}


def perturbed(
    rng: random.Random, labels: dict[str, str], rate: float
) -> dict[str, str]:
    out = dict(labels)
    for name, value in labels.items():
        if rng.random() < rate:
            out[name] = rng.choice([o for o in LABEL_OPTIONS if o != value])
    return out


@dataclass
class SyntheticReview:
    """One record's labels from every rater and the agent."""

    record_index: int
    rater_labels: list[dict[str, str]]
    agent_labels: dict[str, str]


def synthetic_reviews(size: int) -> list[SyntheticReview]:
    rng = random.Random(SEED + 1)
    reviews: list[SyntheticReview] = []
    for index in range(size):
        first = gold_labels(rng)
        raters = [first] + [
            perturbed(rng, first, RATER_DISAGREEMENT) for _ in range(RATER_COUNT - 1)
        ]
        reviews.append(
            SyntheticReview(index, raters, perturbed(rng, first, AGENT_DISAGREEMENT))
        )
    return reviews


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "text", "source"])
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# Timing
# ---------------------------------------------------------------------------


@dataclass
class Timing:
    path: str
    size: int
    seconds: list[float]
    work: list[int]
    errors: int
    note: str = ""

    @property
    def median(self) -> float:
        return statistics.median(self.seconds)

    @property
    def p95(self) -> float:
        ordered = sorted(self.seconds)
        rank = max(1, int(-(-0.95 * len(ordered) // 1)))
        return ordered[rank - 1]

    def row(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "size": self.size,
            "runs": len(self.seconds),
            "median_s": round(self.median, 4),
            "p95_s": round(self.p95, 4),
            "min_s": round(min(self.seconds), 4),
            "max_s": round(max(self.seconds), 4),
            "work": self.work[0] if len(set(self.work)) == 1 else self.work,
            "errors": self.errors,
            "note": self.note,
        }


RunFn = Callable[[], tuple[int, int]]
"""Runs one iteration and returns (work done, errors seen)."""


def timed(
    path: str,
    size: int,
    run: RunFn,
    *,
    runs: int,
    warmup: int,
    max_run_seconds: float,
    note: str = "",
) -> Timing:
    for _ in range(warmup):
        start = time.perf_counter()
        run()
        if time.perf_counter() - start > max_run_seconds:
            runs = 1
            note = f"{note} capped: warmup run exceeded {max_run_seconds:g}s".strip()
    seconds: list[float] = []
    work: list[int] = []
    errors = 0
    for _ in range(runs):
        start = time.perf_counter()
        done, failed = run()
        seconds.append(time.perf_counter() - start)
        work.append(done)
        errors += failed
    timing = Timing(path, size, seconds, work, errors, note)
    print(
        f"  {path:<34} n={size:<8} median={timing.median:9.4f}s "
        f"p95={timing.p95:9.4f}s work={timing.work[0]} errors={errors}",
        flush=True,
    )
    return timing


def profile_once(path: str, size: int, run: RunFn, out_dir: Path) -> Path:
    profiler = cProfile.Profile()
    profiler.enable()
    run()
    profiler.disable()
    out = out_dir / f"profile-{path}-{size}.txt"
    buffer = io.StringIO()
    stats = pstats.Stats(profiler, stream=buffer)
    stats.strip_dirs()
    buffer.write(
        f"# cProfile of one {path} run at n={size}, not counted in timings\n\n"
    )
    buffer.write("## top 25 by cumulative time\n")
    stats.sort_stats("cumulative").print_stats(25)
    buffer.write("\n## top 25 by own time\n")
    stats.sort_stats("tottime").print_stats(25)
    out.write_text(buffer.getvalue(), encoding="utf-8")
    print(f"  profile -> {out.relative_to(REPO)}", flush=True)
    return out


# ---------------------------------------------------------------------------
# The server, booted the way uvicorn boots it
# ---------------------------------------------------------------------------


@dataclass
class Workspace:
    """A bootstrapped workspace and the session of its first reviewer."""

    id: str
    reviewer_id: str
    root: Path
    token: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Cookie": f"molabel_session={self.token}"}


class BenchServer:
    """The FastAPI app with its real lifespan, on a SQLite file in ``tmp``."""

    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.db_path = tmp / "server" / "molabel.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        os.environ["MOLABEL_DB_URL"] = f"sqlite:///{self.db_path.as_posix()}"
        os.environ["MOLABEL_DATA_DIR"] = str(tmp / "server")
        for name in list(os.environ):
            if name.endswith(("_API_KEY", "_AUTH_TOKEN")):
                del os.environ[name]
        from fastapi.testclient import TestClient

        from molabel.app.main import create_app

        self.app = create_app()
        self._client_cm = TestClient(self.app, raise_server_exceptions=False)

    def __enter__(self) -> BenchServer:
        self.client = self._client_cm.__enter__()
        self.engine = self.app.state.engine
        return self

    def __exit__(self, *exc: object) -> None:
        self._client_cm.__exit__(*exc)
        self.engine.dispose()

    def bootstrap_workspace(self, name: str) -> Workspace:
        root = self.tmp / "workspaces" / name
        root.mkdir(parents=True, exist_ok=True)
        resp = self.client.post(
            "/api/v1/cli/workspaces/bootstrap",
            json={
                "path": str(root),
                "workspace_name": name,
                "reviewer_name": "synthetic-rater-1",
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        token = resp.cookies["molabel_session"]
        self.client.cookies.clear()
        return Workspace(body["workspace_id"], body["reviewer_id"], root, token)

    def create_dataset(self, workspace: Workspace, name: str) -> str:
        resp = self.client.post(
            "/api/v1/datasets",
            json={
                "dataset_name": name,
                "workspace_id": workspace.id,
                "source_type": "jsonl",
                "loader_plugin": "molabel.loaders.jsonl",
                "record_kind": "text",
            },
            headers=workspace.headers,
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["dataset_id"]

    def import_jsonl(
        self, workspace: Workspace, dataset_id: str, source_uri: str
    ) -> dict[str, Any]:
        resp = self.client.post(
            f"/api/v1/datasets/{dataset_id}/import",
            json={"source_uri": source_uri},
            headers=workspace.headers,
        )
        assert resp.status_code == 202, resp.text
        return resp.json()


# ---------------------------------------------------------------------------
# Seeding a reviewed dataset straight into the database (setup, not timed)
# ---------------------------------------------------------------------------


@dataclass
class ReviewedDataset:
    workspace: Workspace
    reviewer_ids: list[str]
    dataset_id: str
    task_schema_id: str
    queue_id: str
    record_ids: list[str]


def seed_reviewed_dataset(server: BenchServer, size: int) -> ReviewedDataset:
    """Import ``size`` records through the API, then seed a reviewed overlap queue.

    The queue holds OVERLAP copies of every record: RATER_COUNT are submitted,
    one per rater, with a review event each, and the rest are unclaimed and
    available. Every record has one agent proposal bound to its tasks. The
    rows mirror what the workflow's human_review step and submit write.
    """
    workspace = server.bootstrap_workspace(f"reviewed-{size}")
    workspace_id, first_reviewer = workspace.id, workspace.reviewer_id
    rows = synthetic_rows(size)
    source = workspace.root / "data" / f"synthetic_{size}.jsonl"
    write_jsonl(source, rows)
    dataset_id = server.create_dataset(workspace, f"synthetic-reviewed-{size}")
    status = server.import_jsonl(workspace, dataset_id, f"data/synthetic_{size}.jsonl")
    assert status["records_imported"] == size, status

    reviews = synthetic_reviews(size)
    now = datetime.now(UTC).isoformat()
    task_schema_id = str(uuid.uuid4())
    model_profile_id = str(uuid.uuid4())
    agent_run_id = str(uuid.uuid4())
    workflow_id = str(uuid.uuid4())
    execution_id = str(uuid.uuid4())
    queue_id = f"queue-{uuid.uuid4()}"
    reviewer_ids = [first_reviewer] + [
        str(uuid.uuid4()) for _ in range(RATER_COUNT - 1)
    ]

    conn = sqlite3.connect(server.db_path)
    try:
        record_ids = [
            row[0]
            for row in conn.execute(
                "SELECT id FROM records WHERE dataset_id = ? ORDER BY sequence_index",
                (dataset_id,),
            ).fetchall()
        ]
        assert len(record_ids) == size
        conn.executemany(
            "INSERT INTO reviewer_profiles (id, display_name, avatar_color, "
            "is_operator, is_active, workspace_id, created_at) VALUES (:id, :name, "
            "'#2255AA', 0, 1, :wid, :now)",
            [
                {
                    "id": rid,
                    "name": f"synthetic-rater-{i + 2}",
                    "wid": workspace_id,
                    "now": now,
                }
                for i, rid in enumerate(reviewer_ids[1:])
            ],
        )
        conn.execute(
            "INSERT INTO task_schemas (id, task_schema_slug, version, task_type, "
            "title, label_fields, required_fields, optional_fields, "
            "blind_review_policy, supported_agent_roles, is_active, is_frozen, "
            "file_path, created_at, updated_at, workspace_id) VALUES (?, "
            "'synthetic-v1', 1, 'classification', 'Synthetic', ?, '[]', '[]', "
            "'show_agent_outputs', '[]', 1, 0, "
            "'workbench/config/task-schemas/synthetic-v1.yaml', ?, ?, ?)",
            (
                task_schema_id,
                json.dumps(
                    [
                        {
                            "name": f"label_{k}",
                            "field_type": "categorical",
                            "required": True,
                            "options": LABEL_OPTIONS,
                        }
                        for k in range(FIELD_COUNT)
                    ]
                ),
                now,
                now,
                workspace_id,
            ),
        )
        conn.execute(
            "INSERT INTO model_profiles (id, model_profile_slug, provider_type, "
            "model_identifier, transport, created_at, updated_at, workspace_id) "
            "VALUES (?, 'synthetic-offline', 'offline', 'offline-heuristic', "
            "'builtin', ?, ?, ?)",
            (model_profile_id, now, now, workspace_id),
        )
        conn.execute(
            "INSERT INTO agent_runs (id, dataset_id, task_schema_id, "
            "model_profile_id, agent_role, status, retry_count, created_at, "
            "updated_at, workspace_id) VALUES (?, ?, ?, ?, 'proposer', 'completed', "
            "0, ?, ?, ?)",
            (
                agent_run_id,
                dataset_id,
                task_schema_id,
                model_profile_id,
                now,
                now,
                workspace_id,
            ),
        )
        output_ids = [str(uuid.uuid4()) for _ in range(size)]
        conn.executemany(
            "INSERT INTO agent_outputs (id, agent_run_id, record_id, task_schema_id, "
            "output_type, labels, validation_passed, retry_attempt, "
            "is_visible_for_review, created_at, workspace_id) VALUES (:id, :run, "
            ":rec, :schema, 'label', :labels, 1, 0, 1, :now, :wid)",
            [
                {
                    "id": output_ids[i],
                    "run": agent_run_id,
                    "rec": record_ids[i],
                    "schema": task_schema_id,
                    "labels": json.dumps(reviews[i].agent_labels),
                    "now": now,
                    "wid": workspace_id,
                }
                for i in range(size)
            ],
        )
        conn.execute(
            "INSERT INTO workflow_definitions (id, workflow_slug, version, name, "
            "steps, is_template, file_path, is_active, created_at, updated_at, "
            "workspace_id) VALUES (?, 'synthetic-review', 1, 'Synthetic review', "
            "'[]', 0, 'workbench/workflows/synthetic-review.yaml', 1, ?, ?, ?)",
            (workflow_id, now, now, workspace_id),
        )
        conn.execute(
            "INSERT INTO workflow_executions (id, workflow_definition_id, "
            "workflow_version, status, created_at, updated_at, workspace_id) "
            "VALUES (?, ?, 1, 'paused', ?, ?, ?)",
            (execution_id, workflow_id, now, now, workspace_id),
        )
        conn.execute(
            "INSERT INTO workflow_step_executions (id, workflow_execution_id, "
            "step_id, step_type, step_config, status, iteration, result, "
            "created_at, updated_at, workspace_id) VALUES (?, ?, 'review', "
            "'human_review', '{}', 'waiting_for_human', 0, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                execution_id,
                json.dumps({"summary": {"queue_id": queue_id}}),
                now,
                now,
                workspace_id,
            ),
        )
        tasks: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []
        for i, record_id in enumerate(record_ids):
            for copy in range(OVERLAP):
                task_id = str(uuid.uuid4())
                submitted = copy < RATER_COUNT
                tasks.append(
                    {
                        "id": task_id,
                        "queue": queue_id,
                        "rec": record_id,
                        "schema": task_schema_id,
                        "status": "submitted" if submitted else "available",
                        "priority": i + 1,
                        "claimed_by": reviewer_ids[copy] if submitted else None,
                        "claimed_at": now if submitted else None,
                        "outputs": json.dumps([output_ids[i]]),
                        "submitted_at": now if submitted else None,
                        "now": now,
                        "wid": workspace_id,
                        "dataset": dataset_id,
                    }
                )
                if submitted:
                    labels = reviews[i].rater_labels[copy]
                    events.append(
                        {
                            "id": str(uuid.uuid4()),
                            "task": task_id,
                            "rec": record_id,
                            "schema": task_schema_id,
                            "reviewer": reviewer_ids[copy],
                            "decision": "accept"
                            if labels == reviews[i].agent_labels
                            else "edit",
                            "labels": json.dumps(labels),
                            "output": output_ids[i],
                            "now": now,
                            "wid": workspace_id,
                        }
                    )
        conn.executemany(
            "INSERT INTO review_tasks (id, queue_id, record_id, task_schema_id, "
            "status, priority, priority_reason, claimed_by, claimed_at, "
            "claim_expired_count, is_overlap, is_calibration, draft_labels, "
            "agent_output_ids, ai_revealed, ai_revealed_at, submitted_at, "
            "created_at, updated_at, workspace_id, dataset_id) VALUES (:id, :queue, "
            ":rec, :schema, :status, :priority, 'workflow_queue', :claimed_by, "
            ":claimed_at, 0, 1, 0, NULL, :outputs, 1, :claimed_at, :submitted_at, "
            ":now, :now, :wid, :dataset)",
            tasks,
        )
        conn.executemany(
            "INSERT INTO review_events (id, review_task_id, record_id, "
            "task_schema_id, task_schema_version, reviewer_id, source, decision, "
            "labels, ai_was_revealed, agent_output_id, created_at, workspace_id) "
            "VALUES (:id, :task, :rec, :schema, 1, :reviewer, 'human', :decision, "
            ":labels, 1, :output, :now, :wid)",
            events,
        )
        conn.executemany(
            "UPDATE records SET latest_label = :labels, label_count = 2 WHERE id = :id",
            [
                {"labels": json.dumps(reviews[i].rater_labels[0]), "id": record_ids[i]}
                for i in range(size)
            ],
        )
        conn.commit()
    finally:
        conn.close()
    return ReviewedDataset(
        workspace, reviewer_ids, dataset_id, task_schema_id, queue_id, record_ids
    )


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def bench_ingest(server: BenchServer, sizes: list[int], ctx: Context) -> None:
    from molabel.plugins.loaders.csv_loader import CsvLoader
    from molabel.plugins.loaders.jsonl_loader import JsonlLoader

    workspace = server.bootstrap_workspace("ingest")
    counter = iter(range(10**6))
    for size in sizes:
        rows = synthetic_rows(size)
        jsonl = workspace.root / "data" / f"synthetic_{size}.jsonl"
        write_jsonl(jsonl, rows)
        csv_path = workspace.root / "data" / f"synthetic_{size}.csv"
        write_csv(csv_path, rows)

        def import_api(size: int = size) -> tuple[int, int]:
            dataset_id = server.create_dataset(
                workspace, f"synthetic-ingest-{size}-{next(counter)}"
            )
            status = server.import_jsonl(
                workspace, dataset_id, f"data/synthetic_{size}.jsonl"
            )
            return status["records_imported"], len(status["errors"]) + int(
                status["records_imported"] != size
            )

        def load_jsonl(size: int = size, jsonl: Path = jsonl) -> tuple[int, int]:
            records = list(JsonlLoader().load_records(jsonl, {"id_field": "id"}))
            return len(records), int(len(records) != size)

        def load_csv(size: int = size, csv_path: Path = csv_path) -> tuple[int, int]:
            records = list(CsvLoader().load_records(csv_path, {"id_column": "id"}))
            return len(records), int(len(records) != size)

        ctx.measure("ingest_api_jsonl", size, import_api)
        ctx.measure("ingest_loader_jsonl", size, load_jsonl)
        ctx.measure("ingest_loader_csv", size, load_csv)


def bench_query(
    server: BenchServer, reviewed: dict[int, ReviewedDataset], ctx: Context
) -> None:
    client = server.client

    def get(data: ReviewedDataset, path: str, **params: Any) -> dict[str, Any]:
        resp = client.get(path, params=params, headers=data.workspace.headers)
        assert resp.status_code == 200, (path, resp.status_code, resp.text[:300])
        return resp.json()

    for size, data in reviewed.items():

        def list_datasets(data: ReviewedDataset = data) -> tuple[int, int]:
            body = get(data, "/api/v1/datasets", limit=200)
            return len(body["items"]), 0

        def list_records(data: ReviewedDataset = data) -> tuple[int, int]:
            body = get(data, f"/api/v1/datasets/{data.dataset_id}/records", limit=200)
            return len(body["items"]), int(len(body["items"]) != 200)

        def list_queues(
            data: ReviewedDataset = data, size: int = size
        ) -> tuple[int, int]:
            body = get(data, "/api/v1/queues", workspace_id=data.workspace.id)
            mine = [q for q in body["items"] if q["queue_id"] == data.queue_id]
            ok = bool(mine) and mine[0]["total"] == size * OVERLAP
            return len(body["items"]), int(not ok)

        def queue_status(
            data: ReviewedDataset = data, size: int = size
        ) -> tuple[int, int]:
            body = get(data, f"/api/v1/queues/{data.queue_id}/status")
            return body["total"], int(body["total"] != size * OVERLAP)

        def my_tasks(data: ReviewedDataset = data, size: int = size) -> tuple[int, int]:
            body = get(data, f"/api/v1/queues/{data.queue_id}/my-tasks", limit=500)
            return len(body["items"]), int(len(body["items"]) != min(500, size))

        ctx.measure("query_datasets", size, list_datasets)
        ctx.measure("query_records", size, list_records)
        ctx.measure("query_queues", size, list_queues)
        ctx.measure("query_queue_status", size, queue_status)
        ctx.measure("query_my_tasks", size, my_tasks)


def agreement_records(size: int) -> list[Any]:
    from molabel.core.quality.agreement_metrics import (
        AgreementAnnotation,
        AgreementRecord,
    )

    return [
        AgreementRecord(
            record_id=f"synthetic-{review.record_index:07d}",
            annotations=[
                AgreementAnnotation(
                    source="human", rater_id=f"synthetic-rater-{i + 1}", labels=labels
                )
                for i, labels in enumerate(review.rater_labels)
            ]
            + [
                AgreementAnnotation(
                    source="agent", rater_id="synthetic-run", labels=review.agent_labels
                )
            ],
        )
        for review in synthetic_reviews(size)
    ]


def bench_agreement(
    server: BenchServer,
    reviewed: dict[int, ReviewedDataset],
    sizes: list[int],
    ctx: Context,
) -> None:
    from molabel.core.quality.agreement_metrics import AgreementMetricsService

    service = AgreementMetricsService()
    fields = [f"label_{k}" for k in range(FIELD_COUNT)]
    for size in sizes:
        records = agreement_records(size)

        def inter_annotator(records: list[Any] = records) -> tuple[int, int]:
            result = service.analyze(
                records, analysis_type="inter_annotator", fields=fields
            )
            return result.overall.comparisons, int(result.overall.comparisons == 0)

        def human_agent(records: list[Any] = records) -> tuple[int, int]:
            result = service.analyze(
                records, analysis_type="human_agent", fields=fields
            )
            assert result.human_agent is not None
            return result.human_agent.comparisons, int(
                result.human_agent.comparisons == 0
            )

        ctx.measure("agreement_service_inter_annotator", size, inter_annotator)
        ctx.measure("agreement_service_human_agent", size, human_agent)

        data = reviewed.get(size)
        if data is None:
            continue

        def agreement_api(
            data: ReviewedDataset = data, size: int = size
        ) -> tuple[int, int]:
            resp = server.client.get(
                "/api/v1/quality/agreement",
                params={"workspace_id": data.workspace.id, "queue_id": data.queue_id},
                headers=data.workspace.headers,
            )
            if resp.status_code != 200:
                ctx.log(
                    f"agreement_api n={size}: HTTP {resp.status_code} {resp.text[:200]}"
                )
                return 0, 1
            body = resp.json()
            return body["record_count"], int(body["record_count"] != size)

        ctx.measure("agreement_api", size, agreement_api)


def authority_bundle(root: Path) -> Any:
    """A scoring bundle from a fixture's authority pack alone.

    The checked-in packs point their scenario paths at a workbench tree that
    is not in git (issue #3), so the files are read from ``authority/`` here.
    """
    import yaml

    from molabel.core.quality.grounded_benchmarks import (
        GroundedBaselines,
        GroundedBenchmarkBundle,
        GroundedBenchmarkScenario,
        GroundedLabelMap,
        GroundedMetricsConfig,
        GroundedPaperMetadata,
    )

    def load(name: str, model: Any) -> Any:
        text = (root / "authority" / name).read_text(encoding="utf-8")
        return model.model_validate(yaml.safe_load(text) or {})

    return GroundedBenchmarkBundle(
        workspace_root=root,
        authority=None,
        scenario=load("scenario.yaml", GroundedBenchmarkScenario),
        paper=load("paper.yaml", GroundedPaperMetadata),
        label_map=load("label-map.yaml", GroundedLabelMap),
        metrics=load("metrics.yaml", GroundedMetricsConfig),
        baselines=load("baselines.yaml", GroundedBaselines),
    )


def bench_benchmark(sizes: list[int], ctx: Context) -> None:
    from molabel.core.quality.grounded_benchmarks import score_grounded_stage

    bundles = {
        name: authority_bundle(GROUNDED_FIXTURES / name)
        for name in ("clinc150", "banking77")
    }
    label_counts = {"clinc150": 150, "banking77": 77}
    for size in sizes:
        for name, bundle in bundles.items():
            rng = random.Random(SEED + 2)
            intents = [f"synthetic_intent_{i}" for i in range(label_counts[name])]
            gold_rows: list[dict[str, Any]] = []
            predictions: list[dict[str, Any]] = []
            for index in range(size):
                intent = rng.choice(intents)
                oos = rng.random() < 0.1
                gold: dict[str, Any] = {"intent_label": intent}
                predicted: dict[str, Any] = {
                    "intent_label": intent
                    if rng.random() < 0.9
                    else rng.choice(intents)
                }
                if name == "clinc150":
                    gold["is_out_of_scope"] = oos
                    predicted["is_out_of_scope"] = (
                        oos if rng.random() < 0.95 else not oos
                    )
                record_id = f"synthetic-{index:07d}"
                gold_rows.append({"record_id": record_id, "labels": gold})
                predictions.append({"record_id": record_id, "labels": predicted})

            def score(
                bundle: Any = bundle,
                gold_rows: list[dict[str, Any]] = gold_rows,
                predictions: list[dict[str, Any]] = predictions,
                size: int = size,
            ) -> tuple[int, int]:
                summary = score_grounded_stage(
                    bundle=bundle,
                    predictions=predictions,
                    gold_rows=gold_rows,
                    run_id="synthetic-bench",
                    stage="molabel_model",
                    variant="molabel_operated",
                )
                return summary.record_count, int(summary.record_count != size)

            ctx.measure(f"benchmark_{name}", size, score)


def bench_export(
    server: BenchServer,
    reviewed: dict[int, ReviewedDataset],
    sizes: list[int],
    ctx: Context,
) -> None:
    from molabel.app.api.v1.workflows import _WorkflowExporter
    from molabel.core.export.export_orchestrator import (
        ExportOrchestrator,
        ExportRequest,
        PackagerRegistry,
        PathContract,
    )
    from molabel.core.types import Record, ReviewEvent
    from molabel.core.workflow.context import RecordSet, WorkflowContext
    from molabel.core.workflow.steps.output_steps import ExportExecutor
    from molabel.plugins.exporters.jsonl_exporter import JsonlExporter

    registry = PackagerRegistry()
    registry.register("jsonl", JsonlExporter())
    export_root = server.tmp / "exports"
    orchestrator = ExportOrchestrator(registry, PathContract(base_dir=export_root))
    counter = iter(range(10**6))
    for size in sizes:
        reviews = synthetic_reviews(size)
        rows = synthetic_rows(size)
        dataset_uuid = uuid.uuid4()
        records = [
            Record(
                id=uuid.uuid4(),
                dataset_id=dataset_uuid,
                external_id=row["id"],
                stable_fields={"text": row["text"]},
                payload=row,
            )
            for row in rows
        ]
        labels = {
            str(record.id): [
                ReviewEvent(
                    id=uuid.uuid4(),
                    record_id=record.id,
                    source="human",
                    decision="accept",
                    labels=review.rater_labels[0],
                    created_at=datetime.now(UTC),
                )
            ]
            for record, review in zip(records, reviews, strict=True)
        }

        def orchestrate(
            records: list[Record] = records,
            labels: dict[str, list[ReviewEvent]] = labels,
            size: int = size,
        ) -> tuple[int, int]:
            result = orchestrator.export(
                ExportRequest(
                    project="synthetic",
                    dataset=f"export-{size}-{next(counter)}",
                    format="jsonl",
                    records=records,
                    labels=labels,
                )
            )
            assert result.success, result.error
            assert result.manifest is not None
            return result.manifest.record_count, int(
                result.manifest.record_count != size
            )

        ctx.measure("export_orchestrator_jsonl", size, orchestrate)

        data = reviewed.get(size)
        if data is None:
            continue

        def workflow_step(
            data: ReviewedDataset = data, size: int = size
        ) -> tuple[int, int]:
            context = WorkflowContext(
                workspace_id=data.workspace.id,
                workflow_execution_id=str(uuid.uuid4()),
                workflow_version=1,
            )
            context.record_sets["review"] = RecordSet(
                record_ids=list(data.record_ids), record_count=size
            )
            context.active_record_set_id = "review"
            with server.engine.connect() as conn:
                result = ExportExecutor().execute(
                    "export_results",
                    {"format": "jsonl", "destination": "workbench/exports/synthetic"},
                    context,
                    services={
                        "exporter": _WorkflowExporter(
                            conn, workspace_root=data.workspace.root
                        )
                    },
                )
            assert result.success, result.error
            assert result.output is not None
            count = result.output.summary["record_count"]
            return count, int(count != size)

        ctx.measure("export_workflow_step", size, workflow_step)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


@dataclass
class Context:
    runs: int
    warmup: int
    profile: bool
    largest: int
    out_dir: Path
    max_run_seconds: float
    skip: set[str] = field(default_factory=set)
    timings: list[Timing] = field(default_factory=list)
    profiles: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def measure(self, path: str, size: int, run: RunFn, note: str = "") -> None:
        if path in self.skip or f"{path}@{size}" in self.skip:
            self.log(f"{path} n={size}: skipped on request")
            return
        self.timings.append(
            timed(
                path,
                size,
                run,
                runs=self.runs,
                warmup=self.warmup,
                max_run_seconds=self.max_run_seconds,
                note=note,
            )
        )
        if self.profile and size == self.largest:
            self.profiles.append(
                str(profile_once(path, size, run, self.out_dir).relative_to(REPO))
            )

    def log(self, message: str) -> None:
        print(f"  note: {message}", flush=True)
        self.notes.append(message)


PATHS = ("ingest", "query", "agreement", "benchmark", "export")


def machine_info() -> dict[str, Any]:
    cpu = platform.processor()
    if sys.platform == "win32":
        try:
            out = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "(Get-CimInstance Win32_Processor).Name",
                ],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            cpu = out.stdout.strip() or cpu
        except OSError:
            pass
    return {
        "platform": platform.platform(),
        "cpu": cpu,
        "logical_cpus": os.cpu_count(),
        "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version,
        "git_rev": subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=REPO,
            check=False,
        ).stdout.strip(),
    }


@contextmanager
def temp_dir(keep: bool) -> Iterator[Path]:
    path = Path(tempfile.mkdtemp(prefix="molabel-bench-"))
    try:
        yield path
    finally:
        if keep:
            print(f"kept {path}")
        else:
            shutil.rmtree(path, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--sizes", default="1000,10000,100000")
    parser.add_argument("--paths", default=",".join(PATHS))
    parser.add_argument("--runs", type=int, default=7)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument(
        "--max-run-seconds",
        type=float,
        default=120.0,
        help="a path whose warmup run takes longer gets one timed run, marked capped",
    )
    parser.add_argument("--profile", action="store_true")
    parser.add_argument(
        "--skip",
        default="",
        help=(
            "comma-separated timing names to leave out, such as query_queues, "
            "or name@size to leave one out at one size only"
        ),
    )
    parser.add_argument(
        "--no-seed",
        action="store_true",
        help="skip the reviewed-dataset seed, and with it every database-backed timing",
    )
    parser.add_argument("--label", default="baseline")
    parser.add_argument("--keep-temp", action="store_true")
    args = parser.parse_args(argv)
    sizes = [int(s) for s in args.sizes.split(",") if s]
    paths = [p for p in args.paths.split(",") if p]
    unknown = set(paths) - set(PATHS)
    if unknown:
        parser.error(f"unknown paths {sorted(unknown)}; choose from {PATHS}")

    sys.path.insert(0, str(REPO))
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ctx = Context(
        args.runs,
        args.warmup,
        args.profile,
        max(sizes),
        RESULTS_DIR,
        args.max_run_seconds,
        {name for name in args.skip.split(",") if name},
    )
    info = machine_info()
    print(f"machine: {info}")
    print(f"sizes={sizes} runs={args.runs} warmup={args.warmup} paths={paths}")

    started = time.perf_counter()
    db_bytes: dict[int, int] = {}
    for size in sizes:
        with temp_dir(args.keep_temp) as tmp, BenchServer(tmp) as server:
            reviewed: dict[int, ReviewedDataset] = {}
            if {"query", "agreement", "export"} & set(paths) and not args.no_seed:
                seed_start = time.perf_counter()
                reviewed[size] = seed_reviewed_dataset(server, size)
                print(
                    f"seeded reviewed dataset n={size} in "
                    f"{time.perf_counter() - seed_start:.1f}s"
                )
            if "ingest" in paths:
                bench_ingest(server, [size], ctx)
            if "query" in paths:
                bench_query(server, reviewed, ctx)
            if "agreement" in paths:
                bench_agreement(server, reviewed, [size], ctx)
            if "benchmark" in paths:
                bench_benchmark([size], ctx)
            if "export" in paths:
                bench_export(server, reviewed, [size], ctx)
            db_bytes[size] = server.db_path.stat().st_size

    report = {
        "label": args.label,
        "generated_at": datetime.now(UTC).isoformat(),
        "machine": info,
        "args": {
            "sizes": sizes,
            "paths": paths,
            "runs": args.runs,
            "warmup": args.warmup,
            "max_run_seconds": args.max_run_seconds,
            "skip": sorted(name for name in args.skip.split(",") if name),
            "no_seed": args.no_seed,
        },
        "synthetic": {
            "fields": FIELD_COUNT,
            "raters": RATER_COUNT,
            "overlap": OVERLAP,
            "rater_disagreement": RATER_DISAGREEMENT,
            "agent_disagreement": AGENT_DISAGREEMENT,
        },
        "database_bytes": db_bytes,
        "wall_seconds": round(time.perf_counter() - started, 1),
        "notes": ctx.notes,
        "profiles": ctx.profiles,
        "timings": [t.row() for t in ctx.timings],
    }
    out = RESULTS_DIR / f"{args.label}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwrote {out.relative_to(REPO)} ({report['wall_seconds']}s wall)")
    print("\n| path | n | runs | median s | p95 s | work | errors |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    for row in report["timings"]:
        print(
            f"| {row['path']} | {row['size']} | {row['runs']} | {row['median_s']} | "
            f"{row['p95_s']} | {row['work']} | {row['errors']} |"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

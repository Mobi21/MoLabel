# Performance

MoLabel's rule on faster languages is that nothing gets rewritten on vibes.
This document is the measurement behind that rule. It profiles the hot paths
on synthetic data at 1k, 10k, 100k and 1M records through the code a request
runs, names what each number is bound by, and lists the candidates with their
expected gain. A candidate that needs a new library or language is adopted
only when a prototype measures a 3x end-to-end gain on the realistic size,
with a pure-Python fallback. Ordinary fixes (an N+1 query, a missing index,
a quadratic loop) go in when they are measured and behavior-preserving, at
any gain.

Every number below comes from a command in this file, on the machine named
in [Method](#method). Rerun them before trusting them on other hardware.

## Method

**Machine.** AMD Ryzen 7 7800X3D (8 cores, 16 threads), 31 GB RAM, Crucial
T500 NVMe SSD, Windows 11 (10.0.26300), CPython 3.12.14, SQLite 3.53.1,
SQLAlchemy from `uv.lock`. CPU load was 17% before the first run and nothing
else was started during a run. Baseline commit `263298d`.

**Harness.** [`benchmarks/bench_hot_paths.py`](../benchmarks/bench_hot_paths.py)
boots the FastAPI app with its real lifespan on a SQLite file in a temp
directory, exactly as uvicorn boots it, including the claim-expiry
background task. It talks to the app through the in-process ASGI test
client, so the API numbers include FastAPI routing, the session middleware,
Pydantic validation and serialization, and exclude the network and HTTP
parsing. Each size gets its own server and database. Each path runs one
untimed warmup and then seven timed runs. The table reports the median and
the p95 of those seven, where the p95 by nearest rank is the slowest run.
Every run asserts the work it did (rows imported, items returned,
comparisons counted, records exported) and counts non-200 responses. The
profiles are one extra cProfile run per path, not counted in the timings.

```sh
uv run python benchmarks/bench_hot_paths.py --sizes 1000,10000 --runs 7 --profile \
    --paths ingest,agreement,benchmark,export --label baseline-1k-10k-clean
uv run python benchmarks/bench_hot_paths.py --sizes 1000,10000,100000 --runs 7 --profile \
    --paths query --skip query_queues@100000 --label baseline-query
uv run python benchmarks/bench_hot_paths.py --sizes 100000 --runs 7 --profile \
    --paths agreement,benchmark,export --label baseline-100k-rest
uv run python benchmarks/bench_hot_paths.py --sizes 100000 --runs 7 --profile \
    --paths ingest --no-seed --label baseline-100k-ingest
uv run python benchmarks/bench_hot_paths.py --sizes 1000000 --runs 3 --no-seed \
    --paths ingest,agreement,benchmark,export --max-run-seconds 600 --label baseline-1m
uv run python benchmarks/explain_query_plans.py --sizes 1000,3000
uv run python benchmarks/render_results.py benchmarks/results/baseline-*.json
```

The results, logs and profiles of those runs are in
[`benchmarks/results/`](../benchmarks/results/). The first pass,
`baseline-1k-10k.json`, seeded every size into one database and is kept
only for its log, which records the writer failure described under
[Queue listing](#queue-listing). Its database-backed numbers were taken
against the 10k tables and are superseded by `baseline-query.json`.

**Synthetic data.** Records are numbered sentences of random words. The
reviewed workspace holds, per record, three copies in one queue, two of them
submitted by two raters with one review event each and one still available,
plus one agent proposal bound to the copies. Labels are three categorical
fields with eight options. The second rater disagrees with the first on 20%
of field values and the agent on 10%, from a seeded generator. None of it is
gold data. Generated files and databases live in a temp directory.

**Sizes.** `n` is records in the dataset. The queue therefore holds `3n`
tasks and `2n` review events. 1M runs only the paths that do not need the
seeded reviewed database, with three timed runs instead of seven.

## Results

Median / p95 seconds of seven runs. "not run" means the path was left out at
that size, "error" that the server answered 500.

| path | n=1,000 | n=10,000 | n=100,000 |
|---|---:|---:|---:|
| ingest_api_jsonl | 0.146 / 0.159 | 1.597 / 2.176 | 13.444 / 14.024 |
| ingest_loader_jsonl | 0.005 / 0.005 | 0.092 / 0.126 | 0.897 / 1.010 |
| ingest_loader_csv | 0.005 / 0.005 | 0.099 / 0.111 | 0.923 / 1.010 |
| query_datasets | 0.002 / 0.002 | 0.002 / 0.002 | 0.002 / 0.002 |
| query_records | 0.003 / 0.004 | 0.009 / 0.009 | 0.070 / 0.089 |
| query_queues | 0.582 / 0.614 | 168.132 / 168.132 (1 run) | not run |
| query_queue_status | 0.003 / 0.003 | 0.005 / 0.006 | 0.033 / 0.037 |
| query_my_tasks | 0.069 / 0.085 | 2.786 / 2.989 | 29.427 / 29.799 |
| agreement_service_inter_annotator | 0.028 / 0.101 | 0.362 / 0.407 | 4.145 / 4.309 |
| agreement_service_human_agent | 0.168 / 0.186 | 1.549 / 1.577 | 17.623 / 18.038 |
| agreement_api | 0.235 / 0.287 | 2.663 / 2.731 | error (7/7 runs) |
| benchmark_clinc150 | 0.018 / 0.018 | 0.175 / 0.223 | 2.073 / 2.091 |
| benchmark_banking77 | 0.036 / 0.036 | 0.411 / 0.421 | 4.604 / 4.836 |
| export_orchestrator_jsonl | 0.008 / 0.008 | 0.070 / 0.073 | 0.838 / 0.883 |
| export_workflow_step | 0.090 / 0.105 | 1.015 / 1.029 | 10.050 / 10.281 |

The 100k ingest row is from `baseline-100k.log`, the first 100k pass, which
ran ingest before the agreement endpoint failed; the rerun in
`baseline-100k-ingest.json` replaces it when the table is regenerated.

What each path runs:

- `ingest_api_jsonl` is `POST /api/v1/datasets/{id}/import` with a
  `source_uri` in the workspace, the endpoint `molabel dataset import`
  calls, on a new dataset each run. `ingest_loader_jsonl` and
  `ingest_loader_csv` are the loader plugins' `load_records` consumed to a
  list. CSV has no API import path today, so its only number is the plugin.
- `query_datasets` is `GET /api/v1/datasets`, `query_records` is
  `GET /api/v1/datasets/{id}/records?limit=200`, `query_queues` is
  `GET /api/v1/queues`, `query_queue_status` is
  `GET /api/v1/queues/{id}/status`, and `query_my_tasks` is
  `GET /api/v1/queues/{id}/my-tasks?limit=500`, all as the first rater.
- `agreement_service_*` is `AgreementMetricsService.analyze` on records
  built in memory, one call per analysis type. `agreement_api` is
  `GET /api/v1/quality/agreement?queue_id=...`, which reads the review
  events and proposals from the database and runs both analyses.
- `benchmark_*` is `score_grounded_stage` with the metric config of the
  clinc150 (accuracy, binary recall, exact match over 150 intents) and
  banking77 (accuracy, macro F1, exact match over 77 intents) authority
  packs, on synthetic gold and predictions that agree 90% of the time.
- `export_orchestrator_jsonl` is `ExportOrchestrator.export` with the JSONL
  packager on in-memory records and labels, written to a temp directory.
  `export_workflow_step` is `ExportExecutor.execute` with the server's
  `_WorkflowExporter`, the service the workflow `export` step calls.

## What each number is

The limiter named for each path comes from its cProfile in
`benchmarks/results/profile-<path>-<n>.txt`, or from the SQLite plan in
`benchmarks/results/explain-query-plans-baseline.txt`. Profiled runs are
slower than timed runs because of profiler overhead, so shares are of the
profiled total.

### Ingest

The import endpoint costs 160 µs per record at 10k and 134 µs at 100k, and
is linear. In the 100k profile (20.9 s profiled), 100,010 `sqlite3` execute
calls take 5.6 s, and SQLAlchemy's per-statement work takes about 8.9 s more:
the endpoint builds a new `text()` INSERT for every row, so SQLAlchemy
re-parses the bind parameters (`re.Pattern.sub`, 100,013 calls, 4.85 s
cumulative), rebuilds the bind objects (1.2M `BindParameter` constructions)
and recomputes the cache key (1.23 s) per row. The rest is `json.dumps`,
`sha256` and `uuid4` per row. Disk is not the limiter. There is one commit
at the end, 0.68 s at 100k. The loaders cost 9 µs per record, which is
`json.loads` or `csv.DictReader` plus one Pydantic `Record` each, and need
nothing.

The work check holds. Every run imported exactly `n` records, with zero
parse errors and zero skipped.

### Querying

`query_datasets` lists at most 200 datasets and is constant. `query_records`
grows from 3 ms to 70 ms with `limit=200` because its `ORDER BY created_at
DESC` sorts every record of the dataset: there is no index on
`(dataset_id, created_at)`. `query_queue_status` is a covering-index count
and costs 33 ms over 300k tasks.

#### Queue listing

`GET /api/v1/queues` takes 0.58 s over 3k tasks and 168 s over 30k. Ten times
the tasks costs 289 times the time, and 100k was not run. In the profile,
166.4 of 166.4 s is one `sqlite3` execute call. The plan shows why:

```
SEARCH t USING INDEX idx_review_tasks_workspace_id (workspace_id=?)
USE TEMP B-TREE FOR GROUP BY
CORRELATED LIST SUBQUERY 1
  SEARCH m USING INDEX idx_review_tasks_queue_status (queue_id=? AND status=?)
USE TEMP B-TREE FOR count(DISTINCT)
```

`my_remaining` counts available records the reviewer has not touched, with
a `NOT IN (SELECT ... FROM review_tasks m WHERE m.queue_id = t.queue_id ...)`
subquery. The subquery is correlated on `t.queue_id`, so SQLite re-runs it
for every available task, and each run walks the queue's tasks of each
status again. The cost is the available tasks times the queue's tasks.

While the 168 s read held the database, the claim-expiry background task
could not commit: `benchmarks/results/baseline-1k-10k.log` records
`sqlite3.OperationalError: database is locked` from
`claims.py:987 expire_claims`. With the rollback journal, a reader blocks the
writer past its 5 s busy timeout. That is the concurrency half of #16.

#### My tasks

`GET /api/v1/queues/{id}/my-tasks` takes 0.069 s, 2.79 s and 29.4 s over
1k, 10k and 100k of the reviewer's own tasks. The 100k profile puts 29.46 of
29.47 s in `sqlite3` execute. The plan:

```
SEARCH t USING INDEX idx_review_tasks_queue_status (queue_id=? AND status=?)
CORRELATED SCALAR SUBQUERY 2
  SEARCH e USING INDEX idx_review_events_task_id (review_task_id=?)
  CORRELATED SCALAR SUBQUERY 1
  SCAN s
```

The decision column reads each task's counted event with `NOT EXISTS (SELECT
1 FROM review_events s WHERE s.supersedes_event_id = e.id)`. Nothing indexes
`supersedes_event_id`, so that is a full scan of `review_events` per event of
every candidate task, before the sort and the `LIMIT 500` apply. The cost is
the reviewer's tasks times the review events.

### Agreement

`AgreementMetricsService.analyze` costs 12 to 14 µs per comparison for
`inter_annotator` (0.36 s for 30k comparisons at 10k, 4.15 s for 300k at
100k) and 26 to 29 µs per comparison for `human_agent` (1.55 s for 60k,
17.6 s for 600k). Both are linear. The 10k `human_agent` profile (4.08 s
profiled) is per-unit Python overhead on two-element units: `_summarize` is
3.29 s cumulative, of which `Counter.update` (1.2M calls, 1.35 s) and
`Counter.__init__` (720k calls, 1.11 s) dominate, with 1.48M `isinstance`
checks behind them (`Counter` checks whether its input is a `Mapping` on
every construction). Each unit is tallied once in `_summarize` for the
agreement count, once in `_fleiss_kappa`, once in
`_krippendorff_alpha_nominal` and once more as a `dict` in `_cohen_kappa`,
and `human_agent` first materializes one two-element unit per human-agent
pair in `_compute_human_agent_breakdown` (0.75 s).

`GET /api/v1/quality/agreement` is 2.66 s at 10k. The two analyses account
for 1.91 s of it, and the remaining 0.75 s is the SQL, the `json.loads` of
every event's labels, and the Pydantic `AgreementAnnotation` per event
(141k constructions in the profile). At 100k the endpoint fails on every
run: `queue_agent_proposals` binds one SQL variable per bound agent output
in `id IN (...)`, and SQLite's limit is 32,766 variables, so a queue of more
than 32,766 records answers `too many SQL variables` as a 500. The log is
`benchmarks/results/baseline-100k.log`. This is a correctness bug at scale,
not a slowness.

### Benchmark scoring

clinc150 scoring costs 17.5 µs per record at 10k and 20.7 µs at 100k, linear,
spread over dict lookups, `canonical_label_value` (160k calls) and the
`json.dumps` the confusion and subset diagnostics do per value. It needs
nothing. banking77 costs 41 to 46 µs per record, and its 10k profile
(1.84 s profiled) puts 1.52 s in `_score_macro_f1`: for each of the 77
labels it loops over every record and canonicalizes the gold and the
predicted value again, 1.65M `canonical_label_value` calls for 10k records.
The cost is the labels times the records, and it would be 150 times the
records on a macro-F1 metric over clinc150's intents.

### Export

The orchestrator with the JSONL packager costs 7 to 8 µs per record (0.84 s
for 100k), which is `json.dumps` per row, one `sha256` over the output, the
validation re-parse and the atomic write. It needs nothing. The workflow
export step costs 100 µs per record (10.05 s for 100k) and is an N+1: the
exporter runs `SELECT ... FROM records WHERE id = :record_id` once per
record. The 10k profile (1.42 s profiled) has 10,000 `sqlite3` execute calls
at 0.48 s and SQLAlchemy's per-statement compile and cache-key work for
most of the rest.

## Candidates

Gains are guesses until the "measured" column is filled by a before/after
run of the same harness.

| path | top cost | candidate | kind | expected gain | measured |
|---|---|---|---|---|---|
| ingest_api_jsonl | one `text()` INSERT built and compiled per row | build the statement once and insert the rows with one `executemany` | ordinary | guess 2x to 3x on the endpoint | pending |
| query_records | sort of the whole dataset for `LIMIT 200` | index on `records(dataset_id, created_at)` | ordinary (migration) | guess 10x at 100k, from 70 ms | pending |
| query_queues | correlated `NOT IN` subquery re-run per available task | compute the reviewer's touched records once per queue and join them | ordinary (SQL rewrite) | guess 100x at 10k, and it stops being super-linear | pending |
| query_my_tasks | full scan of `review_events` per event, no index on `supersedes_event_id` | index on `review_events(supersedes_event_id)` | ordinary (migration) | guess 50x at 100k | pending |
| agreement_service_* | four tallies per unit, each a `Counter` on two or three values | tally each unit once and share the counts across the metrics | ordinary (algorithmic) | guess 3x to 5x on the service | pending |
| agreement_service_* | same | Polars or DuckDB group-by over a (record, field, rater, value) frame | new library | the endpoint's SQL, JSON and record building floor is 0.75 s of 2.66 s at 10k, so the end-to-end ceiling is 3.5x before the ordinary fix and below 3x after it | pending, expected rejection |
| agreement_api | `id IN (...)` over every bound agent output | join the proposals through the tasks' `agent_output_ids`, or chunk the ids | ordinary (bug fix) | from 500 to a number | pending |
| benchmark_banking77 | `_score_macro_f1` canonicalizes every record once per label | one pass that tallies true and false positives and negatives per label | ordinary (algorithmic) | guess 5x to 10x on banking77, none on clinc150 | pending |
| export_workflow_step | one SELECT per record | one `WHERE id IN (...)` per chunk of record ids | ordinary (N+1) | guess 5x to 10x | pending |
| any | | Rust or PyO3 hot loop | new language | no path has a hot loop left after the ordinary fixes above; the Python loops that remain (agreement, macro F1) are per-unit overhead that a one-pass rewrite removes | not proposed until a post-fix number says otherwise |

Arrow has no candidate: no path moves a columnar batch between libraries.
Polars and DuckDB have one candidate each at most, the agreement
computation, and its ceiling is set by the endpoint's non-analysis work.

## Phase 2: ordinary fixes

Filled in as each fix lands, with the before and after from the same
harness command.

## Phase 2: prototypes of faster libraries

Filled in with the measured end-to-end gain of each prototype, adopted or
rejected against the 3x bar.

## Phase 3: WAL and foreign keys (#16)

Filled in with `benchmarks/bench_wal_concurrency.py`'s reader latency and
writer throughput under the rollback journal and under WAL.

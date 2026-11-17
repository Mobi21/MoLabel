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
seeded reviewed database, with three timed runs instead of seven; seeding a
1M reviewed queue is 3M tasks and 2M events, which the query paths above
already show to be super-linear, so they stop at 100k.

## Results

Median / p95 seconds of seven runs, or of the number of runs in brackets.
"not run" means the path was left out at that size, "error" that the server
answered 500. The 1M column covers the paths that need no seeded reviewed
database. Two independent 1k and 10k baseline passes (`baseline-1k-10k.json`
and `baseline-1k-10k-clean.json`) put the run-to-run spread of a median at
5% to 20%, so a gain under 1.3x is inside the noise.

| path | n=1,000 | n=10,000 | n=100,000 | n=1,000,000 |
|---|---:|---:|---:|---:|
| ingest_api_jsonl | 0.146 / 0.159 | 1.597 / 2.176 | 13.353 / 14.080 | 135.541 / 138.668 (3 runs) |
| ingest_loader_jsonl | 0.005 / 0.005 | 0.092 / 0.126 | 0.919 / 0.944 | 8.864 / 9.369 (3 runs) |
| ingest_loader_csv | 0.005 / 0.005 | 0.099 / 0.111 | 0.896 / 1.014 | 9.288 / 9.314 (3 runs) |
| query_datasets | 0.002 / 0.002 | 0.002 / 0.002 | 0.002 / 0.002 | not run |
| query_records | 0.003 / 0.004 | 0.009 / 0.009 | 0.070 / 0.089 | not run |
| query_queues | 0.582 / 0.614 | 168.132 / 168.132 (1 run) | not run | not run |
| query_queue_status | 0.003 / 0.003 | 0.005 / 0.006 | 0.033 / 0.037 | not run |
| query_my_tasks | 0.069 / 0.085 | 2.786 / 2.989 | 29.427 / 29.799 | not run |
| agreement_service_inter_annotator | 0.028 / 0.101 | 0.362 / 0.407 | 4.145 / 4.309 | 41.407 / 45.392 (3 runs) |
| agreement_service_human_agent | 0.168 / 0.186 | 1.549 / 1.577 | 17.623 / 18.038 | 171.329 / 171.561 (3 runs) |
| agreement_api | 0.235 / 0.287 | 2.663 / 2.731 | error (7/7 runs) | not run |
| benchmark_clinc150 | 0.018 / 0.018 | 0.175 / 0.223 | 2.073 / 2.091 | 24.364 / 24.515 (3 runs) |
| benchmark_banking77 | 0.036 / 0.036 | 0.411 / 0.421 | 4.604 / 4.836 | 53.262 / 53.779 (3 runs) |
| export_orchestrator_jsonl | 0.008 / 0.008 | 0.070 / 0.073 | 0.838 / 0.883 | 9.204 / 9.316 (3 runs) |
| export_workflow_step | 0.090 / 0.105 | 1.015 / 1.029 | 10.050 / 10.281 | not run |

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

Each candidate was a guess until the "measured" column was filled by a
before/after run of the same harness command, in
[Phase 2](#phase-2-ordinary-fixes). Gains are ratios of medians.

| path | top cost | candidate | kind | expected gain | measured |
|---|---|---|---|---|---|
| ingest_api_jsonl | one `text()` INSERT built and compiled per row | build the statement once and insert the rows with one `executemany` | ordinary | guess 2x to 3x | 2.3x at 10k, 2.0x at 100k; adopted |
| query_records | sort of the whole dataset for `LIMIT 200` | index on `records(dataset_id, created_at)` | ordinary (migration) | guess 10x at 100k | 23x at 100k (70 ms to 3 ms); adopted |
| query_queues | correlated `NOT IN` subquery re-run per available task | compute the reviewer's touched records once per queue and join them | ordinary (SQL rewrite) | guess 100x at 10k | 9x at 10k, still quadratic, 48 min at 100k; rejected |
| query_queues | same | `NOT EXISTS` probe for the reviewer's copy of the record on a `(claimed_by, queue_id, record_id)` index | ordinary (SQL rewrite and migration) | linear | 116x at 1k, 2,200x at 10k, 1.2 s at 100k; adopted |
| query_my_tasks | full scan of `review_events` per event, no index on `supersedes_event_id` | index on `review_events(supersedes_event_id)` | ordinary (migration) | guess 50x at 100k | 55x at 10k, 57x at 100k; adopted |
| agreement_service_* | four tallies per unit, each a `Counter` on two or three values, and the human-agent units summarized twice | tally each unit once and share the counts; reuse the human-agent summaries as the overall ones | ordinary (algorithmic) | guess 3x to 5x | 2.4x on human_agent, 1.5x to 1.7x on inter_annotator, 1.7x on the endpoint at 10k; adopted |
| agreement_service_* | same | Polars or DuckDB group-by over a (record, field, rater, value) frame | new library | end-to-end ceiling 3.5x before the ordinary fix | ceiling 2.0x after it, from the endpoint's own floor; rejected without a prototype |
| agreement_api | `id IN (...)` over every bound agent output | read the ids 500 at a time | ordinary (bug fix) | from 500 to a number | 100k answers in 20.3 s instead of failing; adopted |
| benchmark_banking77 | `_score_macro_f1` canonicalizes every record once per label | one pass that tallies true and false positives and negatives per label | ordinary (algorithmic) | guess 5x to 10x | 3.6x at 10k, 3.3x at 100k; adopted |
| export_workflow_step | one SELECT per record | one `WHERE id IN (...)` per chunk of record ids | ordinary (N+1) | guess 5x to 10x | 8.7x at 10k, 7.7x at 100k; adopted |
| ingest_api_jsonl | after the fix, SQLite's own insert | Rust or PyO3 for the per-row hashing and serialization | new language | | SQLite's `executemany` is 52% of the profiled endpoint, so the Python half caps a hot loop at 2.1x; rejected |
| any other | | Rust, Polars, DuckDB or Arrow | new library or language | | no path left with a Python hot loop at a user wait; not proposed |

## Phase 2: ordinary fixes

Each fix is one commit on `p7/performance`, measured with the same harness
commands as the baseline, after the full test suite passed on the fixed
tree. "Before" is the baseline table above; "after" is
`benchmarks/results/fixed-*.json`, median of seven runs, same machine.

```sh
uv run python benchmarks/bench_hot_paths.py --sizes 1000,10000 --runs 7 \
    --paths ingest,agreement,benchmark,export --label fixed-1k-10k
uv run python benchmarks/bench_hot_paths.py --sizes 1000,10000,100000 --runs 7 \
    --paths query --label fixed-query
uv run python benchmarks/bench_hot_paths.py --sizes 100000 --runs 7 \
    --paths agreement,benchmark,export --label fixed-100k-rest
uv run python benchmarks/bench_hot_paths.py --sizes 100000 --runs 7 \
    --paths ingest --no-seed --label fixed-100k-ingest
uv run python benchmarks/bench_hot_paths.py --sizes 10000,100000 --runs 7 \
    --paths agreement --label fixed-agreement
uv run python benchmarks/explain_query_plans.py --sizes 1000,3000,10000
```

| fix | path | n | before | after | gain |
|---|---|---:|---:|---:|---:|
| one `executemany` per import | ingest_api_jsonl | 10k | 1.597 s | 0.701 s | 2.3x |
| | | 100k | 13.35 s | 6.68 s | 2.0x |
| chunked record reads in the export step | export_workflow_step | 10k | 1.015 s | 0.116 s | 8.7x |
| | | 100k | 10.05 s | 1.31 s | 7.7x |
| chunked proposal reads | agreement_api | 100k | 500 on every run | 20.3 s | works |
| indexed probe in the queue listing | query_queues | 1k | 0.582 s | 0.005 s | 116x |
| | | 10k | 168.1 s | 0.076 s | 2,200x |
| | | 100k | not run | 1.20 s | |
| index on `supersedes_event_id` | query_my_tasks | 10k | 2.786 s | 0.051 s | 55x |
| | | 100k | 29.43 s | 0.512 s | 57x |
| index on `(dataset_id, created_at)` | query_records | 100k | 0.070 s | 0.003 s | 23x |
| one tally per unit, no duplicate summaries | agreement_service_human_agent | 10k | 1.549 s | 0.645 s | 2.4x |
| | | 100k | 17.62 s | 7.33 s | 2.4x |
| | agreement_service_inter_annotator | 10k | 0.362 s | 0.213 s | 1.7x |
| | | 100k | 4.145 s | 2.81 s | 1.5x |
| | agreement_api | 10k | 2.663 s | 1.602 s | 1.7x |
| one-pass macro F1 | benchmark_banking77 | 10k | 0.411 s | 0.115 s | 3.6x |
| | | 100k | 4.604 s | 1.383 s | 3.3x |

Every after-fix run did the same work as before: the same record, item,
comparison and export counts, with zero errors. The unchanged paths moved
inside the noise floor (clinc150 2.07 s to 2.05 s at 100k, the export
orchestrator 0.84 s to 0.85 s), except the loaders at 10k, which read 47%
slower in the first after-fix pass while a formatter ran beside it, and
back to 0.88 s to 0.91 s at 100k with the machine idle. Treat any gain
under 1.3x as unproven.

What bounds each path now:

- **Ingest.** The 100k profile after the fix (`profile-ingest_api_jsonl-100000.txt`,
  6.6 s profiled) has SQLite's own `executemany` at 3.46 s, which is the
  primary key and seven index B-trees taking 100k random UUID keys, then
  `json.dumps` at 1.0 s over 400k calls, bind construction at 0.4 s and
  `uuid4` at 0.3 s. Into an empty database the endpoint takes 4.0 s; the
  6.68 s median is eight imports into one growing database. The
  remaining lever is the index count on `records`, not the language.
- **Queue listing.** 1.2 s over 300k tasks is the `GROUP BY` with a
  `COUNT(DISTINCT)` temp B-tree over every task of the workspace, once.
  The plan in `explain-query-plans-fixed.txt` shows the probe on
  `idx_review_tasks_claimed_by_queue_record`. The listing is linear now;
  a per-queue summary table would make it constant, and nothing asks for
  that yet.
- **My tasks.** 0.51 s at 100k is the sort of the reviewer's 100k tasks by
  `submitted_at` before the `LIMIT 500`. An index on
  `(claimed_by, queue_id, status, submitted_at)` would remove it.
- **Agreement.** The endpoint's 20.3 s at 100k is the two analyses at
  2.8 s and 7.3 s plus a 10.2 s floor: the SQL fetch (2.9 s of 40.7 s
  profiled), `json.loads` of 300k label columns, 1.4M Pydantic
  `AgreementAnnotation` constructions and the per-field breakdown's
  Pydantic attribute writes (3.5M `__setattr__` calls). Inside the
  analyses, `_tally` over 3M units and `_cohen_kappa` are what is left.
- **Benchmark scoring.** 14 µs per record for banking77 and 21 µs for
  clinc150, in dict lookups, `canonical_label_value` and the `json.dumps`
  the diagnostics do per value.

The rejected first rewrite of the queue listing is worth keeping on record.
A `WITH mine AS (SELECT DISTINCT queue_id, record_id ...)` materialized the
reviewer's records once, but SQLite joined it with `SCAN mine` per task:
9x faster at 10k, still quadratic, and 48 minutes at 100k. The plan, not
the row count, decides.

Two tests pin behavior the fixes could have broken:
`tests/unit/test_workflow_export_chunks.py` exports 1,203 records across
three id chunks in the step's order and skips an unknown id, and
`tests/unit/test_review_events_proposals.py` reads 33,000 proposals, more
than SQLite binds at once. `tests/unit/test_grounded_macro_f1.py` checks
macro F1 against a worked example and the per-label definition, and the
agreement rewrite is held to the published reference values in
`tests/unit/test_agreement_reference_values.py`.

## Phase 2: prototypes of faster libraries

Nothing was adopted, and no prototype was built, because the arithmetic
on the measured floors rules every candidate out before a prototype could
reach 3x end to end. No optional extra, no Rust toolchain and no build
step were added.

- **Agreement with Polars or DuckDB: rejected.** The analyses are 10.1 s
  of the endpoint's 20.3 s at 100k. An analysis that cost nothing would
  make the endpoint 2.0x faster, under the bar, and the same floor holds
  for the workflow's `agreement_analysis` step, which loads its records
  through the same SQL and JSON. The floor is the fetch, the JSON decode
  and the Pydantic records, which a columnar library does not touch. A
  Polars group-by would still be the right tool if the floor were
  removed first, and that is ordinary Python work.
- **Ingest with a Rust hot loop: rejected.** SQLite's `executemany` is
  52% of the profiled endpoint. A hot loop that did the hashing, JSON and
  bind construction for free would make the import 2.1x faster.
- **Benchmark scoring with Polars: not pursued.** The scorers run at 14
  to 21 µs per record after the macro-F1 fix. The committed fixtures
  score a few thousand records, which is tens of milliseconds, and the
  100k synthetic run is 1.4 s to 2.1 s with nobody waiting on it.
- **Export: nothing to do.** 8 µs per record in the orchestrator, 13 µs
  in the workflow step.
- **Arrow: no path moves a columnar batch between libraries.**

## Phase 3: WAL and foreign keys (#16)

The server built its own engine in `molabel.app.main` and never set the two
pragmas that `molabel.core.database.get_engine` set for everyone else. Every
engine now comes from one factory, `molabel.core.database.engine_from_url`,
which sets `journal_mode=WAL` and `foreign_keys=ON` on every connection it
hands out: the server's lifespan, `get_engine` for file paths, the e2e test
client that mirrors the server, and the integration tests that migrate their
own databases. The data directory, `MOLABEL_DB_URL`, the migration lock and
Alembic-only schema changes from P2 are unchanged.

**What foreign keys change.** SQLite checks a foreign key when a row is
written, so enforcement refuses new dangling rows and leaves old ones in
place. The API answers such a refusal with `409 CONFLICT` and the database's
message ("FOREIGN KEY constraint failed") instead of a 500; before #16 the
same request silently wrote the orphan. Alembic's batch mode copies and
drops tables, which other tables' foreign keys would refuse, so
`upgrade_database` turns the pragma off on the migration's connection,
outside the transaction where the pragma takes effect, and back on after.

**Orphans in existing data.** `foreign_key_violations(engine)` wraps
`PRAGMA foreign_key_check` and counts dangling rows per table and parent.
It runs once after a migration, logged as a warning, and on every
`GET /api/v1/cli/status`, which `molabel status` prints whole and
`molabel doctor` shows under `database.foreign_key_violations`. Dangling
rows are reported and never deleted: a review event whose task is gone is
still a reviewer's decision, and only a person can say what it means. The
two legacy fixtures in `fixtures/migrations/` hold schema and no rows, so
they report none after upgrade, and this machine has no server database in
its data directory to check. On a synthetic 100k reviewed database the
check costs 2.5 s over 700k rows in a 582 MB file, median of 5 runs
(`benchmarks/results/fk-check-100k.txt`, from
`uv run python benchmarks/bench_fk_check.py --size 100000`), which is
why it runs on demand and after a migration, not on every start.

```sh
uv run python - <<'EOF'
import sqlite3, tempfile
from pathlib import Path
from molabel.core.database import foreign_key_violations, get_engine
from molabel.core.migration_runner import upgrade_database
db = Path(tempfile.mkdtemp()) / "legacy.db"
with sqlite3.connect(db) as conn:
    for name in ("pre-alembic-create-all.sql", "pre-alembic-audit-events.sql"):
        conn.executescript(Path("fixtures/migrations", name).read_text())
engine = get_engine(db)
upgrade_database(engine)
print(foreign_key_violations(engine))
EOF
```

**What enforcement found in the test suite.** With every test engine on the
factory, 45 tests failed, and none of them was a server route writing an
orphan on its own:

- 21 e2e tests created reviewer profiles in a shared workspace id that no
  test ever created; the e2e client now seeds that workspace, which is what
  the suite's `SHARED_WORKSPACE` marker always described.
- Two integration fixtures inserted a workflow execution for a made-up
  definition id; the fixture now inserts the definition.
- One e2e test saved a label mapping against a task schema id that was
  not a UUID; it now seeds a schema.
- One migration test expects a refused database to keep only its own file;
  the lifespan now disposes the engine when the upgrade raises, so SQLite
  removes the WAL and shared-memory files it opened. The refused file's
  header is switched to WAL mode by the connect pragma, and its tables and
  rows are untouched.
- Five integration tests write a dataset through the SQLModel ORM and
  reference a workspace written by a route. They are marked expected
  failures, because they found a split that is not P7's to fix: the ORM
  stores UUIDs as 32-character hex (`sa.Uuid` on SQLite) while every route
  stores them as 36-character hyphenated strings, so the two never match,
  neither in a foreign key nor in `session.get`. Only one production route
  uses the ORM (`restore_snapshot`), and it only updates rows, so no route
  breaks today. Unifying the storage format needs a decision and a data
  migration.

**Concurrency.** The baseline runs showed the cost of the rollback journal:
while a 168 s queue listing held the database, the claim-expiry background
task failed to commit with `database is locked`
(`benchmarks/results/baseline-1k-10k.log`). With WAL, readers never block
the writer. `benchmarks/bench_wal_concurrency.py` runs one writer thread
submitting 300 reviews, each in its own transaction the way `submit_review`
writes them, against four reader threads reading the queue status and the
writer's task list through the services the endpoints call, on a 10k
reviewed workspace, three rounds per journal mode, alternating sides.

```sh
uv run python benchmarks/bench_wal_concurrency.py
```

Three rounds per side, alternating (`benchmarks/results/wal-concurrency.json`):

| journal mode | writer, writes/s (median of rounds) | reader median | reader p95 | errors |
|---|---:|---:|---:|---:|
| DELETE (before #16) | 143 | 117 ms | 271 ms | 0 |
| WAL (after #16) | 736 | 60 ms | 115 ms | 0 |

The writer's 300 submits took 2.0 s to 2.5 s under the rollback journal and
0.40 s to 0.41 s under WAL, a 5.2x gain in throughput, because each commit
no longer waits for the readers' shared locks to clear. The readers' median
fell from 117 ms to 60 ms and their p95 from 271 ms to 115 ms, because they
no longer queue behind the writer's exclusive lock. Neither side saw an
error or a `database is locked`. The reader counts differ per round only
because the readers run until the writer finishes.

**Tests.** `tests/unit/test_database_engine.py` starts the server on a file
and asserts a fresh pooled connection reports `wal` and `foreign_keys = 1`,
that a review event whose keys point nowhere is refused with
`IntegrityError`, that a write to a missing workspace through the API
answers 409, that an in-memory URL shares one connection with foreign keys
on, and that rows written before enforcement are counted by
`foreign_key_violations` and kept. `tests/integration/test_cli_status_integrity.py`
asserts `GET /api/v1/cli/status` lists them per table and parent, and
`cli/tests/doctor.test.ts` that `molabel doctor` prints them.

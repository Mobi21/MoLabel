# MoLabel E2E Test Suite

143 scenarios across 9 tiers covering every API endpoint, workflow step type, data format, and resilience case in the MoLabel labeling workbench.

## Prerequisites

- Python 3.12+ via `uv`
- All workspace packages installed: `uv sync`
- Optional: `MINIMAX_API_KEY` for real LLM tests

## Quick Start

```bash
# Run the full suite (parallel, mocked LLM)
uv run pytest tests/e2e/ -n 4 --dist loadgroup -v

# Run with the CLI runner
uv run python -m tests.e2e

# Skip tests that need a real LLM key
uv run python -m tests.e2e --skip-real-llm
```

## Running Subsets

### By tier

```bash
# Single tier
uv run pytest tests/e2e/tier1_pipeline/ -v
uv run python -m tests.e2e --tier 2

# Tiers 1–9:
# 1  Full Pipeline          (6 data types, real smoke test)
# 2  Complex Workflows      (loops, conditionals, gates, breakpoints)
# 3  API Coverage           (every router domain, contract tests)
# 4  Queue & Review         (claims, ordering, adjudication, drafts)
# 5  Agent & LLM            (roles, confidence, provider health)
# 6  Quality Metrics        (agreement, delta analysis, readiness)
# 7  Data Management        (import/export, snapshots, label mapping)
# 8  Resilience             (malformed input, timeouts, concurrency)
# 9  Cross-Cutting          (auth, audit trail, SSE, cost tracking)
```

### By scenario ID

```bash
uv run pytest tests/e2e/ -k "T2-20" -v
uv run python -m tests.e2e --scenario T2-20
```

### By marker

```bash
# Only real LLM tests
uv run pytest tests/e2e/ -m real_llm -v

# Everything except real LLM
uv run pytest tests/e2e/ -m "not real_llm" -n 4 --dist loadgroup -v

# Combine markers
uv run python -m tests.e2e --tags tier1 tier3
```

## Real LLM Tests

A small subset of tests (`@pytest.mark.real_llm`) make actual API calls to verify the provider integration end-to-end. All others use pre-recorded VCR cassettes.

```bash
export MINIMAX_API_KEY=sk-...
uv run pytest tests/e2e/ -m real_llm -v
```

### Recording new cassettes

When you need to refresh cassettes after changing a prompt or model:

```bash
export MINIMAX_API_KEY=sk-...
export E2E_RECORD_CASSETTES=1
uv run pytest tests/e2e/ -m real_llm -v

# or via CLI
uv run python -m tests.e2e --record-cassettes --api-key sk-...
```

Cassettes are stored as JSON under `tests/e2e/fixtures/cassettes/` and committed to the repo. Each file is named after the scenario ID (e.g. `T1-01.json`).

## Parallel Execution

Tests are grouped into three xdist groups:

| Group | Marker | Tests |
|---|---|---|
| `independent` | `@INDEPENDENT` | Tier 1, 2, 7, 8 — own in-memory DB each |
| `shared_workspace` | `@SHARED_WORKSPACE` | Tier 3, 5, 6 — read-only shared fixtures |
| `sequential` | `@SEQUENTIAL` | Tier 4, some Tier 9 — concurrent/SSE semantics |

The default `-n 4 --dist loadgroup` flag respects these groups automatically.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `MINIMAX_API_KEY` | — | API key for real LLM calls |
| `E2E_RECORD_CASSETTES` | `0` | Set to `1` to record new cassettes |
| `MOLABEL_DB_URL` | `sqlite+aiosqlite://` | DB URL injected per test (in-memory) |

## Reports & Logs

After each run, reports are written to `tests/e2e/logs/`:

```
tests/e2e/logs/
  e2e_<run_id>.log       JSONL structured log (one entry per event)
  report_<run_id>.json   Machine-readable summary
  report_<run_id>.md     Markdown summary with pass/fail per tier
```

The Markdown report includes per-tier pass rates, total duration, and API call counts.

## Directory Layout

```
tests/e2e/
  conftest.py                  Session + per-test fixtures, pytest hooks
  __main__.py                  CLI entry point
  infrastructure/
    client.py                  InstrumentedClient (httpx ASGI, no network)
    cassettes.py               CassetteManager (record/replay LLM calls)
    hooks.py                   E2EHook protocol + LoggingHook
    runner.py                  E2ERunner programmatic API
    assertions.py              checkpoint() context manager
    factories.py               Data factories for all 6 data types
    logging_config.py          JSONFormatter, TestContext, setup_logging
    reporter.py                E2EReporter (JSON + Markdown output)
    parallel.py                INDEPENDENT / SHARED_WORKSPACE / SEQUENTIAL
  fixtures/
    text_classification/       50 product reviews (JSONL)
    multi_label/               40 news articles (JSONL)
    ner/                       30 NER sentences (JSONL)
    content_moderation/        45 user comments (JSONL)
    pairwise_comparison/       35 response pairs (JSONL)
    structured_extraction/     25 invoice texts (JSONL)
    schemas/                   6 task schema JSON files
    workflows/                 23 workflow YAML files
    cassettes/                 Pre-recorded LLM responses (JSON)
  tier1_pipeline/              Full pipeline smoke tests
  tier2_workflows/             Workflow step type coverage
  tier3_api_coverage/          API contract tests (all 26 routers)
  tier4_queue_review/          Queue & review flow tests
  tier5_agent_llm/             Agent roles & LLM integration
  tier6_quality/               Quality metrics & agreement
  tier7_data_management/       Import / export / snapshots
  tier8_resilience/            Edge cases & failure modes
  tier9_cross_cutting/         Auth, audit, SSE, costs
  logs/                        Generated reports (gitignored)
```

## Writing New Tests

Each test file follows this pattern:

```python
import pytest
from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.parallel import INDEPENDENT

@INDEPENDENT
@pytest.mark.tier1
@pytest.mark.asyncio
async def test_my_scenario(client, ctx):
    async with checkpoint(ctx, "setup"):
        resp = await client.post("/api/v1/workspaces", json={"name": "test"})
        assert resp.status_code == 201

    async with checkpoint(ctx, "verify"):
        resp = await client.get("/api/v1/workspaces")
        assert resp.status_code == 200
```

- `client` — `InstrumentedClient` backed by a fresh in-memory SQLite DB
- `ctx` — `TestContext` that records all API calls and checkpoint results
- `checkpoint()` — labels assertion phases; failures are reported per-phase
- Use `cassette` fixture for tests that call LLM adapters directly

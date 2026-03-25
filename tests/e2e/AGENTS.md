# AGENTS.md — E2E Test Suite Agent Guide

Instructions for AI agents driving the MoLabel E2E test pipeline.

## Running the Suite

The `E2ERunner` class is the programmatic entry point. It wraps pytest and exposes async methods.

```python
import asyncio
from pathlib import Path
from tests.e2e.infrastructure.runner import E2ERunner
from tests.e2e.infrastructure.hooks import LoggingHook
from tests.e2e.infrastructure.logging_config import setup_logging

async def run():
    runner = E2ERunner(api_key="sk-...")
    logger = setup_logging(runner.reporter.run_id)
    runner.hooks = [LoggingHook(logger)]

    # Run everything (parallel by default)
    report = await runner.run_all()

    # Or a single tier
    report = await runner.run_tier(2)

    # Or a single scenario
    report = await runner.run_scenario("T2-20")

    # Or by marker tags
    report = await runner.run_tags(["real_llm"])

    runner.write_report(Path("tests/e2e/logs"))
    print(report)

asyncio.run(run())
```

### CLI alternative

```bash
# Full suite
uv run python -m tests.e2e

# Specific tier
uv run python -m tests.e2e --tier 2

# Specific scenario
uv run python -m tests.e2e --scenario T2-20

# Skip real LLM
uv run python -m tests.e2e --skip-real-llm

# Record cassettes
uv run python -m tests.e2e --record-cassettes --api-key sk-...
```

## Hook Protocol

Implement `E2EHook` to receive structured lifecycle events:

```python
from typing import Any
from tests.e2e.infrastructure.hooks import E2EHook

class MyHook:
    async def on_run_start(self, run_id: str, total_tests: int) -> None: ...
    async def on_tier_start(self, tier: int, test_count: int) -> None: ...
    async def on_test_start(self, test_id: str, name: str) -> None: ...
    async def on_checkpoint(self, test_id: str, checkpoint: str, passed: bool) -> None: ...
    async def on_test_end(self, test_id: str, passed: bool, summary: dict[str, Any]) -> None: ...
    async def on_tier_end(self, tier: int, passed: int, failed: int) -> None: ...
    async def on_run_end(self, report: dict[str, Any]) -> None: ...
    async def on_failure(self, test_id: str, error: str, context: dict[str, Any]) -> None: ...
```

Register hooks with `E2ERunner(hooks=[MyHook()])`.

`on_test_end` receives a `summary` dict with:
- `total_duration_ms` — wall-clock time for the test
- `api_calls` — number of API calls logged
- `checkpoints` — list of `{name, passed, duration_ms}` dicts
- `errors` — list of error strings if any

## Reading Reports

Reports are written to `tests/e2e/logs/` after each run.

### JSON report

```jsonc
{
  "run_id": "20260325_143022_a1b2c3",
  "total_tests": 143,
  "passed": 141,
  "failed": 2,
  "total_duration_ms": 42300,
  "tiers": {
    "1": {"passed": 6, "failed": 0},
    "2": {"passed": 23, "failed": 1}
    // ...
  },
  "tests": [
    {
      "test_id": "T1-01",
      "tier": 1,
      "passed": true,
      "duration_ms": 812,
      "api_calls": 7,
      "checkpoints": [
        {"name": "workspace_created", "passed": true, "duration_ms": 120},
        {"name": "labels_ingested",   "passed": true, "duration_ms": 340}
      ]
    }
  ]
}
```

### Structured log (JSONL)

Each line in `e2e_<run_id>.log` is a JSON event:

```jsonc
{"ts": 1711370422.1, "level": "INFO", "event": "test_start",  "test_id": "T1-01", "name": "test_text_classification"}
{"ts": 1711370422.9, "level": "INFO", "event": "checkpoint",  "test_id": "T1-01", "checkpoint": "workspace_created", "passed": true}
{"ts": 1711370423.7, "level": "INFO", "event": "api_call",    "test_id": "T1-01", "method": "POST", "path": "/api/v1/workspaces", "status": 201, "duration_ms": 45.2}
{"ts": 1711370424.5, "level": "INFO", "event": "test_end",    "test_id": "T1-01", "passed": true,  "duration_ms": 812}
```

## Recording Cassettes

Real LLM calls (`@pytest.mark.real_llm`) are recorded once and replayed in CI.

```bash
# Set env vars
export MINIMAX_API_KEY=sk-...
export E2E_RECORD_CASSETTES=1

# Record all real_llm tests
uv run pytest tests/e2e/ -m real_llm -v

# Record a single scenario
uv run pytest tests/e2e/ -k "T1-01" -v
```

Cassette files land in `tests/e2e/fixtures/cassettes/<scenario_id>.json`. Commit them so CI can replay without a key.

To verify a cassette replays correctly (no key needed):

```bash
uv run pytest tests/e2e/ -k "T1-01" -v   # E2E_RECORD_CASSETTES unset → replay mode
```

## Scenario IDs

Every test is tagged with a scenario ID in the format `T<tier>-<number>`. Use these to target specific tests:

```bash
uv run pytest tests/e2e/ -k "T3-05" -v
uv run python -m tests.e2e --scenario T3-05
```

Tier map:
- T1-xx: Full pipeline (text classification, multi-label, NER, content moderation, pairwise, structured extraction, real LLM smoke)
- T2-xx: Workflow step types (loops, conditionals, gates, breakpoints, parallel, compositions, error recovery, lifecycle)
- T3-xx: API contract coverage (all 26 router domains)
- T4-xx: Queue & review (claim expiry, concurrency, ordering, adjudication, drafts, overlap, calibration)
- T5-xx: Agent & LLM (roles, confidence, provider health, batch partial failure)
- T6-xx: Quality metrics (agreement, delta analysis, validation runs, readiness, throughput)
- T7-xx: Data management (import/export for all formats, snapshots, label mapping, dataset operations)
- T8-xx: Resilience (malformed input, unicode, long text, empty dataset, duplicate records, nested JSON, concurrent ops, partial labels, rollback, invalid YAML, session expiry, provider timeouts, empty filter)
- T9-xx: Cross-cutting (audit trail, cost tracking, SSE events, auth/session, RBAC)

## Parallel Execution Model

Tests run in three xdist groups. The default `-n 4 --dist loadgroup` flag respects them:

- `independent` — Tier 1, 2, 7, 8: fully parallel (own in-memory DB per test)
- `shared_workspace` — Tier 3, 5, 6: parallel with shared read-only fixtures
- `sequential` — Tier 4, Tier 9 concurrency/SSE: must run in order

When running a subset that mixes groups, xdist handles scheduling automatically.

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `MINIMAX_API_KEY` | For real LLM tests | API key passed to the MiniMax provider adapter |
| `E2E_RECORD_CASSETTES` | No (default `0`) | Set to `1` to record new cassettes instead of replaying |
| `MOLABEL_DB_URL` | No | Overridden per test to `sqlite+aiosqlite://` (in-memory) |

## Interpreting Failures

1. Check the checkpoint that failed — each `async with checkpoint(ctx, "name"):` block reports independently.
2. Read the JSONL log for the sequence of API calls leading to the failure.
3. Look at `--tb=short` output for the Python traceback.
4. If the failure is in a real LLM test, re-record the cassette or check the provider key.
5. If the failure is in a resilience test (Tier 8), the test may be asserting that an error response is returned — check whether the API now returns a different error code.

## Adding New Scenarios

1. Pick the correct tier directory.
2. Create `test_<feature>.py` following the pattern in existing files.
3. Mark the test with `@INDEPENDENT`, `@SHARED_WORKSPACE`, or `@SEQUENTIAL` and the appropriate `@pytest.mark.tierN`.
4. Add a scenario ID comment: `# T8-15`.
5. Use `async with checkpoint(ctx, "phase_name"):` to label assertion phases.
6. If the test calls LLM adapters, add `@pytest.mark.real_llm` and wire up the `cassette` fixture.

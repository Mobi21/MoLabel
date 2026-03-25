# MoLabel E2E Test Suite Design

**Date**: 2026-03-25
**Status**: Approved
**Phase**: 6 — End-to-End Testing

## 1. Goals

Build a comprehensive end-to-end test suite that:

1. Tests every API endpoint, workflow step type, and data model in the system
2. Covers 6 distinct data types requiring different labeling approaches
3. Exercises complex workflow compositions (loops, conditionals, parallel, gates, breakpoints)
4. Validates resilience under failure conditions (timeouts, malformed data, concurrency)
5. Provides full logging and observability for every test run
6. Runs tests in parallel where independent for speed
7. Works as an agent-drivable pipeline via skills and hooks

## 2. Architecture

### 2.1 Test Infrastructure

```
tests/e2e/
├── conftest.py                    # Shared fixtures, logging setup, parallel config
├── infrastructure/
│   ├── __init__.py
│   ├── client.py                  # Async test client (httpx ASGI transport)
│   ├── cassettes.py               # VCR cassette manager (record/replay LLM calls)
│   ├── factories.py               # Data factories for all 6 data types
│   ├── assertions.py              # Reusable checkpoint assertion helpers
│   ├── logging_config.py          # Structured logging setup (JSON + human-readable)
│   ├── reporter.py                # Test run reporter (summary, timing, failures)
│   ├── hooks.py                   # Pre/post test hooks for agent integration
│   └── parallel.py                # Parallel execution helpers and group markers
├── fixtures/
│   ├── text_classification/       # 50 product reviews (JSONL)
│   ├── multi_label/               # 40 news articles (JSONL)
│   ├── ner/                       # 30 annotated sentences (JSONL)
│   ├── content_moderation/        # 45 user comments (JSONL)
│   ├── pairwise_comparison/       # 35 response pairs (JSONL)
│   ├── structured_extraction/     # 25 invoice texts (JSONL)
│   ├── workflows/                 # YAML workflow definitions for Tier 2
│   ├── schemas/                   # Task schema definitions per data type
│   └── cassettes/                 # Recorded LLM responses (VCR cassettes)
├── tier1_pipeline/                # Full pipeline per data type (7 tests)
│   ├── test_text_classification.py
│   ├── test_multi_label.py
│   ├── test_ner.py
│   ├── test_content_moderation.py
│   ├── test_pairwise_comparison.py
│   ├── test_structured_extraction.py
│   └── test_real_llm_smoke.py
├── tier2_workflows/               # Complex workflow scenarios (33 tests)
│   ├── test_loops.py              # 5 loop variants
│   ├── test_conditionals.py       # 4 conditional variants
│   ├── test_parallel.py           # 4 parallel variants
│   ├── test_gates.py              # 3 gate variants
│   ├── test_breakpoints.py        # 3 breakpoint variants
│   ├── test_compositions.py       # 4 multi-step compositions
│   ├── test_lifecycle.py          # 3 pause/resume/cancel
│   ├── test_error_recovery.py     # 3 failure/retry scenarios
│   ├── test_templates.py          # 2 built-in template end-to-end
│   ├── test_feedback_loop.py      # 1 full agent feedback cycle
│   └── test_human_triage.py      # 1 human triage step
├── tier3_api_coverage/            # Every API endpoint (28 tests)
│   ├── test_workspaces_api.py
│   ├── test_datasets_api.py
│   ├── test_task_schemas_api.py
│   ├── test_workflows_api.py
│   ├── test_agent_runs_api.py
│   ├── test_queue_review_api.py
│   ├── test_adjudication_api.py
│   ├── test_quality_api.py
│   ├── test_exports_api.py
│   ├── test_releases_api.py
│   ├── test_prompts_api.py
│   ├── test_corrections_api.py
│   ├── test_providers_api.py
│   ├── test_model_profiles_api.py
│   ├── test_runtime_profiles_api.py
│   ├── test_reviewer_profiles_api.py
│   ├── test_sessions_api.py
│   ├── test_label_mappings_api.py
│   ├── test_costs_api.py
│   ├── test_audit_api.py
│   ├── test_plugins_api.py
│   ├── test_assistant_api.py
│   ├── test_events_sse_api.py
│   └── test_review_events_api.py
├── tier4_queue_review/            # Queue & review scenarios (15 tests)
│   ├── test_blind_review.py
│   ├── test_ai_reveal.py
│   ├── test_drafts.py
│   ├── test_claim_expiry.py
│   ├── test_concurrent_claims.py
│   ├── test_overlap_records.py
│   ├── test_calibration.py
│   ├── test_adjudication_flow.py
│   ├── test_ordering_strategies.py
│   └── test_review_decisions.py
├── tier5_agent_llm/               # Agent & LLM scenarios (10 tests)
│   ├── test_validation.py
│   ├── test_comparison_runs.py
│   ├── test_confidence_scoring.py
│   ├── test_cost_tracking.py
│   ├── test_provider_health.py
│   ├── test_batch_partial_failure.py
│   └── test_agent_roles.py
├── tier6_quality/                 # Quality & analytics (10 tests)
│   ├── test_agreement_metrics.py
│   ├── test_drift_detection.py
│   ├── test_distribution.py
│   ├── test_throughput.py
│   ├── test_calibration_analysis.py
│   ├── test_validation_runs.py
│   ├── test_delta_analysis.py
│   └── test_readiness.py
├── tier7_data_management/         # Data management (15 tests)
│   ├── test_import_csv.py
│   ├── test_import_json.py
│   ├── test_import_jsonl.py
│   ├── test_import_parquet.py
│   ├── test_import_markdown.py
│   ├── test_import_yaml.py
│   ├── test_export_csv.py
│   ├── test_export_parquet.py
│   ├── test_export_jsonl.py
│   ├── test_export_huggingface.py
│   ├── test_label_mapping.py
│   ├── test_prelabel_trust.py
│   ├── test_snapshots.py
│   ├── test_dataset_operations.py
│   └── test_large_dataset.py
├── tier8_resilience/              # Resilience & edge cases (13 tests)
│   ├── test_malformed_input.py
│   ├── test_invalid_workflow_yaml.py
│   ├── test_provider_timeouts.py
│   ├── test_concurrent_operations.py
│   ├── test_session_expiry.py
│   ├── test_duplicate_records.py
│   ├── test_empty_dataset.py
│   ├── test_empty_filter.py
│   ├── test_partial_labels.py
│   ├── test_rollback_partial.py
│   ├── test_unicode.py
│   ├── test_long_text.py
│   └── test_nested_json.py
└── tier9_cross_cutting/           # Cross-cutting concerns (12 tests)
    ├── test_audit_completeness.py
    ├── test_cost_pipeline.py
    ├── test_sse_delivery.py
    ├── test_plugin_lifecycle.py
    ├── test_session_persistence.py
    ├── test_deletion_safety.py
    ├── test_pagination.py
    ├── test_error_format.py
    ├── test_parser_coverage.py
    ├── test_provider_adapters.py
    ├── test_executor_registry.py
    └── test_db_migration.py
```

**File-to-test mapping**: Some test files contain multiple test functions or parameterized test cases. For example, `tier4_queue_review/test_blind_review.py` contains T4-01, T4-02, and T4-03 (all three blind review policy variants). `tier5_agent_llm/test_comparison_runs.py` contains both T5-03 (2-model) and T5-04 (3-model). Each scenario ID maps to one `async def test_*` function, potentially parameterized.

### 2.2 Test Client

All tests use `httpx.AsyncClient` with ASGI transport — no network needed for mocked tests.

```python
# infrastructure/client.py
import httpx
from molabel.app.main import create_app

class E2EClient:
    """Async test client wrapping httpx + ASGI transport.

    NOTE: create_app() currently takes no arguments. The implementation
    must extend create_app() to accept an optional db_url override,
    OR configure the in-memory DB via environment variable before calling
    create_app(). Recommended approach: set MOLABEL_DB_URL env var.
    """

    def __init__(self, db_url: str = "sqlite+aiosqlite://"):
        import os
        os.environ["MOLABEL_DB_URL"] = db_url
        self.app = create_app()
        self._client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://test",
            timeout=30.0,
        )
        self._session_cookie: str | None = None

    async def login(self, reviewer_id: str) -> None:
        resp = await self.post("/sessions", json={"reviewer_id": reviewer_id})
        self._session_cookie = resp.cookies.get("molabel_session")

    async def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        if self._session_cookie:
            kwargs.setdefault("cookies", {})["molabel_session"] = self._session_cookie
        return await self._client.request(method, path, **kwargs)

    async def get(self, path, **kw): return await self.request("GET", path, **kw)
    async def post(self, path, **kw): return await self.request("POST", path, **kw)
    async def put(self, path, **kw): return await self.request("PUT", path, **kw)
    async def patch(self, path, **kw): return await self.request("PATCH", path, **kw)
    async def delete(self, path, **kw): return await self.request("DELETE", path, **kw)

    async def close(self):
        await self._client.aclose()
```

### 2.3 VCR Cassette Manager

Records real LLM responses on first run, replays them on subsequent runs. Cassettes are stored as JSON files per test scenario.

```python
# infrastructure/cassettes.py
import json
from pathlib import Path
from unittest.mock import AsyncMock

CASSETTE_DIR = Path(__file__).parent.parent / "fixtures" / "cassettes"

class CassetteManager:
    """Record/replay LLM API calls for deterministic tests."""

    def __init__(self, scenario_id: str, record: bool = False):
        self.path = CASSETTE_DIR / f"{scenario_id}.json"
        self.record = record
        self._responses: list[dict] = []
        self._call_index = 0

    def load(self) -> None:
        if self.path.exists() and not self.record:
            self._responses = json.loads(self.path.read_text())

    def save(self) -> None:
        if self.record:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._responses, indent=2))

    def next_response(self) -> dict:
        resp = self._responses[self._call_index]
        self._call_index += 1
        return resp

    def add_response(self, response: dict) -> None:
        self._responses.append(response)

    def mock_provider(self, adapter, result_type=None) -> AsyncMock:
        """Replace adapter.complete() with cassette playback.

        Args:
            adapter: The provider adapter to mock.
            result_type: The Pydantic model class for deserialization
                         (e.g., CompletionResult from molabel.core.types).
                         Required for replay mode.
        """
        from molabel.core.types import CompletionResult
        result_cls = result_type or CompletionResult
        original = adapter.complete
        async def replay(*args, **kwargs):
            if self.record:
                result = await original(*args, **kwargs)
                self.add_response(result.model_dump())
                return result
            return result_cls.model_validate(self.next_response())
        adapter.complete = replay
        return adapter
```

## 3. Logging and Observability

### 3.1 Structured Logging

Every test emits structured JSON logs with full context. Human-readable logs also written to console for local dev.

```python
# infrastructure/logging_config.py
import logging
import json
import time
from pathlib import Path
from datetime import datetime, timezone

LOG_DIR = Path("tests/e2e/logs")

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "test_id": getattr(record, "test_id", None),
            "tier": getattr(record, "tier", None),
            "phase": getattr(record, "phase", None),
            "duration_ms": getattr(record, "duration_ms", None),
            "api_call": getattr(record, "api_call", None),
            "status_code": getattr(record, "status_code", None),
            "error": getattr(record, "error", None),
        }
        # Strip None values
        return json.dumps({k: v for k, v in log_entry.items() if v is not None})

def setup_logging(run_id: str) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"e2e_run_{run_id}.jsonl"

    logger = logging.getLogger("molabel.e2e")
    logger.setLevel(logging.DEBUG)

    # JSON file handler (structured, machine-readable)
    fh = logging.FileHandler(log_file)
    fh.setFormatter(JSONFormatter())
    logger.addHandler(fh)

    # Console handler (human-readable)
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
    ))
    ch.setLevel(logging.INFO)
    logger.addHandler(ch)

    return logger
```

### 3.2 Per-Test Logging Context

Each test gets a `TestContext` that tracks all API calls, timings, checkpoints, and assertions. This is the observability backbone.

```python
# infrastructure/logging_config.py (continued)
from dataclasses import dataclass, field
from typing import Any

@dataclass
class APICallLog:
    method: str
    path: str
    status_code: int
    duration_ms: float
    request_body: dict | None = None
    response_summary: str | None = None

@dataclass
class CheckpointLog:
    name: str
    passed: bool
    duration_ms: float
    assertions_passed: int
    assertions_failed: int
    details: list[str] = field(default_factory=list)

@dataclass
class TestContext:
    """Full observability context for a single test scenario."""
    test_id: str
    tier: int
    name: str
    started_at: float = field(default_factory=time.monotonic)
    api_calls: list[APICallLog] = field(default_factory=list)
    checkpoints: list[CheckpointLog] = field(default_factory=list)
    llm_calls: int = 0
    llm_tokens_in: int = 0
    llm_tokens_out: int = 0
    real_llm_calls: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def log_api_call(self, method, path, status, duration_ms, body=None, summary=None):
        self.api_calls.append(APICallLog(method, path, status, duration_ms, body, summary))

    def log_checkpoint(self, name, passed, duration_ms, passed_count, failed_count, details=None):
        self.checkpoints.append(CheckpointLog(name, passed, duration_ms, passed_count, failed_count, details or []))

    def elapsed_ms(self) -> float:
        return (time.monotonic() - self.started_at) * 1000

    def summary(self) -> dict:
        return {
            "test_id": self.test_id,
            "tier": self.tier,
            "name": self.name,
            "total_duration_ms": round(self.elapsed_ms(), 1),
            "api_calls": len(self.api_calls),
            "checkpoints_passed": sum(1 for c in self.checkpoints if c.passed),
            "checkpoints_failed": sum(1 for c in self.checkpoints if not c.passed),
            "llm_calls": self.llm_calls,
            "real_llm_calls": self.real_llm_calls,
            "errors": len(self.errors),
            "warnings": len(self.warnings),
        }
```

### 3.3 Instrumented Client

The test client automatically logs every API call with timing, status, and context.

```python
# infrastructure/client.py (instrumented version)
class InstrumentedClient(E2EClient):
    """E2E client that logs every API call to TestContext."""

    def __init__(self, ctx: TestContext, **kwargs):
        super().__init__(**kwargs)
        self.ctx = ctx
        self.logger = logging.getLogger("molabel.e2e.client")

    async def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        start = time.monotonic()
        resp = await super().request(method, path, **kwargs)
        duration_ms = (time.monotonic() - start) * 1000

        self.ctx.log_api_call(
            method=method,
            path=path,
            status=resp.status_code,
            duration_ms=round(duration_ms, 1),
            body=kwargs.get("json"),
            summary=f"{resp.status_code} in {duration_ms:.0f}ms",
        )

        self.logger.info(
            f"{method} {path} -> {resp.status_code} ({duration_ms:.0f}ms)",
            extra={"test_id": self.ctx.test_id, "api_call": f"{method} {path}", "status_code": resp.status_code},
        )
        return resp
```

### 3.4 Test Run Reporter

Generates a summary report after the full test run — JSON for machines, markdown table for humans.

```python
# infrastructure/reporter.py
class E2EReporter:
    """Aggregates all TestContext results into a run report."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.contexts: list[TestContext] = []

    def add(self, ctx: TestContext):
        self.contexts.append(ctx)

    def generate_report(self) -> dict:
        by_tier = {}
        for ctx in self.contexts:
            by_tier.setdefault(ctx.tier, []).append(ctx)

        return {
            "run_id": self.run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_tests": len(self.contexts),
            "passed": sum(1 for c in self.contexts if not c.errors),
            "failed": sum(1 for c in self.contexts if c.errors),
            "total_duration_ms": sum(c.elapsed_ms() for c in self.contexts),
            "total_api_calls": sum(len(c.api_calls) for c in self.contexts),
            "total_llm_calls": sum(c.llm_calls for c in self.contexts),
            "total_real_llm_calls": sum(c.real_llm_calls for c in self.contexts),
            "by_tier": {
                tier: {
                    "total": len(ctxs),
                    "passed": sum(1 for c in ctxs if not c.errors),
                    "failed": sum(1 for c in ctxs if c.errors),
                    "duration_ms": sum(c.elapsed_ms() for c in ctxs),
                }
                for tier, ctxs in sorted(by_tier.items())
            },
            "tests": [c.summary() for c in self.contexts],
        }

    def write_report(self, output_dir: Path):
        output_dir.mkdir(parents=True, exist_ok=True)
        report = self.generate_report()

        # JSON report (machine-readable)
        json_path = output_dir / f"e2e_report_{self.run_id}.json"
        json_path.write_text(json.dumps(report, indent=2))

        # Markdown report (human-readable)
        md_path = output_dir / f"e2e_report_{self.run_id}.md"
        md_path.write_text(self._render_markdown(report))

    def _render_markdown(self, report: dict) -> str:
        lines = [
            f"# E2E Test Report — {report['run_id']}",
            f"",
            f"**Date**: {report['timestamp']}",
            f"**Total**: {report['total_tests']} tests | "
            f"**Passed**: {report['passed']} | **Failed**: {report['failed']}",
            f"**Duration**: {report['total_duration_ms']/1000:.1f}s | "
            f"**API calls**: {report['total_api_calls']} | "
            f"**LLM calls**: {report['total_llm_calls']} "
            f"({report['total_real_llm_calls']} real)",
            "",
            "## By Tier",
            "",
            "| Tier | Tests | Passed | Failed | Duration |",
            "|------|-------|--------|--------|----------|",
        ]
        tier_names = {
            1: "Pipeline", 2: "Workflows", 3: "API Coverage", 4: "Queue/Review",
            5: "Agent/LLM", 6: "Quality", 7: "Data Mgmt", 8: "Resilience", 9: "Cross-Cut",
        }
        for tier, data in report["by_tier"].items():
            lines.append(
                f"| {tier}. {tier_names.get(tier, '')} | {data['total']} | "
                f"{data['passed']} | {data['failed']} | {data['duration_ms']/1000:.1f}s |"
            )

        # Failed tests detail
        failed = [t for t in report["tests"] if t["errors"] > 0]
        if failed:
            lines.extend(["", "## Failures", ""])
            for t in failed:
                lines.append(f"- **{t['test_id']}** {t['name']} — {t['errors']} error(s)")

        return "\n".join(lines)
```

### 3.5 Log Outputs

Every test run produces:

| Output | Location | Purpose |
|--------|----------|---------|
| Structured log (JSONL) | `tests/e2e/logs/e2e_run_{run_id}.jsonl` | Machine-parseable event stream: every API call, checkpoint, LLM call, error |
| JSON report | `tests/e2e/logs/e2e_report_{run_id}.json` | Full run summary with per-test breakdowns, timings, pass/fail |
| Markdown report | `tests/e2e/logs/e2e_report_{run_id}.md` | Human-readable summary table with tier breakdown and failure details |
| Console output | stdout | Real-time progress with pass/fail indicators per checkpoint |
| pytest JUnit XML | `tests/e2e/logs/junit_{run_id}.xml` | CI integration (pytest `--junitxml`) |

## 4. Parallel Execution

### 4.1 Parallelization Strategy

Tests are grouped into **parallel-safe groups** — tests within a group share no state and can run concurrently. Tests between groups may share DB fixtures and run sequentially.

```python
# infrastructure/parallel.py
import pytest

# Parallel groups — tests within a group run concurrently via pytest-xdist
# Tests across groups run sequentially when they share fixtures

# Group 1: Fully independent (each test gets its own DB)
INDEPENDENT = pytest.mark.xdist_group("independent")

# Group 2: Shared workspace fixtures (read-only)
SHARED_WORKSPACE = pytest.mark.xdist_group("shared_workspace")

# Group 3: Tests that must run sequentially (SSE, concurrent claim tests)
SEQUENTIAL = pytest.mark.xdist_group("sequential")
```

### 4.2 Parallel Group Assignments

| Group | Tiers / Tests | Why Parallel-Safe |
|-------|---------------|-------------------|
| `independent` (parallel) | Tier 1 (all 7), Tier 2 (all 32), Tier 7 (all 14), Tier 8 (all 13), Tier 9 (10 of 12) | Each test creates its own workspace + DB — zero shared state |
| `shared_workspace` (parallel) | Tier 3 (all 28), Tier 5 (all 10), Tier 6 (all 10) | Read-only access to shared pre-populated workspace — safe to parallelize |
| `sequential` | Tier 4 (all 15), Tier 9 (SSE + concurrency) | Concurrent claims, SSE streams, and session tests require ordered execution |

### 4.3 pytest Configuration

```ini
# pyproject.toml (test section)
[tool.pytest.ini_options]
markers = [
    "e2e: End-to-end test",
    "tier1: Full pipeline test",
    "tier2: Complex workflow test",
    "tier3: API coverage test",
    "tier4: Queue and review test",
    "tier5: Agent and LLM test",
    "tier6: Quality and analytics test",
    "tier7: Data management test",
    "tier8: Resilience test",
    "tier9: Cross-cutting test",
    "real_llm: Requires real LLM API call",
    "slow: Test takes >30 seconds",
]
```

### 4.4 Running Tests

```bash
# Run all E2E tests with 4 parallel workers
uv run pytest tests/e2e/ -n 4 --dist loadgroup -v

# Run a specific tier
uv run pytest tests/e2e/tier2_workflows/ -n 4 -v

# Run only mocked tests (skip real LLM calls)
uv run pytest tests/e2e/ -n 4 -m "not real_llm"

# Run only real LLM smoke tests
uv run pytest tests/e2e/ -m "real_llm" -v

# Run with full logging + JUnit output
uv run pytest tests/e2e/ -n 4 --dist loadgroup \
    --junitxml=tests/e2e/logs/junit.xml \
    -v --tb=short

# Run a single scenario by ID
uv run pytest tests/e2e/ -k "T2-20" -v

# Record new VCR cassettes (first run or after API changes)
E2E_RECORD_CASSETTES=1 uv run pytest tests/e2e/ -m "real_llm" -v
```

## 5. Agent Integration (Skills + Hooks)

### 5.1 Hook System

Hooks allow an agent to drive the full test pipeline and react to results.

```python
# infrastructure/hooks.py
from typing import Protocol, Any

class E2EHook(Protocol):
    """Protocol for E2E test lifecycle hooks."""

    async def on_run_start(self, run_id: str, total_tests: int) -> None: ...
    async def on_tier_start(self, tier: int, test_count: int) -> None: ...
    async def on_test_start(self, test_id: str, name: str) -> None: ...
    async def on_checkpoint(self, test_id: str, checkpoint: str, passed: bool) -> None: ...
    async def on_test_end(self, test_id: str, passed: bool, summary: dict) -> None: ...
    async def on_tier_end(self, tier: int, passed: int, failed: int) -> None: ...
    async def on_run_end(self, report: dict) -> None: ...
    async def on_failure(self, test_id: str, error: str, context: dict) -> None: ...

class LoggingHook:
    """Default hook that logs all events."""

    def __init__(self, logger):
        self.logger = logger

    async def on_run_start(self, run_id, total_tests):
        self.logger.info(f"E2E run {run_id} starting — {total_tests} tests")

    async def on_test_start(self, test_id, name):
        self.logger.info(f"[{test_id}] Starting: {name}")

    async def on_checkpoint(self, test_id, checkpoint, passed):
        status = "PASS" if passed else "FAIL"
        self.logger.info(f"[{test_id}] Checkpoint {checkpoint}: {status}")

    async def on_test_end(self, test_id, passed, summary):
        status = "PASSED" if passed else "FAILED"
        duration = summary.get("total_duration_ms", 0)
        self.logger.info(f"[{test_id}] {status} ({duration:.0f}ms, {summary.get('api_calls', 0)} API calls)")

    async def on_failure(self, test_id, error, context):
        self.logger.error(f"[{test_id}] FAILURE: {error}")

    async def on_tier_start(self, tier, test_count):
        self.logger.info(f"Tier {tier} starting — {test_count} tests")

    async def on_tier_end(self, tier, passed, failed):
        self.logger.info(f"Tier {tier} complete — {passed} passed, {failed} failed")

    async def on_run_end(self, report):
        self.logger.info(
            f"E2E run complete — {report['passed']}/{report['total_tests']} passed "
            f"in {report['total_duration_ms']/1000:.1f}s"
        )
```

### 5.2 Agent-Drivable Pipeline

The test suite exposes a programmatic API that an agent skill can call to run the full pipeline or specific tiers.

```python
# infrastructure/runner.py
class E2ERunner:
    """Programmatic E2E test runner for agent integration."""

    def __init__(self, hooks: list[E2EHook] | None = None, api_key: str | None = None):
        self.hooks = hooks or []
        self.api_key = api_key  # MiniMax API key for real LLM tests
        self.reporter = E2EReporter(run_id=self._generate_run_id())

    async def run_all(self, parallel: bool = True, skip_real_llm: bool = False) -> dict:
        """Run all 143 tests. Returns report dict."""
        ...

    async def run_tier(self, tier: int, parallel: bool = True) -> dict:
        """Run all tests in a specific tier."""
        ...

    async def run_scenario(self, scenario_id: str) -> dict:
        """Run a single scenario by ID (e.g., 'T2-20')."""
        ...

    async def run_tags(self, tags: list[str], parallel: bool = True) -> dict:
        """Run all tests matching any of the given tags."""
        ...

    def get_report(self) -> dict:
        """Get the current run report."""
        return self.reporter.generate_report()
```

### 5.3 CLI Entry Point

```python
# tests/e2e/__main__.py
"""Run E2E tests from command line with full observability."""
import asyncio
import argparse

async def main():
    parser = argparse.ArgumentParser(description="MoLabel E2E Test Runner")
    parser.add_argument("--tier", type=int, help="Run specific tier (1-9)")
    parser.add_argument("--scenario", type=str, help="Run specific scenario (e.g., T2-20)")
    parser.add_argument("--tags", nargs="+", help="Run tests matching tags")
    parser.add_argument("--parallel", action="store_true", default=True)
    parser.add_argument("--no-parallel", dest="parallel", action="store_false")
    parser.add_argument("--skip-real-llm", action="store_true")
    parser.add_argument("--record-cassettes", action="store_true")
    parser.add_argument("--api-key", type=str, help="MiniMax API key for real LLM tests")
    parser.add_argument("--output-dir", type=str, default="tests/e2e/logs")
    args = parser.parse_args()

    runner = E2ERunner(
        hooks=[LoggingHook(setup_logging(runner.reporter.run_id))],
        api_key=args.api_key,
    )

    if args.scenario:
        report = await runner.run_scenario(args.scenario)
    elif args.tier:
        report = await runner.run_tier(args.tier, parallel=args.parallel)
    elif args.tags:
        report = await runner.run_tags(args.tags, parallel=args.parallel)
    else:
        report = await runner.run_all(parallel=args.parallel, skip_real_llm=args.skip_real_llm)

    runner.reporter.write_report(Path(args.output_dir))
    print(f"\nReport written to {args.output_dir}/")

if __name__ == "__main__":
    asyncio.run(main())
```

## 6. Test Scenarios — Complete Reference

### 6.1 Tier 1: Full Pipeline Per Data Type (7 tests)

Each test runs: workspace creation -> reviewer profiles -> session -> dataset import -> task schema -> model profile -> prompt -> agent run -> queue claim -> human review -> quality check -> export -> release.

| ID | Name | Data Type | Mock Mode | Key Assertions |
|----|------|-----------|-----------|---------------|
| T1-01 | Full pipeline — text classification | Sentiment (50 reviews) | Hybrid | 50 agent outputs validated, review events created, Cohen's kappa computed, JSONL export |
| T1-01-REAL | Full pipeline — real LLM smoke | Sentiment (5 reviews) | Real LLM | Real MiniMax returns valid JSON, tokens + cost tracked |
| T1-02 | Full pipeline — multi-label tagging | Topics (40 articles) | Hybrid | Multi-select outputs, set-based agreement, list labels in export |
| T1-03 | Full pipeline — NER | Entities (30 sentences) | Hybrid | Entity spans {start,end,label,text}, span-based F1, offset preservation |
| T1-04 | Full pipeline — content moderation | Toxicity (45 comments) | Hybrid | Ordinal severity 1-5 + rationale, weighted kappa |
| T1-05 | Full pipeline — pairwise comparison | Rankings (35 pairs) | Hybrid | Preference A/B/tie, 3-class agreement, stable_fields with both responses |
| T1-06 | Full pipeline — structured extraction | Invoices (25 texts) | Hybrid | Multi-field JSON {vendor,total,date,line_items}, per-field accuracy, nested export |

### 6.2 Tier 2: Complex Workflow Scenarios (32 tests)

#### Loops (5 tests)
| ID | Name | Terminates By | Key Assertion |
|----|------|--------------|--------------|
| T2-01 | Count-based loop | Exact count (3) | Iteration counter, step output archiving with `__iter_N` |
| T2-02 | Metric-based loop | `quality.agreement >= 0.95` | Early termination, reason = `metric_threshold_met` |
| T2-03 | Coverage-based loop | `review_coverage >= 0.95` | Coverage target termination |
| T2-04 | Manual termination loop | Operator gate per iteration | Gate pause/approve/reject controls loop |
| T2-05 | Max iterations safety | Never meets threshold | Stops at `max_iterations`, reason = `max_iterations_reached` |

#### Conditionals (4 tests)
| ID | Name | Predicate | Key Assertion |
|----|------|-----------|--------------|
| T2-06 | Branch by confidence | `avg_confidence >= 0.8` | Then/else branch selection, skipped step status |
| T2-07 | Branch by distribution | `>70% in one class` | Skewed data routes to resampling |
| T2-08 | Branch by quality | `agreement >= 0.85` | Quality-driven routing to export vs more review |
| T2-09 | Nested predicates | Compound boolean, arithmetic, security | Function calls rejected, missing keys return safe defaults |

#### Parallel Execution (4 tests)
| ID | Name | Mode | Key Assertion |
|----|------|------|--------------|
| T2-10 | Multi-model comparison | 3 agents parallel | All 3 complete, outputs merged, metric conflicts warn |
| T2-11 | Fail-fast mode | `fail_fast=True` | First failure cancels remaining, `is_partial=True` |
| T2-12 | Wait-all mode | `fail_fast=False` | All children attempted, partial failure reported |
| T2-13 | Multi-dataset | 2 datasets parallel | Record sets don't cross-contaminate |

#### Gates (3 tests)
| ID | Name | Outcome | Key Assertion |
|----|------|---------|--------------|
| T2-14 | Approval gate (approve) | Continues | Gate stores operator_id, decided_at, successor steps unblocked |
| T2-15 | Approval gate (reject) | Cancelled | Workflow + all pending steps cancelled |
| T2-16 | Quality gate blocking export | Conditional | Gate message includes metric values, blocks/allows export |

#### Breakpoints (3 tests)

**API note**: Breakpoints are a runtime mode, not a step type. They are configured either via a `breakpoint: true` flag on individual steps in the workflow YAML, or via `pause_on_every_step: true` in the execution request. The continue/skip APIs are `POST /workflows/{wf_id}/executions/{exec_id}/steps/{step_id}/continue` and `POST .../skip`. The implementation must verify these endpoints exist or create them.
| ID | Name | Behavior | Key Assertion |
|----|------|----------|--------------|
| T2-17 | Pause before step | Single breakpoint | `waiting_for_breakpoint`, config override at continue |
| T2-18 | Pause on every step | All steps pause | Each step hits breakpoint, must continue individually |
| T2-19 | Skip at breakpoint | Skip instead of execute | Skipped status, skip propagation to dependents |

#### Multi-Step Compositions (4 tests)
| ID | Name | Composition | Key Assertion |
|----|------|------------|--------------|
| T2-20 | Loop containing conditional | Loop body has conditional | Conditional evaluates differently per iteration |
| T2-21 | Parallel inside loop | Loop body has parallel step | Context archived between iterations, metrics accumulate |
| T2-22 | Gate after parallel | Parallel -> gate -> export | Gate accesses parallel outputs |
| T2-23 | Conditional after quality | quality_check -> conditional -> export/review | Quality-driven branching |

#### Workflow Lifecycle (3 tests)
| ID | Name | Operation | Key Assertion |
|----|------|-----------|--------------|
| T2-24 | Pause mid-execution | Pause running workflow | `paused` status, `paused_at` timestamp |
| T2-25 | Resume after pause | Resume paused workflow | Completed steps not re-executed, continues from correct step |
| T2-26 | Cancel mid-execution | Cancel workflow | All non-terminal steps cancelled, completed steps preserved |

#### Error Recovery (3 tests)
| ID | Name | Failure | Key Assertion |
|----|------|---------|--------------|
| T2-27 | Provider failure + retry | Agent step fails, then succeeds on retry | Workflow pauses, `retry_step()` works |
| T2-28 | Crash recovery | Simulated app crash | `detect_interrupted_steps()` finds running steps |
| T2-29 | Step timeout | Step exceeds timeout | Timeout error, workflow pauses, retry possible |

#### Templates + Feedback Loop (3 tests)
| ID | Name | What | Key Assertion |
|----|------|------|--------------|
| T2-30 | full_quality_pipeline.yaml | Built-in template end-to-end | All 11 steps parse, DAG no cycles, gate pauses correctly |
| T2-31 | iterative_refinement.yaml | Built-in template with loop | Loop terminates on quality metric |
| T2-32 | Agent feedback loop | correct -> refine -> re-run | Correction batch lifecycle, prompt v2 created, v1 vs v2 comparison |

#### Human Triage (1 test)
| ID | Name | What | Key Assertion |
|----|------|------|--------------|
| T2-33 | Human triage step | Triage queue with category routing | `triage_mode=True` forwarded, category counts tracked, records routed by triage decision |

### 6.3 Tier 3: API Endpoint Coverage (28 tests)

| ID | Router | Endpoints Covered | Key Assertions |
|----|--------|-------------------|----------------|
| T3-01 | Workspaces | CRUD + reindex | 201 response, correct fields, reindex 202 |
| T3-02 | Workspaces (errors) | 404 on nonexistent | Consistent error format |
| T3-03 | Workspaces (auth) | 401 without session | Cookie required |
| T3-04 | Datasets | CRUD + import + records + analytics | Paginated records, analytics response |
| T3-05 | Datasets (snapshots) | Create, list, compare | Snapshot diff with base/compare IDs |
| T3-06 | Datasets (pagination) | Limit, offset, ordering | Items ordered, limit respected |
| T3-07 | Task Schemas | CRUD for categorical + JSON types | Label fields, blind review policy |
| T3-08 | Workflows | CRUD + execute + pause + cancel | Execution lifecycle, step states |
| T3-09 | Agent Runs | CRUD + outputs + compare + analytics | Comparison creates multiple runs, analytics fields |
| T3-10 | Queue + Review | Claim, submit, skip, draft, reveal, release, correct, status | All claim operations, mission control |
| T3-11 | Adjudication | Detect, build queue, resolve | 4 resolution types, severity tracking |
| T3-12 | Quality | Dashboard, agreement, drift | Agreement scores, drift indicators |
| T3-13 | Exports | Preview, create, validate, download, push-hf | Preview samples, validation checks |
| T3-14 | Releases | CRUD + approve | Draft -> approved lifecycle |
| T3-15 | Prompts | CRUD + versioning + diff | Append-only versions, diff between versions |
| T3-16 | Corrections | List, analyze, get refinement | Batch status transitions, refinement suggestions |
| T3-17 | Providers | List, scan, health, models, HF auth | Provider discovery, health status |
| T3-18 | Model Profiles | Full CRUD + test connectivity | Delete 204, test returns ConnectivityTestResult |
| T3-19 | Runtime Profiles | Full CRUD + retry config | Retry config fields |
| T3-20 | Reviewer Profiles | CRUD + active filtering | Auto avatar_color, active_only filter |
| T3-21 | Sessions | Create, me, switch, delete | Cookie lifecycle, 401 after logout |
| T3-22 | Label Mappings | Preview + save | Field/value mappings, missing field warnings |
| T3-23 | Costs | Summary + estimate | by_model, by_role, daily_trend |
| T3-24 | Audit | List + filter + get | Time range, event_type, actor, object_type filters |
| T3-25 | Plugins | List, detail, enable, disable | Compatibility info, toggle enabled |
| T3-26 | Assistant | Query (SSE) + context | SSE stream, workspace_summary |
| T3-27 | Events (SSE) | All 4 SSE streams | Content-Type, keepalive, initial events |
| T3-28 | Review Events (`/api/v1/review/events`) | List with filters | Paginated, record/reviewer/draft filters |

### 6.4 Tier 4: Queue & Review (15 tests)

| ID | Name | Key Assertion |
|----|------|--------------|
| T4-01 | Blind review — hide policy | Agent output hidden on claim, revealed on request |
| T4-02 | Blind review — show policy | Agent output included in claim |
| T4-03 | Blind review — no_agent policy | No agent output, reveal-ai errors |
| T4-04 | AI reveal tracking | Pre-reveal vs post-reveal decisions distinguishable |
| T4-05 | Draft saving | Last-write-wins, submit uses final labels not draft |
| T4-06 | Claim expiry + reclaim | Expired claim returns to pool, `claim_expired_count` incremented |
| T4-07 | Concurrent claims (atomicity) | Only 1 of 2 simultaneous claimers gets the task |
| T4-08 | Overlap records | Same record reviewed by multiple reviewers |
| T4-09 | Calibration queues | Known ground truth, reviewer alignment measured |
| T4-10 | Adjudication — disagreement resolution | Detect -> build queue -> resolve with canonical label |
| T4-11 | Ordering — low_confidence | Lowest confidence records first |
| T4-12 | Ordering — uncertainty_sampling | Records nearest decision boundary first |
| T4-13 | Ordering — stratified | Even class distribution in queue |
| T4-14 | Ordering — disagreement_first | Disagreement records prioritized |
| T4-15 | All 7 review decisions | accept, accept_ai, edit_ai, reject_ai, correct, reject, skip |

### 6.5 Tier 5: Agent & LLM (10 tests)

| ID | Name | Key Assertion |
|----|------|--------------|
| T5-01 | Validation pass | All outputs `validation_passed=True` |
| T5-02 | Validation failure + retry | Retry increments counter, some succeed on retry |
| T5-03 | 2-model comparison | Separate runs, per-model accuracy + agreement_rate |
| T5-04 | 3-model comparison | 3 agent runs, all in comparison result |
| T5-05 | Self-reported confidence | `confidence_self_reported` float in [0,1] |
| T5-06 | Self-consistency | 3 samples, consistency score computed |
| T5-07 | Cost tracking | Per-output tokens, per-run cost, cost summary aggregation |
| T5-08 | Provider health | All 5 provider types return HealthStatus (anthropic, openai_compatible, ollama, openrouter, custom) |
| T5-09 | Batch partial failure | 8/10 succeed, `failed_records=2`, error details |
| T5-10 | All 8 agent roles | proposer, critic, normalizer, disagreement_flagger, deduper, rubric_judge, edge_case_miner, export_prep |

### 6.6 Tier 6: Quality & Analytics (10 tests)

| ID | Name | Key Assertion |
|----|------|--------------|
| T6-01 | Cohen's kappa | Correct computation, perfect=1.0, random~0 |
| T6-02 | Krippendorff's alpha | Ordinal scale, multiple raters, missing data |
| T6-03 | Chi-squared drift | Significant shift detected, p-value computed |
| T6-04 | KL divergence | Zero for identical, high for shifted |
| T6-05 | Label distribution | Per-value counts, class imbalance detection |
| T6-06 | Throughput metrics | Records/hour, per-reviewer, average review time |
| T6-07 | Calibration analysis | Confidence buckets, predicted vs actual accuracy |
| T6-08 | Validation runs | Multiple threshold configs, overall pass/fail |
| T6-09 | Delta analysis | Snapshot comparison, improvement/regression |
| T6-10 | Readiness dashboard | Gate evaluation, passing/failing/not_evaluated |

### 6.7 Tier 7: Data Management (14 tests)

| ID | Name | Key Assertion |
|----|------|--------------|
| T7-01 | CSV import | Headers parsed, stable_fields from columns |
| T7-02 | JSON import | Nested JSON preserved, array records split |
| T7-03 | JSONL import | Line-per-record, malformed lines reported |
| T7-04 | Parquet import | Column types preserved |
| T7-05 | Markdown import | Content preserved, front matter extracted |
| T7-06 | YAML import | Structure preserved in stable_fields |
| T7-07 | CSV export | Header row, correct columns, UTF-8 |
| T7-08 | Parquet export | Correct schema, column types |
| T7-09 | JSONL export | One object per line, all fields |
| T7-10a | HuggingFace export | push-hf creates repo, handles auth failure, dataset name conflict |
| T7-10 | Label mapping | Field rename + value translation |
| T7-11 | Pre-label trust levels | ground_truth, expert, external, untrusted behaviors |
| T7-12 | Snapshot lifecycle | Create, compare, restore |
| T7-13 | Dataset operations | Filter, random/stratified/confidence sample, exact/flag dedup |
| T7-14 | Large dataset (1000+) | No timeout, pagination, batch processing |

### 6.8 Tier 8: Resilience (13 tests)

| ID | Name | Key Assertion |
|----|------|--------------|
| T8-01 | Malformed input | Valid lines imported, errors reported with row_index |
| T8-02 | Invalid workflow YAML | 8 parse error types with descriptive messages |
| T8-03 | Provider timeout + retry | Retry on timeout, success on second attempt |
| T8-04 | Concurrent operations | No data corruption, DB constraints enforced |
| T8-05 | Session expiry | 401 on expired session, claim eventually reclaimed |
| T8-06 | Duplicate records | Dedup by content_hash, `duplicate_rate` metric |
| T8-07 | Empty dataset | Agent/export/quality handle 0 records gracefully |
| T8-08 | Empty filter result | Agent handles 0-record input |
| T8-09 | Partial labels export | Filtered vs full export, metadata counts |
| T8-10 | Rollback partial | Partial outputs preserved, retry processes remaining |
| T8-11 | Unicode + special chars | Emoji, CJK, Arabic, newlines preserved through pipeline |
| T8-12 | Very long text | 10000+ chars stored, no overflow |
| T8-13 | Deeply nested JSON | 5+ levels preserved in payload and export |

### 6.9 Tier 9: Cross-Cutting (12 tests)

| ID | Name | Key Assertion |
|----|------|--------------|
| T9-01 | Audit completeness | All 31 AuditAction types generated across pipeline |
| T9-02 | Cost pipeline | Token aggregation, by_model/by_role/daily_trend |
| T9-03 | SSE delivery | Step events, keepalive, reconnection IDs |
| T9-04 | Plugin lifecycle | List, enable, disable, detail with supports |
| T9-05 | Session persistence | Cookie across 10+ calls, switch, logout -> 401 |
| T9-06 | Deletion safety | Foreign key constraints, cascade behavior |
| T9-07 | Pagination | All list endpoints respect limit, no gaps/dupes |
| T9-08 | Error format consistency | 400, 401, 404, 409 all follow ErrorResponse schema |
| T9-09 | Parser — all 20 step types | Every WorkflowStepType enum accepted |
| T9-10 | All 5 providers | Each adapter instantiates, list_models() works |
| T9-11 | All 20 executors | create_default_registry() has all step types |
| T9-12 | DB migration | All 30 tables created with indexes and FKs |

## 7. Test Data — Synthetic Fixtures

All test data is synthetic, self-contained, and checked into the repo under `tests/e2e/fixtures/`.

### 7.1 Text Classification (50 records)

Product reviews with clear sentiment signals. Mix of obviously positive ("Amazing product, exceeded expectations"), obviously negative ("Broke after one day, waste of money"), and ambiguous ("It's okay, nothing special") to test confidence calibration.

### 7.2 Multi-Label (40 records)

News article summaries spanning 8 topics: politics, sports, technology, science, health, entertainment, business, environment. Some articles have 1 topic, some have 3-4 (e.g., a health-tech-business article about biotech funding).

### 7.3 NER (30 records)

Sentences with diverse entity types: PERSON, ORG, LOC, DATE, MONEY. Includes edge cases: overlapping entities, entities at start/end of sentence, multi-word entities, entities with special characters.

### 7.4 Content Moderation (45 records)

User comments across the severity spectrum: clearly safe (severity 1), borderline (severity 2-3), clearly toxic (severity 4-5). Includes sarcasm, coded language, and context-dependent content that requires rationale.

### 7.5 Pairwise Comparison (35 records)

Pairs of LLM responses to the same prompt. Some with clear winner (factual vs hallucinated), some genuinely close (both good, different styles), and some where both are poor.

### 7.6 Structured Extraction (25 records)

Invoice/receipt text in varying formats: formal invoices with line items, handwritten-style receipts, email confirmations. Fields: vendor_name, total_amount (float), date (ISO), currency, line_items (array of {description, quantity, price}).

### 7.7 Workflow YAML Fixtures

Pre-built workflow definitions for every Tier 2 test:

| File | Steps | Used By |
|------|-------|---------|
| `wf_count_loop.yaml` | loop(count=3) + agent + review + quality | T2-01 |
| `wf_metric_loop.yaml` | loop(metric=quality.agreement >= 0.95) | T2-02 |
| `wf_coverage_loop.yaml` | loop(coverage=0.95) | T2-03 |
| `wf_manual_loop.yaml` | loop(manual) + gate | T2-04 |
| `wf_conditional_confidence.yaml` | conditional(avg_confidence >= 0.8) | T2-06 |
| `wf_conditional_distribution.yaml` | conditional(skew > 0.7) | T2-07 |
| `wf_conditional_quality.yaml` | conditional(agreement >= 0.85) | T2-08 |
| `wf_parallel_3model.yaml` | parallel(agent_a, agent_b, agent_c) | T2-10 |
| `wf_parallel_failfast.yaml` | parallel(fail_fast=true) | T2-11 |
| `wf_gate_approval.yaml` | agent -> gate -> export | T2-14 |
| `wf_gate_quality.yaml` | quality -> gate -> export | T2-16 |
| `wf_composition_loop_cond.yaml` | loop(agent, conditional, quality) | T2-20 |
| `wf_composition_parallel_loop.yaml` | loop(parallel(a,b), agreement, quality) | T2-21 |
| `wf_feedback_loop.yaml` | agent -> review -> correct -> refine -> re-run | T2-32 |

### 7.8 VCR Cassettes

One cassette file per scenario that uses mocked LLM calls. Each cassette contains:

```json
[
  {
    "request": {
      "model": "minimax-2.7",
      "messages": [...],
      "max_tokens": 1024
    },
    "response": {
      "content": [{"type": "text", "text": "{\"sentiment\": \"positive\"}"}],
      "usage": {"input_tokens": 150, "output_tokens": 25},
      "model": "minimax-2.7",
      "stop_reason": "end_turn"
    },
    "latency_ms": 450
  }
]
```

Cassettes are recorded once with real MiniMax calls, then replayed. To re-record: `E2E_RECORD_CASSETTES=1 uv run pytest tests/e2e/ -m real_llm`.

## 8. LLM Provider Configuration

### 8.1 MiniMax 2.7 via Anthropic SDK

MiniMax 2.7 is accessed through the Anthropic SDK with a custom base URL pointing
to MiniMax's API. The `AnthropicAdapter` must be configured with an overridden
`base_url` so requests are routed to MiniMax's endpoint, not `api.anthropic.com`.

**Implementation note**: The `AnthropicAdapter` currently hardcodes the Anthropic
base URL. The implementation must either:
- (a) Extend `AnthropicAdapter` to accept a `base_url` override, OR
- (b) Use the `custom` provider type with Anthropic SDK protocol compatibility

Recommended: option (a) — add `base_url` to `ModelProfile` and pass it through.

```python
# Test configuration for real LLM calls
MINIMAX_CONFIG = {
    "provider": "anthropic",
    "model_identifier": "minimax-2.7",
    "base_url": "https://api.minimax.chat/v1",  # MiniMax API endpoint
    "api_key_env": "MINIMAX_API_KEY",            # Resolved via resolve_api_key()
    "pricing": {
        "input_per_1k": 0.001,                   # Update with actual MiniMax pricing
        "output_per_1k": 0.003,
    },
}
```

### 8.2 Environment Variables

```bash
# Required for real LLM tests
MINIMAX_API_KEY=<user-provided>

# Optional
E2E_RECORD_CASSETTES=1              # Record new cassettes instead of replaying
E2E_PARALLEL_WORKERS=4              # Number of parallel workers (default: 4)
E2E_LOG_LEVEL=DEBUG                 # Log verbosity (default: INFO)
E2E_SKIP_REAL_LLM=1                # Skip real LLM tests entirely
```

## 9. conftest.py — Shared Fixtures

```python
# tests/e2e/conftest.py
import pytest
import uuid
import time
from pathlib import Path

from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import setup_logging, TestContext
from tests.e2e.infrastructure.reporter import E2EReporter
from tests.e2e.infrastructure.hooks import LoggingHook
from tests.e2e.infrastructure.cassettes import CassetteManager

# ── Session-scoped fixtures ──────────────────────────────────────────

@pytest.fixture(scope="session")
def run_id():
    return f"{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

@pytest.fixture(scope="session")
def e2e_logger(run_id):
    return setup_logging(run_id)

@pytest.fixture(scope="session")
def reporter(run_id):
    return E2EReporter(run_id)

# ── Per-test fixtures ────────────────────────────────────────────────

@pytest.fixture
async def ctx(request) -> TestContext:
    """Per-test observability context, auto-populated from markers."""
    markers = {m.name for m in request.node.iter_markers()}
    tier = next((int(m[4:]) for m in markers if m.startswith("tier")), 0)
    callspec = getattr(request.node, "callspec", None)
    test_id = callspec.id if callspec is not None else request.node.name
    return TestContext(test_id=test_id, tier=tier, name=request.node.name)

@pytest.fixture
async def client(ctx) -> InstrumentedClient:
    """Instrumented async client with fresh in-memory DB."""
    c = InstrumentedClient(ctx)
    yield c
    await c.close()

@pytest.fixture
def cassette(request) -> CassetteManager:
    """VCR cassette manager — record or replay LLM calls."""
    import os
    scenario_id = request.node.name
    record = os.environ.get("E2E_RECORD_CASSETTES") == "1"
    mgr = CassetteManager(scenario_id, record=record)
    mgr.load()
    yield mgr
    mgr.save()

# ── Hooks ────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
async def log_test_lifecycle(ctx, e2e_logger, reporter, request):
    """Log test start/end and register with reporter."""
    hook = LoggingHook(e2e_logger)
    await hook.on_test_start(ctx.test_id, ctx.name)
    yield
    # rep_call is set by the pytest_runtest_makereport hook below
    rep_call = getattr(request.node, "rep_call", None)
    passed = not rep_call.failed if rep_call is not None else len(ctx.errors) == 0
    await hook.on_test_end(ctx.test_id, passed, ctx.summary())
    reporter.add(ctx)

# ── Hooks for test result tracking ───────────────────────────────────

@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Attach test result to node so log_test_lifecycle can read it."""
    outcome = yield
    rep = outcome.get_result()
    if rep.when == "call":
        item.rep_call = rep

def pytest_configure(config):
    """Attach reporter to config for session-level access."""
    run_id = f"{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    config._e2e_reporter = E2EReporter(run_id=run_id)

# ── Session teardown ─────────────────────────────────────────────────

def pytest_sessionfinish(session, exitstatus):
    """Write final report on session end."""
    reporter = getattr(session.config, "_e2e_reporter", None)
    if reporter:
        reporter.write_report(Path("tests/e2e/logs"))
```

## 10. Example Test — Checkpoint Pattern

Every test uses the checkpoint pattern for independent assertion phases.

```python
# tier1_pipeline/test_text_classification.py
import pytest
from tests.e2e.infrastructure.assertions import checkpoint

@pytest.mark.e2e
@pytest.mark.tier1
@pytest.mark.asyncio
async def test_full_pipeline_text_classification(client, ctx, cassette):
    """T1-01: Full pipeline for sentiment classification."""

    # ── Checkpoint 1: Workspace Setup ────────────────────────────
    with checkpoint(ctx, "workspace_setup"):
        ws = await client.post("/workspaces", json={
            "workspace_name": "Sentiment Test",
        })
        assert ws.status_code == 201
        ws_id = ws.json()["workspace_id"]

        # Create reviewer profiles
        reviewer1 = await client.post("/reviewer-profiles", json={
            "display_name": "Reviewer 1",
        })
        assert reviewer1.status_code == 201
        r1_id = reviewer1.json()["reviewer_id"]

        # Login
        await client.login(r1_id)

    # ── Checkpoint 2: Data Import ────────────────────────────────
    with checkpoint(ctx, "data_import"):
        ds = await client.post("/datasets", json={
            "dataset_name": "Product Reviews",
            "workspace_id": ws_id,
        })
        assert ds.status_code == 201
        ds_id = ds.json()["dataset_id"]

        import_resp = await client.post(f"/datasets/{ds_id}/import", json={
            "source_type": "jsonl",
            "source_path": "fixtures/text_classification/reviews.jsonl",
        })
        assert import_resp.status_code == 202

        # Verify records
        records = await client.get(f"/datasets/{ds_id}/records")
        assert records.json()["total"] == 50

    # ── Checkpoint 3: Schema + Prompt ────────────────────────────
    with checkpoint(ctx, "schema_config"):
        schema = await client.post("/task-schemas", json={
            "task_slug": "sentiment",
            "task_type": "classification",
            "label_fields": [
                {"name": "sentiment", "field_type": "categorical",
                 "options": ["positive", "negative", "neutral"]}
            ],
        })
        assert schema.status_code == 201

        prompt = await client.post("/prompts", json={
            "prompt_slug": "sentiment-v1",
            "base_template": "Classify the sentiment of this product review.",
            "task_schema_id": schema.json()["task_schema_id"],
        })
        assert prompt.status_code == 201

    # ── Checkpoint 4: Agent Run ──────────────────────────────────
    with checkpoint(ctx, "agent_run"):
        model = await client.post("/model-profiles", json={
            "model_identifier": "minimax-2.7",
            "provider": "anthropic",
            "base_url": "https://api.minimax.chat/v1",
        })
        assert model.status_code == 201

        schema_id = schema.json()["task_schema_id"]
        prompt_version = prompt.json()["version"]

        # Mock LLM via cassette
        run = await client.post("/agent-runs", json={
            "workspace_id": ws_id,
            "dataset_id": ds_id,
            "task_schema_id": schema_id,
            "model_profile_id": model.json()["model_profile_id"],
            "prompt_version": prompt_version,
            "agent_role": "proposer",
        })
        assert run.status_code == 202
        run_id = run.json()["agent_run_id"]

        # Verify outputs
        outputs = await client.get(f"/agent-runs/{run_id}/outputs")
        assert outputs.json()["total"] == 50
        for output in outputs.json()["items"]:
            assert output["validation_passed"] is True

    # ── Checkpoint 5: Queue Creation + Human Review ──────────────
    with checkpoint(ctx, "human_review"):
        # Queue is created separately (by workflow human_review step or API)
        queue = await client.post("/queues", json={
            "workspace_id": ws_id,
            "dataset_id": ds_id,
            "task_schema_id": schema_id,
            "agent_run_id": run_id,
        })
        assert queue.status_code == 201
        queue_id = queue.json()["queue_id"]

        claim = await client.post(f"/queues/{queue_id}/claim")
        assert claim.status_code == 200
        task_id = claim.json()["review_task_id"]

        submit = await client.post(f"/review-tasks/{task_id}/submit", json={
            "labels": {"sentiment": "positive"},
            "decision": "accept",
        })
        assert submit.status_code == 200

    # ── Checkpoint 6: Quality ────────────────────────────────────
    with checkpoint(ctx, "quality_check"):
        quality = await client.get(f"/quality/dashboard?workspace_id={ws_id}")
        assert quality.status_code == 200
        assert quality.json()["overall_agreement"] is not None

    # ── Checkpoint 7: Export + Release ───────────────────────────
    with checkpoint(ctx, "export_release"):
        export = await client.post("/exports", json={
            "dataset_id": ds_id,
            "format": "jsonl",
        })
        assert export.status_code == 202

        release = await client.post("/releases", json={
            "workspace_id": ws_id,
            "export_bundle_ids": [export.json()["export_id"]],
        })
        assert release.status_code == 201
        assert release.json()["status"] == "draft"
```

### 10.1 Checkpoint Context Manager

```python
# infrastructure/assertions.py
import time
from contextlib import contextmanager

@contextmanager
def checkpoint(ctx: TestContext, name: str):
    """Independently assertable test phase."""
    start = time.monotonic()
    passed_count = 0
    failed_count = 0
    details = []
    try:
        yield
        passed_count += 1
    except AssertionError as e:
        failed_count += 1
        details.append(str(e))
        ctx.errors.append(f"Checkpoint '{name}': {e}")
        raise  # Still fail the test, but checkpoint is logged
    finally:
        duration_ms = (time.monotonic() - start) * 1000
        ctx.log_checkpoint(
            name=name,
            passed=failed_count == 0,
            duration_ms=round(duration_ms, 1),
            passed_count=passed_count,
            failed_count=failed_count,
            details=details,
        )
```

## 11. Dependencies

Add to `pyproject.toml` under `[project.optional-dependencies]` or test group:

```toml
[tool.uv.dev-dependencies]
# Existing test deps...
pytest-asyncio = ">=0.23"
pytest-xdist = ">=3.5"       # Parallel execution
httpx = ">=0.27"              # Async test client with ASGI transport
```

No new production dependencies. All test infrastructure lives under `tests/e2e/`.

## 12. Implementation Sequence

Build order to maximize incremental testability:

| Step | What | Depends On |
|------|------|-----------|
| 1 | `infrastructure/` — client, logging, cassettes, assertions, hooks, reporter, parallel | Nothing |
| 2 | `fixtures/` — all 6 data type JSONL files, workflow YAMLs, task schemas | Nothing |
| 3 | `conftest.py` — shared fixtures wiring everything together | Step 1 |
| 4 | `tier1_pipeline/` — 7 full pipeline tests (validates infrastructure works) | Steps 1-3 |
| 5 | `tier3_api_coverage/` — 28 API endpoint tests (maximum endpoint coverage) | Steps 1-3 |
| 6 | `tier2_workflows/` — 33 complex workflow tests | Steps 1-3 |
| 7 | `tier4_queue_review/` — 15 queue/review tests | Steps 1-3 |
| 8 | `tier5_agent_llm/` — 10 agent/LLM tests | Steps 1-3 |
| 9 | `tier6_quality/` — 10 quality/analytics tests | Steps 1-3 |
| 10 | `tier7_data_management/` — 15 data management tests | Steps 1-3 |
| 11 | `tier8_resilience/` — 13 resilience tests | Steps 1-3 |
| 12 | `tier9_cross_cutting/` — 12 cross-cutting tests | Steps 1-3 |
| 13 | VCR cassette recording — record real LLM responses for all hybrid/real tests | Steps 4-12 + API key |
| 14 | Parallel tuning — verify xdist groups, optimize worker count | Steps 4-12 |

Steps 4-12 can be developed in parallel by separate agents since each tier is independent once the infrastructure (steps 1-3) is in place.

## 13. Success Criteria

- All 143 tests pass with mocked LLM responses
- All 6 real LLM smoke tests pass with MiniMax 2.7
- Every API endpoint hit at least once across the suite
- All 20 workflow step types exercised
- All 4 queue ordering strategies tested
- All 7 review decision types tested
- All 8 agent roles tested
- All 6 data import formats + 3 export formats tested
- Parallel execution completes in under 5 minutes (mocked tests)
- Full structured logs + reports generated per run
- Agent can drive the pipeline via `E2ERunner` or CLI

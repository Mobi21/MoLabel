"""Structured logging setup for the E2E test suite.

Produces JSON log files (machine-readable) and human-readable console output.
Every test gets a TestContext that tracks API calls, timings, checkpoints,
and errors throughout the test run.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LOG_DIR = Path("tests/e2e/logs")


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "test_id": getattr(record, "test_id", None),
            "tier": getattr(record, "tier", None),
            "phase": getattr(record, "phase", None),
            "duration_ms": getattr(record, "duration_ms", None),
            "api_call": getattr(record, "api_call", None),
            "status_code": getattr(record, "status_code", None),
            "cli_command": getattr(record, "cli_command", None),
            "exit_code": getattr(record, "exit_code", None),
            "stdout_preview": getattr(record, "stdout_preview", None),
            "stderr_preview": getattr(record, "stderr_preview", None),
            "error": getattr(record, "error", None),
        }
        # Strip None values to keep log lines compact
        return json.dumps({k: v for k, v in log_entry.items() if v is not None})


def setup_logging(run_id: str) -> logging.Logger:
    """Initialise the E2E logger for a given run.

    Creates a JSONL file handler (machine-readable) and a human-readable
    console handler at INFO level.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"e2e_run_{run_id}.jsonl"

    logger = logging.getLogger("molabel.e2e")
    logger.setLevel(logging.DEBUG)
    # Avoid duplicate handlers when called multiple times in a session
    if logger.handlers:
        return logger

    # JSON file handler — machine-parseable event stream
    fh = logging.FileHandler(log_file)
    fh.setFormatter(JSONFormatter())
    logger.addHandler(fh)

    # Console handler — human-readable
    ch = logging.StreamHandler()
    ch.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s — %(message)s")
    )
    ch.setLevel(logging.INFO)
    logger.addHandler(ch)

    return logger


# ---------------------------------------------------------------------------
# Per-test observability types
# ---------------------------------------------------------------------------


@dataclass
class APICallLog:
    """Record of a single HTTP API call."""

    method: str
    path: str
    status_code: int
    duration_ms: float
    request_body: dict[str, Any] | None = None
    response_summary: str | None = None


@dataclass
class CliCommandLog:
    """Record of a single CLI transcript entry."""

    argv: list[str]
    cwd: str | None
    exit_code: int
    duration_ms: float
    stdout: str
    stderr: str
    command: str | None = None


@dataclass
class CheckpointLog:
    """Record of a single test checkpoint (assertion phase)."""

    name: str
    passed: bool
    duration_ms: float
    assertions_passed: int
    assertions_failed: int
    details: list[str] = field(default_factory=list)


@dataclass
class TestContext:
    """Full observability context for a single test scenario.

    Tracks all API calls, checkpoints, LLM stats, errors, and warnings
    for a single test run. Used by InstrumentedClient, checkpoint(), and
    the E2EReporter.
    """

    test_id: str
    tier: int
    name: str
    started_at: float = field(default_factory=time.monotonic)
    api_calls: list[APICallLog] = field(default_factory=list)
    checkpoints: list[CheckpointLog] = field(default_factory=list)
    cli_commands: list[CliCommandLog] = field(default_factory=list)
    llm_calls: int = 0
    llm_tokens_in: int = 0
    llm_tokens_out: int = 0
    real_llm_calls: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def log_api_call(
        self,
        method: str,
        path: str,
        status: int,
        duration_ms: float,
        body: dict[str, Any] | None = None,
        summary: str | None = None,
    ) -> None:
        self.api_calls.append(
            APICallLog(method, path, status, duration_ms, body, summary)
        )

    def log_checkpoint(
        self,
        name: str,
        passed: bool,
        duration_ms: float,
        passed_count: int,
        failed_count: int,
        details: list[str] | None = None,
    ) -> None:
        self.checkpoints.append(
            CheckpointLog(
                name, passed, duration_ms, passed_count, failed_count, details or []
            )
        )

    def log_cli_command(
        self,
        argv: list[str],
        *,
        cwd: str | None,
        exit_code: int,
        duration_ms: float,
        stdout: str,
        stderr: str,
        command: str | None = None,
    ) -> None:
        self.cli_commands.append(
            CliCommandLog(
                argv=list(argv),
                cwd=cwd,
                exit_code=exit_code,
                duration_ms=duration_ms,
                stdout=stdout,
                stderr=stderr,
                command=command,
            )
        )

    def elapsed_ms(self) -> float:
        return (time.monotonic() - self.started_at) * 1000

    def summary(self) -> dict[str, Any]:
        return {
            "test_id": self.test_id,
            "tier": self.tier,
            "name": self.name,
            "total_duration_ms": round(self.elapsed_ms(), 1),
            "api_calls": len(self.api_calls),
            "cli_commands": len(self.cli_commands),
            "checkpoints_passed": sum(1 for c in self.checkpoints if c.passed),
            "checkpoints_failed": sum(1 for c in self.checkpoints if not c.passed),
            "llm_calls": self.llm_calls,
            "real_llm_calls": self.real_llm_calls,
            "errors": len(self.errors),
            "warnings": len(self.warnings),
        }


def serialize_test_context(ctx: TestContext) -> dict[str, Any]:
    """Render the full per-test context into a JSON-serializable structure."""
    return {
        "summary": ctx.summary(),
        "api_calls": [asdict(call) for call in ctx.api_calls],
        "cli_commands": [asdict(command) for command in ctx.cli_commands],
        "checkpoints": [asdict(checkpoint) for checkpoint in ctx.checkpoints],
        "llm_calls": ctx.llm_calls,
        "llm_tokens_in": ctx.llm_tokens_in,
        "llm_tokens_out": ctx.llm_tokens_out,
        "real_llm_calls": ctx.real_llm_calls,
        "errors": list(ctx.errors),
        "warnings": list(ctx.warnings),
    }

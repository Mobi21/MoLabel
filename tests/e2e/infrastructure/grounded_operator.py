"""Helpers for live grounded operator benchmark e2e tests."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import uvicorn
import yaml
from sqlalchemy import create_engine, text

import molabel.core.workflow.engine as workflow_engine
from molabel.app.main import create_app
from molabel.app.services.session import get_or_create_app_secret
from molabel.core.database import create_all_tables
from molabel.core.quality.grounded_benchmarks import (
    GroundedBenchmarkBundle,
    load_grounded_benchmark,
    load_jsonl,
)
from molabel.core.types import Message
from tests.e2e.infrastructure.logging_config import TestContext


@dataclass(frozen=True)
class GroundedOperatorFixture:
    """Loaded grounded benchmark assets for an operator-oriented live run."""

    source_root: Path
    authority_root: Path
    workspace_root: Path
    bundle: GroundedBenchmarkBundle
    task_schema: dict[str, Any]
    workflow_doc: dict[str, Any]
    raw_records: list[dict[str, Any]]
    paper_gold_rows: list[dict[str, Any]]
    molabel_gold_rows: list[dict[str, Any]]
    human_rows: list[dict[str, Any]]
    review_rows: list[dict[str, Any]]
    original_hashes: dict[str, str]


@dataclass(frozen=True)
class CliTranscriptEntry:
    """Single CLI subprocess transcript entry."""

    label: str
    argv: list[str]
    cwd: str | None
    exit_code: int
    duration_ms: float
    stdout: str
    stderr: str


@dataclass(frozen=True)
class AgentExecResult:
    """Result of a single non-interactive agent operator run."""

    prompt: str
    runner: str  # "codex" or "claude"
    exit_code: int
    duration_ms: float
    stdout: str
    stderr: str
    events: list[dict[str, Any]]
    last_message: str | None
    agent_home: Path


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _copy_workspace(source_root: Path) -> Path:
    temp_dir = Path(
        tempfile.mkdtemp(prefix=f"molabel-grounded-operator-{source_root.name}-")
    )
    workspace_root = temp_dir / source_root.name
    shutil.copytree(source_root, workspace_root)
    return workspace_root


_BENCHMARK_LEAK_FIELDS = frozenset(
    {
        "source_label",
        "gold_label",
        "gold_labels",
        "ground_truth",
        "ground_truth_label",
        "ground_truth_labels",
    }
)


def _scrub_benchmark_value(raw: Any) -> Any:
    """Recursively drop benchmark-truth fields from operator-visible data."""
    if isinstance(raw, dict):
        sanitized: dict[str, Any] = {}
        for key, value in raw.items():
            if key.lower() in _BENCHMARK_LEAK_FIELDS:
                continue
            sanitized[key] = _scrub_benchmark_value(value)
        return sanitized
    if isinstance(raw, list):
        return [_scrub_benchmark_value(item) for item in raw]
    return raw


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=True, sort_keys=False) for row in rows)
        + ("\n" if rows else ""),
        encoding="utf-8",
    )


def _sanitize_operator_workspace(
    authority_root: Path,
    bundle: GroundedBenchmarkBundle,
) -> Path:
    """Create an operator-visible workspace stripped of truth-bearing assets."""
    operator_root = _copy_workspace(authority_root)

    # Remove hidden authority artifacts and benchmark truth references from the
    # operator-visible workspace; scoring continues against the authority copy.
    for relative in (
        "authority",
        "workbench/benchmarks/gold",
        "workbench/benchmarks/human-labels",
        "workbench/benchmarks/reviews",
    ):
        target = operator_root / relative
        if target.exists():
            shutil.rmtree(target)

    for relative in (
        "workbench/benchmarks/label-map.yaml",
        "workbench/benchmarks/metrics.yaml",
        "workbench/benchmarks/baselines.yaml",
        "workbench/benchmarks/operator.yaml",
        "workbench/benchmarks/paper.yaml",
        "workbench/benchmarks/scenario.yaml",
    ):
        target = operator_root / relative
        if target.exists():
            target.unlink()

    split_paths = {bundle.scenario.source_path, *bundle.scenario.split_paths}
    for relative in split_paths:
        if not relative:
            continue
        path = operator_root / relative
        if not path.exists() or path.suffix.lower() != ".jsonl":
            continue
        rows = load_jsonl(path)
        sanitized_rows = [
            _scrub_benchmark_value(row) if isinstance(row, dict) else row
            for row in rows
        ]
        _write_jsonl(path, sanitized_rows)

    (operator_root / "workbench" / "benchmarks" / "runs" / "live-operator").mkdir(
        parents=True, exist_ok=True
    )
    return operator_root


def hash_paths(root: Path, relative_paths: list[str]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative_path in relative_paths:
        if not relative_path:
            continue
        path = root / relative_path
        if path.exists():
            hashes[relative_path] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def _find_free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _preview(text: str, limit: int = 512) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}…"


class GroundedBackendServer:
    """Run a local MoLabel backend with deterministic, file-backed state."""

    def __init__(self, ctx: TestContext, workspace_root: Path, repo_root: Path) -> None:
        self.ctx = ctx
        self.workspace_root = workspace_root
        self.repo_root = repo_root
        self._tempdir = tempfile.TemporaryDirectory(
            prefix=f"molabel-grounded-backend-{workspace_root.name}-"
        )
        self.temp_root = Path(self._tempdir.name)
        self.workbench_root = self.temp_root / "workbench"
        self.workbench_root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.temp_root / "grounded.sqlite"
        self.base_url = f"http://127.0.0.1:{_find_free_port()}"
        self.config_path = self.temp_root / "cli-config.json"
        self._thread: threading.Thread | None = None
        self._server: uvicorn.Server | None = None
        self._original_signal_handler = workflow_engine.signal.signal
        self._original_signal_alarm = workflow_engine.signal.alarm

        app = create_app()
        engine = create_engine(
            f"sqlite:///{self.db_path}",
            connect_args={"check_same_thread": False},
        )
        create_all_tables(engine)
        app.state.engine = engine
        app.state.app_secret = get_or_create_app_secret(self.workbench_root)

        def _noop_signal(_signum: int, _handler: Any) -> None:
            return None

        def _noop_alarm(_seconds: int) -> int:
            return 0

        workflow_engine.signal.signal = _noop_signal
        workflow_engine.signal.alarm = _noop_alarm

        @app.middleware("http")
        async def _record_request(request, call_next):  # type: ignore[no-untyped-def]
            start = time.monotonic()
            body_bytes = await request.body()
            parsed_body: dict[str, Any] | None = None
            if body_bytes:
                try:
                    loaded = json.loads(body_bytes.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    loaded = None
                if isinstance(loaded, dict):
                    parsed_body = loaded

            path = request.url.path
            if request.url.query:
                path = f"{path}?{request.url.query}"

            try:
                response = await call_next(request)
            except Exception:
                duration_ms = (time.monotonic() - start) * 1000
                self.ctx.log_api_call(
                    method=request.method,
                    path=path,
                    status=500,
                    duration_ms=round(duration_ms, 1),
                    body=parsed_body,
                    summary="500 from middleware exception",
                )
                raise

            duration_ms = (time.monotonic() - start) * 1000
            self.ctx.log_api_call(
                method=request.method,
                path=path,
                status=response.status_code,
                duration_ms=round(duration_ms, 1),
                body=parsed_body,
                summary=f"{response.status_code} in {duration_ms:.0f}ms",
            )
            return response

        self.app = app
        self.engine = engine
        self.config_path.write_text(
            json.dumps(
                {
                    "baseUrl": self.base_url,
                    "workspaceRoot": str(self.workspace_root),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    @property
    def started(self) -> bool:
        return bool(self._server and self._server.started)

    def start(self) -> None:
        if self._thread is not None:
            return

        config = uvicorn.Config(
            self.app,
            host="127.0.0.1",
            port=int(self.base_url.rsplit(":", 1)[1]),
            log_level="warning",
            lifespan="off",
        )
        server = uvicorn.Server(config)
        self._server = server

        def _run() -> None:
            server.run()

        thread = threading.Thread(target=_run, name="grounded-backend", daemon=True)
        thread.start()
        self._thread = thread

        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if server.started:
                return
            if not thread.is_alive():
                break
            time.sleep(0.05)

        raise RuntimeError("Grounded backend server failed to start")

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
            self._server.force_exit = True
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self._thread = None

    def close(self) -> None:
        try:
            self.stop()
        finally:
            workflow_engine.signal.signal = self._original_signal_handler
            workflow_engine.signal.alarm = self._original_signal_alarm
            self._tempdir.cleanup()


class GroundedCliHarness:
    """Transcript-capturing wrapper around the public ``molabel`` CLI."""

    def __init__(self, ctx: TestContext, workspace_root: Path, repo_root: Path) -> None:
        self.ctx = ctx
        self.workspace_root = workspace_root
        self.repo_root = repo_root
        self.server = GroundedBackendServer(ctx, workspace_root, repo_root)
        self.server.start()
        self.cli_bin = repo_root / "cli" / "dist" / "bin" / "molabel.js"
        self.node_bin = "node"
        self.codex_bin = shutil.which("codex") or "codex"
        self.claude_bin = shutil.which("claude") or "claude"

    def __enter__(self) -> GroundedCliHarness:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        self.close()

    @property
    def base_cli_args(self) -> list[str]:
        return [
            self.node_bin,
            str(self.cli_bin),
            "--config",
            str(self.server.config_path),
            "--json",
        ]

    def close(self) -> None:
        self.server.close()

    def _prepare_codex_home(self) -> Path:
        codex_home = self.server.temp_root / "codex-home"
        codex_home.mkdir(parents=True, exist_ok=True)

        source_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
        for filename in ("auth.json", "config.toml"):
            source = source_home / filename
            destination = codex_home / filename
            if source.exists():
                shutil.copy2(source, destination)

        skills_root = codex_home / "skills" / "molabel-cli"
        shutil.copytree(
            self.repo_root / "cli" / "skills" / "shared",
            skills_root / "shared",
            dirs_exist_ok=True,
        )
        shutil.copytree(
            self.repo_root / "cli" / "skills" / "codex",
            skills_root,
            dirs_exist_ok=True,
        )
        return codex_home

    def _prepare_operator_env(self) -> dict[str, str]:
        env = dict(os.environ)
        codex_home = self._prepare_codex_home()

        xdg_config_home = self.server.temp_root / "xdg-config"
        molabel_config_dir = xdg_config_home / "molabel"
        molabel_config_dir.mkdir(parents=True, exist_ok=True)
        (molabel_config_dir / "cli.json").write_text(
            json.dumps(
                {
                    "baseUrl": self.server.base_url,
                    "workspaceRoot": str(self.workspace_root),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        bin_dir = self.server.temp_root / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        molabel_wrapper = bin_dir / "molabel"
        molabel_wrapper.write_text(
            "#!/bin/sh\n"
            f'exec "{shutil.which("node") or self.node_bin}" "{self.cli_bin}" "$@"\n',
            encoding="utf-8",
        )
        molabel_wrapper.chmod(0o755)

        env["CODEX_HOME"] = str(codex_home)
        env["XDG_CONFIG_HOME"] = str(xdg_config_home)
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        return env

    async def run_json(
        self,
        label: str,
        *args: str,
        cwd: Path | None = None,
    ) -> Any:
        argv = [*self.base_cli_args, *args]
        start = time.monotonic()
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(cwd or self.workspace_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_b, stderr_b = await proc.communicate()
        duration_ms = (time.monotonic() - start) * 1000
        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")
        self.ctx.log_cli_command(
            argv=list(argv),
            cwd=str(cwd or self.workspace_root),
            exit_code=proc.returncode,
            duration_ms=round(duration_ms, 1),
            stdout=stdout,
            stderr=stderr,
            command=label,
        )
        if proc.returncode != 0:
            raise AssertionError(
                f"{label} failed with exit code {proc.returncode}: "
                f"{_preview(stderr or stdout)}"
            )
        text = stdout.strip()
        if not text:
            return {}
        return json.loads(text)

    async def run_codex_prompt(
        self,
        prompt: str,
        *,
        cwd: Path | None = None,
    ) -> AgentExecResult:
        env = self._prepare_operator_env()
        last_message_path = self.server.temp_root / "codex-last-message.txt"
        argv = [
            self.codex_bin,
            "exec",
            "--json",
            "--skip-git-repo-check",
            "--sandbox",
            "workspace-write",
            "-C",
            str(cwd or self.workspace_root),
            "-o",
            str(last_message_path),
            "-",
        ]
        timeout_secs = int(os.environ.get("MOLABEL_OPERATOR_TIMEOUT_SECS", "1500"))
        timed_out = False
        start = time.monotonic()
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(cwd or self.workspace_root),
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(prompt.encode("utf-8")),
                timeout=timeout_secs,
            )
        except TimeoutError:
            timed_out = True
            proc.kill()
            await proc.wait()
            # Read whatever partial output was buffered
            stdout_b = await proc.stdout.read() if proc.stdout else b""
            stderr_b = await proc.stderr.read() if proc.stderr else b""
        duration_ms = (time.monotonic() - start) * 1000
        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")
        if timed_out:
            stderr += f"\n[molabel] codex exec timed out after {timeout_secs}s"
        self.ctx.log_cli_command(
            argv=list(argv),
            cwd=str(cwd or self.workspace_root),
            exit_code=proc.returncode,
            duration_ms=round(duration_ms, 1),
            stdout=stdout,
            stderr=stderr,
            command="codex exec",
        )
        events: list[dict[str, Any]] = []
        for line in stdout.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                events.append(parsed)

        last_message = (
            last_message_path.read_text(encoding="utf-8").strip()
            if last_message_path.exists()
            else None
        )
        return AgentExecResult(
            prompt=prompt,
            runner="codex",
            exit_code=proc.returncode if proc.returncode is not None else -1,
            duration_ms=round(duration_ms, 1),
            stdout=stdout,
            stderr=stderr,
            events=events,
            last_message=last_message or None,
            agent_home=Path(env["CODEX_HOME"]),
        )

    def _prepare_claude_env(self) -> dict[str, str]:
        """Prepare environment for a Claude Code operator run.

        Uses the user's normal Claude Code auth (OAuth/keychain) by not
        overriding ``ANTHROPIC_API_KEY`` for Claude's own brain.  The MoLabel
        backend gets its MiniMax key from ``XDG_CONFIG_HOME`` CLI config.
        """
        env = dict(os.environ)

        xdg_config_home = self.server.temp_root / "xdg-config"
        molabel_config_dir = xdg_config_home / "molabel"
        molabel_config_dir.mkdir(parents=True, exist_ok=True)
        (molabel_config_dir / "cli.json").write_text(
            json.dumps(
                {
                    "baseUrl": self.server.base_url,
                    "workspaceRoot": str(self.workspace_root),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        bin_dir = self.server.temp_root / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        molabel_wrapper = bin_dir / "molabel"
        molabel_wrapper.write_text(
            "#!/bin/sh\n"
            f'exec "{shutil.which("node") or self.node_bin}" "{self.cli_bin}" "$@"\n',
            encoding="utf-8",
        )
        molabel_wrapper.chmod(0o755)

        env["XDG_CONFIG_HOME"] = str(xdg_config_home)
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        return env

    def _build_claude_skill_prompt(self) -> str:
        """Assemble the MoLabel Claude Code skill as a system prompt appendix."""
        parts: list[str] = []
        shared_agents = self.repo_root / "cli" / "skills" / "shared" / "AGENTS.md"
        if shared_agents.exists():
            parts.append(shared_agents.read_text(encoding="utf-8").strip())
        claude_skill = self.repo_root / "cli" / "skills" / "claude-code" / "SKILL.md"
        if claude_skill.exists():
            # Strip YAML frontmatter
            raw = claude_skill.read_text(encoding="utf-8")
            if raw.startswith("---"):
                end = raw.find("---", 3)
                if end != -1:
                    raw = raw[end + 3 :].strip()
            parts.append(raw)
        return "\n\n".join(parts)

    async def run_claude_prompt(
        self,
        prompt: str,
        *,
        cwd: Path | None = None,
    ) -> AgentExecResult:
        """Run a single non-interactive Claude Code prompt."""
        env = self._prepare_claude_env()
        skill_prompt = self._build_claude_skill_prompt()

        timeout_secs = int(os.environ.get("MOLABEL_OPERATOR_TIMEOUT_SECS", "1500"))
        timed_out = False
        work_dir = cwd or self.workspace_root
        argv = [
            self.claude_bin,
            "-p",
            "--output-format",
            "stream-json",
            "--verbose",
            "--dangerously-skip-permissions",
            "--no-session-persistence",
            "--disable-slash-commands",
            "--tools",
            "Bash",
            "--max-budget-usd",
            os.environ.get("MOLABEL_OPERATOR_BUDGET_USD", "10.00"),
            "--append-system-prompt",
            skill_prompt,
            "--add-dir",
            str(work_dir),
        ]
        start = time.monotonic()
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(work_dir),
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(prompt.encode("utf-8")),
                timeout=timeout_secs,
            )
        except TimeoutError:
            timed_out = True
            proc.kill()
            await proc.wait()
            # Read whatever partial output was buffered
            stdout_b = await proc.stdout.read() if proc.stdout else b""
            stderr_b = await proc.stderr.read() if proc.stderr else b""
        duration_ms = (time.monotonic() - start) * 1000
        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")
        if timed_out:
            stderr += f"\n[molabel] claude -p timed out after {timeout_secs}s"
        self.ctx.log_cli_command(
            argv=list(argv),
            cwd=str(work_dir),
            exit_code=proc.returncode,
            duration_ms=round(duration_ms, 1),
            stdout=stdout,
            stderr=stderr,
            command="claude -p",
        )

        events: list[dict[str, Any]] = []
        last_message: str | None = None
        last_assistant_text: str | None = None
        for line in stdout.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                events.append(parsed)
                # Capture latest assistant text as fallback (e.g. budget exhausted)
                if parsed.get("type") == "assistant" and "message" in parsed:
                    msg = parsed["message"]
                    if isinstance(msg, dict):
                        for block in msg.get("content", []):
                            if isinstance(block, dict) and block.get("type") == "text":
                                last_assistant_text = block.get("text")
                # Extract the final result text
                if parsed.get("type") == "result" and "result" in parsed:
                    last_message = str(parsed["result"]) if parsed["result"] else None

        return AgentExecResult(
            prompt=prompt,
            runner="claude",
            exit_code=proc.returncode if proc.returncode is not None else -1,
            duration_ms=round(duration_ms, 1),
            stdout=stdout,
            stderr=stderr,
            events=events,
            last_message=last_message or last_assistant_text,
            agent_home=Path(env.get("HOME", str(Path.home()))),
        )

    async def run_agent_prompt(
        self,
        prompt: str,
        *,
        runner: str | None = None,
        cwd: Path | None = None,
    ) -> AgentExecResult:
        """Run a single-prompt operator benchmark with the best available runner.

        If *runner* is ``None``, auto-detect: prefer Claude Code, fall back to
        Codex.
        """
        if runner is None:
            runner = self.detect_runner()

        if runner == "claude":
            return await self.run_claude_prompt(prompt, cwd=cwd)
        elif runner == "codex":
            return await self.run_codex_prompt(prompt, cwd=cwd)
        else:
            raise ValueError(f"Unknown runner: {runner!r}")

    def detect_runner(self) -> str:
        """Return the best available runner: ``'claude'`` or ``'codex'``."""
        if shutil.which("claude"):
            return "claude"
        if shutil.which("codex"):
            return "codex"
        raise RuntimeError(
            "No supported agent runner found on PATH. "
            "Install Claude Code (claude) or Codex (codex)."
        )

    def extract_shell_commands(self, events: list[dict[str, Any]]) -> list[str]:
        """Best-effort extraction of shell commands from agent transcript events.

        Handles both Codex JSONL (``command``/``cmd``/``argv`` keys) and
        Claude Code stream-json (``tool_use`` blocks with ``name: "Bash"``).
        """

        commands: list[str] = []

        def _walk(value: Any) -> None:
            if isinstance(value, dict):
                # Claude Code: tool_use content blocks inside assistant messages
                if value.get("type") == "tool_use" and value.get("name") == "Bash":
                    inp = value.get("input", {})
                    if isinstance(inp, dict) and "command" in inp:
                        commands.append(inp["command"])
                        return
                # Claude Code: assistant message with content blocks
                if value.get("type") == "assistant" and "message" in value:
                    msg = value["message"]
                    if isinstance(msg, dict):
                        for block in msg.get("content", []):
                            if isinstance(block, dict):
                                _walk(block)
                    return
                # Codex: direct command/cmd/argv keys
                for key, nested in value.items():
                    if key in {"command", "cmd"} and isinstance(nested, str):
                        commands.append(nested)
                    elif key == "argv" and isinstance(nested, list):
                        commands.append(" ".join(str(part) for part in nested))
                    else:
                        _walk(nested)
                return
            if isinstance(value, list):
                for nested in value:
                    _walk(nested)

        for event in events:
            _walk(event)
        return commands

    def find_record_payload_leaks(
        self,
        leak_fields: set[str] | None = None,
    ) -> dict[str, list[str]]:
        """Return any imported record payloads still containing leak fields."""
        leak_names = {
            field.lower() for field in (leak_fields or _BENCHMARK_LEAK_FIELDS)
        }
        leaked: dict[str, list[str]] = {}

        def _collect(raw: Any, path: str = "") -> list[str]:
            found: list[str] = []
            if isinstance(raw, dict):
                for key, value in raw.items():
                    next_path = f"{path}.{key}" if path else key
                    if key.lower() in leak_names:
                        found.append(next_path)
                    found.extend(_collect(value, next_path))
            elif isinstance(raw, list):
                for idx, value in enumerate(raw):
                    found.extend(_collect(value, f"{path}[{idx}]"))
            return found

        with self.server.engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT external_id, payload FROM records ORDER BY external_id ASC"
                )
            ).all()

        for external_id, payload in rows:
            parsed = payload
            if isinstance(payload, str):
                try:
                    parsed = json.loads(payload)
                except json.JSONDecodeError:
                    parsed = None
            found = _collect(parsed)
            if found:
                leaked[str(external_id)] = found
        return leaked

    def load_latest_review_submissions(self) -> list[dict[str, Any]]:
        """Load the latest submitted review labels keyed by source record ID."""

        latest_by_record: dict[str, dict[str, Any]] = {}
        with self.server.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT records.external_id, review_events.labels
                    FROM review_events
                    JOIN records ON records.id = review_events.record_id
                    ORDER BY review_events.created_at ASC
                    """
                )
            ).all()

        for external_id, labels in rows:
            if external_id is None:
                continue
            parsed_labels = labels
            if isinstance(labels, str):
                try:
                    parsed_labels = json.loads(labels)
                except json.JSONDecodeError:
                    parsed_labels = {}
            latest_by_record[str(external_id)] = {
                "record_id": str(external_id),
                "labels": dict(parsed_labels or {}),
            }
        return list(latest_by_record.values())

    def load_review_events(self) -> list[dict[str, Any]]:
        """Load review events in persisted order for diagnostic analysis."""
        results: list[dict[str, Any]] = []
        with self.server.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT records.external_id,
                           review_events.labels,
                           review_events.decision,
                           review_events.source,
                           review_events.ai_was_revealed,
                           review_events.created_at
                    FROM review_events
                    JOIN records ON records.id = review_events.record_id
                    ORDER BY review_events.created_at ASC
                    """
                )
            ).all()

        for external_id, labels, decision, source, ai_was_revealed, created_at in rows:
            if external_id is None:
                continue
            parsed_labels = labels
            if isinstance(labels, str):
                try:
                    parsed_labels = json.loads(labels)
                except json.JSONDecodeError:
                    parsed_labels = {}
            results.append(
                {
                    "record_id": str(external_id),
                    "labels": dict(parsed_labels or {}),
                    "decision": str(decision or ""),
                    "source": str(source or ""),
                    "ai_was_revealed": bool(ai_was_revealed),
                    "created_at": str(created_at or ""),
                }
            )
        return results

    def load_agent_outputs(self) -> list[dict[str, Any]]:
        """Load agent_outputs (LLM proposals) keyed by source record ID."""
        results: list[dict[str, Any]] = []
        with self.server.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT records.external_id, agent_outputs.labels,
                           agent_outputs.raw_response
                    FROM agent_outputs
                    JOIN records ON records.id = agent_outputs.record_id
                    ORDER BY agent_outputs.created_at ASC
                    """
                )
            ).all()
        for external_id, labels, raw_response in rows:
            if external_id is None:
                continue
            parsed_labels = labels
            if isinstance(labels, str):
                try:
                    parsed_labels = json.loads(labels)
                except json.JSONDecodeError:
                    parsed_labels = {}
            parsed_raw = raw_response
            if isinstance(raw_response, str):
                try:
                    parsed_raw = json.loads(raw_response)
                except json.JSONDecodeError:
                    parsed_raw = {}
            results.append(
                {
                    "record_id": str(external_id),
                    "labels": dict(parsed_labels or {}),
                    "raw_response": parsed_raw or {},
                }
            )
        return results

    _KNOWN_TABLES = frozenset(
        {
            "datasets",
            "records",
            "prompt_templates",
            "workflow_definitions",
            "model_profiles",
            "review_events",
            "adjudications",
            "workspaces",
            "task_schemas",
            "snapshots",
        }
    )

    def table_row_count(self, table_name: str) -> int:
        """Return the row count for a known benchmark table."""
        if table_name not in self._KNOWN_TABLES:
            raise ValueError(f"Unknown table: {table_name!r}")

        with self.server.engine.connect() as conn:
            row = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).first()
        return int(row[0]) if row is not None and row[0] is not None else 0

    async def bootstrap_workspace(self, workspace_name: str) -> dict[str, Any]:
        return await self.run_json(
            "workspace bootstrap",
            "workspace",
            "bootstrap",
            str(self.workspace_root),
            "--workspace-name",
            workspace_name,
        )

    async def create_dataset(
        self,
        *,
        name: str,
        source_type: str,
        loader_plugin: str,
        record_kind: str,
    ) -> dict[str, Any]:
        return await self.run_json(
            "dataset create",
            "dataset",
            "create",
            "--name",
            name,
            "--source-type",
            source_type,
            "--loader-plugin",
            loader_plugin,
            "--record-kind",
            record_kind,
            "--canonical-id-strategy",
            "source_record_id",
            "--indexing-mode",
            "projection",
        )

    async def import_dataset(self, dataset_id: str, source_uri: str) -> dict[str, Any]:
        return await self.run_json(
            "dataset import",
            "dataset",
            "import",
            dataset_id,
            "--source-uri",
            source_uri,
        )

    async def create_task_schema(self, file_path: Path) -> dict[str, Any]:
        return await self.run_json(
            "task-schema create",
            "task-schema",
            "create",
            "--file",
            str(file_path),
        )

    async def create_prompt(
        self,
        *,
        name: str,
        task_schema_id: str,
        system_instructions: str,
        task_rubric: str,
    ) -> dict[str, Any]:
        return await self.run_json(
            "prompt create",
            "prompt",
            "create",
            "--name",
            name,
            "--agent-role",
            "proposer",
            "--task-schema-id",
            task_schema_id,
            "--system-instructions",
            system_instructions,
            "--task-rubric",
            task_rubric,
        )

    async def provider_health(
        self,
        provider_type: str,
        *,
        auth_ref: str,
        provider_base_url: str | None = None,
    ) -> dict[str, Any]:
        args = ["provider", "health", provider_type, "--auth-ref", auth_ref]
        if provider_base_url:
            args.extend(["--provider-base-url", provider_base_url])
        return await self.run_json("provider health", *args)

    async def create_model_profile(
        self,
        *,
        slug: str,
        provider_type: str,
        provider_name: str,
        model_identifier: str,
        auth_ref: str,
        provider_base_url: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model_profile_slug": slug,
            "provider_type": provider_type,
            "provider_name": provider_name,
            "model_identifier": model_identifier,
            "auth_ref": auth_ref,
            "supports_structured_output": True,
        }
        if provider_base_url:
            body["base_url"] = provider_base_url
        return await self.run_json(
            "model-profile create",
            "model-profile",
            "create",
            "--body-text",
            json.dumps(body),
        )

    async def test_model_profile(self, profile_id: str) -> dict[str, Any]:
        return await self.run_json(
            "model-profile test",
            "model-profile",
            "test",
            profile_id,
        )

    async def create_workflow(self, file_path: Path) -> dict[str, Any]:
        return await self.run_json(
            "workflow create",
            "workflow",
            "create",
            "--file",
            str(file_path),
        )

    async def run_workflow(self, selector: str) -> dict[str, Any]:
        return await self.run_json(
            "workflow run",
            "workflow",
            "run",
            selector,
        )

    async def get_workflow_execution(
        self, selector: str, execution_id: str
    ) -> dict[str, Any]:
        return await self.run_json(
            "workflow execution",
            "workflow",
            "execution",
            selector,
            execution_id,
        )

    async def advance_workflow_step(
        self, selector: str, execution_id: str, step_id: str
    ) -> dict[str, Any]:
        return await self.run_json(
            "workflow advance",
            "workflow",
            "advance",
            selector,
            execution_id,
            step_id,
        )

    async def claim_queue(self, queue_id: str) -> dict[str, Any]:
        return await self.run_json("queue claim", "queue", "claim", queue_id)

    async def queue_status(self, queue_id: str) -> dict[str, Any]:
        return await self.run_json("queue status", "queue", "status", queue_id)

    async def review_submit(
        self,
        task_id: str,
        *,
        labels: dict[str, Any],
        decision: str,
        rationale: str,
    ) -> dict[str, Any]:
        return await self.run_json(
            "review submit",
            "review",
            "submit",
            task_id,
            "--labels-json",
            json.dumps(labels),
            "--decision",
            decision,
            "--rationale",
            rationale,
            "--no-auto-claim-next",
        )

    async def adjudication_detect(
        self, task_schema_id: str, events_by_record: dict[str, list[dict[str, Any]]]
    ) -> dict[str, Any]:
        return await self.run_json(
            "adjudication detect",
            "adjudication",
            "detect",
            "--task-schema-id",
            task_schema_id,
            "--events-json",
            json.dumps(events_by_record),
        )

    async def adjudication_build(
        self, task_schema_id: str, events_by_record: dict[str, list[dict[str, Any]]]
    ) -> dict[str, Any]:
        return await self.run_json(
            "adjudication build",
            "adjudication",
            "build",
            "--task-schema-id",
            task_schema_id,
            "--events-json",
            json.dumps(events_by_record),
        )

    async def adjudication_queue(self) -> dict[str, Any]:
        return await self.run_json("adjudication queue", "adjudication", "queue")

    def lookup_source_record_id(self, record_id: str) -> str | None:
        """Return the source/external record ID for a workflow-ingest record."""
        with self.server.engine.connect() as conn:
            row = conn.execute(
                text("SELECT external_id FROM records WHERE id = :record_id"),
                {"record_id": record_id},
            ).first()
        if row is None or row[0] is None:
            return None
        return str(row[0])

    async def adjudication_resolve(
        self,
        queue_item_id: str,
        *,
        resolved_labels: dict[str, Any],
        rationale: str,
    ) -> dict[str, Any]:
        return await self.run_json(
            "adjudication resolve",
            "adjudication",
            "resolve",
            queue_item_id,
            "--resolution",
            "resolve",
            "--resolved-labels-json",
            json.dumps(resolved_labels),
            "--rationale",
            rationale,
        )


def resolve_auth_ref(repo_root: Path) -> str | None:
    """Resolve MiniMax auth via Anthropic-compatible credentials."""
    dotenv_path = repo_root / ".env"
    if dotenv_path.exists():
        for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :].strip()
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'").strip('"'))

    if os.environ.get("ANTHROPIC_API_KEY"):
        return "ANTHROPIC_API_KEY"
    if os.environ.get("MINIMAX_API_KEY"):
        os.environ.setdefault("ANTHROPIC_API_KEY", os.environ["MINIMAX_API_KEY"])
        return "ANTHROPIC_API_KEY"
    return None


def prepare_grounded_operator_fixture(source_root: Path) -> GroundedOperatorFixture:
    """Load and copy a grounded benchmark fixture for live operator testing."""
    authority_root = _copy_workspace(source_root)
    bundle = load_grounded_benchmark(authority_root)
    workspace_root = _sanitize_operator_workspace(authority_root, bundle)

    task_schema = _load_yaml(workspace_root / bundle.scenario.task_schema_path)
    workflow_doc = _load_yaml(workspace_root / bundle.scenario.workflow_path)
    raw_records = load_jsonl(workspace_root / bundle.scenario.source_path)
    paper_gold_rows = load_jsonl(
        authority_root
        / (bundle.scenario.paper_gold_path or bundle.scenario.gold_labels_path)
    )
    molabel_gold_rows = load_jsonl(
        authority_root
        / (bundle.scenario.molabel_gold_path or bundle.scenario.gold_labels_path)
    )
    human_rows: list[dict[str, Any]] = []
    for relative_path in bundle.scenario.human_label_paths:
        human_rows.extend(load_jsonl(authority_root / relative_path))
    review_rows: list[dict[str, Any]] = []
    for relative_path in bundle.scenario.review_paths:
        review_rows.extend(load_jsonl(authority_root / relative_path))

    original_hashes = hash_paths(
        authority_root,
        [
            "workbench.project.yaml",
            bundle.scenario.paper_metadata_path,
            bundle.scenario.label_map_path,
            bundle.scenario.metrics_path,
            bundle.scenario.baselines_path,
            bundle.scenario.operator_path or "",
            bundle.scenario.gold_labels_path,
            bundle.scenario.paper_gold_path or "",
            bundle.scenario.molabel_gold_path or "",
            *bundle.scenario.human_label_paths,
            *bundle.scenario.review_paths,
            bundle.scenario.task_schema_path,
            bundle.scenario.workflow_path,
        ],
    )

    return GroundedOperatorFixture(
        source_root=source_root,
        authority_root=authority_root,
        workspace_root=workspace_root,
        bundle=bundle,
        task_schema=task_schema,
        workflow_doc=workflow_doc,
        raw_records=raw_records,
        paper_gold_rows=paper_gold_rows,
        molabel_gold_rows=molabel_gold_rows,
        human_rows=human_rows,
        review_rows=review_rows,
        original_hashes=original_hashes,
    )


def build_output_schema(
    task_schema: dict[str, Any],
    benchmark_id: str,
) -> dict[str, Any]:
    """Convert a grounded task schema into an Anthropic structured output schema."""
    properties: dict[str, Any] = {}
    required: list[str] = []

    for field in task_schema.get("label_fields", []):
        field_name = field["name"]
        field_type = field["field_type"]

        if field_type == "categorical":
            properties[field_name] = {
                "type": "string",
                "enum": field.get("options", []),
            }
        elif field_type == "bool":
            properties[field_name] = {"type": "boolean"}
        elif field_type == "numeric":
            properties[field_name] = {"type": "number"}
        elif field_type == "multi_select":
            properties[field_name] = {
                "type": "array",
                "items": {"type": "string", "enum": field.get("options", [])},
            }
        elif field_type == "json" and field_name == "evidence_atoms":
            properties[field_name] = {"type": "array", "items": {"type": "string"}}
        elif field_type == "json" and field_name == "rationale_token_mask":
            properties[field_name] = {"type": "array", "items": {"type": "integer"}}
        else:
            properties[field_name] = {"type": "string"}

        if field.get("required", True):
            required.append(field_name)

    return {
        "title": f"{benchmark_id}_grounded_labels",
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required,
    }


def build_messages(
    *,
    agents_prompt: str,
    task_schema: dict[str, Any],
    benchmark_name: str,
    description: str,
    record: dict[str, Any],
    record_id: str,
) -> list[Message]:
    """Construct live MiniMax messages for a grounded benchmark record."""
    system_prompt = (
        f"{agents_prompt.strip()}\n\n"
        "The current MoLabel labeling engine under test is MiniMax 2.7.\n"
        f"Task schema title: {task_schema['title']}\n"
        f"Task instructions: {task_schema.get('instructions', '')}\n"
        "Return only the structured JSON object."
    )
    # Strip fields that leak gold labels to avoid contaminating the baseline
    _LEAK_FIELDS = {"source_label", "gold_label", "label", "ground_truth"}
    sanitized = {k: v for k, v in record.items() if k not in _LEAK_FIELDS}
    user_prompt = (
        f"Grounded benchmark: {benchmark_name}\n"
        f"Benchmark description: {description}\n"
        f"Record ID: {record_id}\n"
        "Raw record:\n"
        f"{json.dumps(sanitized, indent=2, ensure_ascii=True)}"
    )
    return [
        Message(role="system", content=system_prompt),
        Message(role="user", content=user_prompt),
    ]


def workflow_payload_from_document(workflow_doc: dict[str, Any]) -> dict[str, Any]:
    """Convert a grounded workflow YAML document into the workflows API shape."""
    steps: list[dict[str, Any]] = []
    for step in workflow_doc.get("steps", []):
        if not isinstance(step, dict):
            continue
        steps.append(
            {
                "step_id": step.get("id", ""),
                "step_type": step.get("type", ""),
                "label": step.get("label"),
                "config": step.get("config", {}),
                "position": step.get("position"),
            }
        )

    return {
        "name": workflow_doc.get("name", "Grounded Operator Workflow"),
        "description": workflow_doc.get("description"),
        "steps": steps,
        "edges": workflow_doc.get("edges", []),
    }


def build_runtime_grounded_workflow_document(
    *,
    bundle: GroundedBenchmarkBundle,
    task_schema_id: str,
) -> dict[str, Any]:
    """Create a runtime-valid operator workflow for a grounded fixture.

    The shipped grounded workflow fixtures still contain legacy step types in
    some scenarios. The harness materializes a runtime-valid workflow that uses
    the current engine's built-in step types while preserving the grounded
    source path and benchmark-specific review/adjudication flow.
    """
    return {
        "name": f"{bundle.scenario.name} Operator Workflow",
        "description": (
            f"Runtime-valid operator workflow for {bundle.scenario.benchmark_id}."
        ),
        "steps": [
            {
                "id": "ingest",
                "type": "data_ingest",
                "config": {
                    "source": bundle.scenario.source_path,
                },
            },
            {
                "id": "normalize",
                "type": "data_normalize",
                "config": {
                    "schema_ref": bundle.scenario.task_schema_path,
                },
            },
            {
                "id": "review",
                "type": "human_review",
                "config": {
                    "sample_strategy": "all",
                    "task_schema_id": task_schema_id,
                    "breakpoint": True,
                },
            },
            {
                "id": "adjudicate",
                "type": "human_adjudication",
                "config": {
                    "adjudication_policy": "expert_consensus",
                },
            },
            {
                "id": "score",
                "type": "quality_check",
                "config": {
                    "min_agreement": 0.75,
                    "min_coverage": 1.0,
                },
            },
            {
                "id": "snapshot",
                "type": "snapshot",
                "config": {
                    "snapshot_name": (
                        f"{bundle.scenario.benchmark_id}_grounded_reference"
                    ),
                },
            },
        ],
    }


def intentionally_wrong_record_ids(
    *rows: list[dict[str, Any]],
) -> set[str]:
    """Collect benchmark records marked as intentionally wrong."""
    wrong: set[str] = set()
    for row_set in rows:
        for row in row_set:
            if row.get("is_intentionally_wrong"):
                wrong.add(str(row["record_id"]))
    return wrong


def build_disagreement_events(
    *,
    conflicting_rows: list[dict[str, Any]],
    resolved_labels_by_record: dict[str, dict[str, Any]],
    resolved_reviewer_id: str = "benchmark-resolver",
) -> dict[str, list[dict[str, Any]]]:
    """Build adjudication inputs from benchmark human artifacts and resolved gold."""
    review_events_by_record: dict[str, list[dict[str, Any]]] = {}
    for row in conflicting_rows:
        record_id = str(row["record_id"])
        review_events_by_record.setdefault(record_id, []).append(
            {
                "id": row.get("review_event_id", row.get("id", record_id)),
                "reviewer_id": str(row.get("reviewer_id", "human")),
                "labels": dict(row.get("labels", {})),
                "decision": row.get("decision", "accept"),
                "source": row.get("source", "human"),
                "rationale": row.get("rationale"),
            }
        )

    for record_id, labels in resolved_labels_by_record.items():
        review_events_by_record.setdefault(record_id, []).append(
            {
                "id": f"resolved-{record_id}",
                "reviewer_id": resolved_reviewer_id,
                "labels": dict(labels),
                "decision": "accept",
                "source": "benchmark-resolver",
                "rationale": "Paper-faithful resolution for benchmark adjudication.",
            }
        )

    return review_events_by_record


def build_adjudication_events(
    *,
    conflicting_rows: list[dict[str, Any]],
    resolved_labels_by_record: dict[str, dict[str, Any]],
    resolved_reviewer_id: str = "benchmark-resolver",
) -> dict[str, list[dict[str, Any]]]:
    """Alias for benchmark-adjudication event construction."""
    return build_disagreement_events(
        conflicting_rows=conflicting_rows,
        resolved_labels_by_record=resolved_labels_by_record,
        resolved_reviewer_id=resolved_reviewer_id,
    )

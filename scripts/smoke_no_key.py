"""No-key end-to-end smoke test: import, offline pre-label, review, export.

It then creates the agent_comparison template, which leaves a model unset,
once with no model and once on the offline provider, and runs it to review.

Starts the real backend with uvicorn on a temporary data directory, with
every provider key unset, and drives the built CLI (cli/dist/bin/molabel.js)
through the whole flow. Prints each command and its exit code, and exits 1 on
the first mismatch.

Run from the repository root after `uv sync` and `npm run build` in cli/:

    uv run python scripts/smoke_no_key.py
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
CLI = REPO / "cli" / "dist" / "bin" / "molabel.js"
FIXTURE = REPO / "fixtures" / "smoke-no-key" / "synthetic_support_tickets.jsonl"
HOSTED_PROVIDERS = {"anthropic", "openai_compatible", "openrouter"}
LABEL_FIELDS = [
    {
        "name": "intent",
        "field_type": "categorical",
        "required": True,
        "options": ["refund", "bug", "shipping", "other"],
    },
    {"name": "urgent", "field_type": "bool", "required": True},
]
OFFLINE_PROPOSALS = {
    "ticket-1": {"intent": "refund", "urgent": False},
    "ticket-2": {"intent": "bug", "urgent": True},
    "ticket-3": {"intent": "shipping", "urgent": False},
    "ticket-4": {"intent": "refund", "urgent": False},
    "ticket-5": {"intent": "refund", "urgent": False},
    "ticket-6": {"intent": "bug", "urgent": False},
}
EDITS = {
    "ticket-4": {"intent": "other", "urgent": False},
    "ticket-6": {"intent": "shipping", "urgent": False},
}


class SmokeFailure(Exception):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)
    print(f"  ok: {message}")


def keyless_env(**overrides: str) -> dict[str, str]:
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.endswith(("_API_KEY", "_AUTH_TOKEN"))
        and not name.startswith("MOLABEL_")
        and name not in {"ANTHROPIC_BASE_URL", "MINIMAX_BASE_URL"}
    }
    env.update(overrides)
    return env


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_health(base_url: str, server: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise SmokeFailure(f"backend exited with code {server.returncode}")
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=2) as resp:
                if resp.status == 200:
                    return
        except OSError:
            time.sleep(0.5)
    raise SmokeFailure("backend did not answer /health within 60s")


def stop(server: subprocess.Popen[bytes]) -> None:
    # On Windows a venv's python.exe starts the real interpreter as a child,
    # so terminating the parent alone leaves the server holding the database.
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(server.pid)],
            capture_output=True,
            check=False,
        )
    else:
        server.terminate()
    server.wait(timeout=30)


class Cli:
    def __init__(self, env: dict[str, str], cwd: Path) -> None:
        self._env = env
        self._cwd = cwd

    def __call__(self, *args: str, expect_exit: int = 0) -> Any:
        print(f"$ molabel {shlex.join(args)}")
        result = subprocess.run(
            ["node", str(CLI), *args],
            cwd=self._cwd,
            env=self._env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        print(f"  exit {result.returncode}")
        if result.returncode != expect_exit:
            raise SmokeFailure(
                f"expected exit {expect_exit}, got {result.returncode}\n"
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise SmokeFailure(
                f"stdout is not one JSON document:\n{result.stdout}"
            ) from exc


def run_flow(molabel: Cli, workspace: Path) -> Path:
    doctor = molabel("doctor")
    provider_types = {item["provider_type"] for item in doctor["providers"]}
    check("offline" in provider_types, "doctor lists the offline provider")
    check(
        not provider_types & HOSTED_PROVIDERS,
        f"doctor lists no hosted provider without keys: {sorted(provider_types)}",
    )

    bootstrap = molabel(
        "workspace", "bootstrap", ".", "--workspace-name", "No-key smoke"
    )
    check(bool(bootstrap["workspace"]["workspace_id"]), "workspace bootstrapped")

    (workspace / "data").mkdir()
    shutil.copy(FIXTURE, workspace / "data" / FIXTURE.name)
    dataset = molabel(
        "dataset",
        "create",
        "--name",
        "Support tickets",
        "--slug",
        "support-tickets",
        "--source-type",
        "file",
        "--loader-plugin",
        "jsonl",
        "--record-kind",
        "text",
        "--canonical-id-strategy",
        "source_record_id",
        "--indexing-mode",
        "projection",
    )
    dataset_id = dataset["dataset_id"]
    imported = molabel(
        "dataset", "import", dataset_id, "--source-uri", f"data/{FIXTURE.name}"
    )
    check(imported["status"] == "completed", "import completed")
    check(imported["records_imported"] == 6, "import stored 6 records")

    schema = molabel(
        "task-schema",
        "create",
        "--slug",
        "ticket-triage",
        "--task-type",
        "classification",
        "--title",
        "Ticket triage",
        "--instructions",
        "Pick the ticket's intent and mark urgent tickets.",
        "--blind-review-policy",
        "show_agent_outputs",
        "--label-fields-json",
        json.dumps(LABEL_FIELDS),
    )
    schema_id = schema["task_schema_id"]

    workflow = molabel(
        "workflow",
        "create",
        "--template",
        "quick_agentic_label",
        "--provider",
        "offline",
        "--dataset",
        dataset_id,
        "--task-schema",
        schema_id,
    )
    agent_steps = [s for s in workflow["steps"] if s["step_type"] == "agent_run"]
    check(
        [(s["config"]["model"], s["config"]["provider_type"]) for s in agent_steps]
        == [("offline-heuristic", "offline")],
        "the template's agent step is bound to the offline provider",
    )
    slug = workflow["workflow_slug"]

    execution = molabel("workflow", "run", slug)
    check(execution["status"] == "paused", "workflow run paused")
    check(execution["current_step_id"] == "review", "workflow run reached review")
    execution_id = execution["execution_id"]

    queues = molabel(
        "queue", "list", "--workspace-id", bootstrap["workspace"]["workspace_id"]
    )
    check(len(queues["items"]) == 1, "one review queue exists")
    queue = queues["items"][0]
    check(queue["total"] == 6 and queue["available"] == 6, "the queue holds 6 tasks")

    reviewed: dict[str, dict[str, Any]] = {}
    while True:
        claim = molabel("queue", "claim", queue["queue_id"])
        if claim["queue_empty"]:
            break
        task = claim["task"]
        external_id = task["record_external_id"]
        output = task["agent_output"]
        expected = OFFLINE_PROPOSALS[external_id]
        check(
            output["labels"] == expected,
            f"{external_id}: offline proposal {output['labels']}, expected {expected}",
        )
        check(
            output["raw_response"]["strategy"] == "offline-heuristic"
            and output["composite_confidence"] == 0,
            f"{external_id}: proposal is marked offline-heuristic with confidence 0",
        )
        if external_id in EDITS:
            labels = EDITS[external_id]
            submitted = molabel(
                "review",
                "submit",
                task["id"],
                "--decision",
                "edit",
                "--labels-json",
                json.dumps(labels),
                "--rationale",
                "The keyword guess was wrong.",
                "--no-auto-claim-next",
            )
        else:
            labels = output["labels"]
            submitted = molabel(
                "review",
                "submit",
                task["id"],
                "--decision",
                "accept",
                "--no-auto-claim-next",
            )
        check(
            submitted["submitted_task"]["status"] == "submitted",
            f"{external_id}: review stored",
        )
        reviewed[external_id] = labels
    check(sorted(reviewed) == sorted(OFFLINE_PROPOSALS), "every task was reviewed")

    advanced = molabel("workflow", "advance", slug, execution_id, "review")
    check(advanced["status"] == "completed", "workflow completed after review")
    bundle_ids = advanced["context"]["export_bundle_ids"]
    check(len(bundle_ids) == 1, "the export step wrote one bundle")

    export_path = workspace / "exports" / f"{bundle_ids[0]}.jsonl"
    check(export_path.is_file(), f"export file exists: {export_path}")
    rows = [
        json.loads(line)
        for line in export_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    check(len(rows) == 6, "export holds 6 records")
    exported = {row["external_id"]: row["labels"] for row in rows}
    check(exported == reviewed, "export holds the reviewed labels, edits included")
    return export_path


def run_comparison(molabel: Cli) -> None:
    unbound = molabel(
        "workflow", "create", "--template", "agent_comparison", expect_exit=1
    )["error"]
    check(
        unbound["code"] == "HTTP_400"
        and unbound["details"]["error"]["code"] == "TEMPLATE_MODEL_REQUIRED",
        "agent_comparison with no model fails at create with TEMPLATE_MODEL_REQUIRED",
    )
    check(
        "--model <id>" in unbound["message"]
        and "--provider offline" in unbound["message"],
        "the error names --model <id> and --provider offline",
    )

    workflow = molabel(
        "workflow", "create", "--template", "agent_comparison", "--provider", "offline"
    )
    compare = next(s for s in workflow["steps"] if s["step_type"] == "agent_compare")
    check(
        set(compare["config"]["models"]) == {"offline-heuristic"}
        and compare["config"]["provider_type"] == "offline",
        "every compared model is bound to the offline provider",
    )
    execution = molabel("workflow", "run", workflow["workflow_slug"])
    check(
        execution["status"] == "paused" and execution["current_step_id"] == "review",
        "the offline comparison runs to review",
    )


def main() -> int:
    if not CLI.is_file():
        print(f"FAIL: {CLI} is missing. Run `npm ci && npm run build` in cli/.")
        return 1
    with tempfile.TemporaryDirectory(prefix="molabel-smoke-") as tmp:
        root = Path(tmp)
        launch, data, workspace, config = (
            root / name for name in ("launch", "data", "workspace", "config")
        )
        for folder in (launch, data, workspace, config):
            folder.mkdir()
        base_url = f"http://127.0.0.1:{free_port()}"
        server_log = root / "server.log"
        with server_log.open("wb") as log:
            server = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "molabel.app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    base_url.rsplit(":", 1)[1],
                ],
                cwd=launch,
                env=keyless_env(MOLABEL_DATA_DIR=str(data)),
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        try:
            wait_for_health(base_url, server)
            molabel = Cli(
                keyless_env(MOLABEL_BASE_URL=base_url, XDG_CONFIG_HOME=str(config)),
                cwd=workspace,
            )
            export_path = run_flow(molabel, workspace)
            run_comparison(molabel)
            check(
                export_path.resolve().is_relative_to(workspace.resolve()),
                "the export stays inside the workspace",
            )
            check(
                not any(launch.iterdir()),
                "the backend wrote nothing into its launch folder",
            )
        except SmokeFailure as failure:
            print(f"FAIL: {failure}")
            print("--- backend log (last 40 lines) ---")
            print("\n".join(server_log.read_text(errors="replace").splitlines()[-40:]))
            return 1
        finally:
            stop(server)
    print("PASS: no-key smoke test")
    return 0


if __name__ == "__main__":
    sys.exit(main())

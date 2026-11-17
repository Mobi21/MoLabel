"""No-key end-to-end smoke test: import, offline pre-label, review, export.

It then creates the agent_comparison template, which leaves a model unset,
once with no model and once on the offline provider. It runs the offline one
to review and checks that it is marked an offline smoke run.

It adjudicates two reviewers through the CLI alone. It creates a second
reviewer, runs a workflow whose review gives each record two copies, has the
reviewers disagree on one record, and resolves that disagreement.

Last, it promotes the adjudicated record into a gold set and reads the gold
files back from the workspace. It appends the first review's failures twice,
and the second append adds nothing.

Starts the real backend with uvicorn on a temporary data directory, with
every provider key unset, and drives the built CLI (cli/dist/bin/molabel.js)
through the whole flow. Prints each command and its exit code, and exits 1 on
the first mismatch.

Run from the repository root after `uv sync` and `npm run build` in cli/:

    uv run python scripts/smoke_no_key.py
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import textwrap
import time
import urllib.request
from pathlib import Path
from typing import Any

import yaml

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
SECOND_REVIEWER_EDITS = {"ticket-4": {"intent": "other", "urgent": False}}
RESOLVED = {"intent": "refund", "urgent": False}


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


def stop(server: subprocess.Popen[bytes], log: Path) -> None:
    # On Windows a venv's python.exe runs the real interpreter as a child, and
    # the child holds the database and the log. Killing the parent kills the
    # child only after the parent is reaped, so the temp folder can still be
    # in use. The parent exits after its child does, so stop the child that
    # uvicorn names and wait on the parent.
    if server.poll() is None:
        started = re.search(
            r"Started server process \[(\d+)\]", log.read_text(errors="replace")
        )
        if os.name != "nt":
            server.terminate()
        elif started:
            os.kill(int(started[1]), signal.SIGTERM)
        else:
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(server.pid)],
                capture_output=True,
                check=False,
            )
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


def run_flow(molabel: Cli, workspace: Path) -> tuple[Path, str, str, str]:
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
    return export_path, dataset_id, schema_id, queue["queue_id"]


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
    detail = molabel(
        "workflow", "execution", workflow["workflow_slug"], execution["execution_id"]
    )
    compared = next(
        state["result"]
        for state in detail["step_states"]
        if state["step_type"] == "agent_compare"
    )
    check(
        compared["summary"]["offline_smoke_run"] is True and compared["warnings"],
        "the comparison is marked an offline smoke run",
    )


def review_queue(molabel: Cli, queue_id: str, edits: dict[str, Any]) -> list[str]:
    reviewed = []
    while not (claim := molabel("queue", "claim", queue_id))["queue_empty"]:
        task = claim["task"]
        external_id = task["record_external_id"]
        decision = (
            ["--decision", "edit", "--labels-json", json.dumps(edits[external_id])]
            if external_id in edits
            else ["--decision", "accept"]
        )
        submitted = molabel(
            "review", "submit", task["id"], *decision, "--no-auto-claim-next"
        )
        check(
            submitted["submitted_task"]["status"] == "submitted",
            f"{external_id}: review stored",
        )
        reviewed.append(external_id)
    return sorted(reviewed)


def run_adjudication(
    molabel: Cli, workspace: Path, dataset_id: str, schema_id: str
) -> tuple[str, str, str, str]:
    """Adjudicate two reviewers; return the queue, the record, and both reviewers."""
    first = molabel("session", "whoami")["reviewer_id"]
    second = molabel("reviewer", "create", "--display-name", "Reviewer 2")
    check(
        second["display_name"] == "Reviewer 2" and second["id"] != first,
        "reviewer create added a second reviewer",
    )

    definition = workspace / "two-reviewers.json"
    definition.write_text(
        json.dumps(
            {
                "name": "Two-reviewer triage",
                "steps": [
                    {
                        "id": "ingest",
                        "type": "data_ingest",
                        "config": {"dataset_id": dataset_id},
                    },
                    {
                        "id": "agent_label",
                        "type": "agent_run",
                        "config": {
                            "provider_type": "offline",
                            "model": "offline-heuristic",
                            "prompt_ref": "prompts/default.yaml",
                            "task_schema_id": schema_id,
                        },
                    },
                    {
                        "id": "review",
                        "type": "human_review",
                        "config": {"overlap_count": 2, "breakpoint": True},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    workflow = molabel("workflow", "create", "--file", definition.name)
    execution = molabel("workflow", "run", workflow["workflow_slug"])
    check(
        execution["status"] == "paused" and execution["current_step_id"] == "review",
        "the two-reviewer workflow runs to review",
    )
    queue_ids = molabel(
        "workflow", "execution", workflow["workflow_slug"], execution["execution_id"]
    )["context"]["review_queue_ids"]
    check(len(queue_ids) == 1, "the review step made one queue")
    queue_id = queue_ids[0]
    queue = next(
        q for q in molabel("queue", "list")["items"] if q["queue_id"] == queue_id
    )
    check(queue["total"] == 12, "overlap_count: 2 gives each of 6 records 2 copies")

    check(
        review_queue(molabel, queue_id, {}) == sorted(OFFLINE_PROPOSALS),
        "the first reviewer reviewed one copy of every record",
    )
    molabel("session", "switch", second["id"])
    check(
        molabel("session", "whoami")["reviewer_id"] == second["id"],
        "session switch acts as the second reviewer",
    )
    check(
        review_queue(molabel, queue_id, SECOND_REVIEWER_EDITS)
        == sorted(OFFLINE_PROPOSALS),
        "the second reviewer reviewed the other copy of every record",
    )

    disagreements = molabel("adjudication", "list", queue_id)
    check(
        [
            (d["record_external_id"], d["fields_in_conflict"])
            for d in disagreements["items"]
        ]
        == [("ticket-4", ["intent"])],
        "the reviewers disagree on ticket-4's intent alone",
    )
    record_id = disagreements["items"][0]["record_id"]
    detail = molabel("adjudication", "show", queue_id, record_id)
    labels = {
        entry["reviewer_id"]: entry["labels"] for entry in detail["reviewer_labels"]
    }
    check(
        labels
        == {
            first: OFFLINE_PROPOSALS["ticket-4"],
            second["id"]: SECOND_REVIEWER_EDITS["ticket-4"],
        },
        "show prints each reviewer's labels",
    )
    event_ids = ",".join(
        entry["review_event_id"] for entry in detail["reviewer_labels"]
    )
    molabel(
        "adjudication",
        "resolve",
        queue_id,
        record_id,
        "--review-event-ids",
        event_ids,
        "--resolved-labels-json",
        json.dumps(RESOLVED),
        "--rationale",
        "The ticket asks for money back.",
    )

    after = molabel("adjudication", "list", queue_id)
    check(
        after["unresolved"] == 0 and after["items"][0]["status"] == "resolved",
        "a fresh adjudication list shows the disagreement resolved",
    )
    stored = molabel("adjudication", "show", queue_id, record_id)["resolution"]
    check(
        stored["resolution"] == "resolve" and stored["resolved_labels"] == RESOLVED,
        "a fresh adjudication show reads the stored resolution and its labels",
    )
    return queue_id, record_id, first, second["id"]


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def run_gold(
    molabel: Cli,
    workspace: Path,
    review_queue: str,
    adjudication: tuple[str, str, str, str],
) -> None:
    queue_id, record_id, first, second = adjudication
    created = molabel("gold", "create", "ticket-gold", "--task-schema", "ticket-triage")
    check(
        (created["version"], created["item_count"]) == (1, 0),
        "gold create wrote version 1 with no items",
    )
    promoted = molabel(
        "gold", "promote", "ticket-gold", "--queue", queue_id, "--record", record_id
    )
    check(
        promoted["counts"]
        == {
            "added": 1,
            "duplicates": 0,
            "conflicts": 0,
            "skipped": 0,
            "corrected": 0,
        },
        "gold promote added the adjudicated record",
    )

    folder = workspace / "gold" / "ticket-gold"
    items = folder / "gold.jsonl"
    check(items.is_file(), f"the gold file exists: {items}")
    (item,) = [json.loads(line) for line in items.read_text("utf-8").splitlines()]
    print(f"  gold.jsonl: {items.read_text('utf-8').strip()}")
    check(
        item["input_ref"]["external_id"] == "ticket-4" and item["expected"] == RESOLVED,
        "the gold item is ticket-4 with the adjudicated labels",
    )
    provenance = item["provenance"]
    check(
        provenance["source"] == "adjudication"
        and provenance["adjudication"]["adjudicator_id"] == second
        and provenance["reviewer_ids"] == sorted([first, second])
        and provenance["promoted_by"] == second
        and provenance["queue_id"] == queue_id,
        "its provenance names the adjudication, both reviewers and the promoter",
    )
    check(
        provenance["ai_revealed"] is True and len(provenance["reviews"]) == 2,
        "its provenance records the two reviews and that a proposal was shown",
    )
    header_text = (folder / "gold.yaml").read_text("utf-8")
    print(textwrap.indent(f"gold.yaml:\n{header_text}", "  "), end="")
    header = yaml.safe_load(header_text)
    check(
        header["version"] == 2 and header["content_hash"] == _sha256(items),
        "gold.yaml is at version 2 with the file's content hash",
    )
    manifest = (workspace / "workbench.project.yaml").read_text("utf-8")
    check(
        "gold_set_id: ticket-gold" in manifest,
        "workbench.project.yaml lists the gold set",
    )

    appended = molabel(
        "gold",
        "append",
        "ticket-gold",
        "--queue",
        review_queue,
        "--allow-single-reviewer",
    )
    check(
        appended["counts"]
        == {
            "added": 1,
            "duplicates": 0,
            "conflicts": 1,
            "skipped": 4,
            "corrected": 0,
        },
        "gold append added ticket-6 and reported ticket-4 as a conflict",
    )
    (added,) = appended["added"]
    check(
        added["input_ref"]["external_id"] == "ticket-6"
        and added["provenance"]["model_failure"]["proposed"]["intent"] == "bug"
        and added["provenance"]["source"] == "single_reviewer",
        "the appended failure records the wrong proposal",
    )
    (conflict,) = appended["conflicts"]
    check(
        conflict["gold"]["expected"] == RESOLVED
        and conflict["other"]["expected"] == EDITS["ticket-4"],
        "the conflict keeps the adjudicated gold label",
    )
    conflicts = folder / "conflicts.jsonl"
    check(conflicts.is_file(), f"the conflict is kept in {conflicts}")
    (stored,) = [json.loads(line) for line in conflicts.read_text("utf-8").splitlines()]
    print(f"  conflicts.jsonl: {conflicts.read_text('utf-8').strip()}")
    check(
        stored["item_id"] == item["item_id"]
        and stored["existing"] == RESOLVED
        and stored["incoming"] == EDITS["ticket-4"]
        and stored["provenance"]["queue_id"] == review_queue,
        "conflicts.jsonl holds ticket-4's gold and incoming labels and their queue",
    )
    check(
        yaml.safe_load((folder / "gold.yaml").read_text("utf-8"))["content_hash"]
        == _sha256(items),
        "recording the conflict left gold.yaml describing gold.jsonl",
    )
    once = items.read_bytes()
    conflicts_once = conflicts.read_bytes()

    again = molabel(
        "gold",
        "append",
        "ticket-gold",
        "--queue",
        review_queue,
        "--allow-single-reviewer",
    )
    check(
        again["written"] is False
        and again["counts"]["added"] == 0
        and again["counts"]["duplicates"] == 1
        and again["gold_set"]["version"] == 3,
        "a second append adds nothing, dedupes ticket-6, and keeps version 3",
    )
    check(items.read_bytes() == once, "the second append left gold.jsonl as it was")
    check(
        conflicts.read_bytes() == conflicts_once
        and [c["item_id"] for c in again["open_conflicts"]] == [item["item_id"]],
        "the second append recorded ticket-4's conflict once",
    )
    shown = molabel("gold", "show", "ticket-gold")
    check(
        [c["incoming"] for c in shown["open_conflicts"]] == [EDITS["ticket-4"]],
        "gold show lists the open conflict",
    )

    exported = molabel("gold", "export", "ticket-gold")
    check(
        exported["content"].encode("utf-8") == once,
        "gold export prints the file's lines",
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
            export_path, dataset_id, schema_id, review_queue = run_flow(
                molabel, workspace
            )
            run_comparison(molabel)
            adjudication = run_adjudication(molabel, workspace, dataset_id, schema_id)
            run_gold(molabel, workspace, review_queue, adjudication)
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
            stop(server, server_log)
    print("PASS: no-key smoke test")
    return 0


if __name__ == "__main__":
    sys.exit(main())

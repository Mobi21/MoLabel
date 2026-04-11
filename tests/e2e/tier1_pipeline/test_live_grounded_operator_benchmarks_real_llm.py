"""Single-prompt grounded operator benchmark runs against MiniMax 2.7.

This path gives the agent runner (Claude Code or Codex) only a temporary
benchmark workspace, the public ``molabel`` command, the installed MoLabel
skill, and one short prompt.  The harness then reconstructs persisted review
outputs after the agent exits and scores those artifacts externally.  The
paper-direct model baseline remains a maintainer-side reference score.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

import pytest

from molabel.core.providers.anthropic_adapter import AnthropicAdapter
from molabel.core.providers.structured_output import StructuredOutputEnforcer
from molabel.core.quality import (
    build_operator_diagnostics,
    compute_stage_deltas,
    render_grounded_stage_report,
    score_grounded_stage,
    summarize_operator_run,
    write_run_outputs,
)
from molabel.core.quality.grounded_benchmarks import GroundedOperatorObservation
from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.grounded_operator import (
    GroundedCliHarness,
    build_messages,
    build_output_schema,
    hash_paths,
    prepare_grounded_operator_fixture,
    resolve_auth_ref,
)
from tests.e2e.infrastructure.logging_config import serialize_test_context
from tests.e2e.infrastructure.parallel import INDEPENDENT

REPO_ROOT = Path(__file__).resolve().parents[3]
GROUNDED_ROOT = REPO_ROOT / "fixtures" / "benchmarks-grounded"
MINIMAX_BASE_URL = os.environ.get(
    "MINIMAX_BASE_URL",
    "https://api.minimax.io/anthropic",
)

SCENARIOS = ["clinc150", "hatexplain", "feverous", "banking77", "goemotions", "scifact"]


def _codex_auth_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))


def _detect_runner() -> str | None:
    """Return the best available runner name, or None if none found."""
    import shutil

    if shutil.which("claude"):
        return "claude"
    if shutil.which("codex"):
        return "codex"
    return None


def _runner_auth_ok(runner: str) -> bool:
    """Check whether the runner has usable auth configured."""
    if runner == "codex":
        return (_codex_auth_home() / "auth.json").exists()
    # Claude Code uses OAuth/keychain or ANTHROPIC_API_KEY.
    # A lightweight check: the binary exists and isn't a MiniMax-only key.
    # Full auth validation happens at runtime; we just gate on presence.
    return runner == "claude"


def _single_prompt(bundle) -> str:
    s = bundle.scenario
    return (
        "Run this grounded benchmark using molabel only.\n"
        f"Use benchmark_id `{s.benchmark_id}` in any written run "
        "artifacts; do not invent alternate benchmark IDs from schema "
        "or workflow names.\n"
        "When writing run artifacts, derive accept/edit/reject counts and rates "
        "from the persisted final review decisions, not from pre-review workflow "
        "summary placeholders.\n"
        "Use MiniMax 2.7 for the proposal stage; do not use Ollama, local models, "
        "or builtin heuristic profiles.\n"
        "Use only these inputs: "
        f"`{s.source_path}`, "
        f"`{s.task_schema_path}`, and "
        f"`{s.workflow_path}`.\n"
        f"The record ID field in the source data is "
        f"`{s.record_id_field or 'record_id'}`. When creating the dataset, "
        "use `canonical_id_strategy: source_record_id` and set the "
        f"`record_id_field` to `{s.record_id_field or 'record_id'}`.\n"
        "When creating the prompt template, use the exact workflow `prompt_ref` "
        "value as the prompt name so the workflow resolves that prompt instead of "
        "falling back to the generic default.\n"
        "Create the model profile with provider `anthropic`, provider name "
        "`MiniMax`, model identifier `minimax-2.7`, auth ref "
        "`ANTHROPIC_API_KEY`, and structured output enabled.\n"
        "Do not inspect authority, gold, human-labels, reviews, or benchmark "
        "config files.\n"
        f"Write run artifacts under workbench/benchmarks/runs/live-operator."
    )


def _valid_labels_check(
    review_submissions: list[dict[str, Any]],
    task_schema: dict[str, Any],
) -> bool:
    """Check all submitted labels use valid values from the task schema."""
    label_fields = task_schema.get("label_fields", [])
    valid_options: dict[str, set[str]] = {}
    for field in label_fields:
        if field["field_type"] in ("categorical", "multi_select"):
            valid_options[field["name"]] = set(field.get("options", []))

    for row in review_submissions:
        labels = row.get("labels", {})
        for field_name, options in valid_options.items():
            if field_name in labels:
                value = labels[field_name]
                if isinstance(value, list):
                    if not all(v in options for v in value):
                        return False
                elif value not in options:
                    return False
    return True


def _audit_operator_shell_commands(shell_commands: list[str]) -> dict[str, list[str]]:
    non_cli_surface_commands: list[str] = []
    hidden_benchmark_path_commands: list[str] = []
    truth_probe_commands: list[str] = []
    queue_claim_commands: list[str] = []
    reveal_ai_commands: list[str] = []
    status_poll_commands: list[str] = []
    repeated_poll_commands: list[str] = []
    duplicate_shell_commands: list[str] = []
    redundant_read_commands: list[str] = []
    forbidden_markers = ("curl ", "wget ", "/api/", "requests.", "httpx.", "fetch(")
    hidden_paths = (
        "/authority/",
        "workbench/benchmarks/gold/",
        "workbench/benchmarks/human-labels/",
        "workbench/benchmarks/reviews/",
        "workbench/benchmarks/label-map.yaml",
        "workbench/benchmarks/metrics.yaml",
        "workbench/benchmarks/baselines.yaml",
        "workbench/benchmarks/operator.yaml",
        "workbench/benchmarks/paper.yaml",
        "workbench/benchmarks/scenario.yaml",
    )
    truth_terms = (
        "source_label",
        "ground_truth",
    )
    read_prefixes = ("cat ", "sed ", "rg ", "ls ", "find ")
    normalized_counts: dict[str, int] = {}
    read_counts: dict[str, int] = {}
    last_poll_command: str | None = None
    for command in shell_commands:
        normalized = " ".join(command.lower().split())
        normalized_counts[normalized] = normalized_counts.get(normalized, 0) + 1
        if normalized_counts[normalized] > 1:
            duplicate_shell_commands.append(command)
        if " molabel " in f" {normalized} " or normalized.rstrip().endswith("/molabel"):
            if " queue claim" in normalized:
                queue_claim_commands.append(command)
            if "reveal-ai" in normalized:
                reveal_ai_commands.append(command)
            if (
                " queue status" in normalized
                or " workflow execution" in normalized
                or " session status" in normalized
            ):
                status_poll_commands.append(command)
                if normalized == last_poll_command:
                    repeated_poll_commands.append(command)
                last_poll_command = normalized
            else:
                last_poll_command = None
            continue
        last_poll_command = None
        if any(marker in normalized for marker in forbidden_markers):
            non_cli_surface_commands.append(command)
            continue
        if any(marker in normalized for marker in hidden_paths):
            hidden_benchmark_path_commands.append(command)
            continue
        if any(marker in normalized for marker in truth_terms):
            truth_probe_commands.append(command)
        if normalized.startswith(read_prefixes):
            read_counts[normalized] = read_counts.get(normalized, 0) + 1
            if read_counts[normalized] > 1:
                redundant_read_commands.append(command)

    return {
        "shell_commands": shell_commands,
        "non_cli_surface_commands": non_cli_surface_commands,
        "hidden_benchmark_path_commands": hidden_benchmark_path_commands,
        "truth_probe_commands": truth_probe_commands,
        "queue_claim_commands": queue_claim_commands,
        "reveal_ai_commands": reveal_ai_commands,
        "status_poll_commands": status_poll_commands,
        "repeated_poll_commands": repeated_poll_commands,
        "duplicate_shell_commands": duplicate_shell_commands,
        "redundant_read_commands": redundant_read_commands,
    }


def _artifact_leak_markers(text: str) -> list[str]:
    normalized = text.lower()
    markers = [
        marker
        for marker in (
            "source_label",
            "ground_truth",
        )
        if marker in normalized
    ]
    return markers


def _build_operator_run_evidence(
    *,
    ctx,
    raw_records: list[dict[str, Any]],
    molabel_gold_rows: list[dict[str, Any]],
    human_rows: list[dict[str, Any]],
    benchmark_review_rows: list[dict[str, Any]],
    agent_outputs: list[dict[str, Any]],
    review_submissions: list[dict[str, Any]],
    review_events: list[dict[str, Any]],
    shell_commands: list[str],
    shell_audit: dict[str, Any],
    agent_result,
    operator_summary,
    operator_label_summary,
    workflow_autorun_summary,
    workflow_reviewed_summary,
    tax_breakdown,
    agent_summary_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "inputs/raw_records.json": raw_records,
        "inputs/gold_rows.json": molabel_gold_rows,
        "inputs/benchmark_human_rows.json": human_rows,
        "inputs/benchmark_review_rows.json": benchmark_review_rows,
        "outputs/agent_outputs.json": agent_outputs,
        "outputs/review_submissions.json": review_submissions,
        "outputs/review_events.json": review_events,
        "logs/shell_commands.json": shell_commands,
        "logs/shell_audit.json": shell_audit,
        "logs/agent_runner.json": {
            "runner": agent_result.runner,
            "exit_code": agent_result.exit_code,
            "duration_ms": agent_result.duration_ms,
            "stdout": agent_result.stdout,
            "stderr": agent_result.stderr,
            "last_message": agent_result.last_message,
        },
        "logs/agent_events.json": agent_result.events,
        "logs/test_context.json": serialize_test_context(ctx),
        "scoring/operator_label_summary_metrics.json": {
            metric.metric_id: metric.model_dump(mode="json")
            for metric in operator_label_summary.metrics
        },
        "scoring/workflow_autorun_diagnostics.json": (
            workflow_autorun_summary.diagnostics
        ),
        "scoring/workflow_reviewed_diagnostics.json": (
            workflow_reviewed_summary.diagnostics
        ),
        "scoring/operator_diagnostics.json": operator_summary.diagnostics,
        "scoring/tax_breakdown.json": [
            tax.model_dump(mode="json") for tax in tax_breakdown
        ],
        "artifacts/agent_summary_payload.json": agent_summary_payload or {},
    }


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier1
@pytest.mark.real_llm
@pytest.mark.slow
@pytest.mark.timeout(2400)
@pytest.mark.parametrize("scenario_id", SCENARIOS, ids=SCENARIOS)
async def test_live_grounded_operator_benchmark_real_llm(
    ctx,
    scenario_id: str,
) -> None:
    """Run a grounded operator benchmark as one agent prompt."""

    auth_ref = resolve_auth_ref(REPO_ROOT)
    if not auth_ref:
        pytest.skip(
            "ANTHROPIC_API_KEY or MINIMAX_API_KEY not set — "
            "skipping live grounded operator benchmark"
        )

    runner = _detect_runner()
    if runner is None:
        pytest.skip(
            "No agent runner (claude or codex) found on PATH — "
            "skipping single-prompt operator benchmark"
        )
    if not _runner_auth_ok(runner):
        pytest.skip(
            f"{runner} auth not configured — skipping single-prompt operator benchmark"
        )

    source_root = GROUNDED_ROOT / scenario_id
    fixture = prepare_grounded_operator_fixture(source_root)
    bundle = fixture.bundle
    task_schema = fixture.task_schema
    agents_prompt = (fixture.workspace_root / "AGENTS.md").read_text(encoding="utf-8")
    output_schema = build_output_schema(task_schema, bundle.scenario.benchmark_id)
    operator_run_root = (
        fixture.workspace_root / "workbench" / "benchmarks" / "runs" / "live-operator"
    )

    with GroundedCliHarness(ctx, fixture.workspace_root, REPO_ROOT) as harness:
        with checkpoint(ctx, "maintainer_paper_direct_baseline"):
            paper_direct_model_summary = None
            model_operated_summary = None
            try:

                async def _run_paper_direct_baseline() -> None:
                    nonlocal paper_direct_model_summary, model_operated_summary
                    adapter = AnthropicAdapter(
                        auth_ref=auth_ref,
                        default_model=(
                            bundle.scenario.default_model_profile.model_identifier
                        ),
                        base_url=MINIMAX_BASE_URL,
                    )
                    enforcer = StructuredOutputEnforcer()
                    direct_predictions: list[dict[str, Any]] = []
                    for record in fixture.raw_records:
                        record_id = str(
                            record[bundle.scenario.record_id_field or "record_id"]
                        )
                        messages = build_messages(
                            agents_prompt=agents_prompt,
                            task_schema=task_schema,
                            benchmark_name=bundle.scenario.name,
                            description=bundle.scenario.description,
                            record=record,
                            record_id=record_id,
                        )
                        result = await asyncio.wait_for(
                            asyncio.to_thread(
                                enforcer.enforce,
                                adapter,
                                messages,
                                bundle.scenario.default_model_profile.model_identifier,
                                output_schema,
                            ),
                            timeout=120,
                        )
                        ctx.llm_calls += 1
                        ctx.real_llm_calls += 1
                        assert result.is_valid, (
                            f"Structured output failed for "
                            f"{bundle.scenario.benchmark_id} "
                            f"record {record_id}: {result.validation_errors}"
                        )
                        direct_predictions.append(
                            {"record_id": record_id, "labels": result.parsed or {}}
                        )

                    paper_direct_model_summary = score_grounded_stage(
                        bundle=bundle,
                        predictions=direct_predictions,
                        gold_rows=fixture.paper_gold_rows,
                        run_id="live-paper-direct-minimax-2-7",
                        stage="paper_model",
                        variant="paper_direct",
                        context_rows=fixture.raw_records,
                    )
                    model_operated_summary = score_grounded_stage(
                        bundle=bundle,
                        predictions=direct_predictions,
                        gold_rows=fixture.molabel_gold_rows,
                        run_id="live-model-operated-minimax-2-7",
                        stage="molabel_model",
                        variant="molabel_operated",
                        context_rows=fixture.raw_records,
                    )

                await asyncio.wait_for(_run_paper_direct_baseline(), timeout=300)
            except (TimeoutError, Exception) as exc:
                ctx.warnings.append(f"Paper-direct baseline failed: {exc}")

        with checkpoint(ctx, "single_prompt_operator_run"):
            agent_result = await harness.run_agent_prompt(
                _single_prompt(bundle),
                runner=runner,
            )

            review_submissions = harness.load_latest_review_submissions()
            budget_exhausted = any(
                e.get("subtype") == "error_max_budget_usd" for e in agent_result.events
            )
            agent_timed_out = agent_result.exit_code in (-1, -9)

            if not review_submissions and (agent_timed_out or budget_exhausted):
                pytest.skip(
                    f"Agent {'timed out' if agent_timed_out else 'exhausted budget'} "
                    f"for {scenario_id} with no review submissions "
                    f"(exit_code={agent_result.exit_code})"
                )

            assert agent_result.exit_code == 0 or (
                (budget_exhausted or agent_timed_out) and review_submissions
            ), agent_result.stderr or agent_result.stdout

            assert review_submissions, (
                f"Expected {runner} to submit review labels through MoLabel after "
                "the single-prompt operator run"
            )

            shell_commands = harness.extract_shell_commands(agent_result.events)
            shell_audit = _audit_operator_shell_commands(shell_commands)
            non_cli_surface_commands = shell_audit["non_cli_surface_commands"]
            hidden_benchmark_path_commands = shell_audit[
                "hidden_benchmark_path_commands"
            ]
            truth_probe_commands = shell_audit["truth_probe_commands"]
            review_events = harness.load_review_events()
            payload_leaks = harness.find_record_payload_leaks()
            assert not payload_leaks, (
                "Reviewer-visible record payload leaked benchmark truth fields: "
                f"{payload_leaks}"
            )

            dataset_count = harness.table_row_count("datasets")
            prompt_count = harness.table_row_count("prompt_templates")
            workflow_count = harness.table_row_count("workflow_definitions")
            model_profile_count = harness.table_row_count("model_profiles")
            adjudication_count = harness.table_row_count("adjudications")

            assert dataset_count >= 1
            assert prompt_count >= 1
            assert workflow_count >= 1
            assert model_profile_count >= 1

            # --- Diagnostic: per-record comparison ---
            agent_outputs = harness.load_agent_outputs()
            gold_by_id = {
                r["record_id"]: r["labels"] for r in fixture.molabel_gold_rows
            }
            submission_by_id = {r["record_id"]: r["labels"] for r in review_submissions}
            proposal_by_id = {r["record_id"]: r["labels"] for r in agent_outputs}
            gold_ids = set(gold_by_id)
            proposal_ids = set(proposal_by_id)
            submission_ids = set(submission_by_id)
            assert proposal_ids == gold_ids, (
                "Workflow autorun coverage mismatch. "
                f"missing={sorted(gold_ids - proposal_ids)} "
                f"extra={sorted(proposal_ids - gold_ids)}"
            )
            assert submission_ids == gold_ids, (
                "Review submission coverage mismatch. "
                f"missing={sorted(gold_ids - submission_ids)} "
                f"extra={sorted(submission_ids - gold_ids)}"
            )
            proposal_strategy = {
                r["record_id"]: r.get("raw_response", {}).get("strategy", "?")
                for r in agent_outputs
            }
            proposal_models = {
                r["record_id"]: r.get("raw_response", {}).get("model", "?")
                for r in agent_outputs
            }
            strategy_values = {
                strategy for strategy in proposal_strategy.values() if strategy != "?"
            }
            model_values = {
                model for model in proposal_models.values() if model not in {"?", ""}
            }

            eval_fields = bundle.scenario.evaluation_fields
            primary_field = (
                eval_fields[0]
                if eval_fields
                else (
                    list(gold_by_id.get(next(iter(gold_ids), ""), {}).keys())[0]
                    if gold_ids and gold_by_id.get(next(iter(gold_ids), ""))
                    else "?"
                )
            )

            print("\n" + "=" * 72)
            print("--- Per-Record Label Comparison ---")
            print(
                f"{'record_id':<22} {'gold':<25} {'proposal':<25} "
                f"{'submitted':<25} {'strategy':<24} {'model':<16} match"
            )
            print("-" * 160)
            rid_field = bundle.scenario.record_id_field or "record_id"
            for record in fixture.raw_records:
                rid = str(record[rid_field])
                gold_val = str(gold_by_id.get(rid, {}).get(primary_field, "?"))[:24]
                prop_val = str(proposal_by_id.get(rid, {}).get(primary_field, "?"))[:24]
                sub_val = str(submission_by_id.get(rid, {}).get(primary_field, "?"))[
                    :24
                ]
                strategy = proposal_strategy.get(rid, "?")
                model_name = proposal_models.get(rid, "?")
                match = "OK" if sub_val == gold_val else "MISMATCH"
                prop_match = "=" if prop_val == gold_val else "!="
                print(
                    f"{rid:<22} {gold_val:<25} {prop_val:<25} "
                    f"{sub_val:<25} {strategy:<24} {model_name:<16} {match} "
                    f"(proposal {prop_match} gold)"
                )
            print(
                f"\nAgent outputs: {len(agent_outputs)}, "
                f"Review submissions: {len(review_submissions)}"
            )

            print("\n--- Shell Commands ---")
            for i, cmd in enumerate(shell_commands, 1):
                print(f"  [{i:02d}] {cmd[:120]}")
            print(
                "\n--- Shell Audit ---\n"
                f"  non_cli_surface_commands: {len(non_cli_surface_commands)}\n"
                f"  hidden_benchmark_path_commands: "
                f"{len(hidden_benchmark_path_commands)}\n"
                f"  truth_probe_commands: {len(truth_probe_commands)}"
            )
            print("=" * 72 + "\n")

            run_id_suffix = f"{runner}-single-prompt"
            workflow_autorun_summary = score_grounded_stage(
                bundle=bundle,
                predictions=agent_outputs,
                gold_rows=fixture.molabel_gold_rows,
                run_id=f"live-workflow-autorun-{run_id_suffix}",
                stage="workflow_autorun",
                variant="molabel_operated",
                context_rows=fixture.raw_records,
            )
            workflow_reviewed_summary = score_grounded_stage(
                bundle=bundle,
                predictions=review_submissions,
                gold_rows=fixture.molabel_gold_rows,
                run_id=f"live-workflow-reviewed-{run_id_suffix}",
                stage="workflow_reviewed",
                variant="molabel_operated",
                context_rows=fixture.raw_records,
            )
            operator_label_summary = score_grounded_stage(
                bundle=bundle,
                predictions=review_submissions,
                gold_rows=fixture.molabel_gold_rows,
                run_id=f"live-operator-{run_id_suffix}",
                stage="operator_reviewed",
                variant="molabel_operated",
                context_rows=fixture.raw_records,
            )

    with checkpoint(ctx, "operator_scoring_and_artifacts"):
        agent_wrote_summary = (operator_run_root / "summary.json").exists()
        agent_wrote_report = (operator_run_root / "report.md").exists()
        agent_summary_payload: dict[str, Any] | None = None
        agent_report_text: str | None = None
        if agent_wrote_summary:
            summary_text = (operator_run_root / "summary.json").read_text(
                encoding="utf-8"
            )
            try:
                parsed_summary = __import__("json").loads(summary_text)
            except Exception:
                parsed_summary = None
            if isinstance(parsed_summary, dict):
                agent_summary_payload = parsed_summary
            summary_markers = _artifact_leak_markers(summary_text)
            assert not summary_markers, (
                "Agent-authored summary leaked gold-bearing terms: "
                + ", ".join(summary_markers)
            )
        if agent_wrote_report:
            agent_report_text = (operator_run_root / "report.md").read_text(
                encoding="utf-8"
            )
            report_markers = _artifact_leak_markers(agent_report_text)
            assert not report_markers, (
                "Agent-authored report leaked gold-bearing terms: "
                + ", ".join(report_markers)
            )
        prompt_text = _single_prompt(bundle)

        operator_diagnostics = build_operator_diagnostics(
            gold_rows=fixture.molabel_gold_rows,
            proposal_rows=agent_outputs,
            review_rows=review_submissions,
            evaluation_fields=bundle.scenario.evaluation_fields,
            review_events=review_events,
            shell_audit=shell_audit,
            report_text=agent_report_text,
            summary_payload=agent_summary_payload,
            source_rows=fixture.raw_records,
            benchmark_human_rows=fixture.human_rows,
            benchmark_review_rows=fixture.review_rows,
            expected_benchmark_id=bundle.scenario.benchmark_id,
        )

        operator_summary = summarize_operator_run(
            bundle=bundle,
            label_summary=operator_label_summary,
            observations=[
                GroundedOperatorObservation(
                    check_id="uses_public_cli_and_skill_only",
                    passed=(
                        not non_cli_surface_commands
                        and not hidden_benchmark_path_commands
                        and not truth_probe_commands
                    ),
                    details={
                        "prompt_words": len(prompt_text.split()),
                        "shell_command_count": len(shell_commands),
                        "non_cli_surface_command_count": len(non_cli_surface_commands),
                        "hidden_benchmark_path_command_count": len(
                            hidden_benchmark_path_commands
                        ),
                        "truth_probe_command_count": len(truth_probe_commands),
                        "non_cli_surface_commands": non_cli_surface_commands,
                        "hidden_benchmark_path_commands": (
                            hidden_benchmark_path_commands
                        ),
                        "truth_probe_commands": truth_probe_commands,
                        "runner": runner,
                    },
                ),
                GroundedOperatorObservation(
                    check_id="configures_minimax_2_7_profile",
                    passed=model_profile_count >= 1,
                    details={"model_profile_count": model_profile_count},
                ),
                GroundedOperatorObservation(
                    check_id="uses_real_minimax_proposals",
                    passed=(
                        strategy_values == {"llm-structured-output"}
                        and model_values == {"minimax-2.7"}
                    ),
                    details={
                        "strategies": sorted(strategy_values),
                        "models": sorted(model_values),
                    },
                ),
                GroundedOperatorObservation(
                    check_id="bootstraps_workspace_and_dataset",
                    passed=(
                        dataset_count >= 1 and workflow_count >= 1 and prompt_count >= 1
                    ),
                    details={
                        "dataset_count": dataset_count,
                        "workflow_count": workflow_count,
                        "prompt_count": prompt_count,
                    },
                ),
                GroundedOperatorObservation(
                    check_id="preserves_valid_labels",
                    passed=_valid_labels_check(review_submissions, task_schema),
                    details={"submitted_records": len(review_submissions)},
                ),
                GroundedOperatorObservation(
                    check_id="writes_benchmark_run_artifacts",
                    passed=agent_wrote_summary and agent_wrote_report,
                    details={
                        "run_root": str(operator_run_root),
                        "summary_exists": agent_wrote_summary,
                        "report_exists": agent_wrote_report,
                    },
                ),
                GroundedOperatorObservation(
                    check_id="writes_truthful_benchmark_run_artifacts",
                    passed=operator_diagnostics.truthfulness_ok,
                    details=operator_diagnostics.artifact_truthfulness,
                ),
                GroundedOperatorObservation(
                    check_id="preserves_artifact_integrity",
                    passed=fixture.original_hashes
                    == hash_paths(
                        fixture.authority_root,
                        list(fixture.original_hashes.keys()),
                    ),
                    details={"verified_files": list(fixture.original_hashes.keys())},
                ),
            ],
            run_id=f"live-operator-{run_id_suffix}",
        )

        operator_summary.notes.extend(
            [
                f"Runner: `{runner}`.",
                f"Single prompt words: `{len(prompt_text.split())}`.",
                f"Agent run duration: `{agent_result.duration_ms:.1f}ms`.",
                f"Agent final message: `{agent_result.last_message or 'n/a'}`.",
                f"Review submissions persisted: `{len(review_submissions)}`.",
                f"Adjudications persisted: `{adjudication_count}`.",
                f"CLI transcript entries captured: `{len(ctx.cli_commands)}`.",
                f"Hidden benchmark path commands: "
                f"`{len(hidden_benchmark_path_commands)}`.",
                f"Truth probe commands: `{len(truth_probe_commands)}`.",
            ]
        )
        stage_summaries = [
            s
            for s in [
                paper_direct_model_summary,
                model_operated_summary,
                workflow_autorun_summary,
                workflow_reviewed_summary,
                operator_label_summary,
            ]
            if s is not None
        ]
        tax_breakdown = compute_stage_deltas(
            stage_summaries,
            bundle.metrics,
        )
        operator_summary.tax_breakdown = tax_breakdown
        operator_summary.diagnostics = operator_diagnostics.model_dump(mode="json")

        # Build lookup for assertions
        metrics_by_id = {m.metric_id: m for m in operator_summary.metrics}
        checklist_metric = metrics_by_id["operator_checklist"]
        per_check = checklist_metric.details.get("per_check", {})

        report_base = render_grounded_stage_report(
            bundle=bundle,
            summaries=stage_summaries,
            tax_breakdown=tax_breakdown,
        )
        report = report_base
        report += "\n## Operator Overall\n"
        report += f"- Operator overall score: `{operator_summary.overall_score:.4f}`\n"
        report += (
            f"- Operator label score (`operator_reviewed`): "
            f"`{operator_label_summary.overall_score:.4f}`\n"
        )
        report += f"- Operator checklist score: `{checklist_metric.value:.4f}`\n"
        report += "\n## Single-Prompt Run\n"
        report += f"- Runner: `{runner}`\n"
        report += f"- Prompt: `{prompt_text}`\n"
        report += f"- Agent last message: `{agent_result.last_message or 'n/a'}`\n"
        report += f"- Agent outputs persisted: `{len(agent_outputs)}`\n"
        report += f"- Review submissions persisted: `{len(review_submissions)}`\n"
        report += f"- Extracted shell commands: `{len(shell_commands)}`\n"
        report += f"- Non-CLI surface commands: `{len(non_cli_surface_commands)}`\n"
        report += (
            f"- Hidden benchmark path commands: "
            f"`{len(hidden_benchmark_path_commands)}`\n"
        )
        report += f"- Truth probe commands: `{len(truth_probe_commands)}`\n"
        report += f"- Adjudications persisted: `{adjudication_count}`\n"
        report += (
            f"- Agent wrote benchmark artifacts: "
            f"`{agent_wrote_summary and agent_wrote_report}`\n"
        )
        report = render_grounded_stage_report(
            bundle=bundle,
            summaries=stage_summaries,
            tax_breakdown=tax_breakdown,
        )
        report += "\n## Operator Overall\n"
        report += f"- Operator overall score: `{operator_summary.overall_score:.4f}`\n"
        report += (
            f"- Operator label score (`operator_reviewed`): "
            f"`{operator_label_summary.overall_score:.4f}`\n"
        )
        report += f"- Operator checklist score: `{checklist_metric.value:.4f}`\n"
        report += "\n## Single-Prompt Run\n"
        report += f"- Runner: `{runner}`\n"
        report += f"- Prompt: `{prompt_text}`\n"
        report += f"- Agent last message: `{agent_result.last_message or 'n/a'}`\n"
        report += f"- Agent outputs persisted: `{len(agent_outputs)}`\n"
        report += f"- Review submissions persisted: `{len(review_submissions)}`\n"
        report += f"- Extracted shell commands: `{len(shell_commands)}`\n"
        report += f"- Non-CLI surface commands: `{len(non_cli_surface_commands)}`\n"
        report += (
            f"- Hidden benchmark path commands: "
            f"`{len(hidden_benchmark_path_commands)}`\n"
        )
        report += f"- Truth probe commands: `{len(truth_probe_commands)}`\n"
        report += f"- Adjudications persisted: `{adjudication_count}`\n"
        report += (
            f"- Agent wrote benchmark artifacts: "
            f"`{agent_wrote_summary and agent_wrote_report}`\n"
        )

        summary_path, report_path = write_run_outputs(
            operator_summary,
            report,
            fixture.workspace_root / "workbench" / "benchmarks" / "runs",
            evidence=_build_operator_run_evidence(
                ctx=ctx,
                raw_records=fixture.raw_records,
                molabel_gold_rows=fixture.molabel_gold_rows,
                human_rows=fixture.human_rows,
                benchmark_review_rows=fixture.review_rows,
                agent_outputs=agent_outputs,
                review_submissions=review_submissions,
                review_events=review_events,
                shell_commands=shell_commands,
                shell_audit=shell_audit,
                agent_result=agent_result,
                operator_summary=operator_summary,
                operator_label_summary=operator_label_summary,
                workflow_autorun_summary=workflow_autorun_summary,
                workflow_reviewed_summary=workflow_reviewed_summary,
                tax_breakdown=tax_breakdown,
                agent_summary_payload=agent_summary_payload,
            ),
        )

        # --- Full report output ---
        print("\n" + "=" * 72)
        print(report)
        print("=" * 72)
        print("\n--- Scores ---")
        if paper_direct_model_summary:
            print(
                f"Paper-direct model score: "
                f"{paper_direct_model_summary.overall_score:.4f}"
            )
            for m in paper_direct_model_summary.metrics:
                print(f"  {m.metric_id}: {m.value:.4f}")
        if model_operated_summary:
            print(
                f"Model-operated score:     {model_operated_summary.overall_score:.4f}"
            )
            for m in model_operated_summary.metrics:
                print(f"  {m.metric_id}: {m.value:.4f}")
        print(f"Workflow autorun score:   {workflow_autorun_summary.overall_score:.4f}")
        for m in workflow_autorun_summary.metrics:
            print(f"  {m.metric_id}: {m.value:.4f}")
        print(
            f"Workflow reviewed score:  {workflow_reviewed_summary.overall_score:.4f}"
        )
        for m in workflow_reviewed_summary.metrics:
            print(f"  {m.metric_id}: {m.value:.4f}")
        print(f"Operator label score:     {operator_label_summary.overall_score:.4f}")
        for m in operator_label_summary.metrics:
            print(f"  {m.metric_id}: {m.value:.4f}")
        print(f"Operator overall score:   {operator_summary.overall_score:.4f}")
        for m in operator_summary.metrics:
            print(f"  {m.metric_id}: {m.value:.4f}")
        print("\n--- Tax Breakdown ---")
        for t in tax_breakdown:
            print(f"  {t.tax_id}: {t.value:.4f}")
        print("\n--- Operator Checklist ---")
        print(f"  Checklist score: {checklist_metric.value:.4f}")
        for check_id, passed in per_check.items():
            status = "PASS" if passed else "FAIL"
            print(f"  [{status}] {check_id}")
        print("\n--- Command Audit ---")
        print(f"  Non-CLI surface commands: {len(non_cli_surface_commands)}")
        print(
            f"  Hidden benchmark path commands: {len(hidden_benchmark_path_commands)}"
        )
        print(f"  Truth probe commands: {len(truth_probe_commands)}")
        print("\n--- Diagnostics ---")
        print(
            "  Proposal exact-match rate: "
            f"{operator_diagnostics.proposal_exact_match_rate:.4f}"
        )
        print(
            "  Review exact-match rate: "
            f"{operator_diagnostics.review_exact_match_rate:.4f}"
        )
        print(
            "  Proposal -> review delta: "
            f"{operator_diagnostics.proposal_to_review_delta:+.4f}"
        )
        print(f"  Operator lift count: {operator_diagnostics.operator_lift_count}")
        print(
            "  Accept AI / edit AI / correct / reject AI / skip: "
            f"{operator_diagnostics.accept_ai_count} / "
            f"{operator_diagnostics.edit_ai_count} / "
            f"{operator_diagnostics.correct_count} / "
            f"{operator_diagnostics.reject_ai_count} / "
            f"{operator_diagnostics.skip_count}"
        )
        print(f"  Truthfulness ok: {operator_diagnostics.truthfulness_ok}")
        print("\n--- Coverage ---")
        print(
            f"  Records reviewed: {len(review_submissions)}/{len(fixture.raw_records)}"
        )
        print(f"  Agent run duration: {agent_result.duration_ms / 1000:.1f}s")
        print(f"  API calls: {ctx.llm_calls}")
        print(f"  Shell commands: {len(shell_commands)}")
        print(f"  Runner: {runner}")
        print("=" * 72 + "\n")

        # --- Blocking gates ---
        # Check values directly (not via per_check) so they work even if
        # a benchmark's operator.yaml hasn't declared the check yet.
        assert model_profile_count >= 1, (
            f"BLOCKING: No MiniMax 2.7 model profile (count={model_profile_count})"
        )
        assert strategy_values == {"llm-structured-output"} and model_values == {
            "minimax-2.7"
        }, (
            "BLOCKING: Proposal stage did not use MiniMax 2.7 structured output "
            f"(strategies={sorted(strategy_values)}, models={sorted(model_values)})"
        )
        assert fixture.original_hashes == hash_paths(
            fixture.authority_root,
            list(fixture.original_hashes.keys()),
        ), "BLOCKING: Agent modified benchmark fixture files"

        # --- Minimum thresholds (generalized via primary metric) ---
        primary_metric_id = bundle.metrics.primary_metric_id
        primary_metric = metrics_by_id.get(primary_metric_id)
        assert primary_metric is not None, (
            f"No {primary_metric_id} metric in operator summary"
        )

        # Find lowest non-oracle baseline for primary metric
        min_threshold = 0.0
        for baseline in bundle.baselines.baselines:
            is_oracle = (
                baseline.baseline_id.endswith("_oracle")
                or baseline.baseline_id == "paper_oracle"
            )
            if is_oracle:
                continue
            baseline_val = baseline.metrics.get(primary_metric_id)
            if baseline_val is not None and baseline_val > min_threshold:
                min_threshold = baseline_val

        if min_threshold > 0.0:
            assert primary_metric.value >= min_threshold, (
                f"{primary_metric_id}={primary_metric.value:.4f} is below the "
                f"baseline threshold ({min_threshold})"
            )

        assert checklist_metric.value > 0.8, (
            f"Checklist score={checklist_metric.value:.4f} below 0.8 minimum. "
            f"Per-check: {per_check}"
        )

        expected_records = len(fixture.raw_records)
        assert len(review_submissions) == expected_records, (
            f"Coverage: {len(review_submissions)}/{expected_records} records"
        )

        assert summary_path.exists()
        assert report_path.exists()

        # --- Aspirational (warn, don't fail) ---
        if primary_metric.value <= 0.7:
            ctx.warnings.append(
                f"Aspirational: {primary_metric_id}="
                f"{primary_metric.value:.4f} below 0.7 target"
            )

        op_tax = next(
            (t for t in tax_breakdown if t.tax_id == "operator_tax"),
            None,
        )
        if op_tax and abs(op_tax.value) > 0.15:
            ctx.warnings.append(
                f"Aspirational: operator_tax={op_tax.value:.4f} exceeds 0.15 threshold"
            )
        if hidden_benchmark_path_commands:
            ctx.warnings.append(
                "Audit: operator touched hidden benchmark paths "
                f"{len(hidden_benchmark_path_commands)} time(s)"
            )
        if non_cli_surface_commands:
            ctx.warnings.append(
                "Audit: operator used non-CLI/API-style shell commands "
                f"{len(non_cli_surface_commands)} time(s)"
            )
        if truth_probe_commands:
            ctx.warnings.append(
                "Audit: operator issued truth-probe commands "
                f"{len(truth_probe_commands)} time(s)"
            )

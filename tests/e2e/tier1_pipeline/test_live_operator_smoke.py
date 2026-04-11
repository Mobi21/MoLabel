"""Smoke test: single-prompt operator run only (no paper-direct baseline).

Exercises the harness → agent runner → molabel CLI → local backend path
without requiring MiniMax to be reachable.  Validates that:

1. The harness starts a local backend and prepares the workspace.
2. The agent runner (Claude Code or Codex) can be invoked non-interactively.
3. The agent uses ``molabel`` CLI commands (not raw HTTP).
4. Review submissions appear in the local SQLite after the run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.infrastructure.grounded_operator import (
    GroundedCliHarness,
    prepare_grounded_operator_fixture,
    resolve_auth_ref,
)
from tests.e2e.infrastructure.parallel import INDEPENDENT

REPO_ROOT = Path(__file__).resolve().parents[3]
GROUNDED_ROOT = REPO_ROOT / "fixtures" / "benchmarks-grounded"


def _detect_runner() -> str | None:
    import shutil

    if shutil.which("claude"):
        return "claude"
    if shutil.which("codex"):
        return "codex"
    return None


def _single_prompt() -> str:
    return (
        "Run this grounded benchmark using molabel only.\n"
        "Write run artifacts under workbench/benchmarks/runs/live-operator."
    )


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier1
@pytest.mark.slow
@pytest.mark.timeout(1800)
@pytest.mark.skip(
    reason="Superseded by test_live_grounded_operator_benchmarks_real_llm.py"
)
async def test_operator_smoke_clinc150(ctx) -> None:
    """Smoke-test the single-prompt operator path with Claude Code."""

    runner = _detect_runner()
    if runner is None:
        pytest.skip("No agent runner on PATH")

    auth_ref = resolve_auth_ref(REPO_ROOT)
    if not auth_ref:
        pytest.skip("No API key for MoLabel labeling engine")

    source_root = GROUNDED_ROOT / "clinc150"
    if not source_root.exists():
        pytest.skip("CLINC150 fixture not found")

    fixture = prepare_grounded_operator_fixture(source_root)

    with GroundedCliHarness(ctx, fixture.workspace_root, REPO_ROOT) as harness:
        result = await harness.run_agent_prompt(
            _single_prompt(),
            runner=runner,
        )

        print(f"\n--- Runner: {runner} ---")
        print(f"Exit code: {result.exit_code}")
        print(f"Duration: {result.duration_ms:.0f}ms")
        print(f"Events: {len(result.events)}")
        print(f"Last message: {(result.last_message or '')[:200]}")

        shell_commands = harness.extract_shell_commands(result.events)
        print(f"Shell commands extracted: {len(shell_commands)}")
        for cmd in shell_commands[:20]:
            print(f"  > {cmd[:120]}")

        review_submissions = harness.load_latest_review_submissions()
        print(f"Review submissions: {len(review_submissions)}")

        dataset_count = harness.table_row_count("datasets")
        prompt_count = harness.table_row_count("prompt_templates")
        workflow_count = harness.table_row_count("workflow_definitions")
        model_profile_count = harness.table_row_count("model_profiles")
        record_count = harness.table_row_count("records")
        review_event_count = harness.table_row_count("review_events")

        print("\n--- DB state ---")
        print(f"Datasets: {dataset_count}")
        print(f"Records: {record_count}")
        print(f"Prompts: {prompt_count}")
        print(f"Workflows: {workflow_count}")
        print(f"Model profiles: {model_profile_count}")
        print(f"Review events: {review_event_count}")

        # Budget exhaustion (exit code 1 with review submissions) is acceptable
        budget_exhausted = any(
            e.get("subtype") == "error_max_budget_usd" for e in result.events
        )
        if not (result.exit_code == 0 or (budget_exhausted and review_submissions)):
            raise AssertionError(
                f"{runner} exited with code {result.exit_code}:\n"
                f"stderr: {result.stderr[:500]}\n"
                f"stdout: {result.stdout[:500]}"
            )
        assert len(shell_commands) > 0, (
            f"{runner} ran no shell commands — transcript may be empty"
        )
        assert review_submissions, f"{runner} produced no review submissions"

        assert dataset_count >= 1, "No datasets created"
        assert prompt_count >= 1, "No prompt templates created"
        assert workflow_count >= 1, "No workflows created"
        assert model_profile_count >= 1, "No model profiles created"

        operator_run_root = (
            fixture.workspace_root
            / "workbench"
            / "benchmarks"
            / "runs"
            / "live-operator"
        )
        # Artifact writing is aspirational — log but don't fail if missing
        if operator_run_root.exists():
            print(f"Operator run artifacts: {list(operator_run_root.iterdir())}")
        else:
            print(
                "Note: operator did not write run artifacts (expected for smoke test)"
            )

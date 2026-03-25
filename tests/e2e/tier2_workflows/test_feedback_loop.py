"""Tier 2 — Agent feedback loop test (T2-32).

Tests the full agent feedback cycle:
  agent → human review → correction accumulation → prompt refinement → re-run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molabel.core.types import WorkflowStepExecutionStatus
from molabel.core.workflow.context import RecordSet, WorkflowContext
from molabel.core.workflow.engine import WorkflowEngine, create_default_registry
from molabel.core.workflow.parser import parse_workflow_yaml
from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.parallel import INDEPENDENT

FIXTURES = Path(__file__).parent.parent / "fixtures" / "workflows"


def _make_context(exec_id: str = "exec-1") -> WorkflowContext:
    ctx = WorkflowContext(
        workspace_id="ws-test",
        workflow_execution_id=exec_id,
        workflow_version=1,
    )
    ctx.record_sets["seed"] = RecordSet(
        record_ids=[f"r{i}" for i in range(15)],
        record_count=15,
        description="seed records",
    )
    ctx.active_record_set_id = "seed"
    return ctx


def _make_engine() -> WorkflowEngine:
    return WorkflowEngine(registry=create_default_registry())


def _patch_agent_configs(engine: WorkflowEngine) -> None:
    """Add required 'model' field to all agent_run step configs."""
    for step_id, config in engine._step_configs.items():
        step = engine._definition.step_index.get(step_id)
        if step and step.type == "agent_run" and not config.get("model"):
            engine._step_configs[step_id] = {**config, "model": "test-model"}


# ---------------------------------------------------------------------------
# T2-32 — Full agent feedback cycle
# ---------------------------------------------------------------------------


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier2
async def test_t2_32_agent_feedback_loop(ctx):
    """T2-32: agent → review → corrections → prompt refinement → compare runs."""
    wf = parse_workflow_yaml(FIXTURES / "wf_feedback_loop.yaml")

    with checkpoint(ctx, "parse"):
        assert wf.name == "Agent Feedback Loop (T2-32)"
        assert len(wf.steps) == 9
        # Verify key steps exist
        initial_run = wf.get_step("initial_agent_run")
        refined_run = wf.get_step("refined_agent_run")
        compare_step = wf.get_step("compare_versions")

        assert initial_run.type == "agent_run"
        assert initial_run.config.get("prompt_ref") == "prompts/sentiment-v1"

        assert refined_run.type == "agent_run"
        assert refined_run.config.get("prompt_ref") == "prompts/sentiment-v2"
        assert refined_run.config.get("use_corrections") is True

        assert compare_step.type == "agent_compare"

    with checkpoint(ctx, "breakpoint_on_human_review"):
        review_step = wf.get_step("human_review")
        assert review_step.breakpoint is True

    with checkpoint(ctx, "dag_order"):
        order = wf.topological_order()
        initial_idx = order.index("initial_agent_run")
        review_idx = order.index("human_review")
        agreement_idx = order.index("agreement")
        snapshot_idx = order.index("snapshot_baseline")
        refined_idx = order.index("refined_agent_run")
        compare_idx = order.index("compare_versions")
        export_idx = order.index("export")

        assert initial_idx < review_idx
        assert review_idx < agreement_idx
        assert snapshot_idx < refined_idx
        assert refined_idx < compare_idx
        assert compare_idx < export_idx

    with checkpoint(ctx, "initial_agent_run_phase"):
        engine = _make_engine()
        wf_ctx = _make_context("t2-32")
        engine.initialize(wf, wf_ctx)
        _patch_agent_configs(engine)

        engine._step_states["initial_agent_run"] = WorkflowStepExecutionStatus.ready
        result = engine.execute_step("initial_agent_run")
        assert result.success

        # agent_run ID recorded in context
        assert len(wf_ctx.agent_run_ids) >= 1
        first_run_id = wf_ctx.agent_run_ids[0]

    with checkpoint(ctx, "human_review_hits_breakpoint"):
        # review step has breakpoint=true in fixture
        engine._step_states["human_review"] = WorkflowStepExecutionStatus.ready
        bp_result = engine.execute_step("human_review")

        assert bp_result.output.status == "waiting_for_breakpoint"
        assert (
            engine._step_states["human_review"]
            == WorkflowStepExecutionStatus.waiting_for_breakpoint
        )

    with checkpoint(ctx, "corrections_accumulated"):
        # Simulate: reviewer makes corrections (written to context variables)
        wf_ctx.variables["corrections.batch_id"] = "batch-001"
        wf_ctx.variables["corrections.count"] = 8
        wf_ctx.variables["corrections.status"] = "pending_refinement"

        assert wf_ctx.variables["corrections.count"] == 8

    with checkpoint(ctx, "prompt_v2_created"):
        # Simulate: corrections trigger prompt refinement (v2 created)
        # This is represented by the refined_agent_run step using prompt_ref v2
        wf_ctx.variables["prompt.active_version"] = "v2"
        wf_ctx.variables["prompts/sentiment-v2.created"] = True

        assert wf_ctx.variables["prompt.active_version"] == "v2"

    with checkpoint(ctx, "continue_review_and_proceed"):
        # Continue past the breakpoint
        engine.continue_breakpoint("human_review")
        result_review = engine.execute_step("human_review")
        # human_review transitions to waiting_for_human
        assert result_review.waiting_for_human is True

        # Simulate human review completion
        engine.resume_human_step("human_review")
        engine._update_ready_steps()

    with checkpoint(ctx, "agreement_and_quality_phases"):
        for step_id in ["agreement", "quality_check", "snapshot_baseline"]:
            engine._step_states[step_id] = WorkflowStepExecutionStatus.ready
            result = engine.execute_step(step_id)
            assert result.success, f"Step {step_id} failed: {result.error}"

    with checkpoint(ctx, "refined_agent_run_phase"):
        engine._step_states["refined_agent_run"] = WorkflowStepExecutionStatus.ready
        result_refined = engine.execute_step("refined_agent_run")
        assert result_refined.success

        # Second run ID should be different from first
        assert len(wf_ctx.agent_run_ids) >= 2
        second_run_id = wf_ctx.agent_run_ids[-1]
        assert second_run_id != first_run_id

    with checkpoint(ctx, "compare_v1_vs_v2"):
        compare_config = compare_step.config
        # compare_versions lists the runs to compare
        compare_runs = compare_config.get("compare_runs", [])
        assert "initial_agent_run" in compare_runs
        assert "refined_agent_run" in compare_runs

        merge_strategy = compare_config.get("merge_strategy", "")
        assert merge_strategy == "prefer_higher_confidence"

    with checkpoint(ctx, "export_includes_run_metadata"):
        export_step = wf.get_step("export")
        assert export_step.config.get("include_run_metadata") is True

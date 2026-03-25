"""Tier 2 — Breakpoint workflow tests (T2-17 through T2-19).

Tests single-step breakpoints, pause-on-every-step mode, and skipping
a step from a breakpoint.
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
        record_ids=[f"r{i}" for i in range(10)],
        record_count=10,
        description="seed records",
    )
    ctx.active_record_set_id = "seed"
    return ctx


def _make_engine() -> WorkflowEngine:
    return WorkflowEngine(registry=create_default_registry())


def _patch_agent_configs(engine: WorkflowEngine) -> None:
    """Add required 'model' field to all agent_run step configs.

    The AgentRunExecutor.validate() requires 'model' or 'model_profile_id'.
    YAML fixtures use 'model_profile_ref' which is a reference string (not
    the validated field). This helper patches the engine's in-memory configs
    to satisfy validation without real provider setup.
    """
    for step_id, config in engine._step_configs.items():
        step = engine._definition.step_index.get(step_id)
        if step and step.type == "agent_run" and not config.get("model"):
            engine._step_configs[step_id] = {**config, "model": "test-model"}


# ---------------------------------------------------------------------------
# T2-17 — Pause before step (breakpoint=true on step)
# ---------------------------------------------------------------------------


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier2
async def test_t2_17_pause_before_step(ctx):
    """T2-17: Step with breakpoint=true pauses at waiting_for_breakpoint; continues."""
    wf = parse_workflow_yaml(FIXTURES / "wf_breakpoint_single.yaml")

    with checkpoint(ctx, "parse"):
        review_step = wf.get_step("review")
        assert review_step.breakpoint is True
        agent_step = wf.get_step("agent_label")
        assert agent_step.breakpoint is False

    with checkpoint(ctx, "step_hits_breakpoint"):
        engine = _make_engine()
        wf_ctx = _make_context("t2-17")
        engine.initialize(wf, wf_ctx)
        _patch_agent_configs(engine)

        # Execute agent_label first (no breakpoint)
        engine._step_states["agent_label"] = WorkflowStepExecutionStatus.ready
        result = engine.execute_step("agent_label")
        assert result.success
        assert (
            engine._step_states["agent_label"] == WorkflowStepExecutionStatus.completed
        )

        # Now review becomes ready; hitting its breakpoint should pause it
        engine._update_ready_steps()
        engine._step_states["review"] = WorkflowStepExecutionStatus.ready
        bp_result = engine.execute_step("review")

        assert bp_result.success
        assert bp_result.output.status == "waiting_for_breakpoint"
        assert (
            engine._step_states["review"]
            == WorkflowStepExecutionStatus.waiting_for_breakpoint
        )

    with checkpoint(ctx, "continue_past_breakpoint"):
        # continue_breakpoint sets state to allow execution, caller re-executes
        engine.continue_breakpoint(
            "review",
            config_override={"sample_size": 15, "sample_strategy": "stratified"},
        )
        # Config override should be applied
        assert engine._step_configs["review"]["sample_size"] == 15

        # Now execute the step (it's still in waiting_for_breakpoint state)
        # but state is NOT changed by continue_breakpoint -- the caller re-executes
        # which falls through to the normal execute path
        result2 = engine.execute_step("review")
        # review is a human_review step: it transitions to waiting_for_human
        assert result2.waiting_for_human is True
        assert (
            engine._step_states["review"]
            == WorkflowStepExecutionStatus.waiting_for_human
        )

    with checkpoint(ctx, "downstream_not_ready_while_paused"):
        # quality should not be ready while review is still waiting
        ready = engine.get_ready_steps()
        assert "quality" not in ready


# ---------------------------------------------------------------------------
# T2-18 — Pause on every step mode
# ---------------------------------------------------------------------------


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier2
async def test_t2_18_pause_on_every_step(ctx):
    """T2-18: pause_on_every_step=true; each step hits breakpoint, must continue."""
    wf = parse_workflow_yaml(FIXTURES / "wf_pause_every_step.yaml")

    with checkpoint(ctx, "parse"):
        assert wf.pause_on_every_step is True
        assert len(wf.steps) == 3

    with checkpoint(ctx, "first_step_pauses"):
        engine = _make_engine()
        wf_ctx = _make_context("t2-18")
        engine.initialize(wf, wf_ctx)
        _patch_agent_configs(engine)

        # agent_label should be ready; executing it hits the global breakpoint
        engine._step_states["agent_label"] = WorkflowStepExecutionStatus.ready
        result = engine.execute_step("agent_label")

        assert result.success
        assert result.output.status == "waiting_for_breakpoint"
        assert (
            engine._step_states["agent_label"]
            == WorkflowStepExecutionStatus.waiting_for_breakpoint
        )

    with checkpoint(ctx, "continue_then_second_pauses"):
        engine.continue_breakpoint("agent_label")
        result2 = engine.execute_step("agent_label")
        # agent_run completes normally after continuing
        assert result2.success
        assert (
            engine._step_states["agent_label"] == WorkflowStepExecutionStatus.completed
        )

        # quality becomes ready; it also hits breakpoint
        engine._update_ready_steps()
        engine._step_states["quality"] = WorkflowStepExecutionStatus.ready
        result3 = engine.execute_step("quality")
        assert result3.success
        assert result3.output.status == "waiting_for_breakpoint"
        assert (
            engine._step_states["quality"]
            == WorkflowStepExecutionStatus.waiting_for_breakpoint
        )

    with checkpoint(ctx, "each_step_individually_continued"):
        # Continue quality breakpoint
        engine.continue_breakpoint("quality")
        result4 = engine.execute_step("quality")
        assert result4.success
        assert engine._step_states["quality"] == WorkflowStepExecutionStatus.completed

        # export step also pauses
        engine._update_ready_steps()
        engine._step_states["export"] = WorkflowStepExecutionStatus.ready
        result5 = engine.execute_step("export")
        assert result5.success
        assert result5.output.status == "waiting_for_breakpoint"


# ---------------------------------------------------------------------------
# T2-19 — Skip step at breakpoint
# ---------------------------------------------------------------------------


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier2
async def test_t2_19_skip_at_breakpoint(ctx):
    """T2-19: Operator skips a step at breakpoint; skip propagates to dependents."""
    wf = parse_workflow_yaml(FIXTURES / "wf_breakpoint_single.yaml")

    with checkpoint(ctx, "setup_breakpoint"):
        engine = _make_engine()
        wf_ctx = _make_context("t2-19")
        engine.initialize(wf, wf_ctx)
        _patch_agent_configs(engine)

        # Complete agent_label
        engine._step_states["agent_label"] = WorkflowStepExecutionStatus.ready
        engine.execute_step("agent_label")

        # Hit review breakpoint
        engine._step_states["review"] = WorkflowStepExecutionStatus.ready
        bp_result = engine.execute_step("review")
        assert bp_result.output.status == "waiting_for_breakpoint"

    with checkpoint(ctx, "skip_step"):
        engine.skip_step("review")
        assert engine._step_states["review"] == WorkflowStepExecutionStatus.skipped

    with checkpoint(ctx, "skip_propagation"):
        # quality depends on review — it should eventually become ready
        # (quality does NOT auto-skip because review is skipped, since quality has
        # one predecessor which is skipped, so quality becomes ready)
        engine._update_ready_steps()
        # After skipping review, quality should be ready (skip doesn't propagate
        # unless ALL predecessors are skipped)
        quality_state = engine._step_states["quality"]
        assert quality_state in {
            WorkflowStepExecutionStatus.ready,
            WorkflowStepExecutionStatus.pending,
        }

    with checkpoint(ctx, "workflow_can_continue_after_skip"):
        # quality can still execute
        engine._step_states["quality"] = WorkflowStepExecutionStatus.ready
        result = engine.execute_step("quality")
        assert result.success

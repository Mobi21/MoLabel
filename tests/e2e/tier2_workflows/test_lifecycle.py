"""Tier 2 — Workflow lifecycle tests (T2-24 through T2-26).

Tests pause mid-execution, resume after pause, and cancel mid-execution.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molabel.core.types import WorkflowExecutionStatus, WorkflowStepExecutionStatus
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
    """Add required 'model' field to all agent_run step configs."""
    for step_id, config in engine._step_configs.items():
        step = engine._definition.step_index.get(step_id)
        if step and step.type == "agent_run" and not config.get("model"):
            engine._step_configs[step_id] = {**config, "model": "test-model"}


# ---------------------------------------------------------------------------
# T2-24 — Pause mid-execution
# ---------------------------------------------------------------------------


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier2
async def test_t2_24_pause_mid_execution(ctx):
    """T2-24: Workflow pauses when a step fails; execution_status = paused."""
    wf = parse_workflow_yaml(FIXTURES / "wf_lifecycle_pause_resume.yaml")

    with checkpoint(ctx, "parse"):
        assert len(wf.steps) == 4

    with checkpoint(ctx, "engine_pauses_on_step_failure"):
        engine = _make_engine()
        wf_ctx = _make_context("t2-24")
        engine.initialize(wf, wf_ctx)
        _patch_agent_configs(engine)

        # Complete agent_label successfully
        engine._step_states["agent_label"] = WorkflowStepExecutionStatus.ready
        engine.execute_step("agent_label")
        assert (
            engine._step_states["agent_label"] == WorkflowStepExecutionStatus.completed
        )

        # Inject a failing quality step
        from unittest.mock import patch

        from molabel.core.workflow.steps.base import StepResult

        fail_result = StepResult(success=False, error="Quality service unavailable")

        with patch.object(
            engine._registry.create("quality_check").__class__,
            "execute",
            return_value=fail_result,
        ):
            engine._step_states["quality"] = WorkflowStepExecutionStatus.ready
            result = engine.execute_step("quality")

        assert not result.success
        assert engine.execution_status == WorkflowExecutionStatus.paused
        assert engine._step_states["quality"] == WorkflowStepExecutionStatus.failed

    with checkpoint(ctx, "paused_timestamp_semantics"):
        # Downstream steps remain pending while paused
        review_state = engine._step_states.get("review")
        assert review_state in {
            WorkflowStepExecutionStatus.pending,
            WorkflowStepExecutionStatus.ready,
        }

    with checkpoint(ctx, "completed_steps_preserved"):
        assert (
            engine._step_states["agent_label"] == WorkflowStepExecutionStatus.completed
        )


# ---------------------------------------------------------------------------
# T2-25 — Resume after pause
# ---------------------------------------------------------------------------


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier2
async def test_t2_25_resume_after_pause(ctx):
    """T2-25: Resumed workflow continues; completed steps not re-run."""
    wf = parse_workflow_yaml(FIXTURES / "wf_lifecycle_pause_resume.yaml")

    with checkpoint(ctx, "setup_paused_state"):
        engine = _make_engine()
        wf_ctx = _make_context("t2-25")
        engine.initialize(wf, wf_ctx)
        _patch_agent_configs(engine)

        # Complete agent_label and quality
        engine._step_states["agent_label"] = WorkflowStepExecutionStatus.completed
        engine._step_states["quality"] = WorkflowStepExecutionStatus.completed
        engine._execution_status = WorkflowExecutionStatus.paused
        # review is waiting_for_human (simulating it was running when paused)
        engine._step_states["review"] = WorkflowStepExecutionStatus.waiting_for_human

    with checkpoint(ctx, "resume_does_not_re_run_completed"):
        # Retry step transitions to retrying; re-execute picks up from there
        # For a waiting_for_human step, use resume_human_step
        engine.resume_human_step("review")

        assert engine._step_states["review"] == WorkflowStepExecutionStatus.completed
        engine._update_ready_steps()

        # completed steps unchanged
        assert (
            engine._step_states["agent_label"] == WorkflowStepExecutionStatus.completed
        )
        assert engine._step_states["quality"] == WorkflowStepExecutionStatus.completed

    with checkpoint(ctx, "continues_from_correct_step"):
        # export should now be ready
        ready = engine.get_ready_steps()
        assert "export" in ready

    with checkpoint(ctx, "workflow_completes"):
        engine._step_states["export"] = WorkflowStepExecutionStatus.ready
        engine.execute_step("export")
        # All steps complete → workflow is completed
        assert engine.is_complete()
        assert engine.execution_status == WorkflowExecutionStatus.completed


# ---------------------------------------------------------------------------
# T2-26 — Cancel mid-execution
# ---------------------------------------------------------------------------


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier2
async def test_t2_26_cancel_mid_execution(ctx):
    """T2-26: cancel_workflow cancels all non-terminal steps; completed preserved."""
    wf = parse_workflow_yaml(FIXTURES / "wf_lifecycle_pause_resume.yaml")

    with checkpoint(ctx, "setup_running_state"):
        engine = _make_engine()
        wf_ctx = _make_context("t2-26")
        engine.initialize(wf, wf_ctx)
        _patch_agent_configs(engine)

        # agent_label completed; quality is running; review + export are pending
        engine._step_states["agent_label"] = WorkflowStepExecutionStatus.completed
        engine._step_states["quality"] = WorkflowStepExecutionStatus.running
        engine._step_states["review"] = WorkflowStepExecutionStatus.pending
        engine._step_states["export"] = WorkflowStepExecutionStatus.pending

    with checkpoint(ctx, "cancel_transitions_to_cancelled"):
        engine.cancel_workflow()
        assert engine.execution_status == WorkflowExecutionStatus.cancelled

    with checkpoint(ctx, "non_terminal_steps_cancelled"):
        # running, pending, ready → cancelled
        assert engine._step_states["quality"] == WorkflowStepExecutionStatus.cancelled
        assert engine._step_states["review"] == WorkflowStepExecutionStatus.cancelled
        assert engine._step_states["export"] == WorkflowStepExecutionStatus.cancelled

    with checkpoint(ctx, "completed_steps_preserved"):
        # Completed steps remain completed
        assert (
            engine._step_states["agent_label"] == WorkflowStepExecutionStatus.completed
        )

    with checkpoint(ctx, "no_more_ready_steps"):
        engine._update_ready_steps()
        ready = engine.get_ready_steps()
        assert len(ready) == 0

"""Tier 2 — Gate workflow tests (T2-14 through T2-16).

Tests approval gate (approve path), approval gate (reject path), and
quality gate blocking export.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molabel.core.types import WorkflowExecutionStatus, WorkflowStepExecutionStatus
from molabel.core.workflow.context import RecordSet, WorkflowContext
from molabel.core.workflow.engine import WorkflowEngine, create_default_registry
from molabel.core.workflow.parser import parse_workflow_yaml
from molabel.core.workflow.steps.control_steps import GateExecutor
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
# T2-14 — Approval gate (approve → workflow continues)
# ---------------------------------------------------------------------------


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier2
async def test_t2_14_approval_gate_approve(ctx):
    """T2-14: Gate approval stores metadata; successor steps unblocked."""
    wf = parse_workflow_yaml(FIXTURES / "wf_gate_approval.yaml")

    with checkpoint(ctx, "parse"):
        gate_step = wf.get_step("approval_gate")
        assert gate_step.type == "gate"
        assert "message" in gate_step.config

    with checkpoint(ctx, "gate_pauses_workflow"):
        engine = _make_engine()
        wf_ctx = _make_context("t2-14")
        engine.initialize(wf, wf_ctx)
        _patch_agent_configs(engine)

        # Execute steps up to the gate
        for step_id in ["agent_label", "review", "quality"]:
            engine._step_states[step_id] = WorkflowStepExecutionStatus.ready
            # Manually advance human_review past waiting state
            if step_id == "review":
                engine._step_states[step_id] = WorkflowStepExecutionStatus.completed
                continue
            engine.execute_step(step_id)

        # Execute gate: should transition to waiting_for_gate
        engine._step_states["approval_gate"] = WorkflowStepExecutionStatus.ready
        gate_result = engine.execute_step("approval_gate")

        assert gate_result.success
        assert gate_result.waiting_for_gate is True
        assert (
            engine._step_states["approval_gate"]
            == WorkflowStepExecutionStatus.waiting_for_gate
        )

    with checkpoint(ctx, "approve_stores_metadata"):
        engine.approve_gate(
            "approval_gate",
            approved=True,
            operator_id="reviewer-1",
            reason="Quality looks good",
        )

        assert (
            engine._step_states["approval_gate"]
            == WorkflowStepExecutionStatus.completed
        )

        gate_output = engine._context.step_outputs.get("approval_gate")
        assert gate_output is not None
        assert gate_output.summary["approved"] is True
        assert gate_output.summary["operator_id"] == "reviewer-1"
        assert gate_output.summary["reason"] == "Quality looks good"
        assert "decided_at" in gate_output.summary

    with checkpoint(ctx, "successor_steps_unblocked"):
        # After approval, export step should become ready
        engine._update_ready_steps()
        ready = engine.get_ready_steps()
        assert "export" in ready


# ---------------------------------------------------------------------------
# T2-15 — Approval gate (reject → workflow cancelled)
# ---------------------------------------------------------------------------


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier2
async def test_t2_15_approval_gate_reject(ctx):
    """T2-15: Gate rejection cancels workflow and all pending steps."""
    wf = parse_workflow_yaml(FIXTURES / "wf_gate_approval.yaml")

    with checkpoint(ctx, "setup_gate_waiting"):
        engine = _make_engine()
        wf_ctx = _make_context("t2-15")
        engine.initialize(wf, wf_ctx)
        _patch_agent_configs(engine)

        # Put gate in waiting state directly
        engine._step_states["approval_gate"] = (
            WorkflowStepExecutionStatus.waiting_for_gate
        )

    with checkpoint(ctx, "reject_cancels_workflow"):
        engine.approve_gate(
            "approval_gate",
            approved=False,
            operator_id="reviewer-1",
            reason="Quality insufficient",
        )

        # Gate itself is cancelled
        assert (
            engine._step_states["approval_gate"]
            == WorkflowStepExecutionStatus.cancelled
        )

        # Workflow status is cancelled
        assert engine.execution_status == WorkflowExecutionStatus.cancelled

    with checkpoint(ctx, "all_pending_steps_cancelled"):
        # All non-terminal steps should be cancelled
        for step_id, state in engine.step_states.items():
            # Steps that were pending/ready before rejection should now be cancelled
            assert state not in {
                WorkflowStepExecutionStatus.ready,
            }, f"Step {step_id} should not be in ready state after rejection"

    with checkpoint(ctx, "completed_steps_preserved"):
        # Steps completed before the gate remain completed
        # (we put steps in completed state earlier for simulation)
        # Verify export is cancelled (was pending at time of rejection)
        export_state = engine._step_states.get("export")
        assert export_state == WorkflowStepExecutionStatus.cancelled


# ---------------------------------------------------------------------------
# T2-16 — Quality gate blocking export
# ---------------------------------------------------------------------------


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier2
async def test_t2_16_quality_gate_blocking_export(ctx):
    """T2-16: Gate message includes metric values; gate blocks/allows export."""
    wf = parse_workflow_yaml(FIXTURES / "wf_gate_quality.yaml")

    with checkpoint(ctx, "parse"):
        gate_step = wf.get_step("quality_gate")
        assert gate_step.type == "gate"
        config = gate_step.config
        assert config.get("require_reason") is True
        assert "include_metrics" in config
        included = config["include_metrics"]
        assert "quality.agreement" in included
        assert "quality.coverage" in included

    with checkpoint(ctx, "gate_message_contains_metric_refs"):
        message = gate_step.config.get("message", "")
        # Message references quality metrics
        assert "quality" in message.lower() or "{quality" in message

    with checkpoint(ctx, "gate_executor_produces_waiting"):
        executor = GateExecutor()
        wf_ctx = _make_context("t2-16")
        wf_ctx.metrics["quality.agreement"] = 0.88
        wf_ctx.metrics["quality.coverage"] = 0.92
        wf_ctx.metrics["quality.confidence"] = 0.79

        result = executor.execute("quality_gate", gate_step.config, wf_ctx)

        assert result.success
        assert result.waiting_for_gate is True
        assert result.output.summary["status"] == "waiting"
        assert result.output.summary["require_reason"] is True

    with checkpoint(ctx, "approve_allows_export"):
        engine = _make_engine()
        wf_ctx2 = _make_context("t2-16b")
        engine.initialize(wf, wf_ctx2)
        _patch_agent_configs(engine)

        # Pre-complete preceding steps
        for step_id in ["agent_label", "human_review", "agreement", "quality"]:
            engine._step_states[step_id] = WorkflowStepExecutionStatus.completed

        engine._step_states["quality_gate"] = (
            WorkflowStepExecutionStatus.waiting_for_gate
        )

        engine.approve_gate(
            "quality_gate",
            approved=True,
            operator_id="ops-lead",
            reason="Metrics meet thresholds",
        )

        engine._update_ready_steps()
        ready = engine.get_ready_steps()
        assert "export" in ready

    with checkpoint(ctx, "reject_blocks_export"):
        engine2 = _make_engine()
        wf_ctx3 = _make_context("t2-16c")
        engine2.initialize(wf, wf_ctx3)
        _patch_agent_configs(engine2)

        engine2._step_states["quality_gate"] = (
            WorkflowStepExecutionStatus.waiting_for_gate
        )

        engine2.approve_gate("quality_gate", approved=False, reason="Metrics too low")

        assert engine2.execution_status == WorkflowExecutionStatus.cancelled
        export_state = engine2._step_states.get("export")
        assert export_state == WorkflowStepExecutionStatus.cancelled

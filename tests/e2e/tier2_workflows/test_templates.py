"""Tier 2 — Built-in template tests (T2-30 through T2-31).

Tests full_quality_pipeline.yaml and iterative_refinement.yaml
end-to-end: parse, DAG validation, execution simulation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molabel.core.types import WorkflowStepExecutionStatus
from molabel.core.workflow.context import RecordSet, WorkflowContext
from molabel.core.workflow.engine import WorkflowEngine, create_default_registry
from molabel.core.workflow.parser import parse_workflow_yaml
from molabel.core.workflow.steps.control_steps import LoopExecutor
from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.parallel import INDEPENDENT

TEMPLATES = (
    Path(__file__).parent.parent.parent.parent
    / "packages"
    / "molabel-core"
    / "src"
    / "molabel"
    / "core"
    / "workflow"
    / "templates"
)


def _make_context(exec_id: str = "exec-1") -> WorkflowContext:
    ctx = WorkflowContext(
        workspace_id="ws-test",
        workflow_execution_id=exec_id,
        workflow_version=1,
    )
    ctx.record_sets["seed"] = RecordSet(
        record_ids=[f"r{i}" for i in range(20)],
        record_count=20,
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
# T2-30 — full_quality_pipeline.yaml template end-to-end
# ---------------------------------------------------------------------------


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier2
async def test_t2_30_full_quality_pipeline_template(ctx):
    """T2-30: All 11 steps parse, DAG is acyclic, gate step pauses correctly."""
    wf = parse_workflow_yaml(TEMPLATES / "full_quality_pipeline.yaml")

    with checkpoint(ctx, "parse"):
        assert wf.name == "Full Quality Pipeline"
        assert len(wf.steps) == 11

    with checkpoint(ctx, "dag_no_cycles"):
        order = wf.topological_order()
        assert len(order) == 11

    with checkpoint(ctx, "all_step_types_registered"):
        registry = create_default_registry()
        for step in wf.steps:
            assert registry.has_executor(step.type), (
                f"No executor for step type: {step.type}"
            )

    with checkpoint(ctx, "gate_step_present"):
        gate_step = wf.get_step("approve_export")
        assert gate_step.type == "gate"
        assert "message" in gate_step.config

    with checkpoint(ctx, "gate_pauses_workflow"):
        engine = _make_engine()
        wf_ctx = _make_context("t2-30")
        engine.initialize(wf, wf_ctx)
        _patch_agent_configs(engine)

        # Fast-forward by manually completing steps before the gate
        steps_before_gate = [
            "ingest",
            "normalize",
            "calibration",
            "agent_label",
            "review",
            "agreement",
            "adjudication",
            "quality",
        ]
        for step_id in steps_before_gate:
            engine._step_states[step_id] = WorkflowStepExecutionStatus.completed

        # Execute gate step
        engine._update_ready_steps()
        engine._step_states["approve_export"] = WorkflowStepExecutionStatus.ready
        gate_result = engine.execute_step("approve_export")

        assert gate_result.waiting_for_gate is True
        assert (
            engine._step_states["approve_export"]
            == WorkflowStepExecutionStatus.waiting_for_gate
        )

    with checkpoint(ctx, "approve_unblocks_export_and_release"):
        engine.approve_gate("approve_export", approved=True, operator_id="admin")
        engine._update_ready_steps()
        ready = engine.get_ready_steps()
        assert "export_results" in ready

    with checkpoint(ctx, "implicit_predecessor_chain"):
        # Each step should have predecessor = previous step (implicit YAML order)
        for i, step in enumerate(wf.steps):
            preds = wf.predecessors[step.id]
            if i == 0:
                assert preds == []
            else:
                prev_step = wf.steps[i - 1]
                assert prev_step.id in preds


# ---------------------------------------------------------------------------
# T2-31 — iterative_refinement.yaml template end-to-end
# ---------------------------------------------------------------------------


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier2
async def test_t2_31_iterative_refinement_template(ctx):
    """T2-31: Refinement loop terminates on quality metric via metric-based loop."""
    wf = parse_workflow_yaml(TEMPLATES / "iterative_refinement.yaml")

    with checkpoint(ctx, "parse"):
        assert wf.name == "Iterative Refinement"
        # 9 steps: ingest, normalize, agent_label, sample, review, quality, loop, etc.
        assert len(wf.steps) == 9

    with checkpoint(ctx, "dag_no_cycles"):
        order = wf.topological_order()
        assert len(order) == 9

    with checkpoint(ctx, "loop_step_config"):
        loop_step = wf.get_step("refinement_loop")
        assert loop_step.type == "loop"
        term = loop_step.config["termination"]
        assert term["type"] == "metric"
        assert term["metric"] == "quality.agreement"
        assert float(term["threshold"]) == 0.95
        assert term.get("max_iterations", 10) >= 1

    with checkpoint(ctx, "loop_body_steps"):
        body_steps = loop_step.config["steps"]
        expected_body = ["agent_label", "sample_low_confidence", "review", "quality"]
        for sid in expected_body:
            assert sid in body_steps

    with checkpoint(ctx, "metric_termination"):
        loop_exec = LoopExecutor()
        wf_ctx = _make_context("t2-31")
        wf_ctx.metrics["quality.agreement"] = 0.96

        should_terminate, reason = loop_exec.check_termination(
            "refinement_loop", loop_step.config, wf_ctx, 0
        )
        assert should_terminate
        assert reason == "metric_threshold_met"

    with checkpoint(ctx, "snapshot_after_loop"):
        # snapshot step depends on refinement_loop
        snapshot_step = wf.get_step("final_snapshot")
        assert snapshot_step.type == "snapshot"
        assert "refinement_loop" in snapshot_step.depends_on

    with checkpoint(ctx, "export_final"):
        export_step = wf.get_step("export_results")
        assert export_step.type == "export"
        assert export_step.config["format"] == "jsonl"

    with checkpoint(ctx, "all_step_types_in_registry"):
        registry = create_default_registry()
        for step in wf.steps:
            assert registry.has_executor(step.type)

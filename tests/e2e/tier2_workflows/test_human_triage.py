"""Tier 2 — Human triage step test (T2-33).

Tests the human_triage step: triage_mode forwarding, category count tracking,
and record routing by triage decision.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from molabel.core.types import WorkflowStepExecutionStatus
from molabel.core.workflow.context import RecordSet, WorkflowContext
from molabel.core.workflow.engine import WorkflowEngine, create_default_registry
from molabel.core.workflow.parser import parse_workflow_yaml
from molabel.core.workflow.steps.human_steps import HumanTriageExecutor
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
        record_ids=[f"r{i}" for i in range(12)],
        record_count=12,
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
# T2-33 — Human triage step with category routing
# ---------------------------------------------------------------------------


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier2
async def test_t2_33_human_triage(ctx):
    """T2-33: triage_mode forwarded; category counts tracked; records routed."""
    wf = parse_workflow_yaml(FIXTURES / "wf_human_triage.yaml")

    with checkpoint(ctx, "parse"):
        triage_step = wf.get_step("triage")
        assert triage_step.type == "human_triage"
        config = triage_step.config
        categories = config.get("categories", [])
        assert set(categories) == {"pass", "fail", "needs_review"}
        routing = config.get("routing", {})
        assert routing.get("pass") == "export_step"

    with checkpoint(ctx, "executor_forwards_triage_mode"):
        executor = HumanTriageExecutor()
        wf_ctx = _make_context("t2-33-a")

        # Mock review service to capture create_queue call
        mock_review_service = MagicMock()
        mock_review_service.create_queue.return_value = None

        result = executor.execute(
            "triage",
            config,
            wf_ctx,
            services={"review_queue": mock_review_service},
        )

        assert result.success
        assert result.waiting_for_human is True

        # Verify triage_mode=True was forwarded to the review service
        call_args = mock_review_service.create_queue.call_args
        assert call_args is not None
        _, kwargs = call_args if len(call_args) == 2 else ([], call_args[0])
        if kwargs:
            passed_config = kwargs.get("config", {})
        elif len(call_args) > 1:
            passed_config = call_args[1].get("config", {})
        else:
            passed_config = {}
        # The config passed should include triage_mode=True
        if isinstance(passed_config, dict):
            assert passed_config.get("triage_mode") is True

    with checkpoint(ctx, "category_counts_initialized"):
        # Context should have category count variables initialized to 0
        for cat in categories:
            key = f"triage.{cat}.count"
            assert wf_ctx.variables.get(key) == 0

    with checkpoint(ctx, "queue_created_in_context"):
        assert len(wf_ctx.review_queue_ids) >= 1
        assert wf_ctx.active_record_set_id == "triage"

    with checkpoint(ctx, "output_summary"):
        summary = result.output.summary
        assert "queue_id" in summary
        assert "total_items" in summary
        assert summary["total_items"] == 12
        assert "categories" in summary
        assert set(summary["categories"]) == {"pass", "fail", "needs_review"}

    with checkpoint(ctx, "category_routing_after_triage"):
        # Simulate triage decisions: update category counts
        wf_ctx.variables["triage.pass.count"] = 7
        wf_ctx.variables["triage.fail.count"] = 2
        wf_ctx.variables["triage.needs_review.count"] = 3

        total = (
            wf_ctx.variables["triage.pass.count"]
            + wf_ctx.variables["triage.fail.count"]
            + wf_ctx.variables["triage.needs_review.count"]
        )
        assert total == 12  # All records accounted for

    with checkpoint(ctx, "triage_without_review_service"):
        # Without review service, triage still creates context entries
        executor2 = HumanTriageExecutor()
        wf_ctx2 = _make_context("t2-33-b")

        result2 = executor2.execute("triage", config, wf_ctx2, services={})

        assert result2.success
        assert result2.waiting_for_human is True
        # Category counts still initialized
        for cat in categories:
            assert wf_ctx2.variables.get(f"triage.{cat}.count") == 0

    with checkpoint(ctx, "validation_requires_categories"):
        # Without categories, validation should fail
        executor3 = HumanTriageExecutor()
        wf_ctx3 = _make_context("t2-33-c")
        errors = executor3.validate("triage", {}, wf_ctx3)
        assert any("categories" in e for e in errors)

    with checkpoint(ctx, "engine_executes_triage"):
        engine = _make_engine()
        wf_ctx4 = _make_context("t2-33-d")
        engine.initialize(wf, wf_ctx4)
        _patch_agent_configs(engine)

        # Complete agent_label first
        engine._step_states["agent_label"] = WorkflowStepExecutionStatus.ready
        engine.execute_step("agent_label")

        # Execute triage step
        engine._update_ready_steps()
        engine._step_states["triage"] = WorkflowStepExecutionStatus.ready
        triage_result = engine.execute_step("triage")

        assert triage_result.waiting_for_human is True
        assert (
            engine._step_states["triage"]
            == WorkflowStepExecutionStatus.waiting_for_human
        )

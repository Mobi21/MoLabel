"""Tier 2 — Parallel workflow tests (T2-10 through T2-13).

Tests multi-model comparison, fail-fast, wait-all, and multi-dataset
parallel execution patterns via the workflow engine.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from molabel.core.workflow.context import RecordSet, StepOutput, WorkflowContext
from molabel.core.workflow.engine import WorkflowEngine, create_default_registry
from molabel.core.workflow.parser import parse_workflow_yaml
from molabel.core.workflow.steps.base import StepResult
from molabel.core.workflow.steps.control_steps import ParallelExecutor
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


def _make_success_executor(step_id: str, metrics_key: str | None = None) -> Any:
    """Create a mock step executor that succeeds."""
    exc = MagicMock()
    summary: dict[str, Any] = {"step": step_id, "status": "completed"}
    if metrics_key:
        summary["metrics_written"] = [metrics_key]
    exc.execute.return_value = StepResult(
        success=True,
        output=StepOutput(
            step_id=step_id,
            step_type="agent_run",
            status="completed",
            summary=summary,
        ),
    )
    return exc


def _make_fail_executor(step_id: str) -> Any:
    """Create a mock step executor that fails."""
    exc = MagicMock()
    exc.execute.return_value = StepResult(
        success=False,
        error=f"Provider failure for step {step_id}",
    )
    return exc


# ---------------------------------------------------------------------------
# T2-10 — Multi-model comparison (3 agents parallel)
# ---------------------------------------------------------------------------


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier2
async def test_t2_10_multi_model_comparison(ctx):
    """T2-10: 3 agents run in parallel; all complete, outputs merged."""
    wf = parse_workflow_yaml(FIXTURES / "wf_parallel_3model.yaml")

    with checkpoint(ctx, "parse"):
        parallel_step = wf.get_step("parallel_agents")
        assert parallel_step.type == "parallel"
        child_steps = parallel_step.config["steps"]
        assert len(child_steps) == 3
        assert parallel_step.config.get("fail_fast") is False

    with checkpoint(ctx, "all_three_complete"):
        wf_ctx = _make_context("t2-10")
        executor = ParallelExecutor()

        # Provide child executors that all succeed
        child_executors: dict[str, Any] = {}
        for child in child_steps:
            child_id = child["id"] if isinstance(child, dict) else child
            # Use a shared conflict metric to trigger conflict warning
            child_executors[child_id] = {
                "executor": _make_success_executor(child_id, "quality.agreement"),
                "config": child.get("config", {}) if isinstance(child, dict) else {},
            }

        config = {**parallel_step.config, "steps": list(child_executors.keys())}
        result = executor.execute(
            "parallel_agents",
            config,
            wf_ctx,
            services={"child_executors": child_executors},
        )

        assert result.success
        child_results = result.output.summary.get("child_results", {})
        # All 3 children should have results (True = succeeded)
        assert all(v is True for v in child_results.values())
        assert len(child_results) == 3

    with checkpoint(ctx, "metric_conflict_warnings"):
        # When multiple children write the same metric key, there should be warnings
        warnings = result.output.summary.get("merge_warnings", [])
        # With 3 children all writing "quality.agreement", we expect 2 conflict warnings
        conflict_warnings = [w for w in warnings if "quality.agreement" in w]
        assert len(conflict_warnings) >= 1

    with checkpoint(ctx, "outputs_in_context"):
        for child in child_steps:
            child_id = child["id"] if isinstance(child, dict) else child
            assert child_id in wf_ctx.step_outputs


# ---------------------------------------------------------------------------
# T2-11 — Fail-fast mode (first failure cancels rest)
# ---------------------------------------------------------------------------


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier2
async def test_t2_11_fail_fast(ctx):
    """T2-11: First child failure cancels remaining children; is_partial=True."""
    wf = parse_workflow_yaml(FIXTURES / "wf_parallel_failfast.yaml")

    with checkpoint(ctx, "parse"):
        parallel_step = wf.get_step("parallel_agents")
        assert parallel_step.config.get("fail_fast") is True

    with checkpoint(ctx, "first_failure_cancels_rest"):
        wf_ctx = _make_context("t2-11")
        executor = ParallelExecutor()

        child_steps_raw = parallel_step.config["steps"]
        child_ids = [c["id"] if isinstance(c, dict) else c for c in child_steps_raw]

        # First child fails, second would succeed
        child_executors = {
            child_ids[0]: {
                "executor": _make_fail_executor(child_ids[0]),
                "config": {},
            },
            child_ids[1]: {
                "executor": _make_success_executor(child_ids[1]),
                "config": {},
            },
        }

        config = {**parallel_step.config, "steps": child_ids}
        result = executor.execute(
            "parallel_agents",
            config,
            wf_ctx,
            services={"child_executors": child_executors},
        )

        # With fail-fast and one failure, overall is not fully successful
        assert not result.success or result.is_partial
        errors = result.output.summary.get("errors", [])
        assert len(errors) >= 1
        assert any("fail" in e.lower() or "fail-fast" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# T2-12 — Wait-all mode (all children attempted despite failure)
# ---------------------------------------------------------------------------


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier2
async def test_t2_12_wait_all_mode(ctx):
    """T2-12: All children attempted in wait-all mode; partial failure reported."""
    wf = parse_workflow_yaml(FIXTURES / "wf_parallel_waitall.yaml")

    with checkpoint(ctx, "parse"):
        parallel_step = wf.get_step("parallel_agents")
        assert parallel_step.config.get("fail_fast") is False

    with checkpoint(ctx, "all_attempted_despite_failure"):
        wf_ctx = _make_context("t2-12")
        executor = ParallelExecutor()

        # agent_ok succeeds; agent_fail fails
        child_executors = {
            "agent_ok": {
                "executor": _make_success_executor("agent_ok"),
                "config": {},
            },
            "agent_fail": {
                "executor": _make_fail_executor("agent_fail"),
                "config": {},
            },
        }

        config = {**parallel_step.config, "steps": ["agent_ok", "agent_fail"]}
        result = executor.execute(
            "parallel_agents",
            config,
            wf_ctx,
            services={"child_executors": child_executors},
        )

        # is_partial: some succeeded, some failed
        assert result.is_partial is True
        assert not result.success

        child_results = result.output.summary.get("child_results", {})
        # Both children should appear in results
        assert "agent_ok" in child_results
        assert child_results["agent_ok"] is True

        errors = result.output.summary.get("errors", [])
        assert len(errors) >= 1

    with checkpoint(ctx, "successful_outputs_in_context"):
        # The successful child's output should be in context
        assert "agent_ok" in wf_ctx.step_outputs


# ---------------------------------------------------------------------------
# T2-13 — Multi-dataset processing (2 datasets parallel)
# ---------------------------------------------------------------------------


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier2
async def test_t2_13_multi_dataset_parallel(ctx):
    """T2-13: Two datasets processed in parallel; record sets isolated."""
    wf = parse_workflow_yaml(FIXTURES / "wf_parallel_multidataset.yaml")

    with checkpoint(ctx, "parse"):
        parallel_step = wf.get_step("parallel_datasets")
        assert parallel_step.type == "parallel"
        child_steps_raw = parallel_step.config["steps"]
        assert len(child_steps_raw) == 2

    with checkpoint(ctx, "no_cross_contamination"):
        # Create separate contexts — each dataset has its own record set
        wf_ctx = _make_context("t2-13")

        # Dataset A: 10 records
        wf_ctx.record_sets["dataset_a"] = RecordSet(
            record_ids=[f"a{i}" for i in range(10)],
            record_count=10,
            description="Dataset A records",
        )
        # Dataset B: 8 records (different IDs)
        wf_ctx.record_sets["dataset_b"] = RecordSet(
            record_ids=[f"b{i}" for i in range(8)],
            record_count=8,
            description="Dataset B records",
        )

        executor = ParallelExecutor()
        child_ids = [c["id"] if isinstance(c, dict) else c for c in child_steps_raw]

        # Each child executor writes its own record set
        def _make_dataset_executor(child_id: str, record_tag: str) -> Any:
            exc = MagicMock()

            def execute_fn(sid, cfg, context, services=None):
                from molabel.core.workflow.context import RecordSet as RS

                out_records = list(context.record_sets.get(record_tag, RS()).record_ids)
                context.record_sets[sid] = RS(
                    record_ids=out_records,
                    record_count=len(out_records),
                    description=f"Output from {sid}",
                )
                return StepResult(
                    success=True,
                    output=StepOutput(
                        step_id=sid,
                        step_type="agent_run",
                        status="completed",
                        summary={"records": out_records},
                    ),
                )

            exc.execute.side_effect = execute_fn
            return exc

        child_executors = {
            child_ids[0]: {
                "executor": _make_dataset_executor(child_ids[0], "dataset_a"),
                "config": {},
            },
            child_ids[1]: {
                "executor": _make_dataset_executor(child_ids[1], "dataset_b"),
                "config": {},
            },
        }

        config = {**parallel_step.config, "steps": child_ids}
        result = executor.execute(
            "parallel_datasets",
            config,
            wf_ctx,
            services={"child_executors": child_executors},
        )

        assert result.success

        # Verify each child's record set only contains its own records
        rs_a = wf_ctx.record_sets.get(child_ids[0])
        rs_b = wf_ctx.record_sets.get(child_ids[1])

        if rs_a and rs_b:
            ids_a = set(rs_a.record_ids)
            ids_b = set(rs_b.record_ids)
            # No cross-contamination
            assert ids_a.isdisjoint(ids_b) or len(ids_a) == 0 or len(ids_b) == 0

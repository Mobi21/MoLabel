"""Tests for the workflow execution engine (WF-035 through WF-044)."""

from __future__ import annotations

import pytest

from molabel.core.types import (
    WorkflowExecutionStatus,
    WorkflowStepExecutionStatus,
)
from molabel.core.workflow.context import RecordSet, WorkflowContext
from molabel.core.workflow.engine import (
    WorkflowEngine,
    WorkflowExecutionError,
    create_default_registry,
)
from molabel.core.workflow.parser import parse_workflow_yaml

# Short aliases for long enum values used in assertions
_BREAKPOINT = WorkflowStepExecutionStatus.waiting_for_breakpoint
_WAITING_HUMAN = WorkflowStepExecutionStatus.waiting_for_human
_WAITING_GATE = WorkflowStepExecutionStatus.waiting_for_gate
_COMPLETED = WorkflowStepExecutionStatus.completed
_FAILED = WorkflowStepExecutionStatus.failed
_SKIPPED = WorkflowStepExecutionStatus.skipped
_CANCELLED = WorkflowStepExecutionStatus.cancelled
_INTERRUPTED = WorkflowStepExecutionStatus.interrupted
_READY = WorkflowStepExecutionStatus.ready
_PENDING = WorkflowStepExecutionStatus.pending
_RETRYING = WorkflowStepExecutionStatus.retrying


def _make_context(**kwargs) -> WorkflowContext:
    """Create a test WorkflowContext with sensible defaults."""
    return WorkflowContext(
        workspace_id=kwargs.get("workspace_id", "test-ws"),
        workflow_execution_id=kwargs.get("execution_id", "test-exec"),
        workflow_version=kwargs.get("version", 1),
    )


def _make_engine(**kwargs) -> WorkflowEngine:
    """Create a WorkflowEngine with the default registry."""
    return WorkflowEngine(
        create_default_registry(),
        services=kwargs.get("services"),
    )


# ---------------------------------------------------------------------------
# Engine initialization and state machine (WF-035, WF-038)
# ---------------------------------------------------------------------------


class TestEngineInitialization:
    """Tests for engine initialization and step state management."""

    def test_initialize_sets_pending(self) -> None:
        engine = _make_engine()
        wf = parse_workflow_yaml(
            """
name: test
version: 1
steps:
  - id: ingest
    type: data_ingest
    config:
      source: "data/*.jsonl"
  - id: export
    type: export
    config:
      format: jsonl
      destination: "exports/"
""",
            from_string=True,
        )
        ctx = _make_context()
        engine.initialize(wf, ctx)

        states = engine.step_states
        assert states["ingest"] == _READY
        assert states["export"] == _PENDING

    def test_first_step_ready_on_init(self) -> None:
        engine = _make_engine()
        wf = parse_workflow_yaml(
            """
name: test
version: 1
steps:
  - id: ingest
    type: data_ingest
    config:
      source: "data/*.jsonl"
""",
            from_string=True,
        )
        ctx = _make_context()
        engine.initialize(wf, ctx)

        ready = engine.get_ready_steps()
        assert ready == ["ingest"]

    def test_execution_status_running_after_init(self) -> None:
        engine = _make_engine()
        wf = parse_workflow_yaml(
            """
name: test
version: 1
steps:
  - id: ingest
    type: data_ingest
    config:
      source: "data/*.jsonl"
""",
            from_string=True,
        )
        engine.initialize(wf, _make_context())
        assert engine.execution_status == WorkflowExecutionStatus.running


# ---------------------------------------------------------------------------
# Step execution (WF-035, WF-036)
# ---------------------------------------------------------------------------


class TestStepExecution:
    """Tests for individual step execution."""

    def test_execute_data_ingest(self) -> None:
        engine = _make_engine()
        wf = parse_workflow_yaml(
            """
name: test
version: 1
steps:
  - id: ingest
    type: data_ingest
    config:
      source: "data/*.jsonl"
""",
            from_string=True,
        )
        ctx = _make_context()
        engine.initialize(wf, ctx)

        result = engine.execute_step("ingest")
        assert result.success
        assert engine.step_states["ingest"] == _COMPLETED
        assert ctx.active_record_set_id == "ingest"

    def test_execute_chain(self) -> None:
        engine = _make_engine()
        wf = parse_workflow_yaml(
            """
name: test
version: 1
steps:
  - id: ingest
    type: data_ingest
    config:
      source: "data/*.jsonl"
  - id: export
    type: export
    config:
      format: jsonl
      destination: "exports/"
""",
            from_string=True,
        )
        ctx = _make_context()
        engine.initialize(wf, ctx)

        result1 = engine.execute_step("ingest")
        assert result1.success

        # After ingest completes, export should become ready
        assert engine.step_states["export"] == _READY

        result2 = engine.execute_step("export")
        assert result2.success
        assert len(ctx.export_bundle_ids) == 1

    def test_cannot_execute_pending_step(self) -> None:
        engine = _make_engine()
        wf = parse_workflow_yaml(
            """
name: test
version: 1
steps:
  - id: ingest
    type: data_ingest
    config:
      source: "data/*.jsonl"
  - id: export
    type: export
    config:
      format: jsonl
      destination: "exports/"
""",
            from_string=True,
        )
        engine.initialize(wf, _make_context())

        with pytest.raises(WorkflowExecutionError, match="Cannot execute"):
            engine.execute_step("export")

    def test_validation_failure_marks_step_failed(self) -> None:
        engine = _make_engine()
        wf = parse_workflow_yaml(
            """
name: test
version: 1
steps:
  - id: bad_filter
    type: data_filter
    config: {}
""",
            from_string=True,
        )
        ctx = _make_context()
        engine.initialize(wf, ctx)

        result = engine.execute_step("bad_filter")
        assert not result.success
        assert "Validation failed" in result.error
        assert engine.step_states["bad_filter"] == _FAILED

    def test_workflow_completes_when_all_steps_done(self) -> None:
        engine = _make_engine()
        wf = parse_workflow_yaml(
            """
name: test
version: 1
steps:
  - id: ingest
    type: data_ingest
    config:
      source: "data/*.jsonl"
""",
            from_string=True,
        )
        ctx = _make_context()
        engine.initialize(wf, ctx)
        engine.execute_step("ingest")

        assert engine.is_complete()
        assert engine.execution_status == WorkflowExecutionStatus.completed


# ---------------------------------------------------------------------------
# Breakpoints (WF-037)
# ---------------------------------------------------------------------------


class TestBreakpoints:
    """Tests for breakpoint behavior."""

    def test_breakpoint_pauses_step(self) -> None:
        engine = _make_engine()
        wf = parse_workflow_yaml(
            """
name: test
version: 1
steps:
  - id: review
    type: human_review
    breakpoint: true
    config: {}
""",
            from_string=True,
        )
        ctx = _make_context()
        # Give it an active record set
        ctx.record_sets["_init"] = RecordSet(record_ids=["r1"])
        ctx.active_record_set_id = "_init"
        engine.initialize(wf, ctx)

        result = engine.execute_step("review")
        assert result.success
        assert engine.step_states["review"] == _BREAKPOINT

    def test_continue_breakpoint(self) -> None:
        engine = _make_engine()
        wf = parse_workflow_yaml(
            """
name: test
version: 1
steps:
  - id: ingest
    type: data_ingest
    breakpoint: true
    config:
      source: "data/*.jsonl"
""",
            from_string=True,
        )
        ctx = _make_context()
        engine.initialize(wf, ctx)

        # First execute hits breakpoint
        engine.execute_step("ingest")
        assert engine.step_states["ingest"] == _BREAKPOINT

        # Continue past breakpoint
        engine.continue_breakpoint("ingest")
        result = engine.execute_step("ingest")
        assert result.success
        assert engine.step_states["ingest"] == _COMPLETED

    def test_pause_on_every_step(self) -> None:
        engine = _make_engine()
        wf = parse_workflow_yaml(
            """
name: test
version: 1
pause_on_every_step: true
steps:
  - id: ingest
    type: data_ingest
    config:
      source: "data/*.jsonl"
""",
            from_string=True,
        )
        ctx = _make_context()
        engine.initialize(wf, ctx)

        engine.execute_step("ingest")
        assert engine.step_states["ingest"] == _BREAKPOINT

    def test_skip_at_breakpoint(self) -> None:
        engine = _make_engine()
        wf = parse_workflow_yaml(
            """
name: test
version: 1
steps:
  - id: ingest
    type: data_ingest
    breakpoint: true
    config:
      source: "data/*.jsonl"
""",
            from_string=True,
        )
        ctx = _make_context()
        engine.initialize(wf, ctx)

        engine.execute_step("ingest")
        engine.skip_step("ingest")
        assert engine.step_states["ingest"] == _SKIPPED


# ---------------------------------------------------------------------------
# Human steps and gate (WF-011 through WF-014, WF-034)
# ---------------------------------------------------------------------------


class TestHumanAndGateSteps:
    """Tests for human step waiting and gate approval."""

    def test_human_review_waits(self) -> None:
        engine = _make_engine()
        wf = parse_workflow_yaml(
            """
name: test
version: 1
steps:
  - id: review
    type: human_review
    config: {}
""",
            from_string=True,
        )
        ctx = _make_context()
        ctx.record_sets["_init"] = RecordSet(record_ids=["r1", "r2"])
        ctx.active_record_set_id = "_init"
        engine.initialize(wf, ctx)

        result = engine.execute_step("review")
        assert result.waiting_for_human
        assert engine.step_states["review"] == _WAITING_HUMAN

    def test_resume_human_step(self) -> None:
        engine = _make_engine()
        wf = parse_workflow_yaml(
            """
name: test
version: 1
steps:
  - id: review
    type: human_review
    config: {}
""",
            from_string=True,
        )
        ctx = _make_context()
        ctx.record_sets["_init"] = RecordSet(record_ids=["r1"])
        ctx.active_record_set_id = "_init"
        engine.initialize(wf, ctx)

        engine.execute_step("review")
        engine.resume_human_step("review")
        assert engine.step_states["review"] == _COMPLETED

    def test_gate_waits_for_approval(self) -> None:
        engine = _make_engine()
        wf = parse_workflow_yaml(
            """
name: test
version: 1
steps:
  - id: approve
    type: gate
    config:
      message: "Ready to continue?"
""",
            from_string=True,
        )
        ctx = _make_context()
        engine.initialize(wf, ctx)

        result = engine.execute_step("approve")
        assert result.waiting_for_gate
        assert engine.step_states["approve"] == _WAITING_GATE

    def test_approve_gate(self) -> None:
        engine = _make_engine()
        wf = parse_workflow_yaml(
            """
name: test
version: 1
steps:
  - id: approve
    type: gate
    config:
      message: "Ready?"
""",
            from_string=True,
        )
        ctx = _make_context()
        engine.initialize(wf, ctx)

        engine.execute_step("approve")
        engine.approve_gate("approve", approved=True, reason="All good")
        assert engine.step_states["approve"] == _COMPLETED

    def test_reject_gate_cancels_workflow(self) -> None:
        engine = _make_engine()
        wf = parse_workflow_yaml(
            """
name: test
version: 1
steps:
  - id: approve
    type: gate
    config:
      message: "Ready?"
  - id: export
    type: export
    config:
      format: jsonl
      destination: "out/"
""",
            from_string=True,
        )
        ctx = _make_context()
        engine.initialize(wf, ctx)

        engine.execute_step("approve")
        engine.approve_gate("approve", approved=False, reason="Not ready")
        assert engine.step_states["approve"] == _CANCELLED
        assert engine.execution_status == WorkflowExecutionStatus.cancelled


# ---------------------------------------------------------------------------
# Error handling and recovery (WF-039, WF-040, WF-041)
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Tests for step failure, retry, skip, and cancellation."""

    def test_retry_failed_step(self) -> None:
        engine = _make_engine()
        wf = parse_workflow_yaml(
            """
name: test
version: 1
steps:
  - id: bad_filter
    type: data_filter
    config: {}
""",
            from_string=True,
        )
        ctx = _make_context()
        engine.initialize(wf, ctx)

        engine.execute_step("bad_filter")
        assert engine.step_states["bad_filter"] == _FAILED

        engine.retry_step("bad_filter")
        assert engine.step_states["bad_filter"] == _RETRYING
        assert engine.execution_status == WorkflowExecutionStatus.running

    def test_skip_failed_step(self) -> None:
        engine = _make_engine()
        wf = parse_workflow_yaml(
            """
name: test
version: 1
steps:
  - id: bad_filter
    type: data_filter
    config: {}
  - id: export
    type: export
    config:
      format: jsonl
      destination: "out/"
""",
            from_string=True,
        )
        ctx = _make_context()
        engine.initialize(wf, ctx)

        engine.execute_step("bad_filter")
        engine.skip_step("bad_filter")
        assert engine.step_states["bad_filter"] == _SKIPPED

    def test_cancel_workflow(self) -> None:
        engine = _make_engine()
        wf = parse_workflow_yaml(
            """
name: test
version: 1
steps:
  - id: ingest
    type: data_ingest
    config:
      source: "data/*.jsonl"
  - id: export
    type: export
    config:
      format: jsonl
      destination: "out/"
""",
            from_string=True,
        )
        ctx = _make_context()
        engine.initialize(wf, ctx)

        engine.cancel_workflow()
        assert engine.step_states["ingest"] == _CANCELLED
        assert engine.step_states["export"] == _CANCELLED
        assert engine.execution_status == WorkflowExecutionStatus.cancelled

    def test_cannot_retry_non_failed_step(self) -> None:
        engine = _make_engine()
        wf = parse_workflow_yaml(
            """
name: test
version: 1
steps:
  - id: ingest
    type: data_ingest
    config:
      source: "data/*.jsonl"
""",
            from_string=True,
        )
        ctx = _make_context()
        engine.initialize(wf, ctx)

        with pytest.raises(WorkflowExecutionError, match="Cannot retry"):
            engine.retry_step("ingest")


# ---------------------------------------------------------------------------
# Crash recovery (WF-044)
# ---------------------------------------------------------------------------


class TestCrashRecovery:
    """Tests for crash recovery on startup."""

    def test_detect_interrupted_steps(self) -> None:
        engine = _make_engine()
        wf = parse_workflow_yaml(
            """
name: test
version: 1
steps:
  - id: ingest
    type: data_ingest
    config:
      source: "data/*.jsonl"
""",
            from_string=True,
        )
        ctx = _make_context()
        engine.initialize(wf, ctx)

        # Simulate crash: manually set a step to running
        engine._step_states["ingest"] = WorkflowStepExecutionStatus.running

        interrupted = engine.detect_interrupted_steps()
        assert interrupted == ["ingest"]
        assert engine.step_states["ingest"] == _INTERRUPTED
        assert engine.execution_status == WorkflowExecutionStatus.paused


# ---------------------------------------------------------------------------
# Conditional execution (WF-028, WF-029, WF-030)
# ---------------------------------------------------------------------------


class TestConditionalExecution:
    """Tests for conditional branching and skip propagation."""

    def test_conditional_then_branch(self) -> None:
        engine = _make_engine()
        wf = parse_workflow_yaml(
            """
name: test
version: 1
steps:
  - id: check
    type: conditional
    config:
      predicate: "True"
      then_steps: [export]
      else_steps: []
  - id: export
    type: export
    config:
      format: jsonl
      destination: "out/"
""",
            from_string=True,
        )
        ctx = _make_context()
        engine.initialize(wf, ctx)

        result = engine.execute_step("check")
        assert result.success
        assert ctx.variables["conditional.check.branch"] == "then"

    def test_conditional_else_branch(self) -> None:
        engine = _make_engine()
        wf = parse_workflow_yaml(
            """
name: test
version: 1
steps:
  - id: check
    type: conditional
    config:
      predicate: "False"
      then_steps: []
      else_steps: []
""",
            from_string=True,
        )
        ctx = _make_context()
        engine.initialize(wf, ctx)

        engine.execute_step("check")
        assert ctx.variables["conditional.check.branch"] == "else"

    def test_conditional_with_metrics(self) -> None:
        engine = _make_engine()
        wf = parse_workflow_yaml(
            """
name: test
version: 1
steps:
  - id: check
    type: conditional
    config:
      predicate: "metrics['quality.agreement'] >= 0.90"
      then_steps: []
      else_steps: []
""",
            from_string=True,
        )
        ctx = _make_context()
        ctx.metrics["quality.agreement"] = 0.95
        engine.initialize(wf, ctx)

        engine.execute_step("check")
        assert ctx.variables["conditional.check.branch"] == "then"

    def test_conditional_metric_below_threshold(self) -> None:
        engine = _make_engine()
        wf = parse_workflow_yaml(
            """
name: test
version: 1
steps:
  - id: check
    type: conditional
    config:
      predicate: "metrics['quality.agreement'] >= 0.90"
      then_steps: []
      else_steps: []
""",
            from_string=True,
        )
        ctx = _make_context()
        ctx.metrics["quality.agreement"] = 0.50
        engine.initialize(wf, ctx)

        engine.execute_step("check")
        assert ctx.variables["conditional.check.branch"] == "else"

    def test_skip_propagation(self) -> None:
        engine = _make_engine()
        wf = parse_workflow_yaml(
            """
name: test
version: 1
steps:
  - id: check
    type: conditional
    config:
      predicate: "True"
      then_steps: [step_a]
      else_steps: [step_b]
  - id: step_a
    type: quality_check
    depends_on: [check]
    config: {}
  - id: step_b
    type: quality_check
    depends_on: [check]
    config: {}
  - id: final
    type: export
    depends_on: [step_b]
    config:
      format: jsonl
      destination: "out/"
""",
            from_string=True,
        )
        ctx = _make_context()
        engine.initialize(wf, ctx)

        engine.execute_step("check")
        # step_b is in else_steps so it should be skipped
        assert engine.step_states["step_b"] == _SKIPPED
        # final depends only on step_b which is skipped, so final should auto-skip
        assert engine.step_states["final"] == _SKIPPED


# ---------------------------------------------------------------------------
# Run-to-completion (WF-036)
# ---------------------------------------------------------------------------


class TestRunToCompletion:
    """Tests for the run_to_completion convenience method."""

    def test_run_simple_workflow(self) -> None:
        engine = _make_engine()
        wf = parse_workflow_yaml(
            """
name: test
version: 1
steps:
  - id: ingest
    type: data_ingest
    config:
      source: "data/*.jsonl"
  - id: snapshot
    type: snapshot
    config:
      snapshot_name: "test"
""",
            from_string=True,
        )
        ctx = _make_context()
        engine.initialize(wf, ctx)

        status = engine.run_to_completion()
        assert status == WorkflowExecutionStatus.completed
        assert engine.step_states["ingest"] == _COMPLETED
        assert engine.step_states["snapshot"] == _COMPLETED

    def test_run_stops_at_human_step(self) -> None:
        engine = _make_engine()
        wf = parse_workflow_yaml(
            """
name: test
version: 1
steps:
  - id: ingest
    type: data_ingest
    config:
      source: "data/*.jsonl"
  - id: review
    type: human_review
    config: {}
""",
            from_string=True,
        )
        ctx = _make_context()
        engine.initialize(wf, ctx)

        engine.run_to_completion()
        assert engine.step_states["ingest"] == _COMPLETED
        assert engine.step_states["review"] == _WAITING_HUMAN

    def test_run_stops_at_breakpoint(self) -> None:
        engine = _make_engine()
        wf = parse_workflow_yaml(
            """
name: test
version: 1
steps:
  - id: ingest
    type: data_ingest
    breakpoint: true
    config:
      source: "data/*.jsonl"
""",
            from_string=True,
        )
        ctx = _make_context()
        engine.initialize(wf, ctx)

        engine.run_to_completion()
        assert engine.step_states["ingest"] == _BREAKPOINT


# ---------------------------------------------------------------------------
# Context persistence callback (WF-043)
# ---------------------------------------------------------------------------


class TestContextPersistence:
    """Tests for context persistence after step completion."""

    def test_persistence_callback_called(self) -> None:
        persisted: list[tuple[str, str]] = []

        def on_persist(ctx: WorkflowContext, step_id: str) -> None:
            persisted.append((ctx.workflow_execution_id, step_id))

        engine = _make_engine()
        engine.set_persistence_callback(on_persist)

        wf = parse_workflow_yaml(
            """
name: test
version: 1
steps:
  - id: ingest
    type: data_ingest
    config:
      source: "data/*.jsonl"
""",
            from_string=True,
        )
        ctx = _make_context()
        engine.initialize(wf, ctx)
        engine.execute_step("ingest")

        assert len(persisted) == 1
        assert persisted[0] == ("test-exec", "ingest")

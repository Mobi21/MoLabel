"""Workflow execution engine: state machine, concurrency, error handling.

WF-035 through WF-044. Orchestrates step execution, manages the step state
machine, handles breakpoints, loops, conditionals, parallel execution,
error recovery, and crash detection.
"""

from __future__ import annotations

import logging
import os
import signal
import time
import traceback
from datetime import UTC, datetime
from typing import Any

from molabel.core.types import (
    WorkflowExecutionStatus,
    WorkflowStepExecutionStatus,
)
from molabel.core.workflow.context import StepOutput, WorkflowContext
from molabel.core.workflow.parser import StepDefinition, WorkflowDefinitionParsed
from molabel.core.workflow.registry import StepExecutorRegistry
from molabel.core.workflow.steps.base import StepResult
from molabel.core.workflow.steps.control_steps import (
    ConditionalExecutor,
    LoopExecutor,
    ParallelExecutor,
)

logger = logging.getLogger(__name__)

# Default timeout for automated steps: 1 hour (3600 seconds)
DEFAULT_STEP_TIMEOUT_SECONDS = 3600


class WorkflowExecutionError(Exception):
    """Raised when workflow execution encounters a fatal error."""


class WorkflowEngine:
    """Orchestrates workflow execution from parsed definitions.

    The engine manages:
    - Step state machine transitions (WF-035)
    - Breakpoint handling (WF-037)
    - Predecessor resolution and DAG-based scheduling (WF-038)
    - Concurrency constraints (WF-042)
    - Context persistence (WF-043)
    - Crash recovery (WF-044)
    - Error handling (WF-039, WF-040, WF-041)
    """

    def __init__(
        self,
        registry: StepExecutorRegistry,
        *,
        services: dict[str, Any] | None = None,
    ) -> None:
        self._registry = registry
        self._services = services or {}
        self._step_states: dict[str, WorkflowStepExecutionStatus] = {}
        self._step_results: dict[str, StepResult] = {}
        self._step_configs: dict[str, dict[str, Any]] = {}
        self._context: WorkflowContext | None = None
        self._definition: WorkflowDefinitionParsed | None = None
        self._execution_status: WorkflowExecutionStatus = (
            WorkflowExecutionStatus.pending
        )
        self._persistence_callback: Any = None
        self._on_step_state_change: Any = None

    @property
    def context(self) -> WorkflowContext | None:
        """The current workflow context."""
        return self._context

    @property
    def execution_status(self) -> WorkflowExecutionStatus:
        """The current workflow execution status."""
        return self._execution_status

    @property
    def step_states(self) -> dict[str, WorkflowStepExecutionStatus]:
        """Current state of each step."""
        return dict(self._step_states)

    def set_persistence_callback(self, callback: Any) -> None:
        """Set a callback for context persistence after each step.

        The callback signature: callback(context: WorkflowContext, step_id: str)
        """
        self._persistence_callback = callback

    def set_step_state_change_callback(self, callback: Any) -> None:
        """Set a callback for step state changes.

        Signature: callback(step_id: str, old_state: str, new_state: str)
        """
        self._on_step_state_change = callback

    def initialize(
        self,
        definition: WorkflowDefinitionParsed,
        context: WorkflowContext,
    ) -> None:
        """Initialize the engine with a workflow definition and context.

        Sets all steps to 'pending' state and computes which steps are
        ready to execute.
        """
        self._definition = definition
        self._context = context
        self._execution_status = WorkflowExecutionStatus.running

        # Initialize all steps to pending
        for step in definition.steps:
            self._step_states[step.id] = WorkflowStepExecutionStatus.pending
            self._step_configs[step.id] = dict(step.config)

        # Compute initial ready set
        self._update_ready_steps()

    def _update_ready_steps(self) -> None:
        """Transition steps from pending to ready if all predecessors are done."""
        if self._definition is None:
            return

        for step_id, preds in self._definition.predecessors.items():
            if self._step_states.get(step_id) != WorkflowStepExecutionStatus.pending:
                continue

            all_done = all(
                self._step_states.get(p)
                in {
                    WorkflowStepExecutionStatus.completed,
                    WorkflowStepExecutionStatus.skipped,
                }
                for p in preds
            )
            if all_done:
                self._transition_step(step_id, WorkflowStepExecutionStatus.ready)

    def _transition_step(
        self,
        step_id: str,
        new_state: WorkflowStepExecutionStatus,
    ) -> None:
        """Transition a step to a new state with logging and callbacks."""
        old_state = self._step_states.get(step_id)
        self._step_states[step_id] = new_state
        logger.debug(
            "Step '%s': %s -> %s",
            step_id,
            old_state.value if old_state else "none",
            new_state.value,
        )
        if self._on_step_state_change:
            try:
                self._on_step_state_change(
                    step_id,
                    old_state.value if old_state else "none",
                    new_state.value,
                )
            except Exception:
                logger.exception("Step state change callback failed")

    def get_ready_steps(self) -> list[str]:
        """Return step IDs that are in 'ready' state."""
        return [
            sid
            for sid, state in self._step_states.items()
            if state == WorkflowStepExecutionStatus.ready
        ]

    def get_waiting_steps(self) -> list[str]:
        """Return step IDs waiting for human/gate/breakpoint action."""
        waiting_states = {
            WorkflowStepExecutionStatus.waiting_for_human,
            WorkflowStepExecutionStatus.waiting_for_gate,
            WorkflowStepExecutionStatus.waiting_for_breakpoint,
        }
        return [
            sid for sid, state in self._step_states.items() if state in waiting_states
        ]

    def is_complete(self) -> bool:
        """Return True if all steps have reached a terminal state."""
        terminal_states = {
            WorkflowStepExecutionStatus.completed,
            WorkflowStepExecutionStatus.skipped,
            WorkflowStepExecutionStatus.failed,
            WorkflowStepExecutionStatus.cancelled,
        }
        return all(s in terminal_states for s in self._step_states.values())

    def execute_step(self, step_id: str) -> StepResult:
        """Execute a single step and update the workflow state.

        Handles breakpoints, timeouts, and state machine transitions.

        Args:
            step_id: The step to execute.

        Returns:
            The StepResult from the step executor.

        Raises:
            WorkflowExecutionError: If the step cannot be executed.
        """
        if self._definition is None or self._context is None:
            raise WorkflowExecutionError("Engine not initialized")

        step_def = self._definition.step_index.get(step_id)
        if step_def is None:
            raise WorkflowExecutionError(f"Unknown step: {step_id}")

        current_state = self._step_states.get(step_id)

        # Handle breakpoint
        if current_state == WorkflowStepExecutionStatus.ready:
            should_break = step_def.breakpoint or self._definition.pause_on_every_step
            if should_break:
                self._transition_step(
                    step_id,
                    WorkflowStepExecutionStatus.waiting_for_breakpoint,
                )
                return StepResult(
                    success=True,
                    output=StepOutput(
                        step_id=step_id,
                        step_type=step_def.type,
                        status="waiting_for_breakpoint",
                        summary={"message": "Breakpoint: waiting for operator"},
                    ),
                )

        # Validate ready/breakpoint-continued state
        allowed_states = {
            WorkflowStepExecutionStatus.ready,
            WorkflowStepExecutionStatus.waiting_for_breakpoint,
            WorkflowStepExecutionStatus.retrying,
        }
        if current_state not in allowed_states:
            raise WorkflowExecutionError(
                f"Cannot execute step '{step_id}' in state '{current_state}'"
            )

        # Get or create executor
        if not self._registry.has_executor(step_def.type):
            raise WorkflowExecutionError(f"No executor for step type '{step_def.type}'")
        executor = self._registry.create(step_def.type)

        # Validate config
        config = self._step_configs[step_id]
        validation_errors = executor.validate(step_id, config, self._context)
        if validation_errors:
            error_msg = "; ".join(validation_errors)
            self._transition_step(step_id, WorkflowStepExecutionStatus.failed)
            return StepResult(
                success=False,
                error=f"Validation failed: {error_msg}",
            )

        # Transition to running
        self._transition_step(step_id, WorkflowStepExecutionStatus.running)
        self._context.record_step_start(step_id)

        # Get timeout
        timeout = _get_step_timeout(step_def, self._registry)

        # Execute with signal-based timeout on Unix
        use_signal_alarm = (
            timeout is not None and hasattr(signal, "SIGALRM") and os.name != "nt"
        )

        old_handler = None
        try:
            if use_signal_alarm:

                def _timeout_handler(signum: int, frame: Any) -> None:
                    raise TimeoutError(f"Step timed out after {int(timeout)} seconds")

                old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
                signal.alarm(int(timeout))

            start_time = time.monotonic()
            result = executor.execute(step_id, config, self._context, self._services)
            elapsed = time.monotonic() - start_time

            if use_signal_alarm:
                signal.alarm(0)  # Cancel the alarm

            # Fallback post-hoc check for platforms without signal.alarm
            if timeout and elapsed > timeout:
                self._transition_step(step_id, WorkflowStepExecutionStatus.failed)
                self._context.record_step_end(step_id)
                self._persist_context(step_id)
                return StepResult(
                    success=False,
                    error=f"Step timed out after {int(elapsed)} seconds",
                )

        except TimeoutError as te:
            if use_signal_alarm:
                signal.alarm(0)
            self._transition_step(step_id, WorkflowStepExecutionStatus.failed)
            self._context.record_step_end(step_id)
            self._execution_status = WorkflowExecutionStatus.paused
            self._persist_context(step_id)
            return StepResult(
                success=False,
                error=str(te),
            )
        except Exception as e:
            if use_signal_alarm:
                signal.alarm(0)
            tb = traceback.format_exc()
            self._transition_step(step_id, WorkflowStepExecutionStatus.failed)
            self._context.record_step_end(step_id)
            self._execution_status = WorkflowExecutionStatus.paused
            self._persist_context(step_id)
            return StepResult(
                success=False,
                error=str(e),
                error_trace=tb[:2000],
            )
        finally:
            if use_signal_alarm and old_handler is not None:
                signal.signal(signal.SIGALRM, old_handler)

        self._context.record_step_end(step_id)

        # Process result
        if not result.success:
            if result.is_partial:
                self._transition_step(
                    step_id,
                    WorkflowStepExecutionStatus.partially_failed,
                )
            else:
                self._transition_step(step_id, WorkflowStepExecutionStatus.failed)
            self._execution_status = WorkflowExecutionStatus.paused
        elif result.waiting_for_human:
            self._transition_step(
                step_id, WorkflowStepExecutionStatus.waiting_for_human
            )
        elif result.waiting_for_gate:
            self._transition_step(step_id, WorkflowStepExecutionStatus.waiting_for_gate)
        else:
            self._transition_step(step_id, WorkflowStepExecutionStatus.completed)

        # Write step output to context
        if result.output:
            self._context.step_outputs[step_id] = result.output

        # Handle conditional branching
        if step_def.type == "conditional" and result.updated_context:
            self._handle_conditional_result(step_id, result)

        # Persist context
        self._persist_context(step_id)

        # Update ready steps if this step completed
        if self._step_states[step_id] == WorkflowStepExecutionStatus.completed:
            self._check_skip_propagation()
            self._update_ready_steps()

        # Check if workflow is complete
        if self.is_complete():
            self._execution_status = WorkflowExecutionStatus.completed

        self._step_results[step_id] = result
        return result

    def _handle_conditional_result(self, step_id: str, result: StepResult) -> None:
        """Process conditional branching: skip non-taken branch steps."""
        skipped_steps = result.updated_context.get("skipped_steps", [])
        for skip_id in skipped_steps:
            if skip_id in self._step_states:
                self._transition_step(skip_id, WorkflowStepExecutionStatus.skipped)

    def _check_skip_propagation(self) -> None:
        """Propagate skips: a step is auto-skipped if ALL predecessors are skipped."""
        if self._definition is None:
            return

        changed = True
        while changed:
            changed = False
            for step_id, preds in self._definition.predecessors.items():
                current = self._step_states.get(step_id)
                if current != WorkflowStepExecutionStatus.pending:
                    continue
                if not preds:
                    continue
                if all(
                    self._step_states.get(p) == WorkflowStepExecutionStatus.skipped
                    for p in preds
                ):
                    self._transition_step(step_id, WorkflowStepExecutionStatus.skipped)
                    changed = True

    def run_loop_iteration(
        self,
        loop_step_id: str,
        iteration: int,
    ) -> tuple[bool, str]:
        """Run one iteration of a loop step's body and check termination.

        Args:
            loop_step_id: The loop step ID.
            iteration: The 0-indexed iteration number.

        Returns:
            Tuple of (should_terminate, reason).
        """
        if self._definition is None or self._context is None:
            raise WorkflowExecutionError("Engine not initialized")

        loop_step = self._definition.step_index.get(loop_step_id)
        if loop_step is None:
            raise WorkflowExecutionError(f"Unknown loop step: {loop_step_id}")

        config = self._step_configs[loop_step_id]
        body_steps = config.get("steps", [])
        executor = LoopExecutor()

        # Reset body steps for this iteration
        if iteration > 0:
            executor.reset_body_steps(loop_step_id, config, self._context, iteration)

        # Update iteration counter
        self._context.variables[f"loop.{loop_step_id}.iteration"] = iteration

        # Execute body steps in order
        for body_step_id in body_steps:
            if body_step_id not in self._step_states:
                logger.warning(
                    "Loop body step '%s' not found in engine state",
                    body_step_id,
                )
                continue

            # Reset body step to ready for this iteration
            self._step_states[body_step_id] = WorkflowStepExecutionStatus.ready

            result = self.execute_step(body_step_id)
            if not result.success and not result.is_partial:
                return True, f"body_step_failed:{body_step_id}"

            # Handle human/gate waiting -- loop pauses
            if result.waiting_for_human or result.waiting_for_gate:
                return False, "waiting_for_human_or_gate"

        # Check termination
        should_terminate, reason = executor.check_termination(
            loop_step_id, config, self._context, iteration
        )

        # Manual termination uses a gate
        if not should_terminate and reason == "waiting_for_operator":
            self._transition_step(
                loop_step_id,
                WorkflowStepExecutionStatus.waiting_for_gate,
            )

        return should_terminate, reason

    def continue_breakpoint(
        self,
        step_id: str,
        *,
        config_override: dict[str, Any] | None = None,
    ) -> None:
        """Continue execution past a breakpoint (WF-037).

        Args:
            step_id: The step waiting at a breakpoint.
            config_override: Optional config changes before executing.
        """
        state = self._step_states.get(step_id)
        if state != WorkflowStepExecutionStatus.waiting_for_breakpoint:
            raise WorkflowExecutionError(
                f"Step '{step_id}' is not at a breakpoint (state: {state})"
            )
        if config_override:
            self._step_configs[step_id].update(config_override)

        # The step is now ready to execute -- the caller should call execute_step()

    def skip_step(self, step_id: str) -> None:
        """Skip a step (from breakpoint, failure, or operator action)."""
        self._transition_step(step_id, WorkflowStepExecutionStatus.skipped)
        self._update_ready_steps()
        self._check_skip_propagation()

    def retry_step(self, step_id: str) -> None:
        """Retry a failed step (WF-039)."""
        current = self._step_states.get(step_id)
        if current not in {
            WorkflowStepExecutionStatus.failed,
            WorkflowStepExecutionStatus.partially_failed,
            WorkflowStepExecutionStatus.interrupted,
        }:
            raise WorkflowExecutionError(
                f"Cannot retry step '{step_id}' in state '{current}'"
            )
        self._transition_step(step_id, WorkflowStepExecutionStatus.retrying)
        self._execution_status = WorkflowExecutionStatus.running

    def cancel_step(self, step_id: str) -> None:
        """Cancel a specific step."""
        self._transition_step(step_id, WorkflowStepExecutionStatus.cancelled)

    def cancel_workflow(self) -> None:
        """Cancel the entire workflow execution (WF-039)."""
        cancellable_states = {
            WorkflowStepExecutionStatus.pending,
            WorkflowStepExecutionStatus.ready,
            WorkflowStepExecutionStatus.running,
            WorkflowStepExecutionStatus.waiting_for_human,
            WorkflowStepExecutionStatus.waiting_for_gate,
            WorkflowStepExecutionStatus.waiting_for_breakpoint,
        }
        for step_id, state in list(self._step_states.items()):
            if state in cancellable_states:
                self._transition_step(step_id, WorkflowStepExecutionStatus.cancelled)
        self._execution_status = WorkflowExecutionStatus.cancelled

    def resume_human_step(self, step_id: str) -> None:
        """Resume a step that was waiting for human work to complete."""
        state = self._step_states.get(step_id)
        if state != WorkflowStepExecutionStatus.waiting_for_human:
            raise WorkflowExecutionError(
                f"Step '{step_id}' is not waiting for human (state: {state})"
            )
        self._transition_step(step_id, WorkflowStepExecutionStatus.completed)
        self._update_ready_steps()
        self._check_skip_propagation()

        if self.is_complete():
            self._execution_status = WorkflowExecutionStatus.completed

    def approve_gate(
        self,
        step_id: str,
        *,
        approved: bool = True,
        reason: str = "",
        operator_id: str = "",
    ) -> None:
        """Process operator approval/rejection for a gate step."""
        if self._step_states.get(step_id) not in {
            WorkflowStepExecutionStatus.waiting_for_gate,
        }:
            raise WorkflowExecutionError(
                f"Step '{step_id}' is not waiting for gate approval"
            )

        if self._context is not None:
            self._context.step_outputs[step_id] = StepOutput(
                step_id=step_id,
                step_type="gate",
                status="completed" if approved else "rejected",
                summary={
                    "approved": approved,
                    "reason": reason,
                    "operator_id": operator_id,
                    "decided_at": datetime.now(UTC).isoformat(),
                },
            )

        if approved:
            self._transition_step(step_id, WorkflowStepExecutionStatus.completed)
            self._update_ready_steps()
        else:
            self._transition_step(step_id, WorkflowStepExecutionStatus.cancelled)
            self.cancel_workflow()

    def detect_interrupted_steps(self) -> list[str]:
        """Crash recovery: detect steps that were running when the app crashed (WF-044).

        Call this on startup. Steps in 'running' state are transitioned to
        'interrupted' and the workflow is paused.
        """
        interrupted: list[str] = []
        for step_id, state in list(self._step_states.items()):
            if state == WorkflowStepExecutionStatus.running:
                self._transition_step(step_id, WorkflowStepExecutionStatus.interrupted)
                interrupted.append(step_id)

        if interrupted:
            self._execution_status = WorkflowExecutionStatus.paused
            logger.warning(
                "Crash recovery: %d step(s) were interrupted: %s",
                len(interrupted),
                interrupted,
            )

        return interrupted

    def run_to_completion(self) -> WorkflowExecutionStatus:
        """Run all ready steps until the workflow completes or blocks.

        Returns the final execution status. Stops on:
        - All steps completed/skipped
        - A step failure (workflow paused)
        - Human/gate waiting
        - Breakpoint
        """
        while True:
            ready = self.get_ready_steps()
            if not ready:
                break

            for step_id in ready:
                result = self.execute_step(step_id)
                if not result.success:
                    return self._execution_status
                if result.waiting_for_human or result.waiting_for_gate:
                    return self._execution_status
                # If breakpoint was hit, the step is now waiting_for_breakpoint
                if (
                    self._step_states.get(step_id)
                    == WorkflowStepExecutionStatus.waiting_for_breakpoint
                ):
                    return self._execution_status

        return self._execution_status

    def _persist_context(self, step_id: str) -> None:
        """Persist the workflow context (WF-043)."""
        if self._persistence_callback and self._context:
            try:
                self._persistence_callback(self._context, step_id)
            except Exception:
                logger.exception("Failed to persist context after step '%s'", step_id)


def _get_step_timeout(
    step_def: StepDefinition,
    registry: StepExecutorRegistry,
) -> float | None:
    """Get the timeout for a step in seconds, or None for no timeout."""
    if not registry.has_timeout(step_def.type):
        return None
    return step_def.config.get("timeout_seconds", DEFAULT_STEP_TIMEOUT_SECONDS)


def create_default_registry() -> StepExecutorRegistry:
    """Create a registry pre-loaded with all built-in step executors."""
    from molabel.core.workflow.steps.agent_steps import (
        AgentCompareExecutor,
        AgentRunExecutor,
    )
    from molabel.core.workflow.steps.control_steps import (
        GateExecutor,
        LoopExecutor,
    )
    from molabel.core.workflow.steps.data_steps import (
        DataDeduplicateExecutor,
        DataFilterExecutor,
        DataIngestExecutor,
        DataNormalizeExecutor,
        DataSampleExecutor,
    )
    from molabel.core.workflow.steps.human_steps import (
        HumanAdjudicationExecutor,
        HumanCalibrationExecutor,
        HumanReviewExecutor,
        HumanTriageExecutor,
    )
    from molabel.core.workflow.steps.output_steps import (
        ExportExecutor,
        ReleaseValidationExecutor,
        SnapshotExecutor,
    )
    from molabel.core.workflow.steps.quality_steps import (
        AgreementAnalysisExecutor,
        DriftDetectionExecutor,
        QualityCheckExecutor,
    )

    registry = StepExecutorRegistry()

    # Data steps
    registry.register("data_ingest", DataIngestExecutor)
    registry.register("data_normalize", DataNormalizeExecutor)
    registry.register("data_filter", DataFilterExecutor)
    registry.register("data_sample", DataSampleExecutor)
    registry.register("data_deduplicate", DataDeduplicateExecutor)

    # Agent steps
    registry.register("agent_run", AgentRunExecutor)
    registry.register("agent_labeling", AgentRunExecutor)  # common alias
    registry.register("agent_compare", AgentCompareExecutor)

    # Human steps
    registry.register("human_review", HumanReviewExecutor)
    registry.register("human_triage", HumanTriageExecutor)
    registry.register("human_calibration", HumanCalibrationExecutor)
    registry.register("human_adjudication", HumanAdjudicationExecutor)

    # Quality steps
    registry.register("quality_check", QualityCheckExecutor)
    registry.register("agreement_analysis", AgreementAnalysisExecutor)
    registry.register("drift_detection", DriftDetectionExecutor)

    # Output steps
    registry.register("export", ExportExecutor)
    registry.register("snapshot", SnapshotExecutor)
    registry.register("release_validation", ReleaseValidationExecutor)

    # Control steps
    registry.register("loop", LoopExecutor)
    registry.register("conditional", ConditionalExecutor)
    registry.register("parallel", ParallelExecutor)
    registry.register("gate", GateExecutor)

    return registry

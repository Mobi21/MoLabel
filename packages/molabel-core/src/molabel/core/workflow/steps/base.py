"""Base class for workflow step executors.

All step executors inherit from StepExecutor and implement the execute()
method. The engine calls validate() before execute() to catch config errors
before runtime.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any

from molabel.core.workflow.context import StepOutput, WorkflowContext


@dataclass
class StepResult:
    """Return value from a step executor's execute() method.

    Attributes:
        success: True if the step completed successfully.
        output: The StepOutput to write to the context.
        error: Error message if the step failed.
        error_trace: Stack trace (truncated) if the step failed.
        is_partial: True if the step partially succeeded.
        waiting_for_human: True if the step is waiting for human work.
        waiting_for_gate: True if the step is waiting for operator approval.
        updated_context: If set, context fields to merge (for steps that
            produce complex outputs like loops/conditionals).
    """

    success: bool
    output: StepOutput | None = None
    error: str = ""
    error_trace: str = ""
    is_partial: bool = False
    waiting_for_human: bool = False
    waiting_for_gate: bool = False
    updated_context: dict[str, Any] = field(default_factory=dict)


class StepExecutor(abc.ABC):
    """Abstract base class for workflow step executors.

    Each step type has a corresponding executor that implements:
    - validate(): check config before execution
    - execute(): perform the step's work and return a StepResult
    """

    @abc.abstractmethod
    def validate(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
    ) -> list[str]:
        """Validate step configuration before execution.

        Args:
            step_id: The unique step identifier.
            config: The step's configuration dict from the workflow YAML.
            context: The current workflow context (for checking prerequisites).

        Returns:
            List of validation error messages. Empty list means valid.
        """

    @abc.abstractmethod
    def execute(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
        services: dict[str, Any] | None = None,
    ) -> StepResult:
        """Execute the step and return its result.

        Args:
            step_id: The unique step identifier.
            config: The step's configuration dict.
            context: The current workflow context (read and write).
            services: Optional dict of service dependencies (e.g. providers,
                data loaders). Steps use protocols/interfaces, not concrete types.

        Returns:
            A StepResult indicating success/failure and outputs.
        """

"""Step type registry for the workflow engine (WF-003).

Provides a central registry mapping step type strings to their executor
classes. Built-in step types are registered at import time; plugins can
register additional types at runtime.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from molabel.core.types import WorkflowStepCategory, WorkflowStepType

if TYPE_CHECKING:
    from molabel.core.workflow.steps.base import StepExecutor

logger = logging.getLogger(__name__)

# Canonical mapping of step types to their category
STEP_TYPE_CATEGORIES: dict[str, WorkflowStepCategory] = {
    WorkflowStepType.data_ingest: WorkflowStepCategory.data,
    WorkflowStepType.data_normalize: WorkflowStepCategory.data,
    WorkflowStepType.data_filter: WorkflowStepCategory.data,
    WorkflowStepType.data_sample: WorkflowStepCategory.data,
    WorkflowStepType.data_deduplicate: WorkflowStepCategory.data,
    WorkflowStepType.agent_run: WorkflowStepCategory.agent,
    WorkflowStepType.agent_compare: WorkflowStepCategory.agent,
    WorkflowStepType.human_review: WorkflowStepCategory.human,
    WorkflowStepType.human_triage: WorkflowStepCategory.human,
    WorkflowStepType.human_calibration: WorkflowStepCategory.human,
    WorkflowStepType.human_adjudication: WorkflowStepCategory.human,
    WorkflowStepType.quality_check: WorkflowStepCategory.quality,
    WorkflowStepType.agreement_analysis: WorkflowStepCategory.quality,
    WorkflowStepType.drift_detection: WorkflowStepCategory.quality,
    WorkflowStepType.export: WorkflowStepCategory.output,
    WorkflowStepType.snapshot: WorkflowStepCategory.output,
    WorkflowStepType.release_validation: WorkflowStepCategory.output,
    WorkflowStepType.loop: WorkflowStepCategory.control,
    WorkflowStepType.conditional: WorkflowStepCategory.control,
    WorkflowStepType.parallel: WorkflowStepCategory.control,
    WorkflowStepType.gate: WorkflowStepCategory.control,
}

# Step types that block for human/operator action
BLOCKING_STEP_TYPES: set[str] = {
    WorkflowStepType.human_review,
    WorkflowStepType.human_triage,
    WorkflowStepType.human_calibration,
    WorkflowStepType.human_adjudication,
    WorkflowStepType.gate,
}

# Step types that have no automatic timeout
NO_TIMEOUT_STEP_TYPES: set[str] = BLOCKING_STEP_TYPES


class StepExecutorRegistry:
    """Registry mapping step type strings to StepExecutor classes.

    Usage::

        registry = StepExecutorRegistry()
        registry.register("data_ingest", DataIngestExecutor)
        executor = registry.create("data_ingest")
    """

    def __init__(self) -> None:
        self._executors: dict[str, type[StepExecutor]] = {}

    def register(
        self,
        step_type: str,
        executor_class: type[StepExecutor],
    ) -> None:
        """Register an executor class for a step type.

        Args:
            step_type: The step type string (e.g. "data_ingest").
            executor_class: The StepExecutor subclass to instantiate.
        """
        if step_type in self._executors:
            logger.warning(
                "Overriding executor for step type '%s': %s -> %s",
                step_type,
                self._executors[step_type].__name__,
                executor_class.__name__,
            )
        self._executors[step_type] = executor_class

    def create(self, step_type: str) -> StepExecutor:
        """Create an executor instance for the given step type.

        Raises:
            KeyError: If no executor is registered for the step type.
        """
        if step_type not in self._executors:
            raise KeyError(
                f"No executor registered for step type '{step_type}'. "
                f"Registered types: {sorted(self._executors.keys())}"
            )
        return self._executors[step_type]()

    def has_executor(self, step_type: str) -> bool:
        """Return True if an executor is registered for the step type."""
        return step_type in self._executors

    def registered_types(self) -> list[str]:
        """Return all registered step type strings."""
        return sorted(self._executors.keys())

    def get_category(self, step_type: str) -> WorkflowStepCategory | None:
        """Return the category for a step type, or None if unknown."""
        return STEP_TYPE_CATEGORIES.get(step_type)

    def is_blocking(self, step_type: str) -> bool:
        """Return True if the step type blocks for human/operator action."""
        return step_type in BLOCKING_STEP_TYPES

    def has_timeout(self, step_type: str) -> bool:
        """Return True if the step type should have an automatic timeout."""
        return step_type not in NO_TIMEOUT_STEP_TYPES

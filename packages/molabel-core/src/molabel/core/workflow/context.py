"""WorkflowContext: shared state for inter-step data flow.

The context accumulates state as steps complete. Steps read from and write
to this context. It is serialized to JSON after every step completion for
crash recovery (WF-002, WF-044).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class DatasetReference:
    """Lightweight reference to a dataset within a workflow execution."""

    dataset_id: str
    dataset_name: str
    record_count: int = 0
    source_path: str | None = None


@dataclass
class RecordSet:
    """A set of record IDs produced or consumed by a step."""

    record_ids: list[str] = field(default_factory=list)
    record_count: int = 0
    description: str = ""


@dataclass
class AgentOutputRef:
    """Reference to agent outputs for a particular run."""

    agent_run_id: str
    model_id: str = ""
    record_count: int = 0
    success_count: int = 0
    failure_count: int = 0


@dataclass
class StepOutput:
    """Summary output from a completed step."""

    step_id: str
    step_type: str
    status: str = "completed"
    summary: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class StepTiming:
    """Timing information for a step execution."""

    step_id: str
    started_at: str | None = None
    completed_at: str | None = None
    duration_seconds: float = 0.0


@dataclass
class WorkflowContext:
    """Shared mutable state that accumulates as workflow steps execute.

    This is the sole mechanism for inter-step data flow. Steps never
    communicate directly -- they read from and write to this context.

    Attributes:
        workspace_id: The workspace this execution belongs to.
        workflow_execution_id: Unique ID for this execution instance.
        workflow_version: Version of the workflow definition being executed.
        datasets: Map of dataset_id to DatasetReference.
        record_sets: Map of step_id to the RecordSet that step produced.
        active_record_set_id: Step ID of the current working record set.
        agent_run_ids: Ordered list of accumulated agent run IDs.
        agent_outputs: Map of agent_run_id to AgentOutputRef.
        review_queue_ids: Ordered list of accumulated review queue IDs.
        adjudication_queue_ids: Ordered list of adjudication queue IDs.
        metrics: Named quality/progress metrics (agreement, coverage, etc.).
        step_outputs: Map of step_id to StepOutput summary.
        step_timings: Map of step_id to StepTiming.
        variables: User-defined variables for conditionals and templates.
        export_bundle_ids: Accumulated export bundle IDs.
        snapshot_ids: Accumulated snapshot IDs.
    """

    workspace_id: str
    workflow_execution_id: str
    workflow_version: int

    # Dataset and record tracking
    datasets: dict[str, DatasetReference] = field(default_factory=dict)
    record_sets: dict[str, RecordSet] = field(default_factory=dict)
    active_record_set_id: str | None = None

    # Agent tracking
    agent_run_ids: list[str] = field(default_factory=list)
    agent_outputs: dict[str, AgentOutputRef] = field(default_factory=dict)

    # Human work tracking
    review_queue_ids: list[str] = field(default_factory=list)
    adjudication_queue_ids: list[str] = field(default_factory=list)

    # Quality metrics
    metrics: dict[str, float] = field(default_factory=dict)

    # Step-level bookkeeping
    step_outputs: dict[str, StepOutput] = field(default_factory=dict)
    step_timings: dict[str, StepTiming] = field(default_factory=dict)

    # User-defined variables (for conditionals and templates)
    variables: dict[str, Any] = field(default_factory=dict)

    # Export and snapshot references
    export_bundle_ids: list[str] = field(default_factory=list)
    snapshot_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize context to a JSON-compatible dict for persistence."""
        return {
            "workspace_id": self.workspace_id,
            "workflow_execution_id": self.workflow_execution_id,
            "workflow_version": self.workflow_version,
            "datasets": {
                k: {
                    "dataset_id": v.dataset_id,
                    "dataset_name": v.dataset_name,
                    "record_count": v.record_count,
                    "source_path": v.source_path,
                }
                for k, v in self.datasets.items()
            },
            "record_sets": {
                k: {
                    "record_ids": v.record_ids,
                    "record_count": v.record_count,
                    "description": v.description,
                }
                for k, v in self.record_sets.items()
            },
            "active_record_set_id": self.active_record_set_id,
            "agent_run_ids": self.agent_run_ids,
            "agent_outputs": {
                k: {
                    "agent_run_id": v.agent_run_id,
                    "model_id": v.model_id,
                    "record_count": v.record_count,
                    "success_count": v.success_count,
                    "failure_count": v.failure_count,
                }
                for k, v in self.agent_outputs.items()
            },
            "review_queue_ids": self.review_queue_ids,
            "adjudication_queue_ids": self.adjudication_queue_ids,
            "metrics": self.metrics,
            "step_outputs": {
                k: {
                    "step_id": v.step_id,
                    "step_type": v.step_type,
                    "status": v.status,
                    "summary": v.summary,
                    "warnings": v.warnings,
                }
                for k, v in self.step_outputs.items()
            },
            "step_timings": {
                k: {
                    "step_id": v.step_id,
                    "started_at": v.started_at,
                    "completed_at": v.completed_at,
                    "duration_seconds": v.duration_seconds,
                }
                for k, v in self.step_timings.items()
            },
            "variables": self.variables,
            "export_bundle_ids": self.export_bundle_ids,
            "snapshot_ids": self.snapshot_ids,
        }

    def to_json(self) -> str:
        """Serialize context to a JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowContext:
        """Deserialize context from a dict (e.g. JSON-parsed database column).

        Validates expected types for key fields and wraps dataclass
        construction in try/except with descriptive error messages.

        Raises:
            TypeError: If required fields are missing or have wrong types.
            ValueError: If nested dataclass construction fails.
        """
        # Validate top-level required fields
        for field_name in ("workspace_id", "workflow_execution_id", "workflow_version"):
            if field_name not in data:
                raise TypeError(
                    f"WorkflowContext.from_dict: missing required field '{field_name}'"
                )

        # Validate expected types for key fields
        _validate_field_type(data, "datasets", dict, default={})
        _validate_field_type(data, "record_sets", dict, default={})
        _validate_field_type(data, "agent_outputs", dict, default={})
        _validate_field_type(data, "step_outputs", dict, default={})
        _validate_field_type(data, "step_timings", dict, default={})
        _validate_field_type(data, "metrics", dict, default={})
        _validate_field_type(data, "variables", dict, default={})
        _validate_field_type(data, "agent_run_ids", list, default=[])
        _validate_field_type(data, "review_queue_ids", list, default=[])
        _validate_field_type(data, "adjudication_queue_ids", list, default=[])
        _validate_field_type(data, "export_bundle_ids", list, default=[])
        _validate_field_type(data, "snapshot_ids", list, default=[])

        ctx = cls(
            workspace_id=data["workspace_id"],
            workflow_execution_id=data["workflow_execution_id"],
            workflow_version=data["workflow_version"],
        )
        ctx.active_record_set_id = data.get("active_record_set_id")
        ctx.agent_run_ids = data.get("agent_run_ids", [])
        ctx.review_queue_ids = data.get("review_queue_ids", [])
        ctx.adjudication_queue_ids = data.get("adjudication_queue_ids", [])
        ctx.metrics = data.get("metrics", {})
        ctx.variables = data.get("variables", {})
        ctx.export_bundle_ids = data.get("export_bundle_ids", [])
        ctx.snapshot_ids = data.get("snapshot_ids", [])

        _deserialize_nested(
            ctx.datasets, data.get("datasets", {}), DatasetReference, "datasets"
        )
        _deserialize_nested(
            ctx.record_sets, data.get("record_sets", {}), RecordSet, "record_sets"
        )
        _deserialize_nested(
            ctx.agent_outputs,
            data.get("agent_outputs", {}),
            AgentOutputRef,
            "agent_outputs",
        )
        _deserialize_nested(
            ctx.step_outputs, data.get("step_outputs", {}), StepOutput, "step_outputs"
        )
        _deserialize_nested(
            ctx.step_timings, data.get("step_timings", {}), StepTiming, "step_timings"
        )

        return ctx

    @classmethod
    def from_json(cls, json_str: str) -> WorkflowContext:
        """Deserialize context from a JSON string."""
        return cls.from_dict(json.loads(json_str))

    def get_active_record_ids(self) -> list[str]:
        """Return record IDs from the active record set, or empty list."""
        if self.active_record_set_id and self.active_record_set_id in self.record_sets:
            return self.record_sets[self.active_record_set_id].record_ids
        return []

    def record_step_start(self, step_id: str) -> None:
        """Record the start time for a step."""
        self.step_timings[step_id] = StepTiming(
            step_id=step_id,
            started_at=datetime.now(UTC).isoformat(),
        )

    def record_step_end(self, step_id: str) -> None:
        """Record the end time for a step and compute duration."""
        if step_id in self.step_timings:
            timing = self.step_timings[step_id]
            timing.completed_at = datetime.now(UTC).isoformat()
            if timing.started_at:
                start = datetime.fromisoformat(timing.started_at)
                end = datetime.fromisoformat(timing.completed_at)
                timing.duration_seconds = (end - start).total_seconds()


def _validate_field_type(
    data: dict[str, Any],
    field_name: str,
    expected_type: type,
    *,
    default: Any = None,
) -> None:
    """Validate that a field in the data dict has the expected type.

    Raises TypeError with a descriptive message if the type is wrong.
    """
    value = data.get(field_name, default)
    if value is not None and not isinstance(value, expected_type):
        raise TypeError(
            f"WorkflowContext.from_dict: field '{field_name}' expected "
            f"{expected_type.__name__}, got {type(value).__name__}"
        )


def _deserialize_nested(
    target: dict[str, Any],
    source: dict[str, Any],
    dataclass_type: type,
    field_name: str,
) -> None:
    """Deserialize nested dict entries into dataclass instances.

    Wraps construction in try/except with descriptive errors.
    """
    for k, v in source.items():
        try:
            target[k] = dataclass_type(**v)
        except (TypeError, KeyError) as e:
            raise ValueError(
                f"WorkflowContext.from_dict: failed to deserialize "
                f"'{field_name}[{k!r}]' as {dataclass_type.__name__}: {e}"
            ) from e

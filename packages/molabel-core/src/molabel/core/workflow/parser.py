"""YAML parser for workflow definition files (WF-001, WF-003, WF-045).

Parses workflow YAML into a validated WorkflowDefinitionParsed with a
dependency DAG. Supports both implicit (YAML order) and explicit
(depends_on) predecessor resolution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from molabel.core.types import WorkflowStepType

# All valid step type strings
_VALID_STEP_TYPES = {e.value for e in WorkflowStepType}


class WorkflowParseError(Exception):
    """Raised when a workflow YAML cannot be parsed or validated."""


@dataclass
class StepDefinition:
    """Parsed representation of a single workflow step.

    Attributes:
        id: Unique step identifier within the workflow.
        type: Step type from the WorkflowStepType enum.
        config: Step-specific configuration dict.
        depends_on: Explicit predecessor step IDs (empty = use YAML order).
        breakpoint: If True, pause before executing this step.
    """

    id: str
    type: str
    config: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    breakpoint: bool = False


@dataclass
class WorkflowDefinitionParsed:
    """Fully parsed and validated workflow definition.

    Attributes:
        name: Human-readable workflow name.
        version: Workflow version (increments on edit after execution).
        description: Optional description text.
        steps: Ordered list of step definitions.
        step_index: Map of step_id to StepDefinition for O(1) lookup.
        predecessors: Map of step_id to list of predecessor step_ids (DAG).
        successors: Map of step_id to list of successor step_ids.
        pause_on_every_step: If True, every step gets an implicit breakpoint.
        metadata: Additional workflow-level metadata from the YAML.
    """

    name: str
    version: int
    description: str = ""
    steps: list[StepDefinition] = field(default_factory=list)
    step_index: dict[str, StepDefinition] = field(default_factory=dict)
    predecessors: dict[str, list[str]] = field(default_factory=dict)
    successors: dict[str, list[str]] = field(default_factory=dict)
    pause_on_every_step: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_root_steps(self) -> list[str]:
        """Return step IDs that have no predecessors (DAG roots)."""
        return [sid for sid, preds in self.predecessors.items() if len(preds) == 0]

    def get_step(self, step_id: str) -> StepDefinition:
        """Look up a step by ID. Raises KeyError if not found."""
        return self.step_index[step_id]

    def topological_order(self) -> list[str]:
        """Return step IDs in a valid topological order.

        Raises WorkflowParseError if a cycle is detected.
        """
        visited: set[str] = set()
        temp_marks: set[str] = set()
        result: list[str] = []

        def visit(node: str) -> None:
            if node in visited:
                return
            if node in temp_marks:
                raise WorkflowParseError(
                    f"Cycle detected in workflow DAG involving step '{node}'"
                )
            temp_marks.add(node)
            for succ in self.successors.get(node, []):
                visit(succ)
            temp_marks.discard(node)
            visited.add(node)
            result.append(node)

        for step_id in self.predecessors:
            visit(step_id)

        result.reverse()
        return result


def parse_workflow_yaml(
    source: str | Path,
    *,
    from_string: bool = False,
) -> WorkflowDefinitionParsed:
    """Parse a workflow YAML file or string into a validated definition.

    Args:
        source: Path to the YAML file, or YAML string if from_string=True.
        from_string: If True, treat source as a YAML string instead of a path.

    Returns:
        A fully parsed and validated WorkflowDefinitionParsed.

    Raises:
        WorkflowParseError: On invalid YAML or failed validation.
    """
    if from_string:
        raw_yaml = str(source)
    else:
        path = Path(source)
        if not path.exists():
            raise WorkflowParseError(f"Workflow file not found: {path}")
        raw_yaml = path.read_text(encoding="utf-8")

    try:
        data = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as e:
        raise WorkflowParseError(f"Invalid YAML: {e}") from e

    if not isinstance(data, dict):
        raise WorkflowParseError("Workflow YAML must be a mapping at the top level")

    return _validate_and_build(data)


def _validate_and_build(data: dict[str, Any]) -> WorkflowDefinitionParsed:
    """Validate raw YAML data and build the workflow definition with DAG."""
    name = data.get("name")
    if not name or not isinstance(name, str):
        raise WorkflowParseError("Workflow must have a 'name' field (string)")

    version = data.get("version", 1)
    if not isinstance(version, int) or version < 1:
        raise WorkflowParseError("Workflow 'version' must be a positive integer")

    description = data.get("description", "")
    pause_on_every_step = data.get("pause_on_every_step", False)

    raw_steps = data.get("steps")
    if not raw_steps or not isinstance(raw_steps, list):
        raise WorkflowParseError(
            "Workflow must have a 'steps' list with at least one step"
        )

    steps: list[StepDefinition] = []
    step_ids: set[str] = set()

    for i, raw_step in enumerate(raw_steps):
        if not isinstance(raw_step, dict):
            raise WorkflowParseError(f"Step {i} must be a mapping")

        step_id = raw_step.get("id")
        if not step_id or not isinstance(step_id, str):
            raise WorkflowParseError(f"Step {i} must have an 'id' field (string)")

        if step_id in step_ids:
            raise WorkflowParseError(f"Duplicate step id: '{step_id}'")
        step_ids.add(step_id)

        step_type = raw_step.get("type")
        if not step_type or not isinstance(step_type, str):
            raise WorkflowParseError(
                f"Step '{step_id}' must have a 'type' field (string)"
            )
        if step_type not in _VALID_STEP_TYPES:
            raise WorkflowParseError(
                f"Step '{step_id}' has unknown type '{step_type}'. "
                f"Valid types: {sorted(_VALID_STEP_TYPES)}"
            )

        config = raw_step.get("config", {})
        if not isinstance(config, dict):
            raise WorkflowParseError(f"Step '{step_id}' config must be a mapping")

        depends_on_raw = raw_step.get("depends_on", [])
        if isinstance(depends_on_raw, str):
            depends_on_raw = [depends_on_raw]
        if not isinstance(depends_on_raw, list):
            raise WorkflowParseError(
                f"Step '{step_id}' depends_on must be a list or string"
            )
        depends_on = [str(d) for d in depends_on_raw]

        # breakpoint can be in config or at step level
        bp = raw_step.get("breakpoint", config.get("breakpoint", False))

        steps.append(
            StepDefinition(
                id=step_id,
                type=step_type,
                config=config,
                depends_on=depends_on,
                breakpoint=bool(bp),
            )
        )

    # Validate depends_on references
    for step in steps:
        for dep in step.depends_on:
            if dep not in step_ids:
                raise WorkflowParseError(
                    f"Step '{step.id}' depends_on references unknown step '{dep}'"
                )

    # Build the DAG: predecessors and successors
    predecessors: dict[str, list[str]] = {}
    successors: dict[str, list[str]] = {}
    step_index: dict[str, StepDefinition] = {}

    for step in steps:
        step_index[step.id] = step
        predecessors[step.id] = []
        if step.id not in successors:
            successors[step.id] = []

    # Determine predecessors: explicit depends_on or implicit YAML order
    for i, step in enumerate(steps):
        if step.depends_on:
            # Explicit predecessors
            predecessors[step.id] = list(step.depends_on)
        elif i > 0:
            # Implicit: depends on the immediately preceding step
            predecessors[step.id] = [steps[i - 1].id]

    # Build successors from predecessors
    for step_id, preds in predecessors.items():
        for pred_id in preds:
            if pred_id not in successors:
                successors[pred_id] = []
            successors[pred_id].append(step_id)

    wf = WorkflowDefinitionParsed(
        name=name,
        version=version,
        description=str(description),
        steps=steps,
        step_index=step_index,
        predecessors=predecessors,
        successors=successors,
        pause_on_every_step=bool(pause_on_every_step),
        metadata={
            k: v
            for k, v in data.items()
            if k
            not in {
                "name",
                "version",
                "description",
                "steps",
                "pause_on_every_step",
            }
        },
    )

    # Validate DAG is acyclic
    wf.topological_order()

    return wf

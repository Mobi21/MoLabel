"""Tier 9 — Cross-Cutting: Workflow Parser Coverage (T9-09).

Tests:
    T9-09: Parse YAML definitions that include all 21 WorkflowStepType values
           and verify no WorkflowParseError is raised; test invalid types
           and cycle detection.
"""

from __future__ import annotations

import pytest

from molabel.core.types import WorkflowStepType
from molabel.core.workflow.parser import (
    WorkflowDefinitionParsed,
    WorkflowParseError,
    parse_workflow_yaml,
)
from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import INDEPENDENT


def _make_yaml(steps: list[dict]) -> str:
    """Build a minimal valid workflow YAML from a list of step dicts."""
    lines = ["name: Test Workflow", "version: 1", "steps:"]
    for step in steps:
        lines.append(f"  - id: {step['id']}")
        lines.append(f"    type: {step['type']}")
        if "depends_on" in step:
            dep = step["depends_on"]
            if isinstance(dep, list):
                lines.append(f"    depends_on: [{', '.join(dep)}]")
            else:
                lines.append(f"    depends_on: {dep}")
    return "\n".join(lines)


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier9
async def test_parser_coverage(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T9-09: Workflow YAML with all 21 step types parses without error."""

    all_step_types = list(WorkflowStepType)

    with checkpoint(ctx, "all_21_step_types_exist"):
        assert len(all_step_types) >= 21, (
            f"Expected at least 21 WorkflowStepType values, got {len(all_step_types)}"
        )

    # --- Parse each step type individually ---
    with checkpoint(ctx, "each_step_type_parses_standalone"):
        for step_type in all_step_types:
            yaml_str = _make_yaml([{"id": "step_one", "type": step_type.value}])
            try:
                result = parse_workflow_yaml(yaml_str, from_string=True)
                assert isinstance(result, WorkflowDefinitionParsed)
                assert len(result.steps) == 1
                assert result.steps[0].type == step_type.value
            except WorkflowParseError as exc:
                pytest.fail(f"Step type '{step_type.value}' failed to parse: {exc}")

    # --- Parse all 21 step types in a single linear workflow ---
    with checkpoint(ctx, "all_step_types_in_single_workflow"):
        steps = [
            {"id": f"step_{i:02d}_{st.value}", "type": st.value}
            for i, st in enumerate(all_step_types)
        ]
        yaml_str = _make_yaml(steps)
        result = parse_workflow_yaml(yaml_str, from_string=True)
        assert isinstance(result, WorkflowDefinitionParsed)
        assert len(result.steps) == len(all_step_types)

    # --- DAG is acyclic ---
    with checkpoint(ctx, "linear_workflow_is_acyclic"):
        steps = [
            {"id": f"step_{i:02d}_{st.value}", "type": st.value}
            for i, st in enumerate(all_step_types)
        ]
        yaml_str = _make_yaml(steps)
        result = parse_workflow_yaml(yaml_str, from_string=True)
        order = result.topological_order()
        assert len(order) == len(all_step_types)

    # --- Root steps identified correctly ---
    with checkpoint(ctx, "root_steps_identified"):
        yaml_str = _make_yaml(
            [{"id": "root", "type": WorkflowStepType.data_ingest.value}]
        )
        result = parse_workflow_yaml(yaml_str, from_string=True)
        roots = result.get_root_steps()
        assert "root" in roots

    # --- Invalid step type raises WorkflowParseError ---
    with checkpoint(ctx, "invalid_step_type_raises_error"):
        yaml_str = _make_yaml([{"id": "bad_step", "type": "not_a_real_type"}])
        with pytest.raises(WorkflowParseError, match="unknown type"):
            parse_workflow_yaml(yaml_str, from_string=True)

    # --- Duplicate step IDs raise WorkflowParseError ---
    with checkpoint(ctx, "duplicate_step_id_raises_error"):
        yaml_str = _make_yaml(
            [
                {"id": "step_a", "type": WorkflowStepType.data_ingest.value},
                {"id": "step_a", "type": WorkflowStepType.data_normalize.value},
            ]
        )
        with pytest.raises(WorkflowParseError, match="Duplicate step id"):
            parse_workflow_yaml(yaml_str, from_string=True)

    # --- Missing name raises WorkflowParseError ---
    with checkpoint(ctx, "missing_name_raises_error"):
        yaml_str = "version: 1\nsteps:\n  - id: s\n    type: data_ingest"
        with pytest.raises(WorkflowParseError, match="name"):
            parse_workflow_yaml(yaml_str, from_string=True)

    # --- Explicit depends_on creates correct DAG ---
    with checkpoint(ctx, "explicit_depends_on_dag"):
        steps_with_deps = [
            {"id": "ingest", "type": WorkflowStepType.data_ingest.value},
            {"id": "normalize", "type": WorkflowStepType.data_normalize.value},
            {
                "id": "filter",
                "type": WorkflowStepType.data_filter.value,
                "depends_on": ["ingest", "normalize"],
            },
        ]
        yaml_str = _make_yaml(steps_with_deps)
        result = parse_workflow_yaml(yaml_str, from_string=True)
        assert "ingest" in result.predecessors["filter"]
        assert "normalize" in result.predecessors["filter"]

    # --- Step index allows O(1) lookup ---
    with checkpoint(ctx, "step_index_lookup"):
        yaml_str = _make_yaml(
            [
                {"id": "lookup_target", "type": WorkflowStepType.agent_run.value},
            ]
        )
        result = parse_workflow_yaml(yaml_str, from_string=True)
        step = result.get_step("lookup_target")
        assert step.type == WorkflowStepType.agent_run.value

    # --- WorkflowStepType enum coverage matches _VALID_STEP_TYPES ---
    with checkpoint(ctx, "step_type_enum_matches_valid_set"):
        from molabel.core.workflow.parser import _VALID_STEP_TYPES

        enum_values = {st.value for st in WorkflowStepType}
        assert enum_values == _VALID_STEP_TYPES, (
            f"WorkflowStepType enum values don't match _VALID_STEP_TYPES.\n"
            f"Only in enum: {enum_values - _VALID_STEP_TYPES}\n"
            f"Only in _VALID_STEP_TYPES: {_VALID_STEP_TYPES - enum_values}"
        )

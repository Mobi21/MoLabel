"""T8-02: 8 invalid YAML inputs — each raises a descriptive WorkflowParseError.

Tests directly against the parser (no API call needed):
1. Bad YAML syntax (unterminated string)
2. Missing top-level 'name' field
3. Unknown step type
4. Duplicate step IDs
5. Cycle in DAG (step A -> B -> A)
6. Unknown depends_on target
7. Empty steps list
8. Non-mapping config (config: "string_not_dict")
"""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.parallel import INDEPENDENT


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier8
async def test_invalid_workflow_yaml(client, ctx):
    """T8-02: 8 invalid YAML inputs each raise descriptive WorkflowParseError."""

    from molabel.core.workflow.parser import WorkflowParseError, parse_workflow_yaml

    # ── Checkpoint 1: Bad YAML syntax ────────────────────────────────────────
    with checkpoint(ctx, "bad_yaml_syntax"):
        bad_syntax = """\
name: "Unclosed string
steps:
  - id: step1
    type: agent_run
"""
        with pytest.raises(WorkflowParseError, match="(?i)yaml|invalid"):
            parse_workflow_yaml(bad_syntax, from_string=True)

    # ── Checkpoint 2: Missing 'name' field ────────────────────────────────────
    with checkpoint(ctx, "missing_name"):
        missing_name = """\
version: 1
steps:
  - id: step1
    type: agent_run
"""
        with pytest.raises(WorkflowParseError, match="(?i)name"):
            parse_workflow_yaml(missing_name, from_string=True)

    # ── Checkpoint 3: Unknown step type ──────────────────────────────────────
    with checkpoint(ctx, "unknown_step_type"):
        unknown_type = """\
name: "Unknown Type Workflow"
version: 1
steps:
  - id: step1
    type: totally_unknown_step_type
"""
        with pytest.raises(WorkflowParseError, match="(?i)unknown|type"):
            parse_workflow_yaml(unknown_type, from_string=True)

    # ── Checkpoint 4: Duplicate step IDs ─────────────────────────────────────
    with checkpoint(ctx, "duplicate_step_ids"):
        dupe_ids = """\
name: "Duplicate IDs Workflow"
version: 1
steps:
  - id: step1
    type: agent_run
  - id: step1
    type: human_review
"""
        with pytest.raises(WorkflowParseError, match="(?i)duplicate"):
            parse_workflow_yaml(dupe_ids, from_string=True)

    # ── Checkpoint 5: Cycle in DAG ────────────────────────────────────────────
    with checkpoint(ctx, "cycle_in_dag"):
        cycle = """\
name: "Cyclic Workflow"
version: 1
steps:
  - id: stepA
    type: agent_run
    depends_on: [stepC]
  - id: stepB
    type: human_review
    depends_on: [stepA]
  - id: stepC
    type: quality_check
    depends_on: [stepB]
"""
        with pytest.raises(WorkflowParseError, match="(?i)cycle|circular"):
            parse_workflow_yaml(cycle, from_string=True)

    # ── Checkpoint 6: Unknown depends_on target ───────────────────────────────
    with checkpoint(ctx, "unknown_depends_on"):
        unknown_dep = """\
name: "Unknown Dep Workflow"
version: 1
steps:
  - id: step1
    type: agent_run
  - id: step2
    type: human_review
    depends_on: [nonexistent_step]
"""
        with pytest.raises(
            WorkflowParseError, match="(?i)unknown|nonexistent|depends_on"
        ):
            parse_workflow_yaml(unknown_dep, from_string=True)

    # ── Checkpoint 7: Empty steps list ───────────────────────────────────────
    with checkpoint(ctx, "empty_steps"):
        empty_steps = """\
name: "Empty Steps Workflow"
version: 1
steps: []
"""
        with pytest.raises(WorkflowParseError, match="(?i)step"):
            parse_workflow_yaml(empty_steps, from_string=True)

    # ── Checkpoint 8: Non-mapping config ─────────────────────────────────────
    with checkpoint(ctx, "non_mapping_config"):
        bad_config = """\
name: "Bad Config Workflow"
version: 1
steps:
  - id: step1
    type: agent_run
    config: "this should be a dict not a string"
"""
        with pytest.raises(WorkflowParseError, match="(?i)config|mapping"):
            parse_workflow_yaml(bad_config, from_string=True)

    # ── Checkpoint 9: Valid YAML parses successfully (sanity check) ───────────
    with checkpoint(ctx, "valid_yaml_control"):
        valid_yaml = """\
name: "Valid Workflow"
version: 1
description: "A valid workflow for sanity checking"
steps:
  - id: ingest
    type: data_ingest
    config:
      source: "s3://bucket/data"
  - id: label
    type: agent_run
    depends_on: [ingest]
    config:
      model: "MiniMax-M2.7-highspeed"
  - id: review
    type: human_review
    depends_on: [label]
"""
        result = parse_workflow_yaml(valid_yaml, from_string=True)
        assert result.name == "Valid Workflow"
        assert len(result.steps) == 3
        assert result.steps[0].id == "ingest"
        assert result.steps[1].id == "label"
        assert result.steps[2].id == "review"
        # DAG structure correct
        assert result.predecessors["ingest"] == []
        assert "ingest" in result.predecessors["label"]
        assert "label" in result.predecessors["review"]

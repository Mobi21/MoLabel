"""Tests for workflow YAML parser and context.

Covers WF-001, WF-002, WF-003, WF-036, WF-045.
"""

from __future__ import annotations

import pytest

from molabel.core.workflow.context import (
    AgentOutputRef,
    DatasetReference,
    RecordSet,
    StepOutput,
    StepTiming,
    WorkflowContext,
)
from molabel.core.workflow.parser import (
    WorkflowParseError,
    parse_workflow_yaml,
)

# ---------------------------------------------------------------------------
# WorkflowContext tests (WF-002)
# ---------------------------------------------------------------------------


class TestWorkflowContext:
    """Tests for WorkflowContext serialization and helper methods."""

    def test_create_empty_context(self) -> None:
        ctx = WorkflowContext(
            workspace_id="ws-1",
            workflow_execution_id="exec-1",
            workflow_version=1,
        )
        assert ctx.workspace_id == "ws-1"
        assert ctx.workflow_execution_id == "exec-1"
        assert ctx.workflow_version == 1
        assert ctx.datasets == {}
        assert ctx.record_sets == {}
        assert ctx.active_record_set_id is None
        assert ctx.agent_run_ids == []
        assert ctx.metrics == {}
        assert ctx.variables == {}

    def test_roundtrip_serialization(self) -> None:
        ctx = WorkflowContext(
            workspace_id="ws-1",
            workflow_execution_id="exec-1",
            workflow_version=2,
        )
        ctx.datasets["ds-1"] = DatasetReference(
            dataset_id="ds-1",
            dataset_name="test-dataset",
            record_count=100,
            source_path="/data/test.jsonl",
        )
        ctx.record_sets["ingest"] = RecordSet(
            record_ids=["r1", "r2", "r3"],
            record_count=3,
            description="Test records",
        )
        ctx.active_record_set_id = "ingest"
        ctx.agent_run_ids = ["run-1"]
        ctx.agent_outputs["run-1"] = AgentOutputRef(
            agent_run_id="run-1",
            model_id="claude-sonnet",
            record_count=3,
            success_count=3,
        )
        ctx.metrics["agreement.kappa"] = 0.85
        ctx.variables["quality.passed"] = True
        ctx.export_bundle_ids = ["export-1"]
        ctx.snapshot_ids = ["snap-1"]
        ctx.step_outputs["ingest"] = StepOutput(
            step_id="ingest",
            step_type="data_ingest",
            summary={"record_count": 3},
        )
        ctx.step_timings["ingest"] = StepTiming(
            step_id="ingest",
            started_at="2026-03-23T00:00:00+00:00",
            completed_at="2026-03-23T00:01:00+00:00",
            duration_seconds=60.0,
        )

        # Serialize to dict
        data = ctx.to_dict()
        assert data["workspace_id"] == "ws-1"
        assert data["datasets"]["ds-1"]["dataset_name"] == "test-dataset"
        assert data["record_sets"]["ingest"]["record_count"] == 3
        assert data["metrics"]["agreement.kappa"] == 0.85

        # Roundtrip through JSON
        json_str = ctx.to_json()
        ctx2 = WorkflowContext.from_json(json_str)
        assert ctx2.workspace_id == "ws-1"
        assert ctx2.workflow_version == 2
        assert ctx2.datasets["ds-1"].dataset_name == "test-dataset"
        assert ctx2.record_sets["ingest"].record_ids == ["r1", "r2", "r3"]
        assert ctx2.active_record_set_id == "ingest"
        assert ctx2.agent_run_ids == ["run-1"]
        assert ctx2.metrics["agreement.kappa"] == 0.85
        assert ctx2.variables["quality.passed"] is True
        assert ctx2.export_bundle_ids == ["export-1"]
        assert ctx2.snapshot_ids == ["snap-1"]
        assert ctx2.step_outputs["ingest"].step_type == "data_ingest"

    def test_get_active_record_ids(self) -> None:
        ctx = WorkflowContext(
            workspace_id="ws-1",
            workflow_execution_id="exec-1",
            workflow_version=1,
        )
        assert ctx.get_active_record_ids() == []

        ctx.record_sets["step1"] = RecordSet(record_ids=["a", "b", "c"])
        ctx.active_record_set_id = "step1"
        assert ctx.get_active_record_ids() == ["a", "b", "c"]

    def test_record_step_timing(self) -> None:
        ctx = WorkflowContext(
            workspace_id="ws-1",
            workflow_execution_id="exec-1",
            workflow_version=1,
        )
        ctx.record_step_start("step1")
        assert "step1" in ctx.step_timings
        assert ctx.step_timings["step1"].started_at is not None

        ctx.record_step_end("step1")
        assert ctx.step_timings["step1"].completed_at is not None
        assert ctx.step_timings["step1"].duration_seconds >= 0


# ---------------------------------------------------------------------------
# YAML parser tests (WF-001, WF-003, WF-045)
# ---------------------------------------------------------------------------


MINIMAL_WORKFLOW = """
name: "Test Workflow"
version: 1
steps:
  - id: ingest
    type: data_ingest
    config:
      source: "data/*.jsonl"
"""

LINEAR_WORKFLOW = """
name: "Linear Pipeline"
version: 2
description: "A simple linear pipeline"
steps:
  - id: ingest
    type: data_ingest
    config:
      source: "data/*.jsonl"
  - id: normalize
    type: data_normalize
    config:
      schema_ref: "schemas/default.yaml"
  - id: agent_label
    type: agent_run
    config:
      prompt_ref: "prompts/default.yaml"
      model: "claude-sonnet"
  - id: export_results
    type: export
    config:
      format: jsonl
      destination: "exports/"
"""

DAG_WORKFLOW = """
name: "DAG Workflow"
version: 1
steps:
  - id: ingest
    type: data_ingest
    config:
      source: "data/*.jsonl"
  - id: review_a
    type: human_review
    config: {}
  - id: review_b
    type: human_review
    depends_on: [ingest]
    config: {}
  - id: merge_results
    type: quality_check
    depends_on: [review_a, review_b]
    config:
      min_agreement: 0.85
"""


class TestWorkflowParser:
    """Tests for parse_workflow_yaml()."""

    def test_parse_minimal(self) -> None:
        wf = parse_workflow_yaml(MINIMAL_WORKFLOW, from_string=True)
        assert wf.name == "Test Workflow"
        assert wf.version == 1
        assert len(wf.steps) == 1
        assert wf.steps[0].id == "ingest"
        assert wf.steps[0].type == "data_ingest"
        assert wf.steps[0].config["source"] == "data/*.jsonl"

    def test_parse_linear_workflow(self) -> None:
        wf = parse_workflow_yaml(LINEAR_WORKFLOW, from_string=True)
        assert wf.name == "Linear Pipeline"
        assert wf.version == 2
        assert wf.description == "A simple linear pipeline"
        assert len(wf.steps) == 4

        # Implicit predecessor chain
        assert wf.predecessors["ingest"] == []
        assert wf.predecessors["normalize"] == ["ingest"]
        assert wf.predecessors["agent_label"] == ["normalize"]
        assert wf.predecessors["export_results"] == ["agent_label"]

        # Successors
        assert "normalize" in wf.successors["ingest"]
        assert "agent_label" in wf.successors["normalize"]

    def test_parse_dag_workflow(self) -> None:
        wf = parse_workflow_yaml(DAG_WORKFLOW, from_string=True)
        assert len(wf.steps) == 4

        # review_a depends on ingest implicitly (YAML order)
        assert wf.predecessors["review_a"] == ["ingest"]
        # review_b depends on ingest explicitly
        assert wf.predecessors["review_b"] == ["ingest"]
        # merge_results depends on both reviews
        assert set(wf.predecessors["merge_results"]) == {"review_a", "review_b"}

    def test_root_steps(self) -> None:
        wf = parse_workflow_yaml(MINIMAL_WORKFLOW, from_string=True)
        roots = wf.get_root_steps()
        assert roots == ["ingest"]

    def test_topological_order(self) -> None:
        wf = parse_workflow_yaml(LINEAR_WORKFLOW, from_string=True)
        order = wf.topological_order()
        assert order == ["ingest", "normalize", "agent_label", "export_results"]

    def test_step_index_lookup(self) -> None:
        wf = parse_workflow_yaml(LINEAR_WORKFLOW, from_string=True)
        step = wf.get_step("agent_label")
        assert step.type == "agent_run"
        assert step.config["model"] == "claude-sonnet"

    def test_breakpoint_in_config(self) -> None:
        yaml_str = """
name: "Breakpoint Test"
version: 1
steps:
  - id: review
    type: human_review
    config:
      breakpoint: true
"""
        wf = parse_workflow_yaml(yaml_str, from_string=True)
        assert wf.steps[0].breakpoint is True

    def test_breakpoint_at_step_level(self) -> None:
        yaml_str = """
name: "Breakpoint Test"
version: 1
steps:
  - id: review
    type: human_review
    breakpoint: true
    config: {}
"""
        wf = parse_workflow_yaml(yaml_str, from_string=True)
        assert wf.steps[0].breakpoint is True

    def test_pause_on_every_step(self) -> None:
        yaml_str = """
name: "Debug Workflow"
version: 1
pause_on_every_step: true
steps:
  - id: ingest
    type: data_ingest
    config:
      source: "data/*.jsonl"
"""
        wf = parse_workflow_yaml(yaml_str, from_string=True)
        assert wf.pause_on_every_step is True


class TestWorkflowParserErrors:
    """Tests for parser error handling."""

    def test_missing_name(self) -> None:
        with pytest.raises(WorkflowParseError, match="'name' field"):
            parse_workflow_yaml("version: 1\nsteps: []", from_string=True)

    def test_missing_steps(self) -> None:
        with pytest.raises(WorkflowParseError, match="'steps' list"):
            parse_workflow_yaml("name: test\nversion: 1", from_string=True)

    def test_empty_steps(self) -> None:
        with pytest.raises(WorkflowParseError, match="'steps' list"):
            parse_workflow_yaml("name: test\nversion: 1\nsteps: []", from_string=True)

    def test_duplicate_step_id(self) -> None:
        yaml_str = """
name: test
version: 1
steps:
  - id: ingest
    type: data_ingest
    config: {}
  - id: ingest
    type: data_filter
    config: {}
"""
        with pytest.raises(WorkflowParseError, match="Duplicate step id"):
            parse_workflow_yaml(yaml_str, from_string=True)

    def test_unknown_step_type(self) -> None:
        yaml_str = """
name: test
version: 1
steps:
  - id: bad
    type: nonexistent_type
    config: {}
"""
        with pytest.raises(WorkflowParseError, match="unknown type"):
            parse_workflow_yaml(yaml_str, from_string=True)

    def test_unknown_depends_on_ref(self) -> None:
        yaml_str = """
name: test
version: 1
steps:
  - id: step1
    type: data_ingest
    depends_on: [nonexistent]
    config: {}
"""
        with pytest.raises(WorkflowParseError, match="unknown step 'nonexistent'"):
            parse_workflow_yaml(yaml_str, from_string=True)

    def test_invalid_yaml_syntax(self) -> None:
        with pytest.raises(WorkflowParseError, match="Invalid YAML"):
            parse_workflow_yaml("{{invalid yaml", from_string=True)

    def test_invalid_version(self) -> None:
        yaml_str = """
name: test
version: -1
steps:
  - id: s
    type: data_ingest
    config: {}
"""
        with pytest.raises(WorkflowParseError, match="positive integer"):
            parse_workflow_yaml(yaml_str, from_string=True)

    def test_cycle_detection(self) -> None:
        yaml_str = """
name: test
version: 1
steps:
  - id: a
    type: data_ingest
    depends_on: [b]
    config: {}
  - id: b
    type: data_filter
    depends_on: [a]
    config: {}
"""
        with pytest.raises(WorkflowParseError, match="Cycle detected"):
            parse_workflow_yaml(yaml_str, from_string=True)

    def test_file_not_found(self) -> None:
        with pytest.raises(WorkflowParseError, match="not found"):
            parse_workflow_yaml("/nonexistent/path/workflow.yaml")

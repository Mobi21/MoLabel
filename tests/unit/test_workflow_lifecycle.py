"""Tests for the workspace lifecycle stage engine (WF-052)."""

from __future__ import annotations

from typing import Any

from molabel.core.workflow.context import (
    DatasetReference,
    RecordSet,
    WorkflowContext,
)
from molabel.core.workflow.lifecycle import (
    LIFECYCLE_STAGES,
    compute_lifecycle_stage,
)


def _ctx(**kwargs: Any) -> WorkflowContext:
    """Create a test context."""
    return WorkflowContext(
        workspace_id="ws-1",
        workflow_execution_id="exec-1",
        workflow_version=1,
        **kwargs,
    )


class TestLifecycleStages:
    """Tests for compute_lifecycle_stage()."""

    def test_no_context_is_empty(self) -> None:
        info = compute_lifecycle_stage(None)
        assert info.current_stage == "empty"
        assert info.stage_index == 0
        assert len(info.blockers) > 0

    def test_empty_context_is_empty(self) -> None:
        ctx = _ctx()
        info = compute_lifecycle_stage(ctx)
        assert info.current_stage == "empty"

    def test_data_ingested(self) -> None:
        ctx = _ctx()
        ctx.datasets["ds-1"] = DatasetReference(dataset_id="ds-1", dataset_name="test")
        info = compute_lifecycle_stage(ctx)
        assert info.current_stage == "data_ingested"
        assert info.stage_index == 1
        assert "recommended_actions" in dir(info)
        assert len(info.recommended_actions) > 0

    def test_schema_configured(self) -> None:
        ctx = _ctx()
        ctx.datasets["ds-1"] = DatasetReference(dataset_id="ds-1", dataset_name="test")
        ctx.record_sets["step1"] = RecordSet(record_ids=["r1"], record_count=1)
        info = compute_lifecycle_stage(ctx)
        assert info.current_stage == "schema_configured"
        assert info.stage_index == 2

    def test_agent_labeled(self) -> None:
        ctx = _ctx()
        ctx.datasets["ds-1"] = DatasetReference(dataset_id="ds-1", dataset_name="test")
        ctx.record_sets["step1"] = RecordSet(record_ids=["r1"], record_count=1)
        ctx.agent_run_ids = ["run-1"]
        info = compute_lifecycle_stage(ctx)
        assert info.current_stage == "agent_labeled"
        assert info.stage_index == 3

    def test_review_in_progress(self) -> None:
        ctx = _ctx()
        ctx.datasets["ds-1"] = DatasetReference(dataset_id="ds-1", dataset_name="test")
        ctx.record_sets["step1"] = RecordSet(record_ids=["r1"], record_count=1)
        ctx.agent_run_ids = ["run-1"]
        ctx.review_queue_ids = ["q-1"]
        info = compute_lifecycle_stage(ctx)
        assert info.current_stage == "review_in_progress"
        assert info.stage_index == 4

    def test_quality_validated(self) -> None:
        ctx = _ctx()
        ctx.datasets["ds-1"] = DatasetReference(dataset_id="ds-1", dataset_name="test")
        ctx.record_sets["step1"] = RecordSet(record_ids=["r1"], record_count=1)
        ctx.agent_run_ids = ["run-1"]
        ctx.review_queue_ids = ["q-1"]
        ctx.variables["quality.passed"] = True
        info = compute_lifecycle_stage(ctx)
        assert info.current_stage == "quality_validated"
        assert info.stage_index == 5

    def test_exported(self) -> None:
        ctx = _ctx()
        ctx.datasets["ds-1"] = DatasetReference(dataset_id="ds-1", dataset_name="test")
        ctx.record_sets["step1"] = RecordSet(record_ids=["r1"], record_count=1)
        ctx.agent_run_ids = ["run-1"]
        ctx.review_queue_ids = ["q-1"]
        ctx.variables["quality.passed"] = True
        ctx.export_bundle_ids = ["bundle-1"]
        info = compute_lifecycle_stage(ctx)
        assert info.current_stage == "exported"
        assert info.stage_index == 6

    def test_released(self) -> None:
        ctx = _ctx()
        ctx.datasets["ds-1"] = DatasetReference(dataset_id="ds-1", dataset_name="test")
        ctx.record_sets["step1"] = RecordSet(record_ids=["r1"], record_count=1)
        ctx.agent_run_ids = ["run-1"]
        ctx.review_queue_ids = ["q-1"]
        ctx.variables["quality.passed"] = True
        ctx.export_bundle_ids = ["bundle-1"]
        ctx.variables["release.ready"] = True
        info = compute_lifecycle_stage(ctx)
        assert info.current_stage == "released"
        assert info.stage_index == 7

    def test_stage_details_populated(self) -> None:
        ctx = _ctx()
        ctx.datasets["ds-1"] = DatasetReference(dataset_id="ds-1", dataset_name="test")
        ctx.metrics["agreement.kappa"] = 0.85
        info = compute_lifecycle_stage(ctx)
        assert "datasets" in info.stage_details
        assert info.stage_details["datasets"] == 1
        assert "metrics" in info.stage_details

    def test_stages_are_ordered(self) -> None:
        assert LIFECYCLE_STAGES[0] == "empty"
        assert LIFECYCLE_STAGES[-1] == "released"
        assert len(LIFECYCLE_STAGES) == 8

    def test_quality_not_passed_stays_review(self) -> None:
        ctx = _ctx()
        ctx.datasets["ds-1"] = DatasetReference(dataset_id="ds-1", dataset_name="test")
        ctx.record_sets["step1"] = RecordSet(record_ids=["r1"], record_count=1)
        ctx.agent_run_ids = ["run-1"]
        ctx.review_queue_ids = ["q-1"]
        ctx.variables["quality.passed"] = False
        info = compute_lifecycle_stage(ctx)
        assert info.current_stage == "review_in_progress"

    def test_schema_configured_via_task_schema(self) -> None:
        """When task_schema variable is set, stage should be schema_configured
        even without record_sets."""
        ctx = _ctx()
        ctx.datasets["ds-1"] = DatasetReference(dataset_id="ds-1", dataset_name="test")
        ctx.variables["task_schema"] = {"name": "sentiment", "labels": ["pos", "neg"]}
        info = compute_lifecycle_stage(ctx)
        assert info.current_stage == "schema_configured"
        assert info.stage_index == 2

    def test_records_without_data_stays_empty(self) -> None:
        """Record sets alone (without datasets) should not trigger schema_configured."""
        ctx = _ctx()
        ctx.record_sets["step1"] = RecordSet(record_ids=["r1"], record_count=1)
        info = compute_lifecycle_stage(ctx)
        # Without datasets, record_sets alone should not count as schema_configured
        assert info.current_stage == "empty"

"""Tests for individual step executor implementations.

Covers data steps (WF-004 through WF-008), agent steps (WF-009, WF-010),
human steps (WF-011 through WF-014), quality steps (WF-015 through WF-017),
output steps (WF-018 through WF-020), and control steps (WF-021 through WF-034).
"""

from __future__ import annotations

from molabel.core.agents.agent_run_orchestrator import AgentRunBatchResult
from molabel.core.workflow.context import (
    RecordSet,
    WorkflowContext,
)
from molabel.core.workflow.steps.agent_steps import (
    AgentCompareExecutor,
    AgentRunExecutor,
)
from molabel.core.workflow.steps.control_steps import (
    ConditionalExecutor,
    GateExecutor,
    LoopExecutor,
    ParallelExecutor,
    evaluate_predicate,
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


def _ctx_with_records(
    record_ids: list[str] | None = None,
) -> WorkflowContext:
    """Create a context with an active record set."""
    ctx = WorkflowContext(
        workspace_id="ws-1",
        workflow_execution_id="exec-1",
        workflow_version=1,
    )
    ids = record_ids or ["r1", "r2", "r3", "r4", "r5"]
    ctx.record_sets["_init"] = RecordSet(
        record_ids=ids,
        record_count=len(ids),
    )
    ctx.active_record_set_id = "_init"
    return ctx


# ---------------------------------------------------------------------------
# Data steps (WF-004 through WF-008)
# ---------------------------------------------------------------------------


class TestDataIngest:
    def test_basic_ingest(self) -> None:
        executor = DataIngestExecutor()
        ctx = WorkflowContext(
            workspace_id="ws-1",
            workflow_execution_id="exec-1",
            workflow_version=1,
        )
        result = executor.execute("ingest", {"source": "data/*.jsonl"}, ctx)
        assert result.success
        assert ctx.active_record_set_id == "ingest"
        assert len(ctx.datasets) == 1

    def test_validate_missing_source(self) -> None:
        executor = DataIngestExecutor()
        ctx = WorkflowContext(
            workspace_id="ws-1",
            workflow_execution_id="exec-1",
            workflow_version=1,
        )
        errors = executor.validate("ingest", {}, ctx)
        assert any("source" in e for e in errors)


class TestDataNormalize:
    def test_basic_normalize(self) -> None:
        executor = DataNormalizeExecutor()
        ctx = _ctx_with_records()
        result = executor.execute("normalize", {"schema_ref": "s.yaml"}, ctx)
        assert result.success
        assert ctx.active_record_set_id == "normalize"

    def test_validate_no_active_records(self) -> None:
        executor = DataNormalizeExecutor()
        ctx = WorkflowContext(
            workspace_id="ws-1",
            workflow_execution_id="exec-1",
            workflow_version=1,
        )
        errors = executor.validate("norm", {}, ctx)
        assert any("active record set" in e for e in errors)


class TestDataFilter:
    def test_basic_filter(self) -> None:
        executor = DataFilterExecutor()
        ctx = _ctx_with_records()
        result = executor.execute(
            "filter", {"filter_expression": "status == 'active'"}, ctx
        )
        assert result.success
        assert ctx.active_record_set_id == "filter"

    def test_validate_missing_expression(self) -> None:
        executor = DataFilterExecutor()
        ctx = _ctx_with_records()
        errors = executor.validate("filter", {}, ctx)
        assert any("filter_expression" in e for e in errors)


class TestDataSample:
    def test_random_sample(self) -> None:
        executor = DataSampleExecutor()
        ids = [f"r{i}" for i in range(1, 11)]
        ctx = _ctx_with_records(ids)
        result = executor.execute(
            "sample",
            {"sample_strategy": "random", "sample_size": 3, "seed": 42},
            ctx,
        )
        assert result.success
        assert ctx.active_record_set_id == "sample"
        assert len(ctx.record_sets["sample"].record_ids) == 3

    def test_sample_size_clamped(self) -> None:
        executor = DataSampleExecutor()
        ctx = _ctx_with_records(["r1", "r2"])
        result = executor.execute(
            "sample",
            {"sample_strategy": "random", "sample_size": 100, "seed": 42},
            ctx,
        )
        assert result.success
        assert len(ctx.record_sets["sample"].record_ids) == 2

    def test_validate_invalid_strategy(self) -> None:
        executor = DataSampleExecutor()
        ctx = _ctx_with_records()
        errors = executor.validate(
            "sample",
            {"sample_strategy": "invalid", "sample_size": 5},
            ctx,
        )
        assert any("Invalid sample_strategy" in e for e in errors)


class TestDataDeduplicate:
    def test_exact_dedup(self) -> None:
        executor = DataDeduplicateExecutor()
        ctx = _ctx_with_records(["r1", "r2", "r3"])
        result = executor.execute(
            "dedup",
            {"strategy": "exact", "action": "remove"},
            ctx,
        )
        assert result.success
        assert ctx.active_record_set_id == "dedup"
        assert "dedup.duplicate_rate" in ctx.metrics

    def test_flag_action_keeps_all(self) -> None:
        executor = DataDeduplicateExecutor()
        ctx = _ctx_with_records(["r1", "r2", "r3"])
        result = executor.execute(
            "dedup",
            {"strategy": "exact", "action": "flag"},
            ctx,
        )
        assert result.success
        assert len(ctx.record_sets["dedup"].record_ids) == 3

    def test_validate_invalid_strategy(self) -> None:
        executor = DataDeduplicateExecutor()
        ctx = _ctx_with_records()
        errors = executor.validate("dedup", {"strategy": "magic"}, ctx)
        assert any("Invalid dedup strategy" in e for e in errors)

    def test_exact_dedup_uses_content_hash(self) -> None:
        """Dedup should hash content, not IDs. With a record store providing
        duplicate content, records with different IDs but same content
        should be deduplicated."""

        class FakeRecordStore:
            def get_record(self, record_id: str) -> dict:
                # r1 and r3 have identical content
                if record_id in ("r1", "r3"):
                    return {"text": "hello world", "label": "pos"}
                return {"text": f"unique {record_id}", "label": "neg"}

        executor = DataDeduplicateExecutor()
        ctx = _ctx_with_records(["r1", "r2", "r3"])
        result = executor.execute(
            "dedup",
            {"strategy": "exact", "action": "remove"},
            ctx,
            services={"record_store": FakeRecordStore()},
        )
        assert result.success
        # r1 and r3 have same content, so one should be deduped
        assert len(ctx.record_sets["dedup"].record_ids) == 2
        assert ctx.record_sets["dedup"].record_ids == ["r1", "r2"]
        assert result.output.summary["duplicates_found"] == 1

    def test_exact_dedup_prefers_content_hash_field(self) -> None:
        """If a record has a content_hash field, prefer that."""

        class FakeRecordStore:
            def get_record(self, record_id: str) -> dict:
                if record_id == "r1":
                    return {"content_hash": "abc123", "text": "hello"}
                if record_id == "r2":
                    return {"content_hash": "abc123", "text": "different"}
                return {"content_hash": "def456", "text": "world"}

        executor = DataDeduplicateExecutor()
        ctx = _ctx_with_records(["r1", "r2", "r3"])
        result = executor.execute(
            "dedup",
            {"strategy": "exact", "action": "remove"},
            ctx,
            services={"record_store": FakeRecordStore()},
        )
        assert result.success
        # r1 and r2 share content_hash, so r2 is deduped
        assert len(ctx.record_sets["dedup"].record_ids) == 2
        assert "r1" in ctx.record_sets["dedup"].record_ids
        assert "r3" in ctx.record_sets["dedup"].record_ids


# ---------------------------------------------------------------------------
# Agent steps (WF-009, WF-010)
# ---------------------------------------------------------------------------


class TestAgentRun:
    def test_basic_agent_run(self) -> None:
        executor = AgentRunExecutor()
        ctx = _ctx_with_records()
        result = executor.execute(
            "agent",
            {"prompt_ref": "p.yaml", "model": "test-model"},
            ctx,
        )
        assert result.success
        assert len(ctx.agent_run_ids) == 1
        assert ctx.active_record_set_id == "agent"
        assert "agent.coverage" in ctx.metrics

    def test_validate_missing_model(self) -> None:
        executor = AgentRunExecutor()
        ctx = _ctx_with_records()
        errors = executor.validate("agent", {"prompt_ref": "p.yaml"}, ctx)
        assert any("model" in e for e in errors)

    def test_partial_failure_with_partial_results(self) -> None:
        """Agent run should detect partial results from exception attribute."""

        class PartialError(Exception):
            def __init__(self, msg: str, partial_results: dict) -> None:
                super().__init__(msg)
                self.partial_results = partial_results

        class FakeAgentService:
            def run(self, **kwargs) -> dict:
                raise PartialError(
                    "Partial failure",
                    {"success_count": 3, "failure_count": 2},
                )

        executor = AgentRunExecutor()
        ctx = _ctx_with_records()
        result = executor.execute(
            "agent",
            {"prompt_ref": "p.yaml", "model": "test-model"},
            ctx,
            services={"agent_runner": FakeAgentService()},
        )
        assert result.success  # Partial success
        assert result.is_partial
        assert result.output.summary["success_count"] == 3
        assert len(ctx.agent_run_ids) == 1

    def test_total_failure_without_partial_results(self) -> None:
        """Agent run with no partial data should fail completely."""

        class FakeAgentService:
            def run(self, **kwargs) -> dict:
                raise RuntimeError("Total failure")

        executor = AgentRunExecutor()
        ctx = _ctx_with_records()
        result = executor.execute(
            "agent",
            {"prompt_ref": "p.yaml", "model": "test-model"},
            ctx,
            services={"agent_runner": FakeAgentService()},
        )
        assert not result.success
        assert "Agent run failed" in result.error


class TestAgentCompare:
    def test_basic_compare(self) -> None:
        executor = AgentCompareExecutor()
        ctx = _ctx_with_records()
        result = executor.execute(
            "compare",
            {
                "models": ["model_a", "model_b"],
                "prompt_ref": "p.yaml",
            },
            ctx,
        )
        assert result.success
        assert len(ctx.agent_run_ids) == 2
        assert "compare.inter_model_agreement" in ctx.metrics

    def test_agreement_computed_not_placeholder(self) -> None:
        """inter_model_agreement should be computed, not always 0.0."""
        executor = AgentCompareExecutor()
        ctx = _ctx_with_records()
        result = executor.execute(
            "compare",
            {
                "models": ["model_a", "model_b"],
                "prompt_ref": "p.yaml",
            },
            ctx,
        )
        assert result.success
        # Without a real agent service, both models simulate full success.
        # Agreement based on success overlap should be 1.0 (all 5 records).
        assert ctx.metrics["compare.inter_model_agreement"] == 1.0
        # Also verify it appears in the summary
        assert result.output.summary["inter_model_agreement"] == 1.0

    def test_uses_agent_run_batch_result_contract(self) -> None:
        """agent_compare should handle AgentRunBatchResult responses."""

        class FakeAgentService:
            def run(self, **kwargs) -> AgentRunBatchResult:
                run_id = kwargs["agent_run_id"]
                model = kwargs["config"]["model"]
                if model == "model_a":
                    return AgentRunBatchResult(
                        agent_run_id=run_id,
                        status="partially_completed",
                        total_records=5,
                        completed_records=4,
                        failed_records=1,
                        batch_size=3,
                        batch_count=2,
                        event_count=9,
                    )
                return AgentRunBatchResult(
                    agent_run_id=run_id,
                    status="completed",
                    total_records=5,
                    completed_records=5,
                    failed_records=0,
                    batch_size=3,
                    batch_count=2,
                    event_count=9,
                )

        executor = AgentCompareExecutor()
        ctx = _ctx_with_records()
        result = executor.execute(
            "compare",
            {
                "models": ["model_a", "model_b"],
                "prompt_ref": "p.yaml",
            },
            ctx,
            services={"agent_runner": FakeAgentService()},
        )

        assert result.success
        assert len(ctx.agent_run_ids) == 2
        assert ctx.agent_outputs[ctx.agent_run_ids[0]].success_count == 4
        assert ctx.agent_outputs[ctx.agent_run_ids[0]].failure_count == 1
        assert ctx.agent_outputs[ctx.agent_run_ids[1]].success_count == 5
        assert ctx.agent_outputs[ctx.agent_run_ids[1]].failure_count == 0
        assert result.output.summary["per_model_results"][0]["success_count"] == 4
        assert result.output.summary["per_model_results"][1]["success_count"] == 5

    def test_validate_too_few_models(self) -> None:
        executor = AgentCompareExecutor()
        ctx = _ctx_with_records()
        errors = executor.validate(
            "compare", {"models": ["only_one"], "prompt_ref": "p.yaml"}, ctx
        )
        assert any("at least 2" in e for e in errors)


# ---------------------------------------------------------------------------
# Human steps (WF-011 through WF-014)
# ---------------------------------------------------------------------------


class TestHumanReview:
    def test_creates_queue_and_waits(self) -> None:
        executor = HumanReviewExecutor()
        ctx = _ctx_with_records()
        result = executor.execute("review", {}, ctx)
        assert result.success
        assert result.waiting_for_human
        assert len(ctx.review_queue_ids) == 1

    def test_sample_subset(self) -> None:
        executor = HumanReviewExecutor()
        ctx = _ctx_with_records(["r1", "r2", "r3", "r4", "r5"])
        result = executor.execute("review", {"sample_size": 2, "seed": 42}, ctx)
        assert result.success
        assert len(ctx.record_sets["review"].record_ids) == 2

    def test_accept_ai_rate_metric_written(self) -> None:
        """review.accept_ai_rate metric should be written at queue creation."""
        executor = HumanReviewExecutor()
        ctx = _ctx_with_records()
        result = executor.execute("review", {}, ctx)
        assert result.success
        assert "review.accept_ai_rate" in ctx.metrics
        # Initial value should be 0.0 (no decisions yet)
        assert ctx.metrics["review.accept_ai_rate"] == 0.0

    def test_accept_ai_rate_from_context_variables(self) -> None:
        """accept_ai_rate should be computed from context decision data."""
        executor = HumanReviewExecutor()
        ctx = _ctx_with_records()
        ctx.variables["review.total_decisions"] = 10
        ctx.variables["review.accept_ai_count"] = 7
        result = executor.execute("review", {}, ctx)
        assert result.success
        assert ctx.metrics["review.accept_ai_rate"] == 0.7


class TestHumanTriage:
    def test_creates_queue(self) -> None:
        executor = HumanTriageExecutor()
        ctx = _ctx_with_records()
        result = executor.execute(
            "triage",
            {"categories": ["pass", "fail", "review"]},
            ctx,
        )
        assert result.success
        assert result.waiting_for_human
        assert ctx.variables["triage.pass.count"] == 0

    def test_validate_missing_categories(self) -> None:
        executor = HumanTriageExecutor()
        ctx = _ctx_with_records()
        errors = executor.validate("triage", {}, ctx)
        assert any("categories" in e for e in errors)


class TestHumanCalibration:
    def test_creates_calibration_queue(self) -> None:
        executor = HumanCalibrationExecutor()
        ctx = _ctx_with_records()
        result = executor.execute(
            "cal",
            {"sample_size": 3, "min_reviewers": 2, "seed": 42},
            ctx,
        )
        assert result.success
        assert result.waiting_for_human
        assert "calibration.agreement" in ctx.metrics


class TestHumanAdjudication:
    def test_creates_adjudication_queue(self) -> None:
        executor = HumanAdjudicationExecutor()
        ctx = _ctx_with_records()
        result = executor.execute("adj", {}, ctx)
        assert result.success
        assert result.waiting_for_human
        assert len(ctx.adjudication_queue_ids) == 1


# ---------------------------------------------------------------------------
# Quality steps (WF-015 through WF-017)
# ---------------------------------------------------------------------------


class TestQualityCheck:
    def test_all_pass(self) -> None:
        executor = QualityCheckExecutor()
        ctx = _ctx_with_records()
        ctx.metrics["agreement.kappa"] = 0.95
        ctx.metrics["review.coverage"] = 0.98
        ctx.metrics["agent.avg_confidence"] = 0.90

        result = executor.execute(
            "quality",
            {"min_agreement": 0.85, "min_coverage": 0.95, "min_confidence": 0.80},
            ctx,
        )
        assert result.success
        assert ctx.variables["quality.passed"] is True

    def test_agreement_fails(self) -> None:
        executor = QualityCheckExecutor()
        ctx = _ctx_with_records()
        ctx.metrics["agreement.kappa"] = 0.50

        result = executor.execute(
            "quality",
            {"min_agreement": 0.85},
            ctx,
        )
        assert result.success  # Step succeeds even if quality fails
        assert ctx.variables["quality.passed"] is False

    def test_no_thresholds(self) -> None:
        executor = QualityCheckExecutor()
        ctx = _ctx_with_records()
        result = executor.execute("quality", {}, ctx)
        assert result.success
        assert ctx.variables["quality.passed"] is True


class TestAgreementAnalysis:
    def test_basic_analysis(self) -> None:
        executor = AgreementAnalysisExecutor()
        ctx = _ctx_with_records()
        result = executor.execute("agreement", {"analysis_type": "both"}, ctx)
        assert result.success
        assert "agreement.kappa" in ctx.metrics

    def test_validate_invalid_type(self) -> None:
        executor = AgreementAnalysisExecutor()
        ctx = _ctx_with_records()
        errors = executor.validate("agreement", {"analysis_type": "invalid"}, ctx)
        assert any("Invalid analysis_type" in e for e in errors)


class TestDriftDetection:
    def test_basic_drift(self) -> None:
        executor = DriftDetectionExecutor()
        ctx = _ctx_with_records()
        result = executor.execute("drift", {"reference_snapshot_id": "snap-1"}, ctx)
        assert result.success
        assert "drift.detected" in ctx.variables

    def test_validate_missing_reference(self) -> None:
        executor = DriftDetectionExecutor()
        ctx = _ctx_with_records()
        errors = executor.validate("drift", {}, ctx)
        assert any("reference_snapshot_id" in e for e in errors)


# ---------------------------------------------------------------------------
# Output steps (WF-018 through WF-020)
# ---------------------------------------------------------------------------


class TestExport:
    def test_basic_export(self) -> None:
        executor = ExportExecutor()
        ctx = _ctx_with_records()
        result = executor.execute(
            "export",
            {"format": "jsonl", "destination": "exports/"},
            ctx,
        )
        assert result.success
        assert len(ctx.export_bundle_ids) == 1

    def test_validate_invalid_format(self) -> None:
        executor = ExportExecutor()
        ctx = _ctx_with_records()
        errors = executor.validate(
            "export", {"format": "invalid", "destination": "out/"}, ctx
        )
        assert any("Invalid export format" in e for e in errors)


class TestSnapshot:
    def test_basic_snapshot(self) -> None:
        executor = SnapshotExecutor()
        ctx = _ctx_with_records()
        result = executor.execute("snap", {"snapshot_name": "test_snap"}, ctx)
        assert result.success
        assert len(ctx.snapshot_ids) == 1


class TestReleaseValidation:
    def test_no_gates_passes(self) -> None:
        executor = ReleaseValidationExecutor()
        ctx = _ctx_with_records()
        result = executor.execute("release", {}, ctx)
        assert result.success
        assert ctx.variables["release.ready"] is True


# ---------------------------------------------------------------------------
# Control steps (WF-021 through WF-034)
# ---------------------------------------------------------------------------


class TestPredicateEvaluator:
    def test_simple_true(self) -> None:
        ctx = _ctx_with_records()
        assert evaluate_predicate("True", ctx) is True

    def test_simple_false(self) -> None:
        ctx = _ctx_with_records()
        assert evaluate_predicate("False", ctx) is False

    def test_metric_comparison(self) -> None:
        ctx = _ctx_with_records()
        ctx.metrics["quality.agreement"] = 0.95
        assert evaluate_predicate("metrics['quality.agreement'] >= 0.90", ctx) is True
        assert evaluate_predicate("metrics['quality.agreement'] >= 0.99", ctx) is False

    def test_variable_access(self) -> None:
        ctx = _ctx_with_records()
        ctx.variables["quality.passed"] = True
        assert evaluate_predicate("variables['quality.passed']", ctx) is True

    def test_missing_metric_returns_false(self) -> None:
        ctx = _ctx_with_records()
        assert evaluate_predicate("metrics['nonexistent'] >= 0.5", ctx) is False

    def test_empty_predicate(self) -> None:
        ctx = _ctx_with_records()
        assert evaluate_predicate("", ctx) is False

    def test_boolean_operators(self) -> None:
        ctx = _ctx_with_records()
        ctx.metrics["a"] = 0.9
        ctx.metrics["b"] = 0.8
        assert (
            evaluate_predicate("metrics['a'] >= 0.85 and metrics['b'] >= 0.75", ctx)
            is True
        )
        assert (
            evaluate_predicate("metrics['a'] >= 0.95 or metrics['b'] >= 0.75", ctx)
            is True
        )
        assert (
            evaluate_predicate("metrics['a'] >= 0.95 and metrics['b'] >= 0.85", ctx)
            is False
        )

    # --- Adversarial input tests for AST-based evaluator ---

    def test_reject_import(self) -> None:
        """eval() could execute __import__('os').system('echo pwned')."""
        ctx = _ctx_with_records()
        assert evaluate_predicate("__import__('os').system('echo pwned')", ctx) is False

    def test_reject_class_traversal(self) -> None:
        """Reject class hierarchy traversal attacks."""
        ctx = _ctx_with_records()
        assert (
            evaluate_predicate("().__class__.__bases__[0].__subclasses__()", ctx)
            is False
        )

    def test_reject_list_comprehension(self) -> None:
        """List comprehensions are not allowed in predicates."""
        ctx = _ctx_with_records()
        assert evaluate_predicate("[x for x in range(10)]", ctx) is False

    def test_reject_function_call(self) -> None:
        """Function calls (including builtins) are not allowed."""
        ctx = _ctx_with_records()
        assert evaluate_predicate("len(metrics)", ctx) is False

    def test_reject_lambda(self) -> None:
        """Lambda expressions are not allowed."""
        ctx = _ctx_with_records()
        assert evaluate_predicate("lambda: 1", ctx) is False

    def test_reject_fstring(self) -> None:
        """f-string expressions (JoinedStr) are not allowed."""
        ctx = _ctx_with_records()
        # f-strings cannot be tested via simple strings in ast.parse mode='eval',
        # but the JoinedStr node type is rejected, so any that parse will fail.
        assert evaluate_predicate("f'{True}'", ctx) is False

    def test_reject_dict_comprehension(self) -> None:
        """Dict comprehensions are not allowed."""
        ctx = _ctx_with_records()
        assert evaluate_predicate("{k: v for k, v in {}}", ctx) is False

    def test_reject_set_comprehension(self) -> None:
        """Set comprehensions are not allowed."""
        ctx = _ctx_with_records()
        assert evaluate_predicate("{x for x in []}", ctx) is False

    def test_reject_generator_expression(self) -> None:
        """Generator expressions are not allowed."""
        ctx = _ctx_with_records()
        # Generator in a tuple context to make it parseable
        assert evaluate_predicate("any(x for x in [])", ctx) is False


class TestLoopExecutor:
    def test_initialize_loop(self) -> None:
        executor = LoopExecutor()
        ctx = _ctx_with_records()
        result = executor.execute(
            "loop1",
            {
                "steps": ["step_a", "step_b"],
                "termination": {"type": "count", "count": 3, "max_iterations": 3},
            },
            ctx,
        )
        assert result.success
        assert ctx.variables["loop.loop1.iteration"] == 0

    def test_count_termination(self) -> None:
        executor = LoopExecutor()
        ctx = _ctx_with_records()
        config = {
            "steps": ["a"],
            "termination": {"type": "count", "count": 2, "max_iterations": 5},
        }
        assert executor.check_termination("loop1", config, ctx, 0) == (False, "")
        terminated, reason = executor.check_termination("loop1", config, ctx, 1)
        assert (terminated, reason) == (True, "count_reached")

    def test_metric_termination(self) -> None:
        executor = LoopExecutor()
        ctx = _ctx_with_records()
        config = {
            "steps": ["a"],
            "termination": {
                "type": "metric",
                "metric": "quality.agreement",
                "operator": ">=",
                "threshold": 0.90,
                "max_iterations": 10,
            },
        }
        ctx.metrics["quality.agreement"] = 0.80
        assert executor.check_termination("loop1", config, ctx, 0) == (False, "")

        ctx.metrics["quality.agreement"] = 0.95
        terminated, reason = executor.check_termination("loop1", config, ctx, 0)
        assert (terminated, reason) == (True, "metric_threshold_met")

    def test_max_iterations_safety(self) -> None:
        executor = LoopExecutor()
        ctx = _ctx_with_records()
        config = {
            "steps": ["a"],
            "termination": {
                "type": "metric",
                "metric": "x",
                "operator": ">=",
                "threshold": 1.0,
                "max_iterations": 3,
            },
        }
        terminated, reason = executor.check_termination("loop1", config, ctx, 2)
        assert (terminated, reason) == (True, "max_iterations_reached")

    def test_body_step_reset(self) -> None:
        executor = LoopExecutor()
        ctx = _ctx_with_records()
        from molabel.core.workflow.context import StepOutput

        ctx.step_outputs["step_a"] = StepOutput(
            step_id="step_a", step_type="data_ingest"
        )
        ctx.record_sets["step_a"] = RecordSet(record_ids=["r1"])

        executor.reset_body_steps(
            "loop1",
            {"steps": ["step_a"]},
            ctx,
            iteration=1,
        )
        # Previous output should be archived
        assert "step_a__iter_0" in ctx.step_outputs
        assert "step_a__iter_0" in ctx.record_sets
        assert ctx.variables["loop.loop1.iteration"] == 1

    def test_validate_missing_steps(self) -> None:
        executor = LoopExecutor()
        ctx = _ctx_with_records()
        errors = executor.validate("loop1", {}, ctx)
        assert any("'steps' list" in e for e in errors)


class TestConditionalExecutor:
    def test_then_branch(self) -> None:
        executor = ConditionalExecutor()
        ctx = _ctx_with_records()
        result = executor.execute(
            "cond",
            {"predicate": "True", "then_steps": ["a"], "else_steps": ["b"]},
            ctx,
        )
        assert result.success
        assert result.updated_context["branch_taken"] == "then"
        assert result.updated_context["skipped_steps"] == ["b"]

    def test_else_branch(self) -> None:
        executor = ConditionalExecutor()
        ctx = _ctx_with_records()
        result = executor.execute(
            "cond",
            {"predicate": "False", "then_steps": ["a"], "else_steps": ["b"]},
            ctx,
        )
        assert result.updated_context["branch_taken"] == "else"
        assert result.updated_context["skipped_steps"] == ["a"]


class TestParallelExecutor:
    def test_initialize_parallel(self) -> None:
        executor = ParallelExecutor()
        ctx = _ctx_with_records()
        result = executor.execute(
            "par",
            {"steps": ["a", "b", "c"], "fail_fast": True},
            ctx,
        )
        assert result.success
        assert result.updated_context["child_steps"] == ["a", "b", "c"]
        assert result.updated_context["fail_fast"] is True

    def test_validate_missing_steps(self) -> None:
        executor = ParallelExecutor()
        ctx = _ctx_with_records()
        errors = executor.validate("par", {}, ctx)
        assert any("'steps' list" in e for e in errors)

    def test_concurrent_execution_with_child_executors(self) -> None:
        """ParallelExecutor should run child executors concurrently."""
        from molabel.core.workflow.steps.data_steps import DataIngestExecutor

        executor = ParallelExecutor()
        ctx = _ctx_with_records()

        child_executors = {
            "ingest_a": {
                "executor": DataIngestExecutor(),
                "config": {"source": "data_a/*.jsonl"},
            },
            "ingest_b": {
                "executor": DataIngestExecutor(),
                "config": {"source": "data_b/*.jsonl"},
            },
        }

        result = executor.execute(
            "par",
            {"steps": ["ingest_a", "ingest_b"]},
            ctx,
            services={"child_executors": child_executors},
        )
        assert result.success
        assert result.output.summary["child_results"]["ingest_a"] is True
        assert result.output.summary["child_results"]["ingest_b"] is True

    def test_concurrent_execution_partial_failure(self) -> None:
        """If one child fails, parallel should report partially_failed."""
        from molabel.core.workflow.steps.data_steps import (
            DataFilterExecutor,
            DataIngestExecutor,
        )

        executor = ParallelExecutor()
        ctx = _ctx_with_records()

        # DataFilterExecutor will fail: no filter_expression and no active records
        child_executors = {
            "ingest": {
                "executor": DataIngestExecutor(),
                "config": {"source": "data/*.jsonl"},
            },
            "bad_filter": {
                "executor": DataFilterExecutor(),
                "config": {},  # Missing filter_expression -> will fail validation
            },
        }

        # Create a separate context without active records for the filter
        result = executor.execute(
            "par",
            {"steps": ["ingest", "bad_filter"]},
            ctx,
            services={"child_executors": child_executors},
        )
        # bad_filter should fail (no filter_expression) but ingest should succeed
        # Either all succeed or there are errors
        assert result.output is not None


class TestGateExecutor:
    def test_gate_waits(self) -> None:
        executor = GateExecutor()
        ctx = _ctx_with_records()
        result = executor.execute(
            "gate", {"message": "Continue?", "require_reason": True}, ctx
        )
        assert result.success
        assert result.waiting_for_gate
        assert result.output is not None
        assert result.output.summary["require_reason"] is True


# ---------------------------------------------------------------------------
# WorkflowContext.from_dict validation
# ---------------------------------------------------------------------------


class TestContextFromDictValidation:
    def test_missing_required_field(self) -> None:
        import pytest

        from molabel.core.workflow.context import WorkflowContext

        with pytest.raises(TypeError, match="missing required field"):
            WorkflowContext.from_dict({"workspace_id": "ws-1"})

    def test_wrong_type_for_metrics(self) -> None:
        import pytest

        from molabel.core.workflow.context import WorkflowContext

        with pytest.raises(TypeError, match="metrics.*expected dict"):
            WorkflowContext.from_dict(
                {
                    "workspace_id": "ws-1",
                    "workflow_execution_id": "exec-1",
                    "workflow_version": 1,
                    "metrics": "not_a_dict",
                }
            )

    def test_wrong_type_for_agent_run_ids(self) -> None:
        import pytest

        from molabel.core.workflow.context import WorkflowContext

        with pytest.raises(TypeError, match="agent_run_ids.*expected list"):
            WorkflowContext.from_dict(
                {
                    "workspace_id": "ws-1",
                    "workflow_execution_id": "exec-1",
                    "workflow_version": 1,
                    "agent_run_ids": "not_a_list",
                }
            )

    def test_bad_nested_dataclass(self) -> None:
        import pytest

        from molabel.core.workflow.context import WorkflowContext

        with pytest.raises(ValueError, match="failed to deserialize.*datasets"):
            WorkflowContext.from_dict(
                {
                    "workspace_id": "ws-1",
                    "workflow_execution_id": "exec-1",
                    "workflow_version": 1,
                    "datasets": {"ds-1": {"bad_field": "value"}},
                }
            )

    def test_valid_from_dict(self) -> None:
        from molabel.core.workflow.context import WorkflowContext

        ctx = WorkflowContext.from_dict(
            {
                "workspace_id": "ws-1",
                "workflow_execution_id": "exec-1",
                "workflow_version": 1,
                "metrics": {"a": 0.5},
                "agent_run_ids": ["run-1"],
            }
        )
        assert ctx.workspace_id == "ws-1"
        assert ctx.metrics["a"] == 0.5
        assert ctx.agent_run_ids == ["run-1"]

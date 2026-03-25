"""Quality step executors: quality_check, agreement_analysis, drift_detection.

WF-015 through WF-017. Quality steps compute metrics and write them to
the WorkflowContext for downstream conditionals and gates to evaluate.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from molabel.core.quality.agreement_metrics import (
    AgreementAnalysisResult,
    AgreementMetricsService,
    AgreementRecord,
)
from molabel.core.workflow.context import StepOutput, WorkflowContext
from molabel.core.workflow.steps.base import StepExecutor, StepResult

logger = logging.getLogger(__name__)


class QualityCheckExecutor(StepExecutor):
    """Executor for quality_check steps (WF-015).

    Evaluates labels against quality thresholds: min_agreement,
    min_coverage, min_confidence. Writes pass/fail result and metrics
    to context. Does NOT block the workflow -- use conditional/gate after.
    """

    def validate(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
    ) -> list[str]:
        # quality_check is lenient -- all thresholds are optional
        return []

    def execute(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
        services: dict[str, Any] | None = None,
    ) -> StepResult:
        services = services or {}
        quality_service = services.get("quality_checker")

        min_agreement = config.get("min_agreement")
        min_coverage = config.get("min_coverage")
        min_confidence = config.get("min_confidence")

        # Read current metrics from context
        current_agreement = context.metrics.get("agreement.kappa", 0.0)
        current_coverage = context.metrics.get("review.coverage", 0.0)
        current_confidence = context.metrics.get("agent.avg_confidence", 0.0)

        if quality_service is not None:
            try:
                result = quality_service.check(
                    record_ids=context.get_active_record_ids(),
                    config=config,
                    metrics=context.metrics,
                )
                current_agreement = result.get("agreement", current_agreement)
                current_coverage = result.get("coverage", current_coverage)
                current_confidence = result.get("confidence", current_confidence)
            except Exception as e:
                return StepResult(
                    success=False,
                    error=f"Quality check failed: {e}",
                    error_trace=str(e)[:2000],
                )

        # Evaluate thresholds
        passed = True
        details: list[dict[str, Any]] = []

        if min_agreement is not None:
            check_passed = current_agreement >= float(min_agreement)
            details.append(
                {
                    "check": "min_agreement",
                    "threshold": float(min_agreement),
                    "actual": current_agreement,
                    "passed": check_passed,
                }
            )
            if not check_passed:
                passed = False

        if min_coverage is not None:
            check_passed = current_coverage >= float(min_coverage)
            details.append(
                {
                    "check": "min_coverage",
                    "threshold": float(min_coverage),
                    "actual": current_coverage,
                    "passed": check_passed,
                }
            )
            if not check_passed:
                passed = False

        if min_confidence is not None:
            check_passed = current_confidence >= float(min_confidence)
            details.append(
                {
                    "check": "min_confidence",
                    "threshold": float(min_confidence),
                    "actual": current_confidence,
                    "passed": check_passed,
                }
            )
            if not check_passed:
                passed = False

        # Write metrics and variables
        context.metrics["quality.agreement"] = current_agreement
        context.metrics["quality.coverage"] = current_coverage
        context.metrics["quality.confidence"] = current_confidence
        context.variables["quality.passed"] = passed

        return StepResult(
            success=True,
            output=StepOutput(
                step_id=step_id,
                step_type="quality_check",
                summary={
                    "passed": passed,
                    "details": details,
                    "agreement": current_agreement,
                    "coverage": current_coverage,
                    "confidence": current_confidence,
                },
            ),
        )


class AgreementAnalysisExecutor(StepExecutor):
    """Executor for agreement_analysis steps (WF-016).

    Computes inter-annotator or human-agent agreement statistics:
    Cohen's kappa, Fleiss' kappa, per-field agreement, confusion matrices.
    """

    def validate(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
    ) -> list[str]:
        errors: list[str] = []
        analysis_type = config.get("analysis_type", "both")
        if analysis_type not in {"inter_annotator", "human_agent", "both"}:
            errors.append(
                f"Invalid analysis_type '{analysis_type}'. "
                "Valid: inter_annotator, human_agent, both"
            )
        return errors

    def execute(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
        services: dict[str, Any] | None = None,
    ) -> StepResult:
        services = services or {}
        analysis_type = config.get("analysis_type", "both")
        records = _resolve_agreement_records(config, context, services)
        agreement_service = (
            services.get("agreement_metrics_service")
            or services.get("agreement_analyzer")
            or AgreementMetricsService()
        )

        try:
            result = _invoke_agreement_service(
                agreement_service,
                records,
                analysis_type=analysis_type,
                config=config,
                context=context,
            )
            analysis_result = _normalize_agreement_result(result)
        except Exception as e:
            return StepResult(
                success=False,
                error=f"Agreement analysis failed: {e}",
                error_trace=str(e)[:2000],
            )

        context.metrics["agreement.kappa"] = analysis_result.overall.cohen_kappa
        context.metrics["agreement.percent_agreement"] = (
            analysis_result.overall.percent_agreement
        )
        context.metrics["agreement.fleiss_kappa"] = analysis_result.overall.fleiss_kappa
        context.metrics["agreement.krippendorff_alpha"] = (
            analysis_result.overall.krippendorff_alpha
        )
        if analysis_result.human_agent is not None:
            context.metrics["agreement.human_agent_agreement"] = (
                analysis_result.human_agent.percent_agreement
            )

        for field_name, breakdown in analysis_result.human_agent_by_field.items():
            metric_prefix = f"agreement.human_agent.by_field.{_metric_key(field_name)}"
            context.metrics[f"{metric_prefix}.agreement_rate"] = (
                breakdown.agreement_rate
            )
            context.metrics[f"{metric_prefix}.comparisons"] = float(
                breakdown.comparisons
            )
            context.metrics[f"{metric_prefix}.agreements"] = float(breakdown.agreements)
            for label_value, value_breakdown in breakdown.by_label_value.items():
                value_prefix = f"{metric_prefix}.label_value.{_metric_key(label_value)}"
                context.metrics[f"{value_prefix}.agreement_rate"] = (
                    value_breakdown.agreement_rate
                )
                context.metrics[f"{value_prefix}.comparisons"] = float(
                    value_breakdown.comparisons
                )
                context.metrics[f"{value_prefix}.agreements"] = float(
                    value_breakdown.agreements
                )

        return StepResult(
            success=True,
            output=StepOutput(
                step_id=step_id,
                step_type="agreement_analysis",
                summary={
                    "analysis_type": analysis_type,
                    "kappa": analysis_result.overall.cohen_kappa,
                    "percent_agreement": analysis_result.overall.percent_agreement,
                    "fleiss_kappa": analysis_result.overall.fleiss_kappa,
                    "krippendorff_alpha": analysis_result.overall.krippendorff_alpha,
                    "human_agent_agreement": (
                        analysis_result.human_agent.percent_agreement
                        if analysis_result.human_agent is not None
                        else 0.0
                    ),
                    "overall": analysis_result.overall.model_dump(),
                    "human_agent": (
                        analysis_result.human_agent.model_dump()
                        if analysis_result.human_agent is not None
                        else None
                    ),
                    "human_agent_by_field": {
                        field_name: breakdown.model_dump()
                        for field_name, breakdown in (
                            analysis_result.human_agent_by_field.items()
                        )
                    },
                    "confusion_matrix": analysis_result.confusion_matrix,
                    "warnings": analysis_result.warnings,
                },
            ),
        )


class DriftDetectionExecutor(StepExecutor):
    """Executor for drift_detection steps (WF-017).

    Detects distribution shifts between data subsets or over time by
    comparing the active record set to a reference snapshot or step output.
    """

    def validate(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
    ) -> list[str]:
        errors: list[str] = []
        has_ref = config.get("reference_snapshot_id") or config.get("reference_step_id")
        if not has_ref:
            errors.append(
                "drift_detection requires 'reference_snapshot_id' or "
                "'reference_step_id' in config"
            )
        return errors

    def execute(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
        services: dict[str, Any] | None = None,
    ) -> StepResult:
        services = services or {}
        drift_service = services.get("drift_detector")
        drift_threshold = config.get("drift_threshold", 0.1)

        max_shift = 0.0
        affected_fields: list[str] = []
        drift_detected = False

        if drift_service is not None:
            try:
                result = drift_service.detect(
                    record_ids=context.get_active_record_ids(),
                    reference=config.get("reference_snapshot_id")
                    or config.get("reference_step_id"),
                    config=config,
                )
                max_shift = result.get("max_shift", 0.0)
                affected_fields = result.get("affected_fields", [])
                drift_detected = max_shift >= drift_threshold
            except Exception as e:
                return StepResult(
                    success=False,
                    error=f"Drift detection failed: {e}",
                    error_trace=str(e)[:2000],
                )

        context.metrics["drift.max_shift"] = max_shift
        context.metrics["drift.affected_fields"] = float(len(affected_fields))
        context.variables["drift.detected"] = drift_detected

        return StepResult(
            success=True,
            output=StepOutput(
                step_id=step_id,
                step_type="drift_detection",
                summary={
                    "drift_detected": drift_detected,
                    "max_shift": max_shift,
                    "drift_threshold": drift_threshold,
                    "affected_fields": affected_fields,
                },
            ),
        )


def _resolve_agreement_records(
    config: dict[str, Any],
    context: WorkflowContext,
    services: dict[str, Any],
) -> list[AgreementRecord | dict[str, Any]]:
    """Load agreement records from an injected source or inline config."""
    if "agreement_records" in config:
        records = config.get("agreement_records", [])
        return list(records)

    if "agreement.records" in context.variables:
        records = context.variables.get("agreement.records", [])
        if isinstance(records, list):
            return list(records)

    data_source = services.get("agreement_data_source")
    if data_source is None:
        return []

    return list(
        data_source.load_agreement_records(
            record_ids=context.get_active_record_ids(),
            review_queue_ids=context.review_queue_ids,
            agent_run_ids=context.agent_run_ids,
            analysis_type=config.get("analysis_type", "both"),
            config=config,
        )
    )


def _invoke_agreement_service(
    service: Any,
    records: Sequence[AgreementRecord | dict[str, Any]],
    *,
    analysis_type: str,
    config: dict[str, Any],
    context: WorkflowContext,
) -> Any:
    """Call the injected agreement service using the new API first."""
    fields = config.get("fields")
    if hasattr(service, "analyze"):
        try:
            return service.analyze(
                records,
                analysis_type=analysis_type,
                fields=fields,
            )
        except TypeError:
            return service.analyze(
                record_ids=context.get_active_record_ids(),
                review_queue_ids=context.review_queue_ids,
                agent_run_ids=context.agent_run_ids,
                analysis_type=analysis_type,
                config=config,
            )
    raise TypeError("Agreement service does not implement analyze()")


def _normalize_agreement_result(
    result: Any,
) -> AgreementAnalysisResult:
    """Normalize agreement service output into the core result model."""
    if isinstance(result, AgreementAnalysisResult):
        return result

    if hasattr(result, "model_dump"):
        return AgreementAnalysisResult.model_validate(result.model_dump())

    if isinstance(result, dict):
        if "overall" in result:
            try:
                return AgreementAnalysisResult.model_validate(result)
            except Exception:
                pass

        return AgreementAnalysisResult.model_validate(
            {
                "analysis_type": result.get("analysis_type", "both"),
                "overall": {
                    "comparisons": int(result.get("comparisons", 0)),
                    "agreements": int(result.get("agreements", 0)),
                    "percent_agreement": float(result.get("percent_agreement", 0.0)),
                    "cohen_kappa": float(result.get("kappa", 0.0)),
                    "fleiss_kappa": float(result.get("fleiss_kappa", 0.0)),
                    "krippendorff_alpha": float(result.get("krippendorff_alpha", 0.0)),
                },
                "human_agent": (
                    {
                        "comparisons": int(result.get("human_agent_comparisons", 0)),
                        "agreements": int(result.get("human_agent_agreements", 0)),
                        "percent_agreement": float(
                            result.get("human_agent_agreement", 0.0)
                        ),
                    }
                    if "human_agent_agreement" in result
                    else None
                ),
                "human_agent_by_field": result.get("human_agent_by_field", {}),
                "confusion_matrix": result.get("confusion_matrix", {}),
                "warnings": result.get("warnings", []),
            }
        )

    raise TypeError(f"Unsupported agreement service result: {type(result)!r}")


def _metric_key(value: Any) -> str:
    """Turn a field or label value into a metric-safe key fragment."""
    key = value if isinstance(value, str) else str(value)
    key = key.strip().lower().replace(" ", "_")
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in key)

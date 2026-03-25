"""Agent step executors: agent_run and agent_compare.

WF-009, WF-010. These steps interface with the provider system through
service protocols -- they never import concrete provider implementations.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from typing import Any

from molabel.core.agents.agent_run_orchestrator import AgentRunBatchResult
from molabel.core.workflow.context import (
    AgentOutputRef,
    RecordSet,
    StepOutput,
    WorkflowContext,
)
from molabel.core.workflow.steps.base import StepExecutor, StepResult

logger = logging.getLogger(__name__)


class AgentRunExecutor(StepExecutor):
    """Executor for agent_run steps (WF-009).

    Runs an LLM agent on the active record set using the configured
    prompt template and model. Integrates with provider services via
    protocol-based interfaces.
    """

    def validate(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
    ) -> list[str]:
        errors: list[str] = []
        has_prompt = config.get("prompt_ref") or config.get("prompt_template")
        if not has_prompt:
            errors.append(
                "agent_run requires 'prompt_ref' or 'prompt_template' in config"
            )
        if not config.get("model") and not config.get("model_profile_id"):
            errors.append("agent_run requires 'model' or 'model_profile_id' in config")
        if not context.active_record_set_id:
            errors.append("agent_run requires an active record set")
        return errors

    def execute(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
        services: dict[str, Any] | None = None,
    ) -> StepResult:
        services = services or {}
        input_record_ids = context.get_active_record_ids()
        agent_service = services.get("agent_runner")

        agent_run_id = str(uuid.uuid4())
        model_id = config.get("model", config.get("model_profile_id", ""))
        agent_role = config.get("agent_role", "proposer")

        success_count = 0
        failure_count = 0
        run_status = "completed"
        partial_error: str | None = None

        persistence_inputs = _resolve_agent_run_persistence_inputs(config, context)

        if agent_service is not None:
            try:
                call_kwargs: dict[str, Any] = {
                    "record_ids": input_record_ids,
                    "config": config,
                    "agent_run_id": agent_run_id,
                    "workspace_id": context.workspace_id,
                    "services": services,
                    "step_id": step_id,
                    "agent_role": agent_role,
                }
                if persistence_inputs is not None:
                    call_kwargs.update(persistence_inputs)
                result = agent_service.run(
                    **call_kwargs,
                )
                normalized = _normalize_agent_run_result(
                    result,
                    default_total=len(input_record_ids),
                    default_run_id=agent_run_id,
                )
                success_count = normalized.completed_records
                failure_count = normalized.failed_records
                run_status = normalized.status.value
            except Exception as e:
                # Extract partial results from the exception if available
                partial_results = getattr(e, "partial_results", None)
                if partial_results is not None:
                    success_count = int(
                        partial_results.get("completed_records")
                        or partial_results.get("success_count")
                        or 0
                    )
                    failure_count = int(
                        partial_results.get("failed_records")
                        or partial_results.get("failure_count")
                        or max(0, len(input_record_ids) - success_count)
                    )
                    run_status = str(
                        partial_results.get(
                            "status",
                            "partially_completed" if success_count else "failed",
                        )
                    )
                    partial_error = str(e)
                else:
                    # Check context for any outputs written before the exception
                    existing_output = context.agent_outputs.get(agent_run_id)
                    if existing_output is not None:
                        success_count = existing_output.success_count
                        failure_count = (
                            len(input_record_ids) - existing_output.success_count
                        )
                        run_status = (
                            "partially_completed"
                            if success_count and failure_count
                            else "failed"
                        )
                        partial_error = str(e)

                if success_count > 0:
                    # Partial failure: some records were processed
                    return _build_agent_run_step_result(
                        context=context,
                        step_id=step_id,
                        agent_run_id=agent_run_id,
                        model_id=model_id,
                        agent_role=agent_role,
                        total_records=len(input_record_ids),
                        success_count=success_count,
                        failure_count=failure_count,
                        status=run_status,
                        is_partial=True,
                        error=partial_error,
                    )
                return StepResult(
                    success=False,
                    error=f"Agent run failed: {e}",
                    error_trace=str(e)[:2000],
                )
        else:
            # Without an agent service, simulate successful processing
            success_count = len(input_record_ids)
            failure_count = 0
            run_status = "completed"
            logger.info(
                "No agent_runner service for step '%s'; "
                "simulating %d record completions",
                step_id,
                success_count,
            )

        return _build_agent_run_step_result(
            context=context,
            step_id=step_id,
            agent_run_id=agent_run_id,
            model_id=model_id,
            agent_role=agent_role,
            total_records=len(input_record_ids),
            success_count=success_count,
            failure_count=failure_count,
            status=run_status,
        )


class AgentCompareExecutor(StepExecutor):
    """Executor for agent_compare steps (WF-010).

    Runs multiple models/agents on the same record set and collects
    comparison outputs. Produces per-model agent runs and a comparison
    summary.
    """

    def validate(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
    ) -> list[str]:
        errors: list[str] = []
        models = config.get("models", [])
        if not models or not isinstance(models, list) or len(models) < 2:
            errors.append(
                "agent_compare requires 'models' list with at least 2 entries"
            )
        if not config.get("prompt_ref") and not config.get("prompt_template"):
            errors.append(
                "agent_compare requires 'prompt_ref' or 'prompt_template' in config"
            )
        if not context.active_record_set_id:
            errors.append("agent_compare requires an active record set")
        return errors

    def execute(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
        services: dict[str, Any] | None = None,
    ) -> StepResult:
        services = services or {}
        input_record_ids = context.get_active_record_ids()
        models = config.get("models", [])
        agent_service = services.get("agent_runner")

        per_model_results: list[dict[str, Any]] = []
        all_run_ids: list[str] = []

        for model_id in models:
            run_id = str(uuid.uuid4())
            success_count = 0
            failure_count = 0

            if agent_service is not None:
                try:
                    result = agent_service.run(
                        record_ids=input_record_ids,
                        config={**config, "model": model_id},
                        agent_run_id=run_id,
                    )
                    normalized = _normalize_agent_run_result(
                        result,
                        default_total=len(input_record_ids),
                        default_run_id=run_id,
                    )
                    success_count = normalized.completed_records
                    failure_count = normalized.failed_records
                except Exception as e:
                    failure_count = len(input_record_ids)
                    logger.warning("Agent compare: model '%s' failed: %s", model_id, e)
            else:
                success_count = len(input_record_ids)

            context.agent_run_ids.append(run_id)
            context.agent_outputs[run_id] = AgentOutputRef(
                agent_run_id=run_id,
                model_id=model_id,
                record_count=len(input_record_ids),
                success_count=success_count,
                failure_count=failure_count,
            )
            all_run_ids.append(run_id)
            per_model_results.append(
                {
                    "model": model_id,
                    "agent_run_id": run_id,
                    "success_count": success_count,
                    "failure_count": failure_count,
                }
            )

        context.record_sets[step_id] = RecordSet(
            record_ids=list(input_record_ids),
            record_count=len(input_record_ids),
            description=f"Agent compare ({len(models)} models)",
        )
        context.active_record_set_id = step_id

        # Compute inter-model agreement
        inter_model_agreement = _compute_inter_model_agreement(
            input_record_ids,
            all_run_ids,
            per_model_results,
            services,
        )
        context.metrics["compare.inter_model_agreement"] = inter_model_agreement

        return StepResult(
            success=True,
            output=StepOutput(
                step_id=step_id,
                step_type="agent_compare",
                summary={
                    "models": models,
                    "agent_run_ids": all_run_ids,
                    "records_processed": len(input_record_ids),
                    "per_model_results": per_model_results,
                    "inter_model_agreement": inter_model_agreement,
                },
            ),
        )


def _compute_inter_model_agreement(
    record_ids: list[str],
    run_ids: list[str],
    per_model_results: list[dict[str, Any]],
    services: dict[str, Any] | None,
) -> float:
    """Compute inter-model agreement across agent compare results."""
    services = services or {}
    comparison_service = services.get("comparison_service")

    if comparison_service is not None:
        try:
            result = comparison_service.compute_agreement(
                record_ids=record_ids,
                run_ids=run_ids,
            )
            return float(result.get("agreement", 0.0))
        except Exception:
            logger.warning(
                "Comparison service failed; computing agreement from results"
            )

    if not record_ids or not per_model_results:
        return 0.0

    total_models = len(per_model_results)
    if total_models < 2:
        return 1.0

    label_service = services.get("label_reader")
    if label_service is not None:
        try:
            agreed = 0
            for rid in record_ids:
                labels = []
                for model_result in per_model_results:
                    run_id = model_result["agent_run_id"]
                    label = label_service.get_label(run_id=run_id, record_id=rid)
                    labels.append(label)
                if labels and all(lbl == labels[0] for lbl in labels):
                    agreed += 1
            return agreed / len(record_ids) if record_ids else 0.0
        except Exception:
            logger.warning("Label reader failed; using success-based agreement")

    min_success = min(m.get("success_count", 0) for m in per_model_results)
    return min_success / len(record_ids) if record_ids else 0.0


def _resolve_agent_run_persistence_inputs(
    config: dict[str, Any],
    context: WorkflowContext,
) -> dict[str, Any] | None:
    """Resolve IDs required for persisted agent-run orchestration."""

    dataset_id = config.get("dataset_id")
    task_schema_id = config.get("task_schema_id")
    model_profile_id = config.get("model_profile_id")
    runtime_profile_id = config.get("runtime_profile_id")

    if not dataset_id or not task_schema_id or not model_profile_id:
        return None

    try:
        persistence_inputs: dict[str, Any] = {
            "dataset_id": str(uuid.UUID(str(dataset_id))),
            "task_schema_id": str(uuid.UUID(str(task_schema_id))),
            "model_profile_id": str(uuid.UUID(str(model_profile_id))),
        }
        if runtime_profile_id:
            persistence_inputs["runtime_profile_id"] = str(
                uuid.UUID(str(runtime_profile_id))
            )
        return persistence_inputs
    except (ValueError, TypeError):
        logger.debug(
            "Agent run persistence skipped for step '%s': invalid UUID config",
            context.active_record_set_id,
        )
        return None


def _normalize_agent_run_result(
    result: Any,
    *,
    default_total: int,
    default_run_id: str,
) -> AgentRunBatchResult:
    """Normalize an agent runner return value into a typed result."""

    if isinstance(result, AgentRunBatchResult):
        return result

    if isinstance(result, Mapping):
        data = dict(result)
        status = data.get("status", "completed")
        return AgentRunBatchResult(
            agent_run_id=uuid.UUID(str(data.get("agent_run_id", default_run_id))),
            status=status,
            total_records=int(data.get("total_records", default_total)),
            completed_records=int(
                data.get("completed_records", data.get("success_count", default_total))
            ),
            failed_records=int(
                data.get("failed_records", data.get("failure_count", 0))
            ),
            batch_size=int(data.get("batch_size", max(1, default_total or 1))),
            batch_count=int(data.get("batch_count", 1 if default_total else 0)),
            event_count=int(data.get("event_count", 0)),
            error_summary=data.get("error_summary"),
            partial_results=data.get("partial_results"),
        )

    completed_records = int(
        getattr(
            result,
            "completed_records",
            getattr(result, "success_count", default_total),
        )
    )
    failed_records = int(
        getattr(result, "failed_records", getattr(result, "failure_count", 0))
    )
    status = getattr(result, "status", "completed")
    return AgentRunBatchResult(
        agent_run_id=uuid.UUID(str(getattr(result, "agent_run_id", default_run_id))),
        status=status,
        total_records=int(getattr(result, "total_records", default_total)),
        completed_records=completed_records,
        failed_records=failed_records,
        batch_size=int(getattr(result, "batch_size", max(1, default_total or 1))),
        batch_count=int(getattr(result, "batch_count", 1 if default_total else 0)),
        event_count=int(getattr(result, "event_count", 0)),
        error_summary=getattr(result, "error_summary", None),
        partial_results=getattr(result, "partial_results", None),
    )


def _build_agent_run_step_result(
    *,
    context: WorkflowContext,
    step_id: str,
    agent_run_id: str,
    model_id: str,
    agent_role: str,
    total_records: int,
    success_count: int,
    failure_count: int,
    status: str,
    is_partial: bool = False,
    error: str | None = None,
) -> StepResult:
    """Apply persisted agent-run counts back into workflow context."""

    is_partial = is_partial or (success_count > 0 and failure_count > 0)
    step_status = "partially_failed" if is_partial else "completed"
    context.agent_run_ids.append(agent_run_id)
    context.agent_outputs[agent_run_id] = AgentOutputRef(
        agent_run_id=agent_run_id,
        model_id=model_id,
        record_count=total_records,
        success_count=success_count,
        failure_count=failure_count,
    )
    context.record_sets[step_id] = RecordSet(
        record_ids=list(context.get_active_record_ids()),
        record_count=total_records,
        description=f"Agent run ({model_id}, role={agent_role})",
    )
    context.active_record_set_id = step_id
    context.metrics["agent.coverage"] = (
        success_count / total_records if total_records else 0.0
    )

    summary = {
        "agent_run_id": agent_run_id,
        "model": model_id,
        "agent_role": agent_role,
        "records_processed": total_records,
        "records_completed": success_count,
        "records_failed": failure_count,
        "success_count": success_count,
        "failure_count": failure_count,
        "agent_run_status": status,
    }
    if error:
        summary["error"] = error

    return StepResult(
        success=not (status == "failed" and success_count == 0),
        output=StepOutput(
            step_id=step_id,
            step_type="agent_run",
            status=step_status,
            summary=summary,
        ),
        is_partial=is_partial,
        error=f"Agent run failed: {error}" if error and not is_partial else "",
    )

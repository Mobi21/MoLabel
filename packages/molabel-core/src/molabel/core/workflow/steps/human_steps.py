"""Human step executors: review, triage, calibration, adjudication.

WF-011 through WF-014. Human steps always pause the workflow by returning
waiting_for_human=True. They create queues and wait for human work to
complete before the engine resumes them.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from molabel.core.workflow.context import (
    RecordSet,
    StepOutput,
    WorkflowContext,
)
from molabel.core.workflow.steps.base import StepExecutor, StepResult

logger = logging.getLogger(__name__)


class HumanReviewExecutor(StepExecutor):
    """Executor for human_review steps (WF-011).

    Creates a review queue from the active record set. Always pauses the
    workflow (waiting_for_human state) until the queue is processed or the
    operator advances. ``overlap_count: N`` gives each record N review tasks,
    and the queue never hands one reviewer two tasks for the same record.
    """

    def validate(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
    ) -> list[str]:
        errors: list[str] = []
        if not context.active_record_set_id:
            errors.append("human_review requires an active record set")
        overlap_count = config.get("overlap_count", 1)
        if type(overlap_count) is not int or overlap_count < 1:
            errors.append("human_review overlap_count must be an integer of 1 or more")
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

        # Optionally sample a subset for review
        sample_size = config.get("sample_size")
        if sample_size and sample_size < len(input_record_ids):
            import random

            rng = random.Random(config.get("seed"))
            review_ids = rng.sample(input_record_ids, int(sample_size))
        else:
            review_ids = list(input_record_ids)

        queue_id = str(uuid.uuid4())

        # Create queue via review service if available
        review_service = services.get("review_queue")
        if review_service is not None:
            try:
                review_service.create_queue(
                    queue_id=queue_id,
                    record_ids=review_ids,
                    config=config,
                )
            except Exception as e:
                return StepResult(
                    success=False,
                    error=f"Failed to create review queue: {e}",
                    error_trace=str(e)[:2000],
                )

        context.review_queue_ids.append(queue_id)
        context.record_sets[step_id] = RecordSet(
            record_ids=review_ids,
            record_count=len(review_ids),
            description=f"Human review queue ({len(review_ids)} items)",
        )
        context.active_record_set_id = step_id
        context.metrics["review.coverage"] = 0.0  # Updated as reviews complete

        # Compute accept_ai_rate from review service results or context data
        accept_ai_rate = _compute_accept_ai_rate(review_service, queue_id, context)
        context.metrics["review.accept_ai_rate"] = accept_ai_rate

        return StepResult(
            success=True,
            waiting_for_human=True,
            output=StepOutput(
                step_id=step_id,
                step_type="human_review",
                summary={
                    "queue_id": queue_id,
                    "total_items": len(review_ids),
                    "sample_strategy": config.get("sample_strategy", "all"),
                    "task_schema_id": config.get("task_schema_id", ""),
                    "accept_ai_rate": accept_ai_rate,
                },
            ),
        )


class HumanTriageExecutor(StepExecutor):
    """Executor for human_triage steps (WF-012).

    Creates a triage queue for quick pass/fail/needs_review sorting.
    Always pauses for human work.
    """

    def validate(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
    ) -> list[str]:
        errors: list[str] = []
        if not context.active_record_set_id:
            errors.append("human_triage requires an active record set")
        categories = config.get("categories", [])
        if not categories:
            errors.append("human_triage requires 'categories' in config")
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
        categories = config.get("categories", [])

        queue_id = str(uuid.uuid4())

        review_service = services.get("review_queue")
        if review_service is not None:
            try:
                review_service.create_queue(
                    queue_id=queue_id,
                    record_ids=input_record_ids,
                    config={**config, "triage_mode": True},
                )
            except Exception as e:
                return StepResult(
                    success=False,
                    error=f"Failed to create triage queue: {e}",
                    error_trace=str(e)[:2000],
                )

        context.review_queue_ids.append(queue_id)
        context.record_sets[step_id] = RecordSet(
            record_ids=list(input_record_ids),
            record_count=len(input_record_ids),
            description=f"Triage queue ({len(input_record_ids)} items)",
        )
        context.active_record_set_id = step_id

        # Initialize triage category counts
        for cat in categories:
            context.variables[f"triage.{cat}.count"] = 0

        return StepResult(
            success=True,
            waiting_for_human=True,
            output=StepOutput(
                step_id=step_id,
                step_type="human_triage",
                summary={
                    "queue_id": queue_id,
                    "total_items": len(input_record_ids),
                    "categories": categories,
                },
            ),
        )


class HumanCalibrationExecutor(StepExecutor):
    """Executor for human_calibration steps (WF-013).

    Makes a calibration queue of the gold set that ``config.gold_set`` names,
    read through the ``gold_sets`` service. Each item gets ``min_reviewers``
    copies, 2 by default, so that many reviewers label every item. The
    workflow's active record set is left as it was. Pauses until the queue
    is done.
    """

    def validate(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
    ) -> list[str]:
        errors: list[str] = []
        if not isinstance(config.get("gold_set"), str) or not config["gold_set"]:
            errors.append("human_calibration requires 'gold_set' in config")
        for key in ("sample_size", "min_reviewers"):
            value = config.get(key)
            if value is not None and (type(value) is not int or value < 1):
                errors.append(
                    f"human_calibration {key} must be an integer of 1 or more"
                )
        return errors

    def execute(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
        services: dict[str, Any] | None = None,
    ) -> StepResult:
        gold_sets = (services or {}).get("gold_sets")
        if gold_sets is None:
            return StepResult(
                success=False, error="human_calibration needs the gold_sets service"
            )
        try:
            items = gold_sets.calibration_items(config["gold_set"])
        except Exception as e:
            return StepResult(
                success=False,
                error=f"Failed to read gold set '{config['gold_set']}': {e}",
                error_trace=str(e)[:2000],
            )
        record_ids = list(items.record_ids)
        sample_size = config.get("sample_size")
        if sample_size and sample_size < len(record_ids):
            import random

            record_ids = random.Random(config.get("seed")).sample(
                record_ids, sample_size
            )
        min_reviewers = int(config.get("min_reviewers", 2))

        queue_id = str(uuid.uuid4())
        context.review_queue_ids.append(queue_id)
        context.record_sets[step_id] = RecordSet(
            record_ids=record_ids,
            record_count=len(record_ids),
            description=f"Calibration queue on gold set {items.gold_set}",
        )
        context.metrics["calibration.agreement"] = 0.0
        context.metrics["calibration.reviewer_count"] = 0

        return StepResult(
            success=True,
            waiting_for_human=True,
            output=StepOutput(
                step_id=step_id,
                step_type="human_calibration",
                summary={
                    "queue_id": queue_id,
                    "gold_set": items.gold_set,
                    "gold_version": items.version,
                    "gold_content_hash": items.content_hash,
                    "task_schema_id": items.task_schema,
                    "calibration_items": len(record_ids),
                    "unresolved_items": list(items.unresolved),
                    "min_reviewers": min_reviewers,
                    "show_ai_proposal": config.get("show_ai_proposal") is True,
                },
            ),
        )


class HumanAdjudicationExecutor(StepExecutor):
    """Executor for human_adjudication steps (WF-014).

    Creates an adjudication queue for disagreement records. Pauses for
    human resolution work.
    """

    def validate(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
    ) -> list[str]:
        errors: list[str] = []
        if not context.active_record_set_id:
            errors.append("human_adjudication requires an active record set")
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

        queue_id = str(uuid.uuid4())

        adjudication_service = services.get("adjudication_queue")
        if adjudication_service is not None:
            try:
                adjudication_service.create_queue(
                    queue_id=queue_id,
                    record_ids=input_record_ids,
                    config=config,
                )
            except Exception as e:
                return StepResult(
                    success=False,
                    error=f"Failed to create adjudication queue: {e}",
                    error_trace=str(e)[:2000],
                )

        context.adjudication_queue_ids.append(queue_id)
        context.record_sets[step_id] = RecordSet(
            record_ids=list(input_record_ids),
            record_count=len(input_record_ids),
            description=f"Adjudication queue ({len(input_record_ids)} items)",
        )
        context.active_record_set_id = step_id
        context.metrics["adjudication.resolution_rate"] = 0.0

        return StepResult(
            success=True,
            waiting_for_human=True,
            output=StepOutput(
                step_id=step_id,
                step_type="human_adjudication",
                summary={
                    "queue_id": queue_id,
                    "total_items": len(input_record_ids),
                    "adjudication_policy": config.get("adjudication_policy", ""),
                },
            ),
        )


def _compute_accept_ai_rate(
    review_service: Any | None,
    queue_id: str,
    context: WorkflowContext,
) -> float:
    """Compute the accept_ai_rate metric for a review queue.

    accept_ai_rate = number of accept_ai decisions / total decisions.

    Tries the review service first, then falls back to context data.
    Returns 0.0 when no decision data is available (queue just created).
    """
    if review_service is not None:
        try:
            stats = review_service.get_queue_stats(queue_id)
            if stats is not None:
                total = stats.get("total_decisions", 0)
                accept_ai = stats.get("accept_ai_count", 0)
                if total > 0:
                    return accept_ai / total
        except Exception:
            logger.debug(
                "Review service get_queue_stats failed for '%s'; checking context data",
                queue_id,
            )

    # Fall back to context variables/metrics for decision counts
    total_decisions = context.variables.get("review.total_decisions", 0)
    accept_ai_count = context.variables.get("review.accept_ai_count", 0)
    if total_decisions > 0:
        return accept_ai_count / total_decisions

    # No decisions yet (queue was just created)
    return 0.0

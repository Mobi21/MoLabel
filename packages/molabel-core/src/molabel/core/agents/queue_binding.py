"""Agent output binding to review queues (AG-005).

Connects validated agent outputs to review tasks through explicit
``agent_output_ids`` references.  Manages visibility of agent outputs
based on the task schema's blind-review policy.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from molabel.core.types import BlindReviewPolicy

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class QueueBindingResult(BaseModel):
    """Summary of a queue-binding operation."""

    review_task_count: int
    agent_output_count: int
    outputs_made_visible: int
    outputs_hidden: int
    errors: list[str] = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def serialize_agent_output_ids(output_ids: list[UUID]) -> str:
    """Serialize a list of UUIDs to a JSON string for SQLite storage."""
    return json.dumps([str(uid) for uid in output_ids])


def deserialize_agent_output_ids(raw: str | None) -> list[UUID]:
    """Deserialize a JSON string of UUID strings back to a list of UUIDs.

    Returns an empty list for ``None`` or empty strings.
    """
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        return [UUID(item) for item in parsed]
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning("Failed to deserialize agent_output_ids: %s", exc)
        return []


def _resolve_blind_review_policy(
    policy_value: str | BlindReviewPolicy | None,
) -> BlindReviewPolicy:
    """Coerce a policy string to a BlindReviewPolicy enum value."""
    if isinstance(policy_value, BlindReviewPolicy):
        return policy_value
    if policy_value is None:
        return BlindReviewPolicy.hide_agent_outputs_by_default
    try:
        return BlindReviewPolicy(str(policy_value))
    except ValueError:
        return BlindReviewPolicy.hide_agent_outputs_by_default


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------


class AgentQueueBinder:
    """Binds validated agent outputs to review tasks.

    The binder is stateless; all persistence is handled by the caller
    (or via the ``apply_*`` methods that mutate objects in place).

    Typical usage:

    1. Call ``bind_outputs_to_tasks`` with agent outputs and review tasks.
    2. Persist the mutated objects through your session / repository.
    3. Use ``get_agent_output_ids_for_task`` to retrieve the IDs later.
    """

    def determine_visibility(
        self,
        blind_review_policy: str | BlindReviewPolicy | None,
    ) -> bool:
        """Return whether agent outputs should be visible based on policy.

        Parameters
        ----------
        blind_review_policy:
            The task schema's ``blind_review_policy`` value.

        Returns
        -------
        bool
            ``True`` if agent outputs should be visible to reviewers,
            ``False`` if they should be hidden.
        """
        policy = _resolve_blind_review_policy(blind_review_policy)
        if policy == BlindReviewPolicy.show_agent_outputs:
            return True
        if policy == BlindReviewPolicy.no_agent:
            return False
        # hide_agent_outputs_by_default
        return False

    def set_visibility_on_outputs(
        self,
        agent_outputs: list[Any],
        *,
        blind_review_policy: str | BlindReviewPolicy | None,
    ) -> tuple[int, int]:
        """Set ``is_visible_for_review`` on each agent output.

        Returns ``(visible_count, hidden_count)``.
        """
        is_visible = self.determine_visibility(blind_review_policy)
        visible_count = 0
        hidden_count = 0

        for output in agent_outputs:
            output.is_visible_for_review = is_visible
            if is_visible:
                visible_count += 1
            else:
                hidden_count += 1

        return visible_count, hidden_count

    def bind_outputs_to_tasks(
        self,
        agent_outputs: list[Any],
        review_tasks: list[Any],
        *,
        blind_review_policy: str | BlindReviewPolicy | None = None,
    ) -> QueueBindingResult:
        """Bind agent outputs to review tasks by record_id.

        For each review task, this method finds all agent outputs whose
        ``record_id`` matches, serializes their IDs into the task's
        ``agent_output_ids`` field, and sets visibility on the outputs
        based on the blind-review policy.

        Parameters
        ----------
        agent_outputs:
            List of agent output objects with ``id``, ``record_id``, and
            ``is_visible_for_review`` attributes.
        review_tasks:
            List of review task objects with ``record_id`` and
            ``agent_output_ids`` attributes.
        blind_review_policy:
            The task schema's blind-review policy.

        Returns
        -------
        QueueBindingResult
            Summary of the binding operation.
        """
        errors: list[str] = []

        # 1. Set visibility on all outputs
        visible_count, hidden_count = self.set_visibility_on_outputs(
            agent_outputs,
            blind_review_policy=blind_review_policy,
        )

        # 2. Index outputs by record_id
        outputs_by_record: dict[UUID, list[UUID]] = {}
        for output in agent_outputs:
            record_id = output.record_id
            if not isinstance(record_id, UUID):
                try:
                    record_id = UUID(str(record_id))
                except (ValueError, TypeError) as exc:
                    errors.append(f"Invalid record_id on agent output: {exc}")
                    continue

            output_id = output.id
            if not isinstance(output_id, UUID):
                try:
                    output_id = UUID(str(output_id))
                except (ValueError, TypeError) as exc:
                    errors.append(f"Invalid id on agent output: {exc}")
                    continue

            outputs_by_record.setdefault(record_id, []).append(output_id)

        # 3. Bind to review tasks
        bound_task_count = 0
        for task in review_tasks:
            task_record_id = task.record_id
            if not isinstance(task_record_id, UUID):
                try:
                    task_record_id = UUID(str(task_record_id))
                except (ValueError, TypeError) as exc:
                    errors.append(f"Invalid record_id on review task: {exc}")
                    continue

            matching_output_ids = outputs_by_record.get(task_record_id, [])

            # Merge with existing agent_output_ids if present
            existing_ids = deserialize_agent_output_ids(
                getattr(task, "agent_output_ids", None)
            )
            merged = list(existing_ids)
            existing_set = set(existing_ids)
            for oid in matching_output_ids:
                if oid not in existing_set:
                    merged.append(oid)
                    existing_set.add(oid)

            task.agent_output_ids = (
                serialize_agent_output_ids(merged) if merged else None
            )

            if matching_output_ids:
                bound_task_count += 1

        return QueueBindingResult(
            review_task_count=bound_task_count,
            agent_output_count=len(agent_outputs),
            outputs_made_visible=visible_count,
            outputs_hidden=hidden_count,
            errors=errors,
        )

    def get_agent_output_ids_for_task(self, review_task: Any) -> list[UUID]:
        """Return the deserialized agent output IDs for a review task.

        Parameters
        ----------
        review_task:
            A review task object with an ``agent_output_ids`` attribute.
        """
        raw = getattr(review_task, "agent_output_ids", None)
        return deserialize_agent_output_ids(raw)

    def add_output_to_task(
        self,
        review_task: Any,
        agent_output_id: UUID,
    ) -> None:
        """Append a single agent output ID to a review task.

        Deduplicates against IDs already present.
        """
        existing = self.get_agent_output_ids_for_task(review_task)
        if agent_output_id not in existing:
            existing.append(agent_output_id)
        review_task.agent_output_ids = serialize_agent_output_ids(existing)

    def remove_output_from_task(
        self,
        review_task: Any,
        agent_output_id: UUID,
    ) -> bool:
        """Remove a single agent output ID from a review task.

        Returns ``True`` if the ID was present and removed.
        """
        existing = self.get_agent_output_ids_for_task(review_task)
        if agent_output_id in existing:
            existing.remove(agent_output_id)
            review_task.agent_output_ids = (
                serialize_agent_output_ids(existing) if existing else None
            )
            return True
        return False

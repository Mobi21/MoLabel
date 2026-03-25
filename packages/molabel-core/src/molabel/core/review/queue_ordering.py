"""Queue assignment ordering logic (RV-008).

Pure ordering functions that determine priority when selecting the next
item from a review queue. Designed to be used by the claim service.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import IntEnum
from typing import Any


class QueuePriority(IntEnum):
    """Priority tiers for queue item ordering.

    Higher numeric values are claimed first. Within each tier,
    items are ordered by creation time (oldest first).
    """

    general_pool = 0
    workflow_assigned = 10
    active_learning_flagged = 20


@dataclass(frozen=True)
class OrderingConfig:
    """Configuration for queue ordering behavior."""

    enable_sticky_assignment: bool = False
    """When True, prefer items the reviewer previously started drafting."""

    enable_active_learning_priority: bool = True
    """When True, active-learning-flagged items are served first."""

    enable_workflow_priority: bool = True
    """When True, workflow-assigned items outrank general pool."""


@dataclass(frozen=True)
class OrderedItem:
    """A queue item with its computed ordering score."""

    task_id: uuid.UUID
    record_id: uuid.UUID
    base_priority: int
    effective_priority: int
    created_at: str
    priority_reason: str | None = None
    is_sticky: bool = False


def classify_priority(
    priority: int,
    priority_reason: str | None,
    config: OrderingConfig,
) -> int:
    """Classify a task's effective priority based on its metadata.

    Maps task priority values and reasons to the tiered ordering system:
    1. Active learning flagged items (highest)
    2. Workflow-assigned items
    3. General pool (lowest)
    """
    if (
        config.enable_active_learning_priority
        and priority_reason is not None
        and "active_learning" in priority_reason.lower()
    ):
        return QueuePriority.active_learning_flagged + priority

    if (
        config.enable_workflow_priority
        and priority_reason is not None
        and "workflow" in priority_reason.lower()
    ):
        return QueuePriority.workflow_assigned + priority

    return QueuePriority.general_pool + priority


def compute_ordering(
    tasks: list[dict[str, Any]],
    reviewer_id: uuid.UUID,
    config: OrderingConfig,
    reviewer_draft_record_ids: list[uuid.UUID] | None = None,
) -> list[OrderedItem]:
    """Compute the ordering for a list of candidate queue items.

    Returns items sorted by:
    1. Sticky assignment (if enabled, items with existing drafts first)
    2. Effective priority (active learning > workflow > general)
    3. Creation time (oldest first within same priority)

    Parameters
    ----------
    tasks:
        List of task dicts (matching the claim service format) with at
        minimum ``id``, ``record_id``, ``priority``, ``priority_reason``,
        and ``created_at``.
    reviewer_id:
        The reviewer requesting the next item.
    config:
        Ordering configuration.
    reviewer_draft_record_ids:
        Record IDs where this reviewer has existing draft labels.
        Used for sticky assignment when enabled.
    """
    draft_ids = set(reviewer_draft_record_ids or [])

    ordered_items: list[OrderedItem] = []
    for task in tasks:
        task_id = (
            task["id"] if isinstance(task["id"], uuid.UUID) else uuid.UUID(task["id"])
        )
        record_id = (
            task["record_id"]
            if isinstance(task["record_id"], uuid.UUID)
            else uuid.UUID(task["record_id"])
        )
        base_priority = int(task.get("priority", 0))
        priority_reason = task.get("priority_reason")
        created_at = str(task.get("created_at", ""))

        effective_priority = classify_priority(base_priority, priority_reason, config)

        is_sticky = config.enable_sticky_assignment and record_id in draft_ids

        ordered_items.append(
            OrderedItem(
                task_id=task_id,
                record_id=record_id,
                base_priority=base_priority,
                effective_priority=effective_priority,
                created_at=created_at,
                priority_reason=priority_reason,
                is_sticky=is_sticky,
            )
        )

    ordered_items.sort(
        key=lambda item: (
            not item.is_sticky,
            -item.effective_priority,
            item.created_at,
        )
    )

    return ordered_items


def build_priority_sql_expression(config: OrderingConfig) -> str:
    """Build a SQL ORDER BY expression for queue priority ordering.

    Returns a SQL fragment suitable for use in an ORDER BY clause that
    implements the tiered priority system. This is used by the claim
    service to order tasks at the database level.
    """
    parts: list[str] = []

    if config.enable_active_learning_priority:
        parts.append(
            "CASE WHEN priority_reason LIKE '%active_learning%' THEN 0 ELSE 1 END ASC"
        )

    if config.enable_workflow_priority:
        parts.append(
            "CASE WHEN priority_reason LIKE '%workflow%' THEN 0 ELSE 1 END ASC"
        )

    parts.append("priority DESC")
    parts.append("created_at ASC")

    return ", ".join(parts)

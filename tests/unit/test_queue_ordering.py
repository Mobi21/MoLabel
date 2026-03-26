"""Unit tests for queue ordering logic (RV-008).

Tests cover:
- Priority classification (active learning > workflow > general)
- Ordering within tiers by creation time
- Sticky assignment preference
- SQL expression generation
- Integration with claim service ordering
"""

from __future__ import annotations

import uuid

import pytest

from molabel.core.review.queue_ordering import (
    OrderingConfig,
    QueuePriority,
    build_priority_sql_expression,
    classify_priority,
    compute_ordering,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def config() -> OrderingConfig:
    """Default ordering config with all features enabled."""
    return OrderingConfig(
        enable_sticky_assignment=False,
        enable_active_learning_priority=True,
        enable_workflow_priority=True,
    )


@pytest.fixture()
def sticky_config() -> OrderingConfig:
    """Config with sticky assignment enabled."""
    return OrderingConfig(
        enable_sticky_assignment=True,
        enable_active_learning_priority=True,
        enable_workflow_priority=True,
    )


def _make_task(
    *,
    priority: int = 0,
    priority_reason: str | None = None,
    created_at: str = "2026-01-01T00:00:00",
    record_id: uuid.UUID | None = None,
) -> dict:
    """Helper to create a task dict for ordering tests."""
    return {
        "id": str(uuid.uuid4()),
        "record_id": str(record_id or uuid.uuid4()),
        "priority": priority,
        "priority_reason": priority_reason,
        "created_at": created_at,
    }


# ---------------------------------------------------------------------------
# Tests: Priority classification
# ---------------------------------------------------------------------------


class TestPriorityClassification:
    """Tests for classify_priority function."""

    def test_general_pool(self, config: OrderingConfig) -> None:
        """Items without special reason get general pool priority."""
        result = classify_priority(0, None, config)
        assert result == QueuePriority.general_pool

    def test_general_pool_with_base_priority(self, config: OrderingConfig) -> None:
        """Base priority is added to tier base."""
        result = classify_priority(5, None, config)
        assert result == QueuePriority.general_pool + 5

    def test_active_learning_priority(self, config: OrderingConfig) -> None:
        """Active learning items get highest tier."""
        result = classify_priority(0, "active_learning_flagged", config)
        assert result == QueuePriority.active_learning_flagged

    def test_workflow_priority(self, config: OrderingConfig) -> None:
        """Workflow-assigned items get middle tier."""
        result = classify_priority(0, "workflow_assigned", config)
        assert result == QueuePriority.workflow_assigned

    def test_active_learning_beats_workflow(self, config: OrderingConfig) -> None:
        """Active learning priority is higher than workflow priority."""
        al = classify_priority(0, "active_learning_flagged", config)
        wf = classify_priority(0, "workflow_assigned", config)
        assert al > wf

    def test_workflow_beats_general(self, config: OrderingConfig) -> None:
        """Workflow priority is higher than general pool."""
        wf = classify_priority(0, "workflow_assigned", config)
        gen = classify_priority(0, None, config)
        assert wf > gen

    def test_disabled_active_learning(self) -> None:
        """Active learning items treated as general pool when disabled."""
        config = OrderingConfig(
            enable_active_learning_priority=False,
            enable_workflow_priority=True,
        )
        result = classify_priority(0, "active_learning_flagged", config)
        assert result == QueuePriority.general_pool

    def test_disabled_workflow(self) -> None:
        """Workflow items treated as general pool when disabled."""
        config = OrderingConfig(
            enable_active_learning_priority=True,
            enable_workflow_priority=False,
        )
        result = classify_priority(0, "workflow_assigned", config)
        assert result == QueuePriority.general_pool


# ---------------------------------------------------------------------------
# Tests: Compute ordering
# ---------------------------------------------------------------------------


class TestComputeOrdering:
    """Tests for the compute_ordering function."""

    def test_active_learning_first(self, config: OrderingConfig) -> None:
        """Active learning items are ordered before general pool."""
        tasks = [
            _make_task(priority=0, created_at="2026-01-01T00:00:00"),
            _make_task(
                priority=0,
                priority_reason="active_learning_flagged",
                created_at="2026-01-01T01:00:00",
            ),
        ]
        reviewer_id = uuid.uuid4()
        ordered = compute_ordering(tasks, reviewer_id, config)

        assert len(ordered) == 2
        assert ordered[0].priority_reason == "active_learning_flagged"

    def test_workflow_before_general(self, config: OrderingConfig) -> None:
        """Workflow items are ordered before general pool."""
        tasks = [
            _make_task(priority=0, created_at="2026-01-01T00:00:00"),
            _make_task(
                priority=0,
                priority_reason="workflow_assigned",
                created_at="2026-01-01T01:00:00",
            ),
        ]
        reviewer_id = uuid.uuid4()
        ordered = compute_ordering(tasks, reviewer_id, config)

        assert ordered[0].priority_reason == "workflow_assigned"

    def test_creation_time_within_tier(self, config: OrderingConfig) -> None:
        """Within same priority tier, oldest items come first."""
        tasks = [
            _make_task(priority=0, created_at="2026-01-02T00:00:00"),
            _make_task(priority=0, created_at="2026-01-01T00:00:00"),
        ]
        reviewer_id = uuid.uuid4()
        ordered = compute_ordering(tasks, reviewer_id, config)

        assert ordered[0].created_at == "2026-01-01T00:00:00"
        assert ordered[1].created_at == "2026-01-02T00:00:00"

    def test_higher_base_priority_first(self, config: OrderingConfig) -> None:
        """Within same tier, higher base priority items come first."""
        tasks = [
            _make_task(priority=1, created_at="2026-01-01T00:00:00"),
            _make_task(priority=5, created_at="2026-01-01T00:00:00"),
        ]
        reviewer_id = uuid.uuid4()
        ordered = compute_ordering(tasks, reviewer_id, config)

        assert ordered[0].base_priority == 5
        assert ordered[1].base_priority == 1

    def test_full_ordering(self, config: OrderingConfig) -> None:
        """Full ordering respects all tiers and creation time."""
        tasks = [
            _make_task(priority=0, created_at="2026-01-01T00:00:00"),
            _make_task(
                priority=0,
                priority_reason="active_learning_flagged",
                created_at="2026-01-01T02:00:00",
            ),
            _make_task(
                priority=0,
                priority_reason="workflow_assigned",
                created_at="2026-01-01T01:00:00",
            ),
        ]
        reviewer_id = uuid.uuid4()
        ordered = compute_ordering(tasks, reviewer_id, config)

        assert ordered[0].priority_reason == "active_learning_flagged"
        assert ordered[1].priority_reason == "workflow_assigned"
        assert ordered[2].priority_reason is None


# ---------------------------------------------------------------------------
# Tests: Sticky assignment
# ---------------------------------------------------------------------------


class TestStickyAssignment:
    """Tests for sticky assignment (prefer items with existing drafts)."""

    def test_sticky_items_first(self, sticky_config: OrderingConfig) -> None:
        """Items with existing drafts are ordered first when sticky enabled."""
        draft_record_id = uuid.uuid4()
        tasks = [
            _make_task(priority=0, created_at="2026-01-01T00:00:00"),
            _make_task(
                priority=0,
                created_at="2026-01-01T01:00:00",
                record_id=draft_record_id,
            ),
        ]
        reviewer_id = uuid.uuid4()
        ordered = compute_ordering(
            tasks,
            reviewer_id,
            sticky_config,
            reviewer_draft_record_ids=[draft_record_id],
        )

        assert ordered[0].is_sticky is True
        assert ordered[0].record_id == draft_record_id

    def test_sticky_disabled(self, config: OrderingConfig) -> None:
        """Sticky does not affect ordering when disabled."""
        draft_record_id = uuid.uuid4()
        tasks = [
            _make_task(priority=5, created_at="2026-01-01T00:00:00"),
            _make_task(
                priority=0,
                created_at="2026-01-01T01:00:00",
                record_id=draft_record_id,
            ),
        ]
        reviewer_id = uuid.uuid4()
        ordered = compute_ordering(
            tasks,
            reviewer_id,
            config,
            reviewer_draft_record_ids=[draft_record_id],
        )

        # Higher priority item should still be first
        assert ordered[0].base_priority == 5

    def test_sticky_over_priority_within_general(
        self, sticky_config: OrderingConfig
    ) -> None:
        """Sticky assignment takes precedence over base priority within same tier."""
        draft_record_id = uuid.uuid4()
        tasks = [
            _make_task(priority=5, created_at="2026-01-01T00:00:00"),
            _make_task(
                priority=0,
                created_at="2026-01-01T01:00:00",
                record_id=draft_record_id,
            ),
        ]
        reviewer_id = uuid.uuid4()
        ordered = compute_ordering(
            tasks,
            reviewer_id,
            sticky_config,
            reviewer_draft_record_ids=[draft_record_id],
        )

        assert ordered[0].is_sticky is True


# ---------------------------------------------------------------------------
# Tests: SQL expression generation
# ---------------------------------------------------------------------------


class TestSQLExpression:
    """Tests for build_priority_sql_expression."""

    def test_default_expression(self, config: OrderingConfig) -> None:
        """Default config produces expression with all priority tiers."""
        sql = build_priority_sql_expression(config)
        assert "active_learning" in sql
        assert "workflow" in sql
        assert "priority DESC" in sql
        assert "created_at ASC" in sql

    def test_no_active_learning(self) -> None:
        """Disabled active learning omits that clause."""
        config = OrderingConfig(
            enable_active_learning_priority=False,
            enable_workflow_priority=True,
        )
        sql = build_priority_sql_expression(config)
        assert "active_learning" not in sql
        assert "workflow" in sql

    def test_no_workflow(self) -> None:
        """Disabled workflow omits that clause."""
        config = OrderingConfig(
            enable_active_learning_priority=True,
            enable_workflow_priority=False,
        )
        sql = build_priority_sql_expression(config)
        assert "active_learning" in sql
        assert "workflow" not in sql

    def test_minimal_expression(self) -> None:
        """Both disabled yields just priority + created_at."""
        config = OrderingConfig(
            enable_active_learning_priority=False,
            enable_workflow_priority=False,
        )
        sql = build_priority_sql_expression(config)
        assert sql == "priority DESC, created_at ASC"

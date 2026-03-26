"""Unit tests for blind first-pass review (RV-001).

Tests cover:
- Blind review policy enforcement when claiming tasks
- Agent output hidden by default (hide_agent_outputs_by_default)
- Agent output shown when policy is show_agent_outputs
- Agent output never shown when policy is no_agent
- Agent output shown when ai_revealed=True despite hide policy
"""

from __future__ import annotations

import json
import uuid

import pytest
from conftest import ReviewerData, TaskData, WorkspaceData, insert_reviewer
from sqlalchemy import text

from molabel.app.services.claims import (
    apply_blind_review_policy,
    claim_next,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

QUEUE_ID = "blind-review-q1"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def reviewer(engine, workspace) -> ReviewerData:
    """Insert a reviewer for blind review tests."""
    return insert_reviewer(
        engine, workspace, display_name="BlindAlice", avatar_color="#4A90D9"
    )


def _create_task_schema(
    engine,
    workspace: WorkspaceData,
    *,
    blind_review_policy: str = "hide_agent_outputs_by_default",
) -> uuid.UUID:
    """Insert a task schema with the given blind review policy."""
    schema_id = uuid.uuid4()
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO task_schemas "
                "(id, task_schema_slug, version, task_type, title, "
                "label_fields, blind_review_policy, workspace_id) "
                "VALUES (:id, :slug, :ver, :tt, :title, :lf, :brp, :ws)"
            ),
            {
                "id": str(schema_id),
                "slug": "test-schema",
                "ver": 1,
                "tt": "classification",
                "title": "Test Schema",
                "lf": json.dumps({"sentiment": {"type": "categorical"}}),
                "brp": blind_review_policy,
                "ws": str(workspace.id),
            },
        )
        conn.commit()
    return schema_id


def _create_tasks_with_schema(
    engine,
    workspace: WorkspaceData,
    task_schema_id: uuid.UUID,
    *,
    count: int = 1,
    queue_id: str = QUEUE_ID,
) -> list[TaskData]:
    """Insert review tasks linked to a specific task schema."""
    dataset_id = uuid.uuid4()
    tasks = []
    with engine.connect() as conn:
        for _ in range(count):
            task_id = uuid.uuid4()
            record_id = uuid.uuid4()
            conn.execute(
                text(
                    "INSERT INTO review_tasks "
                    "(id, queue_id, record_id, task_schema_id, status, priority, "
                    "workspace_id, dataset_id) "
                    "VALUES (:id, :qid, :rid, :sid, 'available', 0, :ws, :ds)"
                ),
                {
                    "id": str(task_id),
                    "qid": queue_id,
                    "rid": str(record_id),
                    "sid": str(task_schema_id),
                    "ws": str(workspace.id),
                    "ds": str(dataset_id),
                },
            )
            tasks.append(
                TaskData(
                    id=task_id,
                    queue_id=queue_id,
                    record_id=record_id,
                    task_schema_id=task_schema_id,
                    workspace_id=workspace.id,
                    dataset_id=dataset_id,
                    priority=0,
                )
            )
        conn.commit()
    return tasks


def _create_agent_output(
    engine,
    workspace: WorkspaceData,
    record_id: uuid.UUID,
    task_schema_id: uuid.UUID,
    *,
    labels: dict | None = None,
) -> uuid.UUID:
    """Insert an agent output for a record + task schema."""
    output_id = uuid.uuid4()
    agent_run_id = uuid.uuid4()
    if labels is None:
        labels = {"sentiment": "positive"}
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO agent_outputs "
                "(id, agent_run_id, record_id, task_schema_id, output_type, "
                "labels, validation_passed, workspace_id) "
                "VALUES (:id, :arid, :rid, :sid, 'label', :labels, 1, :ws)"
            ),
            {
                "id": str(output_id),
                "arid": str(agent_run_id),
                "rid": str(record_id),
                "sid": str(task_schema_id),
                "labels": json.dumps(labels),
                "ws": str(workspace.id),
            },
        )
        conn.commit()
    return output_id


# ===================================================================
# RV-001: Blind first-pass review
# ===================================================================


class TestBlindReviewPolicyHide:
    """Tests for hide_agent_outputs_by_default policy."""

    def test_agent_output_hidden_by_default(self, engine, reviewer, workspace) -> None:
        """Agent output is stripped when policy is hide_agent_outputs_by_default."""
        schema_id = _create_task_schema(
            engine,
            workspace,
            blind_review_policy="hide_agent_outputs_by_default",
        )
        tasks = _create_tasks_with_schema(engine, workspace, schema_id)
        _create_agent_output(engine, workspace, tasks[0].record_id, schema_id)

        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None

        result = apply_blind_review_policy(engine, claimed)
        assert result["agent_output"] is None
        assert result["blind_review_policy"] == "hide_agent_outputs_by_default"

    def test_agent_output_shown_after_reveal(self, engine, reviewer, workspace) -> None:
        """Agent output is included when ai_revealed=True despite hide policy."""
        schema_id = _create_task_schema(
            engine,
            workspace,
            blind_review_policy="hide_agent_outputs_by_default",
        )
        tasks = _create_tasks_with_schema(engine, workspace, schema_id)
        _create_agent_output(
            engine,
            workspace,
            tasks[0].record_id,
            schema_id,
            labels={"sentiment": "negative"},
        )

        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None

        # Simulate reveal by manually setting ai_revealed
        with engine.connect() as conn:
            conn.execute(
                text("UPDATE review_tasks SET ai_revealed = 1 WHERE id = :id"),
                {"id": claimed["id"]},
            )
            conn.commit()

        # Re-read the task with ai_revealed=True
        claimed["ai_revealed"] = True

        result = apply_blind_review_policy(engine, claimed)
        assert result["agent_output"] is not None
        assert result["agent_output"]["labels"] == {"sentiment": "negative"}
        assert result["blind_review_policy"] == "hide_agent_outputs_by_default"

    def test_no_agent_output_exists(self, engine, reviewer, workspace) -> None:
        """When no agent output exists, agent_output is None regardless of policy."""
        schema_id = _create_task_schema(
            engine,
            workspace,
            blind_review_policy="hide_agent_outputs_by_default",
        )
        _create_tasks_with_schema(engine, workspace, schema_id)

        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None

        result = apply_blind_review_policy(engine, claimed)
        assert result["agent_output"] is None


class TestBlindReviewPolicyShow:
    """Tests for show_agent_outputs policy."""

    def test_agent_output_always_included(self, engine, reviewer, workspace) -> None:
        """Agent output is always included when policy is show_agent_outputs."""
        schema_id = _create_task_schema(
            engine,
            workspace,
            blind_review_policy="show_agent_outputs",
        )
        tasks = _create_tasks_with_schema(engine, workspace, schema_id)
        _create_agent_output(
            engine,
            workspace,
            tasks[0].record_id,
            schema_id,
            labels={"sentiment": "positive"},
        )

        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None
        assert claimed["ai_revealed"] is False  # Not manually revealed

        result = apply_blind_review_policy(engine, claimed)
        assert result["agent_output"] is not None
        assert result["agent_output"]["labels"] == {"sentiment": "positive"}
        assert result["blind_review_policy"] == "show_agent_outputs"

    def test_show_policy_without_agent_output(
        self, engine, reviewer, workspace
    ) -> None:
        """show_agent_outputs returns None when no agent output exists."""
        schema_id = _create_task_schema(
            engine,
            workspace,
            blind_review_policy="show_agent_outputs",
        )
        _create_tasks_with_schema(engine, workspace, schema_id)

        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None

        result = apply_blind_review_policy(engine, claimed)
        assert result["agent_output"] is None
        assert result["blind_review_policy"] == "show_agent_outputs"


class TestBlindReviewPolicyNoAgent:
    """Tests for no_agent policy."""

    def test_agent_output_never_shown(self, engine, reviewer, workspace) -> None:
        """Agent output is never included when policy is no_agent, even if it exists."""
        schema_id = _create_task_schema(
            engine,
            workspace,
            blind_review_policy="no_agent",
        )
        tasks = _create_tasks_with_schema(engine, workspace, schema_id)
        _create_agent_output(engine, workspace, tasks[0].record_id, schema_id)

        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None

        result = apply_blind_review_policy(engine, claimed)
        assert result["agent_output"] is None
        assert result["blind_review_policy"] == "no_agent"

    def test_no_agent_even_when_revealed(self, engine, reviewer, workspace) -> None:
        """Even with ai_revealed=True, no_agent policy blocks output."""
        schema_id = _create_task_schema(
            engine,
            workspace,
            blind_review_policy="no_agent",
        )
        tasks = _create_tasks_with_schema(engine, workspace, schema_id)
        _create_agent_output(engine, workspace, tasks[0].record_id, schema_id)

        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None

        # Force ai_revealed True
        claimed["ai_revealed"] = True

        result = apply_blind_review_policy(engine, claimed)
        assert result["agent_output"] is None
        assert result["blind_review_policy"] == "no_agent"


class TestBlindReviewPolicyFallback:
    """Tests for fallback behavior when task schema is missing."""

    def test_missing_schema_defaults_to_hide(self, engine, reviewer, workspace) -> None:
        """Missing task_schema defaults to hide_agent_outputs_by_default."""
        # Create tasks without a corresponding task_schemas row
        dataset_id = uuid.uuid4()
        fake_schema_id = uuid.uuid4()
        task_id = uuid.uuid4()
        record_id = uuid.uuid4()
        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO review_tasks "
                    "(id, queue_id, record_id, task_schema_id, status, priority, "
                    "workspace_id, dataset_id) "
                    "VALUES (:id, :qid, :rid, :sid, 'available', 0, :ws, :ds)"
                ),
                {
                    "id": str(task_id),
                    "qid": QUEUE_ID,
                    "rid": str(record_id),
                    "sid": str(fake_schema_id),
                    "ws": str(workspace.id),
                    "ds": str(dataset_id),
                },
            )
            conn.commit()

        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None

        result = apply_blind_review_policy(engine, claimed)
        # Falls back to hide
        assert result["agent_output"] is None
        assert result["blind_review_policy"] == "hide_agent_outputs_by_default"

"""Unit tests for AI reveal mechanism (RV-002).

Tests cover:
- Successful reveal sets ai_revealed and ai_revealed_at
- Reveal returns agent output data
- Reveal fails for unclaimed task
- Reveal fails for wrong reviewer
- Reveal fails when policy is no_agent
- API endpoint integration
"""

from __future__ import annotations

import json
import uuid

import pytest
from conftest import (
    TEST_SECRET,
    ReviewerData,
    TaskData,
    WorkspaceData,
    insert_reviewer,
)
from fastapi.testclient import TestClient
from sqlalchemy import text

from molabel.app.services.claims import (
    claim_next,
    reveal_ai,
)
from molabel.app.services.session import (
    COOKIE_NAME,
    create_session_token,
    reset_last_active_cache,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

QUEUE_ID = "reveal-ai-q1"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def reviewer(engine, workspace) -> ReviewerData:
    """Insert a reviewer for AI reveal tests."""
    return insert_reviewer(
        engine, workspace, display_name="RevealAlice", avatar_color="#4A90D9"
    )


@pytest.fixture()
def second_reviewer(engine, workspace) -> ReviewerData:
    """Insert a second reviewer for ownership tests."""
    return insert_reviewer(
        engine, workspace, display_name="RevealBob", avatar_color="#E67E22"
    )


@pytest.fixture(autouse=True)
def _cleanup():
    """Reset shared state between tests."""
    reset_last_active_cache()
    yield
    reset_last_active_cache()


def _login(client: TestClient, reviewer: ReviewerData) -> None:
    """Set a valid session cookie for the given reviewer."""
    token = create_session_token(reviewer.id, TEST_SECRET)
    client.cookies.set(COOKIE_NAME, token)


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
                "slug": "reveal-schema",
                "ver": 1,
                "tt": "classification",
                "title": "Reveal Test Schema",
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
                    "INSERT INTO records "
                    "("
                    "id, external_id, stable_fields, payload, "
                    "workspace_id, dataset_id"
                    ") "
                    "VALUES ("
                    ":id, :external_id, :stable_fields, :payload, "
                    ":workspace_id, :dataset_id"
                    ")"
                ),
                {
                    "id": str(record_id),
                    "external_id": f"reveal-record-{task_id}",
                    "stable_fields": json.dumps(
                        {"record_id": f"reveal-record-{task_id}"}
                    ),
                    "payload": json.dumps({"text": f"Reveal text for {task_id}"}),
                    "workspace_id": str(workspace.id),
                    "dataset_id": str(dataset_id),
                },
            )
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
# RV-002: AI Reveal Mechanism — Service layer tests
# ===================================================================


class TestRevealAIService:
    """Tests for the reveal_ai service function."""

    def test_reveal_sets_flags(self, engine, reviewer, workspace) -> None:
        """reveal_ai sets ai_revealed=True and ai_revealed_at on the task."""
        schema_id = _create_task_schema(
            engine,
            workspace,
            blind_review_policy="hide_agent_outputs_by_default",
        )
        tasks = _create_tasks_with_schema(engine, workspace, schema_id)
        _create_agent_output(engine, workspace, tasks[0].record_id, schema_id)

        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None
        assert claimed["ai_revealed"] is False

        result = reveal_ai(engine, uuid.UUID(claimed["id"]), reviewer.id)
        assert result is not None
        assert result["ai_revealed"] is True
        assert result["ai_revealed_at"] is not None

    def test_reveal_returns_agent_output(self, engine, reviewer, workspace) -> None:
        """reveal_ai returns the agent output data after revealing."""
        schema_id = _create_task_schema(
            engine,
            workspace,
            blind_review_policy="hide_agent_outputs_by_default",
        )
        tasks = _create_tasks_with_schema(engine, workspace, schema_id)
        agent_labels = {"sentiment": "negative", "confidence": 0.95}
        _create_agent_output(
            engine, workspace, tasks[0].record_id, schema_id, labels=agent_labels
        )

        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None

        result = reveal_ai(engine, uuid.UUID(claimed["id"]), reviewer.id)
        assert result is not None
        assert result["agent_output"] is not None
        assert result["agent_output"]["labels"] == agent_labels

    def test_reveal_returns_policy(self, engine, reviewer, workspace) -> None:
        """reveal_ai includes the blind_review_policy in the response."""
        schema_id = _create_task_schema(
            engine,
            workspace,
            blind_review_policy="hide_agent_outputs_by_default",
        )
        tasks = _create_tasks_with_schema(engine, workspace, schema_id)
        _create_agent_output(engine, workspace, tasks[0].record_id, schema_id)

        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None

        result = reveal_ai(engine, uuid.UUID(claimed["id"]), reviewer.id)
        assert result is not None
        assert result["blind_review_policy"] == "hide_agent_outputs_by_default"
        assert result["record_external_id"] is not None
        assert result["record_view"] is not None
        assert result["record_view"]["payload"]["text"].startswith("Reveal text for ")
        assert result["record_text"].startswith("Reveal text for ")

    def test_reveal_idempotent(self, engine, reviewer, workspace) -> None:
        """Calling reveal_ai twice succeeds and returns the same data."""
        schema_id = _create_task_schema(
            engine,
            workspace,
            blind_review_policy="hide_agent_outputs_by_default",
        )
        tasks = _create_tasks_with_schema(engine, workspace, schema_id)
        _create_agent_output(engine, workspace, tasks[0].record_id, schema_id)

        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None

        result1 = reveal_ai(engine, uuid.UUID(claimed["id"]), reviewer.id)
        assert result1 is not None

        result2 = reveal_ai(engine, uuid.UUID(claimed["id"]), reviewer.id)
        assert result2 is not None
        assert result2["ai_revealed"] is True

    def test_reveal_wrong_reviewer_fails(
        self, engine, reviewer, second_reviewer, workspace
    ) -> None:
        """reveal_ai returns None when task is not claimed by the reviewer."""
        schema_id = _create_task_schema(engine, workspace)
        tasks = _create_tasks_with_schema(engine, workspace, schema_id)
        _create_agent_output(engine, workspace, tasks[0].record_id, schema_id)

        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None

        result = reveal_ai(engine, uuid.UUID(claimed["id"]), second_reviewer.id)
        assert result is None

    def test_reveal_nonexistent_task_fails(self, engine, reviewer, workspace) -> None:
        """reveal_ai returns None for a non-existent task ID."""
        result = reveal_ai(engine, uuid.uuid4(), reviewer.id)
        assert result is None

    def test_reveal_blocked_by_no_agent_policy(
        self, engine, reviewer, workspace
    ) -> None:
        """reveal_ai returns None when policy is no_agent."""
        schema_id = _create_task_schema(
            engine,
            workspace,
            blind_review_policy="no_agent",
        )
        tasks = _create_tasks_with_schema(engine, workspace, schema_id)
        _create_agent_output(engine, workspace, tasks[0].record_id, schema_id)

        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None

        result = reveal_ai(engine, uuid.UUID(claimed["id"]), reviewer.id)
        assert result is None

    def test_reveal_allowed_for_show_policy(self, engine, reviewer, workspace) -> None:
        """reveal_ai works when policy is show_agent_outputs (already visible)."""
        schema_id = _create_task_schema(
            engine,
            workspace,
            blind_review_policy="show_agent_outputs",
        )
        tasks = _create_tasks_with_schema(engine, workspace, schema_id)
        _create_agent_output(engine, workspace, tasks[0].record_id, schema_id)

        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None

        result = reveal_ai(engine, uuid.UUID(claimed["id"]), reviewer.id)
        assert result is not None
        assert result["ai_revealed"] is True
        assert result["agent_output"] is not None

    def test_reveal_scrubs_truth_bearing_fields(
        self, engine, reviewer, workspace
    ) -> None:
        """Reveal response must not expose source/gold labels via record context."""
        schema_id = _create_task_schema(
            engine,
            workspace,
            blind_review_policy="hide_agent_outputs_by_default",
        )
        tasks = _create_tasks_with_schema(engine, workspace, schema_id)
        _create_agent_output(engine, workspace, tasks[0].record_id, schema_id)
        with engine.connect() as conn:
            conn.execute(
                text(
                    """
                    UPDATE records
                    SET payload = :payload
                    WHERE id = :record_id
                    """
                ),
                {
                    "record_id": str(tasks[0].record_id),
                    "payload": json.dumps(
                        {
                            "text": "Reveal-safe text",
                            "source_label": "positive",
                            "nested": {"gold_label": "negative"},
                        }
                    ),
                },
            )
            conn.commit()

        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None

        result = reveal_ai(engine, uuid.UUID(claimed["id"]), reviewer.id)
        assert result is not None
        assert result["record_text"] == "Reveal-safe text"
        assert result["record_view"] is not None
        payload = result["record_view"]["payload"]
        assert payload["text"] == "Reveal-safe text"
        assert "source_label" not in payload
        assert "gold_label" not in payload["nested"]

    def test_reveal_with_no_agent_output(self, engine, reviewer, workspace) -> None:
        """reveal_ai succeeds but agent_output is None when no output exists."""
        schema_id = _create_task_schema(
            engine,
            workspace,
            blind_review_policy="hide_agent_outputs_by_default",
        )
        _create_tasks_with_schema(engine, workspace, schema_id)

        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None

        result = reveal_ai(engine, uuid.UUID(claimed["id"]), reviewer.id)
        assert result is not None
        assert result["ai_revealed"] is True
        assert result["agent_output"] is None


# ===================================================================
# RV-002: AI Reveal Mechanism — API endpoint tests
# ===================================================================


class TestRevealAIEndpoint:
    """Tests for the POST /review-tasks/{id}/reveal-ai endpoint."""

    def test_reveal_api_success(self, client, engine, reviewer, workspace) -> None:
        """POST /review-tasks/{id}/reveal-ai reveals agent output."""
        _login(client, reviewer)

        schema_id = _create_task_schema(engine, workspace)
        tasks = _create_tasks_with_schema(engine, workspace, schema_id)
        _create_agent_output(
            engine,
            workspace,
            tasks[0].record_id,
            schema_id,
            labels={"sentiment": "positive"},
        )

        # Claim
        resp = client.post(f"/api/v1/queues/{QUEUE_ID}/claim")
        assert resp.status_code == 200
        task_id = resp.json()["task"]["id"]
        assert resp.json()["task"]["agent_output"] is None  # Hidden by policy

        # Reveal
        resp = client.post(f"/api/v1/review-tasks/{task_id}/reveal-ai")
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "ai_revealed"
        assert data["task"]["ai_revealed"] is True
        assert data["task"]["ai_revealed_at"] is not None
        assert data["task"]["agent_output"] is not None
        assert data["task"]["agent_output"]["labels"] == {"sentiment": "positive"}

    def test_reveal_api_no_agent_policy_409(
        self, client, engine, reviewer, workspace
    ) -> None:
        """POST /review-tasks/{id}/reveal-ai returns 409 for no_agent policy."""
        _login(client, reviewer)

        schema_id = _create_task_schema(
            engine, workspace, blind_review_policy="no_agent"
        )
        tasks = _create_tasks_with_schema(engine, workspace, schema_id)
        _create_agent_output(engine, workspace, tasks[0].record_id, schema_id)

        # Claim
        resp = client.post(f"/api/v1/queues/{QUEUE_ID}/claim")
        assert resp.status_code == 200
        task_id = resp.json()["task"]["id"]

        # Reveal should fail
        resp = client.post(f"/api/v1/review-tasks/{task_id}/reveal-ai")
        assert resp.status_code == 409

    def test_reveal_api_requires_auth(self, client) -> None:
        """POST /review-tasks/{id}/reveal-ai returns 401 without session."""
        fake_id = uuid.uuid4()
        resp = client.post(f"/api/v1/review-tasks/{fake_id}/reveal-ai")
        assert resp.status_code == 401

    def test_reveal_api_wrong_reviewer_409(
        self, client, engine, reviewer, second_reviewer, workspace
    ) -> None:
        """POST /review-tasks/{id}/reveal-ai returns 409 for wrong reviewer."""
        _login(client, reviewer)

        schema_id = _create_task_schema(engine, workspace)
        tasks = _create_tasks_with_schema(engine, workspace, schema_id)
        _create_agent_output(engine, workspace, tasks[0].record_id, schema_id)

        # Claim as Alice
        resp = client.post(f"/api/v1/queues/{QUEUE_ID}/claim")
        assert resp.status_code == 200
        task_id = resp.json()["task"]["id"]

        # Try to reveal as Bob
        _login(client, second_reviewer)
        resp = client.post(f"/api/v1/review-tasks/{task_id}/reveal-ai")
        assert resp.status_code == 409

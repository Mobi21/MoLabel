"""Unit tests for review event append-only corrections (RV-004).

Tests cover:
- Correction creates a new event with supersedes_event_id
- Original event is preserved exactly as-is
- Correction includes previous_labels from the superseded event
- Correction fails without an existing review event
- Correction fails for wrong reviewer
- Multiple corrections form a chain of supersedes_event_id
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
    submit_correction,
    submit_review,
)
from molabel.app.services.session import (
    COOKIE_NAME,
    create_session_token,
    reset_last_active_cache,
)
from molabel.core.types import ReviewDecision

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

QUEUE_ID = "correction-q1"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def reviewer(engine, workspace) -> ReviewerData:
    """Insert a reviewer for correction tests."""
    return insert_reviewer(
        engine, workspace, display_name="CorrAlice", avatar_color="#4A90D9"
    )


@pytest.fixture()
def second_reviewer(engine, workspace) -> ReviewerData:
    """Insert a second reviewer for ownership tests."""
    return insert_reviewer(
        engine, workspace, display_name="CorrBob", avatar_color="#E67E22"
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
) -> uuid.UUID:
    """Insert a task schema for correction tests."""
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
                "slug": "correction-schema",
                "ver": 1,
                "tt": "classification",
                "title": "Correction Test Schema",
                "lf": json.dumps({"sentiment": {"type": "categorical"}}),
                "brp": "hide_agent_outputs_by_default",
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
    count: int = 3,
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


def _review_events_for_task(engine, task_id: uuid.UUID) -> list:
    """Fetch all review events for a task, ordered by created_at."""
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT id, review_task_id, record_id, task_schema_id, "
                "task_schema_version, reviewer_id, source, decision, labels, "
                "rationale, ai_was_revealed, supersedes_event_id, "
                "previous_labels, workspace_id, created_at "
                "FROM review_events WHERE review_task_id = :task_id "
                "ORDER BY created_at ASC"
            ),
            {"task_id": str(task_id)},
        ).all()


# ===================================================================
# RV-004: Append-only corrections — Service layer tests
# ===================================================================


class TestSubmitCorrectionService:
    """Tests for the submit_correction service function."""

    def test_correction_creates_new_event(self, engine, reviewer, workspace) -> None:
        """submit_correction creates a new event, not an update."""
        schema_id = _create_task_schema(engine, workspace)
        _create_tasks_with_schema(engine, workspace, schema_id)

        # Claim and submit original review
        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None
        task_id = uuid.UUID(claimed["id"])

        submit_review(
            engine,
            task_id,
            reviewer.id,
            {"sentiment": "positive"},
            ReviewDecision.accept,
            "Initial review",
        )

        # Verify one event exists
        events = _review_events_for_task(engine, task_id)
        assert len(events) == 1

        # Submit correction
        correction = submit_correction(
            engine,
            task_id,
            reviewer.id,
            {"sentiment": "negative"},
            ReviewDecision.correct,
            "Changed my mind after re-reading",
        )

        assert correction is not None
        assert correction["labels"] == {"sentiment": "negative"}
        assert correction["decision"] == ReviewDecision.correct.value
        assert correction["rationale"] == "Changed my mind after re-reading"

        # Now there should be 2 events
        events = _review_events_for_task(engine, task_id)
        assert len(events) == 2

    def test_correction_has_supersedes_event_id(
        self, engine, reviewer, workspace
    ) -> None:
        """Correction event has supersedes_event_id pointing to the original."""
        schema_id = _create_task_schema(engine, workspace)
        _create_tasks_with_schema(engine, workspace, schema_id)

        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None
        task_id = uuid.UUID(claimed["id"])

        submit_review(
            engine,
            task_id,
            reviewer.id,
            {"sentiment": "positive"},
            ReviewDecision.accept,
            "Initial",
        )

        events_before = _review_events_for_task(engine, task_id)
        original_event_id = events_before[0][0]  # id of original event

        correction = submit_correction(
            engine,
            task_id,
            reviewer.id,
            {"sentiment": "negative"},
            ReviewDecision.correct,
        )

        assert correction is not None
        assert correction["supersedes_event_id"] == original_event_id

    def test_original_event_preserved(self, engine, reviewer, workspace) -> None:
        """The original review event is never modified by a correction."""
        schema_id = _create_task_schema(engine, workspace)
        _create_tasks_with_schema(engine, workspace, schema_id)

        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None
        task_id = uuid.UUID(claimed["id"])

        submit_review(
            engine,
            task_id,
            reviewer.id,
            {"sentiment": "positive"},
            ReviewDecision.accept,
            "Original rationale",
        )

        # Snapshot the original event
        events_before = _review_events_for_task(engine, task_id)
        original = events_before[0]
        original_id = original[0]
        original_labels = original[8]
        original_decision = original[7]
        original_rationale = original[9]

        # Submit correction
        submit_correction(
            engine,
            task_id,
            reviewer.id,
            {"sentiment": "negative"},
            ReviewDecision.correct,
            "New rationale",
        )

        # Re-read the original event and verify it's unchanged
        events_after = _review_events_for_task(engine, task_id)
        assert len(events_after) == 2

        # First event should be unchanged
        preserved = events_after[0]
        assert preserved[0] == original_id
        assert preserved[8] == original_labels
        assert preserved[7] == original_decision
        assert preserved[9] == original_rationale
        # Original should have no supersedes_event_id
        assert preserved[11] is None

    def test_correction_includes_previous_labels(
        self, engine, reviewer, workspace
    ) -> None:
        """Correction event stores previous_labels from the superseded event."""
        schema_id = _create_task_schema(engine, workspace)
        _create_tasks_with_schema(engine, workspace, schema_id)

        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None
        task_id = uuid.UUID(claimed["id"])

        submit_review(
            engine,
            task_id,
            reviewer.id,
            {"sentiment": "positive", "score": 0.9},
            ReviewDecision.accept,
        )

        correction = submit_correction(
            engine,
            task_id,
            reviewer.id,
            {"sentiment": "negative", "score": 0.3},
            ReviewDecision.correct,
        )

        assert correction is not None
        assert correction["previous_labels"] == {
            "sentiment": "positive",
            "score": 0.9,
        }

    def test_correction_chain(self, engine, reviewer, workspace) -> None:
        """Multiple corrections form a chain via supersedes_event_id."""
        schema_id = _create_task_schema(engine, workspace)
        _create_tasks_with_schema(engine, workspace, schema_id)

        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None
        task_id = uuid.UUID(claimed["id"])

        # Original review
        submit_review(
            engine,
            task_id,
            reviewer.id,
            {"sentiment": "positive"},
            ReviewDecision.accept,
        )

        # First correction
        corr1 = submit_correction(
            engine,
            task_id,
            reviewer.id,
            {"sentiment": "neutral"},
            ReviewDecision.correct,
            "First correction",
        )
        assert corr1 is not None

        # Second correction supersedes the first correction
        corr2 = submit_correction(
            engine,
            task_id,
            reviewer.id,
            {"sentiment": "negative"},
            ReviewDecision.correct,
            "Second correction",
        )
        assert corr2 is not None

        # Verify the chain
        events = _review_events_for_task(engine, task_id)
        assert len(events) == 3

        original_id = events[0][0]
        corr1_id = events[1][0]

        # First correction supersedes original
        assert corr1["supersedes_event_id"] == original_id

        # Second correction supersedes first correction
        assert corr2["supersedes_event_id"] == corr1_id

    def test_correction_fails_without_prior_event(
        self, engine, reviewer, workspace
    ) -> None:
        """submit_correction returns None if no prior review event exists."""
        schema_id = _create_task_schema(engine, workspace)
        _create_tasks_with_schema(engine, workspace, schema_id)

        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None
        task_id = uuid.UUID(claimed["id"])

        # No submit_review was called, so no review event exists
        result = submit_correction(
            engine,
            task_id,
            reviewer.id,
            {"sentiment": "negative"},
            ReviewDecision.correct,
        )
        assert result is None

    def test_correction_fails_for_wrong_reviewer(
        self, engine, reviewer, second_reviewer, workspace
    ) -> None:
        """submit_correction returns None if task is not owned by reviewer."""
        schema_id = _create_task_schema(engine, workspace)
        _create_tasks_with_schema(engine, workspace, schema_id)

        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None
        task_id = uuid.UUID(claimed["id"])

        submit_review(
            engine,
            task_id,
            reviewer.id,
            {"sentiment": "positive"},
            ReviewDecision.accept,
        )

        # Bob tries to correct Alice's task
        result = submit_correction(
            engine,
            task_id,
            second_reviewer.id,
            {"sentiment": "negative"},
            ReviewDecision.correct,
        )
        assert result is None

    def test_correction_fails_for_nonexistent_task(
        self, engine, reviewer, workspace
    ) -> None:
        """submit_correction returns None for a non-existent task ID."""
        result = submit_correction(
            engine,
            uuid.uuid4(),
            reviewer.id,
            {"sentiment": "negative"},
            ReviewDecision.correct,
        )
        assert result is None

    def test_correction_preserves_source_as_human(
        self, engine, reviewer, workspace
    ) -> None:
        """Correction events have source='human'."""
        schema_id = _create_task_schema(engine, workspace)
        _create_tasks_with_schema(engine, workspace, schema_id)

        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None
        task_id = uuid.UUID(claimed["id"])

        submit_review(
            engine,
            task_id,
            reviewer.id,
            {"sentiment": "positive"},
            ReviewDecision.accept,
        )

        correction = submit_correction(
            engine,
            task_id,
            reviewer.id,
            {"sentiment": "negative"},
            ReviewDecision.correct,
        )
        assert correction is not None
        assert correction["source"] == "human"


# ===================================================================
# RV-004: Append-only corrections — API endpoint tests
# ===================================================================


class TestCorrectionEndpoint:
    """Tests for the POST /review-tasks/{id}/correct endpoint."""

    def test_correction_api_success(self, client, engine, reviewer, workspace) -> None:
        """POST /review-tasks/{id}/correct creates a correction event."""
        _login(client, reviewer)

        schema_id = _create_task_schema(engine, workspace)
        _create_tasks_with_schema(engine, workspace, schema_id)

        # Claim and submit
        resp = client.post(f"/api/v1/queues/{QUEUE_ID}/claim")
        assert resp.status_code == 200
        task_id = resp.json()["task"]["id"]

        resp = client.post(
            f"/api/v1/review-tasks/{task_id}/submit",
            json={
                "labels": {"sentiment": "positive"},
                "decision": "accept",
                "rationale": "Looks good",
                "auto_claim_next": False,
            },
        )
        assert resp.status_code == 200

        # Submit correction
        resp = client.post(
            f"/api/v1/review-tasks/{task_id}/correct",
            json={
                "labels": {"sentiment": "negative"},
                "decision": "correct",
                "rationale": "Actually, this is negative",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "correction_submitted"
        assert data["event"]["labels"] == {"sentiment": "negative"}
        assert data["event"]["decision"] == "correct"
        assert data["event"]["rationale"] == "Actually, this is negative"
        assert data["event"]["supersedes_event_id"] is not None
        assert data["event"]["source"] == "human"

    def test_correction_api_preserves_original(
        self, client, engine, reviewer, workspace
    ) -> None:
        """API correction does not modify the original event."""
        _login(client, reviewer)

        schema_id = _create_task_schema(engine, workspace)
        _create_tasks_with_schema(engine, workspace, schema_id)

        # Claim and submit
        resp = client.post(f"/api/v1/queues/{QUEUE_ID}/claim")
        task_id = resp.json()["task"]["id"]

        client.post(
            f"/api/v1/review-tasks/{task_id}/submit",
            json={
                "labels": {"sentiment": "positive"},
                "decision": "accept",
                "auto_claim_next": False,
            },
        )

        # Get original events
        events_before = _review_events_for_task(engine, uuid.UUID(task_id))
        assert len(events_before) == 1
        original_event = events_before[0]

        # Submit correction via API
        client.post(
            f"/api/v1/review-tasks/{task_id}/correct",
            json={
                "labels": {"sentiment": "negative"},
                "decision": "correct",
            },
        )

        # Verify original event is unchanged
        events_after = _review_events_for_task(engine, uuid.UUID(task_id))
        assert len(events_after) == 2
        preserved = events_after[0]
        assert preserved[0] == original_event[0]  # same id
        assert preserved[8] == original_event[8]  # same labels
        assert preserved[7] == original_event[7]  # same decision
        assert preserved[11] is None  # no supersedes

    def test_correction_api_no_prior_event_409(
        self, client, engine, reviewer, workspace
    ) -> None:
        """POST /review-tasks/{id}/correct returns 409 without prior event."""
        _login(client, reviewer)

        schema_id = _create_task_schema(engine, workspace)
        _create_tasks_with_schema(engine, workspace, schema_id)

        # Claim but don't submit
        resp = client.post(f"/api/v1/queues/{QUEUE_ID}/claim")
        task_id = resp.json()["task"]["id"]

        resp = client.post(
            f"/api/v1/review-tasks/{task_id}/correct",
            json={
                "labels": {"sentiment": "negative"},
                "decision": "correct",
            },
        )
        assert resp.status_code == 409

    def test_correction_api_requires_auth(self, client) -> None:
        """POST /review-tasks/{id}/correct returns 401 without session."""
        fake_id = uuid.uuid4()
        resp = client.post(
            f"/api/v1/review-tasks/{fake_id}/correct",
            json={
                "labels": {"sentiment": "negative"},
                "decision": "correct",
            },
        )
        assert resp.status_code == 401

    def test_correction_api_wrong_reviewer_409(
        self, client, engine, reviewer, second_reviewer, workspace
    ) -> None:
        """POST /review-tasks/{id}/correct returns 409 for wrong reviewer."""
        _login(client, reviewer)

        schema_id = _create_task_schema(engine, workspace)
        _create_tasks_with_schema(engine, workspace, schema_id)

        # Alice claims and submits
        resp = client.post(f"/api/v1/queues/{QUEUE_ID}/claim")
        task_id = resp.json()["task"]["id"]

        client.post(
            f"/api/v1/review-tasks/{task_id}/submit",
            json={
                "labels": {"sentiment": "positive"},
                "decision": "accept",
                "auto_claim_next": False,
            },
        )

        # Bob tries to correct
        _login(client, second_reviewer)
        resp = client.post(
            f"/api/v1/review-tasks/{task_id}/correct",
            json={
                "labels": {"sentiment": "negative"},
                "decision": "correct",
            },
        )
        assert resp.status_code == 409

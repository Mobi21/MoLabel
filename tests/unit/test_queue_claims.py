"""Unit tests for queue claim model (SE-006 through SE-010).

Tests cover:
- SE-006: Atomic queue claim preventing double-assignment
- SE-007: Claim timeout expiry
- SE-008: Claim expiry notification via X-MoLabel-Notification header
- SE-009: Same-profile multi-session handling (draft last-write-wins)
- SE-010: Mission control reviewer visibility (active/idle/offline)
"""

from __future__ import annotations

import json
import uuid

import pytest
from conftest import TEST_SECRET, ReviewerData, TaskData, insert_reviewer
from fastapi.testclient import TestClient
from sqlalchemy import text

from molabel.app.services.claims import (
    claim_next,
    expire_claims,
    get_expired_claims,
    get_queue_status,
    get_reviewer_visibility,
    pop_expired_notifications,
    release_claim,
    reset_expired_notifications,
    save_draft,
    skip_task,
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

QUEUE_ID = "sentiment-review-q1"

# SQL for backdating claims in tests (avoids line-length issues).
_BACKDATE_CLAIM_BY_ID = (
    "UPDATE review_tasks SET claimed_at = datetime('now', '-60 minutes') WHERE id = :id"
)
_BACKDATE_CLAIM_BY_REVIEWER = (
    "UPDATE review_tasks "
    "SET claimed_at = datetime('now', '-60 minutes') "
    "WHERE claimed_by = :rid AND status = 'claimed'"
)


# ---------------------------------------------------------------------------
# Fixtures specific to queue claim tests
# ---------------------------------------------------------------------------

# engine, workspace, reviewer, second_reviewer, app, client, and
# _clear_debounce_cache fixtures are provided by conftest.py.
# The conftest reviewer uses default name "Test Reviewer"; queue tests
# override with "Alice" and "Bob" below.


@pytest.fixture()
def reviewer(engine, workspace) -> ReviewerData:
    """Insert the Alice reviewer for queue tests."""
    return insert_reviewer(
        engine, workspace, display_name="Alice", avatar_color="#4A90D9"
    )


@pytest.fixture()
def second_reviewer(engine, workspace) -> ReviewerData:
    """Insert the Bob reviewer for queue tests."""
    return insert_reviewer(
        engine, workspace, display_name="Bob", avatar_color="#E67E22"
    )


@pytest.fixture()
def idle_reviewer(engine, workspace) -> ReviewerData:
    """A reviewer whose last_active_at is 15 minutes ago (idle)."""
    return insert_reviewer(
        engine,
        workspace,
        display_name="Charlie",
        avatar_color="#27AE60",
        last_active_at_expr="datetime('now', '-15 minutes')",
    )


@pytest.fixture()
def offline_reviewer(engine, workspace) -> ReviewerData:
    """A reviewer whose last_active_at is 60 minutes ago (offline)."""
    return insert_reviewer(
        engine,
        workspace,
        display_name="Diana",
        avatar_color="#9B59B6",
        last_active_at_expr="datetime('now', '-60 minutes')",
    )


def _create_tasks(
    engine, workspace, *, count: int = 5, queue_id: str = QUEUE_ID, priority: int = 0
) -> list[TaskData]:
    """Insert test review tasks."""
    schema_id = uuid.uuid4()
    dataset_id = uuid.uuid4()
    tasks = []
    with engine.connect() as conn:
        for _i in range(count):
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
                    "external_id": f"queue-record-{task_id}",
                    "stable_fields": json.dumps(
                        {"record_id": f"queue-record-{task_id}"}
                    ),
                    "payload": json.dumps({"text": f"Queue text for {task_id}"}),
                    "workspace_id": str(workspace.id),
                    "dataset_id": str(dataset_id),
                },
            )
            conn.execute(
                text(
                    "INSERT INTO review_tasks "
                    "(id, queue_id, record_id, task_schema_id, status, priority, "
                    "workspace_id, dataset_id) "
                    "VALUES (:id, :qid, :rid, :sid, 'available', :pri, :ws, :ds)"
                ),
                {
                    "id": str(task_id),
                    "qid": queue_id,
                    "rid": str(record_id),
                    "sid": str(schema_id),
                    "pri": priority,
                    "ws": str(workspace.id),
                    "ds": str(dataset_id),
                },
            )
            tasks.append(
                TaskData(
                    id=task_id,
                    queue_id=queue_id,
                    record_id=record_id,
                    task_schema_id=schema_id,
                    workspace_id=workspace.id,
                    dataset_id=dataset_id,
                    priority=priority,
                )
            )
        conn.commit()
    return tasks


def _insert_task_schema(
    engine,
    workspace,
    *,
    schema_id: uuid.UUID,
    slug: str,
    label_fields: list[dict[str, object]],
) -> None:
    with engine.connect() as conn:
        conn.execute(
            text(
                """
                INSERT INTO task_schemas (
                    id, task_schema_slug, version, task_type, title, instructions,
                    label_fields, blind_review_policy, workspace_id
                ) VALUES (
                    :id, :slug, 1, 'classification', :title, :instructions,
                    :label_fields, 'hide_agent_outputs_by_default', :workspace_id
                )
                """
            ),
            {
                "id": str(schema_id),
                "slug": slug,
                "title": slug,
                "instructions": f"Schema for {slug}",
                "label_fields": json.dumps(label_fields),
                "workspace_id": str(workspace.id),
            },
        )
        conn.commit()


def _create_task_with_schema(
    engine,
    workspace,
    *,
    schema_id: uuid.UUID,
    payload: dict[str, object],
    queue_id: str = QUEUE_ID,
) -> TaskData:
    dataset_id = uuid.uuid4()
    task_id = uuid.uuid4()
    record_id = uuid.uuid4()
    with engine.connect() as conn:
        conn.execute(
            text(
                """
                INSERT INTO records (
                    id, external_id, stable_fields, payload, workspace_id, dataset_id
                ) VALUES (
                    :id, :external_id, :stable_fields, :payload,
                    :workspace_id, :dataset_id
                )
                """
            ),
            {
                "id": str(record_id),
                "external_id": f"structured-record-{task_id}",
                "stable_fields": json.dumps(
                    {"record_id": f"structured-record-{task_id}"}
                ),
                "payload": json.dumps(payload),
                "workspace_id": str(workspace.id),
                "dataset_id": str(dataset_id),
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO review_tasks (
                    id, queue_id, record_id, task_schema_id, status, priority,
                    workspace_id, dataset_id
                ) VALUES (
                    :id, :queue_id, :record_id, :task_schema_id, 'available', 0,
                    :workspace_id, :dataset_id
                )
                """
            ),
            {
                "id": str(task_id),
                "queue_id": queue_id,
                "record_id": str(record_id),
                "task_schema_id": str(schema_id),
                "workspace_id": str(workspace.id),
                "dataset_id": str(dataset_id),
            },
        )
        conn.commit()
    return TaskData(
        id=task_id,
        queue_id=queue_id,
        record_id=record_id,
        task_schema_id=schema_id,
        workspace_id=workspace.id,
        dataset_id=dataset_id,
        priority=0,
    )


@pytest.fixture()
def tasks(engine, workspace) -> list[TaskData]:
    """Insert 5 test review tasks."""
    return _create_tasks(engine, workspace)


@pytest.fixture(autouse=True)
def _cleanup():
    """Reset shared state between tests."""
    reset_last_active_cache()
    reset_expired_notifications()
    yield
    reset_last_active_cache()
    reset_expired_notifications()


def _login(client: TestClient, reviewer: ReviewerData) -> None:
    """Set a valid session cookie for the given reviewer."""
    token = create_session_token(reviewer.id, TEST_SECRET)
    client.cookies.set(COOKIE_NAME, token)


def _review_events_for_task(engine, task_id: uuid.UUID):
    """Fetch review events created for a task."""
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT id, review_task_id, record_id, task_schema_id, "
                "task_schema_version, reviewer_id, source, decision, labels, "
                "rationale, ai_was_revealed, workspace_id "
                "FROM review_events WHERE review_task_id = :task_id "
                "ORDER BY created_at ASC"
            ),
            {"task_id": str(task_id)},
        ).all()


# ===================================================================
# SE-006: Atomic queue claim
# ===================================================================


class TestAtomicClaim:
    """Tests for atomic queue claim (SE-006)."""

    def test_claim_next_returns_task(self, engine, reviewer, tasks) -> None:
        """claim_next returns the highest-priority, oldest available task."""
        result = claim_next(engine, QUEUE_ID, reviewer.id)
        assert result is not None
        assert result["status"] == "claimed"
        assert result["claimed_by"] == str(reviewer.id)
        assert result["queue_id"] == QUEUE_ID

    def test_claim_next_empty_queue(self, engine, reviewer) -> None:
        """claim_next returns None when the queue is empty."""
        result = claim_next(engine, QUEUE_ID, reviewer.id)
        assert result is None

    def test_claim_prevents_double_assignment(
        self, engine, reviewer, second_reviewer, tasks
    ) -> None:
        """Two reviewers claiming from the same queue get different tasks (SE-006)."""
        task_a = claim_next(engine, QUEUE_ID, reviewer.id)
        task_b = claim_next(engine, QUEUE_ID, second_reviewer.id)

        assert task_a is not None
        assert task_b is not None
        assert task_a["id"] != task_b["id"]
        assert task_a["claimed_by"] == str(reviewer.id)
        assert task_b["claimed_by"] == str(second_reviewer.id)

    def test_claim_exhausts_queue(self, engine, reviewer, workspace) -> None:
        """Claims drain the queue until empty."""
        _create_tasks(engine, workspace, count=2)
        t1 = claim_next(engine, QUEUE_ID, reviewer.id)
        t2 = claim_next(engine, QUEUE_ID, reviewer.id)
        t3 = claim_next(engine, QUEUE_ID, reviewer.id)

        assert t1 is not None
        assert t2 is not None
        assert t3 is None  # Queue exhausted

    def test_claim_respects_priority(self, engine, reviewer, workspace) -> None:
        """Higher priority tasks are claimed first."""
        _create_tasks(engine, workspace, count=1, priority=0)
        high = _create_tasks(engine, workspace, count=1, priority=10)

        result = claim_next(engine, QUEUE_ID, reviewer.id)
        assert result is not None
        assert result["id"] == str(high[0].id)
        assert result["priority"] == 10

    def test_claim_excludes_already_claimed_records(
        self, engine, reviewer, workspace
    ) -> None:
        """Overlap exclusion: a reviewer cannot re-claim a record they already own."""
        _create_tasks(engine, workspace, count=3)
        # Claim the first task
        t1 = claim_next(engine, QUEUE_ID, reviewer.id)
        assert t1 is not None
        # Subsequent claims should get different records
        t2 = claim_next(engine, QUEUE_ID, reviewer.id)
        assert t2 is not None
        assert t2["record_id"] != t1["record_id"]

    def test_claim_api_endpoint(self, client, reviewer, tasks) -> None:
        """POST /queues/{queue_id}/claim returns a claimed task via API."""
        _login(client, reviewer)
        resp = client.post(f"/api/v1/queues/{QUEUE_ID}/claim")
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "claimed"
        assert data["task"]["status"] == "claimed"
        assert data["task"]["claimed_by"] == str(reviewer.id)
        assert data["task"]["record_external_id"] is not None
        assert data["task"]["record_view"]["payload"]["text"].startswith(
            "Queue text for "
        )
        assert data["task"]["record_text"].startswith("Queue text for ")
        assert data["queue_empty"] is False

    def test_claim_api_uses_token_list_for_record_text(
        self, client, reviewer, engine, workspace
    ) -> None:
        """Tokenized payloads should expose readable joined text to reviewers."""
        _login(client, reviewer)
        schema_id = uuid.uuid4()
        _insert_task_schema(
            engine,
            workspace,
            schema_id=schema_id,
            slug="tokenized-review",
            label_fields=[
                {
                    "name": "stance_label",
                    "field_type": "categorical",
                    "options": ["normal", "offensive", "hatespeech"],
                    "required": True,
                }
            ],
        )
        _create_task_with_schema(
            engine,
            workspace,
            schema_id=schema_id,
            payload={
                "post_id": "post-1",
                "post_tokens": ["<user>", "why", "so", "loud"],
                "annotators": [{"label": "offensive"}],
            },
        )

        resp = client.post(f"/api/v1/queues/{QUEUE_ID}/claim")
        assert resp.status_code == 200
        data = resp.json()
        assert data["task"]["record_text"] == "<user> why so loud"
        assert data["task"]["record_view"]["payload"]["post_tokens"] == [
            "<user>",
            "why",
            "so",
            "loud",
        ]

    def test_claim_api_empty_queue(self, client, reviewer) -> None:
        """POST /queues/{queue_id}/claim returns queue_empty=True for empty queue."""
        _login(client, reviewer)
        resp = client.post(f"/api/v1/queues/{QUEUE_ID}/claim")
        assert resp.status_code == 200
        data = resp.json()
        assert data["queue_empty"] is True
        assert data["task"] is None

    def test_claim_requires_auth(self, client, tasks) -> None:
        """POST /queues/{queue_id}/claim returns 401 without session."""
        resp = client.post(f"/api/v1/queues/{QUEUE_ID}/claim")
        assert resp.status_code == 401


# ===================================================================
# Submit / skip / release
# ===================================================================


class TestSubmitSkipRelease:
    """Tests for submit, skip, and release operations."""

    def test_submit_review(self, engine, reviewer, tasks) -> None:
        """submit_review marks task as submitted and clears drafts."""
        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None
        task_id = uuid.UUID(claimed["id"])

        result = submit_review(
            engine,
            task_id,
            reviewer.id,
            {"sentiment": "positive"},
            ReviewDecision.accept,
            "Primary label is clear",
        )
        assert result is not None
        assert result["status"] == "submitted"
        assert result["draft_labels"] is None
        assert result["submitted_at"] is not None

        events = _review_events_for_task(engine, task_id)
        assert len(events) == 1
        event = events[0]
        assert event[1] == str(task_id)
        assert event[5] == str(reviewer.id)
        assert event[6] == "human"
        assert event[7] == ReviewDecision.accept.value
        assert json.loads(event[8]) == {"sentiment": "positive"}
        assert event[9] == "Primary label is clear"
        assert event[10] in (0, 1)

    def test_submit_wrong_reviewer_fails(
        self, engine, reviewer, second_reviewer, tasks
    ) -> None:
        """submit_review fails if the task is not claimed by the reviewer."""
        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None
        task_id = uuid.UUID(claimed["id"])

        result = submit_review(engine, task_id, second_reviewer.id, {"label": "x"})
        assert result is None

    def test_submit_review_rejects_stringified_evidence_atoms(
        self, engine, workspace, reviewer
    ) -> None:
        schema_id = uuid.uuid4()
        _insert_task_schema(
            engine,
            workspace,
            schema_id=schema_id,
            slug="evidence-qa",
            label_fields=[
                {
                    "name": "verdict",
                    "field_type": "categorical",
                    "options": ["supports", "refutes", "nei"],
                    "required": True,
                },
                {
                    "name": "evidence_atoms",
                    "field_type": "json",
                    "required": True,
                },
            ],
        )
        task = _create_task_with_schema(
            engine,
            workspace,
            schema_id=schema_id,
            payload={"text": "claim"},
        )
        claimed = claim_next(engine, task.queue_id, reviewer.id)
        assert claimed is not None

        with pytest.raises(
            ValueError,
            match="evidence_atoms must be a JSON array of stable evidence atom IDs",
        ):
            submit_review(
                engine,
                task.id,
                reviewer.id,
                {
                    "verdict": "supports",
                    "evidence_atoms": '["doc_1_sentence_0"]',
                },
                ReviewDecision.accept,
            )

    def test_submit_review_rejects_bad_rationale_mask_shape(
        self, client, engine, workspace, reviewer
    ) -> None:
        _login(client, reviewer)
        schema_id = uuid.uuid4()
        _insert_task_schema(
            engine,
            workspace,
            schema_id=schema_id,
            slug="rationale-mask",
            label_fields=[
                {
                    "name": "stance_label",
                    "field_type": "categorical",
                    "options": ["normal", "offensive", "hatespeech"],
                    "required": True,
                },
                {
                    "name": "rationale_token_mask",
                    "field_type": "json",
                    "required": True,
                },
            ],
        )
        task = _create_task_with_schema(
            engine,
            workspace,
            schema_id=schema_id,
            payload={"tokens": ["a", "b", "c", "d"]},
        )

        claim_resp = client.post(f"/api/v1/queues/{task.queue_id}/claim")
        assert claim_resp.status_code == 200
        task_id = claim_resp.json()["task"]["id"]

        submit_resp = client.post(
            f"/api/v1/review-tasks/{task_id}/submit",
            json={
                "labels": {
                    "stance_label": "offensive",
                    "rationale_token_mask": [1, 0],
                },
                "decision": "accept",
                "auto_claim_next": False,
            },
        )
        assert submit_resp.status_code == 422
        assert "token count (4), got 2" in submit_resp.text

    def test_submit_api_auto_claims_next(self, client, engine, reviewer, tasks) -> None:
        """POST /review-tasks/{id}/submit auto-claims next item."""
        _login(client, reviewer)
        # Claim first
        resp = client.post(f"/api/v1/queues/{QUEUE_ID}/claim")
        task_id = resp.json()["task"]["id"]

        # Submit and auto-claim
        resp = client.post(
            f"/api/v1/review-tasks/{task_id}/submit",
            json={
                "labels": {"sentiment": "positive"},
                "decision": "accept_ai",
                "rationale": "Model output matches the record",
                "auto_claim_next": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "submitted"
        assert data["submitted_task"]["status"] == "submitted"
        assert data["next_task"] is not None
        assert data["next_task"]["status"] == "claimed"

        events = _review_events_for_task(engine, uuid.UUID(task_id))
        assert len(events) == 1
        event = events[0]
        assert event[7] == ReviewDecision.accept_ai.value
        assert json.loads(event[8]) == {"sentiment": "positive"}
        assert event[9] == "Model output matches the record"

    def test_submit_api_duplicate_submit_fails_cleanly(
        self, client, engine, reviewer, tasks
    ) -> None:
        """A second submit on the same task returns 409 and adds no event."""
        _login(client, reviewer)
        resp = client.post(f"/api/v1/queues/{QUEUE_ID}/claim")
        task_id = resp.json()["task"]["id"]

        first = client.post(
            f"/api/v1/review-tasks/{task_id}/submit",
            json={
                "labels": {"sentiment": "positive"},
                "decision": "accept",
                "rationale": "First submission",
                "auto_claim_next": False,
            },
        )
        assert first.status_code == 200

        second = client.post(
            f"/api/v1/review-tasks/{task_id}/submit",
            json={
                "labels": {"sentiment": "positive"},
                "decision": "accept",
                "rationale": "Second submission",
                "auto_claim_next": False,
            },
        )
        assert second.status_code == 409

        events = _review_events_for_task(engine, uuid.UUID(task_id))
        assert len(events) == 1

    def test_skip_task(self, engine, reviewer, tasks) -> None:
        """skip_task marks the task as skipped (retaining claimed_by)."""
        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None
        task_id = uuid.UUID(claimed["id"])

        result = skip_task(engine, task_id, reviewer.id)
        assert result is not None
        assert result["status"] == "skipped"
        assert result["claimed_by"] == str(reviewer.id)

    def test_skip_excludes_from_future_claims(
        self, engine, reviewer, workspace
    ) -> None:
        """A skipped record is not re-served to the same reviewer."""
        _create_tasks(engine, workspace, count=2)
        # Claim and skip the first task
        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None
        skip_task(engine, uuid.UUID(claimed["id"]), reviewer.id)
        skipped_record = claimed["record_id"]

        # Next claim should not return the skipped record
        next_claim = claim_next(engine, QUEUE_ID, reviewer.id)
        assert next_claim is not None
        assert next_claim["record_id"] != skipped_record

    def test_skip_api_auto_claims_next(self, client, engine, reviewer, tasks) -> None:
        """POST /review-tasks/{id}/skip auto-claims next item."""
        _login(client, reviewer)
        resp = client.post(f"/api/v1/queues/{QUEUE_ID}/claim")
        task_id = resp.json()["task"]["id"]

        resp = client.post(f"/api/v1/review-tasks/{task_id}/skip")
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "skipped"
        assert data["skipped_task"]["status"] == "skipped"
        # Next task should be claimed (a different record, not the skipped one)
        assert data["next_task"] is not None
        assert data["next_task"]["id"] != task_id

    def test_release_claim(self, engine, reviewer, tasks) -> None:
        """release_claim returns the item to available."""
        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None
        task_id = uuid.UUID(claimed["id"])

        result = release_claim(engine, task_id, reviewer.id)
        assert result is not None
        assert result["status"] == "available"
        assert result["claimed_by"] is None

    def test_release_api_endpoint(self, client, reviewer, tasks) -> None:
        """POST /review-tasks/{id}/release returns the task to pool."""
        _login(client, reviewer)
        resp = client.post(f"/api/v1/queues/{QUEUE_ID}/claim")
        task_id = resp.json()["task"]["id"]

        resp = client.post(f"/api/v1/review-tasks/{task_id}/release")
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "released"
        assert data["task"]["status"] == "available"

    def test_submit_nonexistent_task_returns_409(self, client, reviewer) -> None:
        """Submit on a non-existent task returns 409."""
        _login(client, reviewer)
        fake_id = uuid.uuid4()
        resp = client.post(
            f"/api/v1/review-tasks/{fake_id}/submit",
            json={"labels": {"x": "y"}, "decision": "accept"},
        )
        assert resp.status_code == 409


# ===================================================================
# SE-007: Claim timeout expiry
# ===================================================================


class TestClaimExpiry:
    """Tests for claim timeout and expiry (SE-007)."""

    def test_get_expired_claims_none(self, engine, reviewer, tasks) -> None:
        """No expired claims when all claims are fresh."""
        claim_next(engine, QUEUE_ID, reviewer.id)
        expired = get_expired_claims(engine, timeout_minutes=30)
        assert len(expired) == 0

    def test_get_expired_claims_finds_stale(self, engine, reviewer, tasks) -> None:
        """Stale claims are detected when using a very short timeout."""
        claim_next(engine, QUEUE_ID, reviewer.id)

        # Manually backdate the claimed_at to trigger expiry.
        with engine.connect() as conn:
            conn.execute(
                text(_BACKDATE_CLAIM_BY_REVIEWER),
                {"rid": str(reviewer.id)},
            )
            conn.commit()

        expired = get_expired_claims(engine, timeout_minutes=30)
        assert len(expired) == 1

    def test_expire_claims_releases_to_pool(self, engine, reviewer, tasks) -> None:
        """expire_claims sets status back to available and increments count."""
        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None
        task_id = claimed["id"]

        # Backdate the claim.
        with engine.connect() as conn:
            conn.execute(
                text(_BACKDATE_CLAIM_BY_ID),
                {"id": task_id},
            )
            conn.commit()

        expired = expire_claims(engine, timeout_minutes=30)
        assert len(expired) == 1
        assert expired[0]["status"] == "available"
        assert expired[0]["claimed_by"] is None
        assert expired[0]["claim_expired_count"] == 1

    def test_expire_increments_count(self, engine, reviewer, tasks) -> None:
        """claim_expired_count increments on each expiry cycle."""
        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None
        task_id = claimed["id"]

        # Expire once.
        with engine.connect() as conn:
            conn.execute(
                text(_BACKDATE_CLAIM_BY_ID),
                {"id": task_id},
            )
            conn.commit()
        expire_claims(engine, timeout_minutes=30)

        # Claim again and expire again.
        claimed2 = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed2 is not None
        assert claimed2["id"] == task_id

        with engine.connect() as conn:
            conn.execute(
                text(_BACKDATE_CLAIM_BY_ID),
                {"id": task_id},
            )
            conn.commit()
        expired2 = expire_claims(engine, timeout_minutes=30)
        assert len(expired2) == 1
        assert expired2[0]["claim_expired_count"] == 2

    def test_draft_preserved_on_expiry(self, engine, reviewer, tasks) -> None:
        """Draft labels are preserved when a claim expires (SE-007)."""
        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None
        task_id = uuid.UUID(claimed["id"])

        # Save a draft.
        save_draft(engine, task_id, reviewer.id, {"sentiment": "neutral"})

        # Backdate and expire.
        with engine.connect() as conn:
            conn.execute(
                text(_BACKDATE_CLAIM_BY_ID),
                {"id": str(task_id)},
            )
            conn.commit()

        expired = expire_claims(engine, timeout_minutes=30)
        assert len(expired) == 1
        # draft_labels should still be present.
        assert expired[0]["draft_labels"] is not None
        assert expired[0]["draft_labels"]["sentiment"] == "neutral"


# ===================================================================
# SE-008: Claim expiry notification
# ===================================================================


class TestClaimExpiryNotification:
    """Tests for claim expiry notification header (SE-008)."""

    def test_notification_stored_on_expiry(self, engine, reviewer, tasks) -> None:
        """expire_claims stores notification for the affected reviewer."""
        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None

        # Backdate and expire.
        with engine.connect() as conn:
            conn.execute(
                text(_BACKDATE_CLAIM_BY_ID),
                {"id": claimed["id"]},
            )
            conn.commit()

        expire_claims(engine, timeout_minutes=30)

        notifications = pop_expired_notifications(reviewer.id)
        assert len(notifications) == 1
        assert notifications[0]["task_id"] == claimed["id"]

    def test_notification_cleared_after_pop(self, engine, reviewer, tasks) -> None:
        """pop_expired_notifications clears after first read."""
        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None

        with engine.connect() as conn:
            conn.execute(
                text(_BACKDATE_CLAIM_BY_ID),
                {"id": claimed["id"]},
            )
            conn.commit()

        expire_claims(engine, timeout_minutes=30)

        # First pop returns notifications.
        n1 = pop_expired_notifications(reviewer.id)
        assert len(n1) == 1

        # Second pop is empty.
        n2 = pop_expired_notifications(reviewer.id)
        assert len(n2) == 0

    def test_notification_header_on_api_call(
        self, client, engine, reviewer, tasks
    ) -> None:
        """API response includes X-MoLabel-Notification header after expiry (SE-008)."""
        _login(client, reviewer)

        # Claim via API.
        resp = client.post(f"/api/v1/queues/{QUEUE_ID}/claim")
        task_id = resp.json()["task"]["id"]

        # Backdate and expire.
        with engine.connect() as conn:
            conn.execute(
                text(_BACKDATE_CLAIM_BY_ID),
                {"id": task_id},
            )
            conn.commit()
        expire_claims(engine, timeout_minutes=30)

        # Next API call should have the notification header.
        resp = client.post(f"/api/v1/queues/{QUEUE_ID}/claim")
        assert resp.headers.get("X-MoLabel-Notification") == "claim_expired"
        assert resp.headers.get("X-MoLabel-Expired-Count") == "1"

    def test_no_notification_header_without_expiry(
        self, client, reviewer, tasks
    ) -> None:
        """API response has no notification header when nothing expired."""
        _login(client, reviewer)
        resp = client.post(f"/api/v1/queues/{QUEUE_ID}/claim")
        assert "X-MoLabel-Notification" not in resp.headers


# ===================================================================
# SE-009: Draft save (last-write-wins)
# ===================================================================


class TestDraftSave:
    """Tests for draft save with last-write-wins semantics (SE-009)."""

    def test_save_draft(self, engine, reviewer, tasks) -> None:
        """save_draft stores draft_labels on the task."""
        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None
        task_id = uuid.UUID(claimed["id"])

        result = save_draft(engine, task_id, reviewer.id, {"sentiment": "positive"})
        assert result is not None
        assert result["draft_labels"] == {"sentiment": "positive"}

    def test_draft_overwrite_last_write_wins(self, engine, reviewer, tasks) -> None:
        """Subsequent draft saves overwrite previous ones (SE-009)."""
        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None
        task_id = uuid.UUID(claimed["id"])

        save_draft(engine, task_id, reviewer.id, {"sentiment": "positive"})
        result = save_draft(
            engine, task_id, reviewer.id, {"sentiment": "negative", "score": 0.2}
        )
        assert result is not None
        assert result["draft_labels"]["sentiment"] == "negative"
        assert result["draft_labels"]["score"] == 0.2

    def test_draft_wrong_reviewer_fails(
        self, engine, reviewer, second_reviewer, tasks
    ) -> None:
        """save_draft fails if the task is not claimed by the reviewer."""
        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None
        task_id = uuid.UUID(claimed["id"])

        result = save_draft(engine, task_id, second_reviewer.id, {"x": "y"})
        assert result is None

    def test_draft_api_endpoint(self, client, reviewer, tasks) -> None:
        """POST /review-tasks/{id}/draft saves draft labels."""
        _login(client, reviewer)
        resp = client.post(f"/api/v1/queues/{QUEUE_ID}/claim")
        task_id = resp.json()["task"]["id"]

        resp = client.post(
            f"/api/v1/review-tasks/{task_id}/draft",
            json={"draft_labels": {"sentiment": "neutral"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "draft_saved"
        assert data["task"]["draft_labels"] == {"sentiment": "neutral"}

    def test_draft_cleared_on_submit(self, engine, reviewer, tasks) -> None:
        """Submitting a review clears the draft_labels."""
        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None
        task_id = uuid.UUID(claimed["id"])

        save_draft(engine, task_id, reviewer.id, {"sentiment": "positive"})
        submitted = submit_review(
            engine, task_id, reviewer.id, {"sentiment": "positive"}
        )
        assert submitted is not None
        assert submitted["draft_labels"] is None


# ===================================================================
# SE-010: Mission control reviewer visibility
# ===================================================================


class TestMissionControlVisibility:
    """Tests for mission control reviewer visibility (SE-010)."""

    def test_active_reviewer_status(self, engine, reviewer, workspace) -> None:
        """Reviewer with recent last_active_at is classified as active."""
        visibility = get_reviewer_visibility(engine, workspace.id)
        assert len(visibility) >= 1
        alice = next(
            (r for r in visibility if r["reviewer_id"] == str(reviewer.id)), None
        )
        assert alice is not None
        assert alice["status"] == "active"

    def test_idle_reviewer_status(self, engine, idle_reviewer, workspace) -> None:
        """Reviewer with last_active_at 15 min ago is classified as idle."""
        visibility = get_reviewer_visibility(engine, workspace.id)
        charlie = next(
            (r for r in visibility if r["reviewer_id"] == str(idle_reviewer.id)),
            None,
        )
        assert charlie is not None
        assert charlie["status"] == "idle"

    def test_offline_reviewer_status(self, engine, offline_reviewer, workspace) -> None:
        """Reviewer with last_active_at 60 min ago is classified as offline."""
        visibility = get_reviewer_visibility(engine, workspace.id)
        diana = next(
            (r for r in visibility if r["reviewer_id"] == str(offline_reviewer.id)),
            None,
        )
        assert diana is not None
        assert diana["status"] == "offline"

    def test_visibility_includes_current_queue(
        self, engine, reviewer, tasks, workspace
    ) -> None:
        """Active reviewer shows current queue and task."""
        claim_next(engine, QUEUE_ID, reviewer.id)

        visibility = get_reviewer_visibility(engine, workspace.id)
        alice = next(
            (r for r in visibility if r["reviewer_id"] == str(reviewer.id)), None
        )
        assert alice is not None
        assert alice["current_queue"] == QUEUE_ID
        assert alice["current_task_id"] is not None

    def test_visibility_shows_completed_count(
        self, engine, reviewer, tasks, workspace
    ) -> None:
        """Completed count reflects submitted tasks."""
        claimed = claim_next(engine, QUEUE_ID, reviewer.id)
        assert claimed is not None
        submit_review(engine, uuid.UUID(claimed["id"]), reviewer.id, {"label": "pos"})

        visibility = get_reviewer_visibility(engine, workspace.id)
        alice = next(
            (r for r in visibility if r["reviewer_id"] == str(reviewer.id)), None
        )
        assert alice is not None
        assert alice["completed_count"] == 1

    def test_mission_control_api_endpoint(
        self, client, reviewer, idle_reviewer, workspace
    ) -> None:
        """GET /mission-control/reviewers returns reviewer visibility (SE-010)."""
        _login(client, reviewer)
        resp = client.get("/api/v1/mission-control/reviewers")
        assert resp.status_code == 200
        data = resp.json()
        assert "reviewers" in data
        assert len(data["reviewers"]) >= 2

        # Active and idle should be present with correct status.
        statuses = {r["reviewer_id"]: r["status"] for r in data["reviewers"]}
        assert statuses[str(reviewer.id)] == "active"
        assert statuses[str(idle_reviewer.id)] == "idle"


# ===================================================================
# Queue status
# ===================================================================


class TestQueueStatus:
    """Tests for queue status endpoint."""

    def test_queue_status_counts(self, engine, reviewer, tasks) -> None:
        """get_queue_status returns correct status counts."""
        status = get_queue_status(engine, QUEUE_ID)
        assert status["queue_id"] == QUEUE_ID
        assert status["total"] == 5
        assert status["available"] == 5
        assert status["claimed"] == 0

    def test_queue_status_after_claim(self, engine, reviewer, tasks) -> None:
        """Queue status reflects claimed items."""
        claim_next(engine, QUEUE_ID, reviewer.id)

        status = get_queue_status(engine, QUEUE_ID)
        assert status["available"] == 4
        assert status["claimed"] == 1
        assert len(status["active_reviewers"]) == 1
        assert status["active_reviewers"][0]["reviewer_id"] == str(reviewer.id)

    def test_queue_status_api(self, client, reviewer, tasks) -> None:
        """GET /queues/{queue_id}/status returns queue statistics."""
        _login(client, reviewer)
        resp = client.get(f"/api/v1/queues/{QUEUE_ID}/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["queue_id"] == QUEUE_ID
        assert data["total"] == 5
        assert data["available"] == 5

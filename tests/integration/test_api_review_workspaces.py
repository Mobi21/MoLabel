"""A reviewer reads and resolves only their own workspace's review queues."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import text

from tests.integration.review_flow import (
    _as,
    _claim,
    _external_ids,
    _review_both,
    _start_review,
    review_app,
    review_client,
)
from tests.integration.test_api_workflows import _seed_reviewer


@pytest.fixture()
def app(tmp_path):
    return review_app(tmp_path)


@pytest_asyncio.fixture()
async def client(app):
    async with review_client(app) as c:
        yield c


def _outsider(app, tmp_path):
    """A session for a reviewer of another workspace."""
    workspace_id = uuid.uuid4()
    now = datetime.now(UTC).isoformat()
    with app.state.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO workspaces (id, workspace_name, workspace_slug, "
                "core_version, root_path, manifest_path, created_at, updated_at) "
                "VALUES (:id, 'Other', 'other', '0.1.0', :root, :manifest, "
                ":now, :now)"
            ),
            {
                "id": str(workspace_id),
                "root": str(tmp_path / "other"),
                "manifest": str(tmp_path / "other" / "workbench.project.yaml"),
                "now": now,
            },
        )
    return _seed_reviewer(app.state.engine, workspace_id)


def _latest_label(app, record_id):
    with app.state.engine.connect() as conn:
        return conn.execute(
            text("SELECT latest_label FROM records WHERE id = :id"), {"id": record_id}
        ).scalar()


@pytest.mark.asyncio
async def test_another_workspace_cannot_read_or_resolve_a_disagreement(
    client, app, tmp_path
):
    _, tokens, queue = await _start_review(client, app, tmp_path)
    queue_id = queue["queue_id"]
    await _review_both(client, queue_id, tokens)
    record_id = _external_ids(app)["r3"]
    base = f"/api/v1/adjudication/queues/{queue_id}/disagreements"
    shown = (await client.get(f"{base}/{record_id}", headers=_as(tokens[0]))).json()
    event_ids = [s["review_event_id"] for s in shown["reviewer_labels"]]
    latest = _latest_label(app, record_id)
    outsider = _outsider(app, tmp_path)

    listed = await client.get(base, headers=_as(outsider))
    assert listed.status_code == 404, listed.text
    detail = await client.get(f"{base}/{record_id}", headers=_as(outsider))
    assert detail.status_code == 404, detail.text
    resolved = await client.post(
        f"{base}/{record_id}/resolve",
        json={
            "resolved_labels": {"sentiment": "positive"},
            "review_event_ids": event_ids,
        },
        headers=_as(outsider),
    )
    assert resolved.status_code == 404, resolved.text

    assert _latest_label(app, record_id) == latest
    with app.state.engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM adjudications")).scalar()
    assert count == 0


@pytest.mark.asyncio
async def test_a_resolution_records_the_queues_workspace(client, app, tmp_path):
    workspace_id, tokens, queue = await _start_review(client, app, tmp_path)
    queue_id = queue["queue_id"]
    await _review_both(client, queue_id, tokens)
    record_id = _external_ids(app)["r3"]
    path = f"/api/v1/adjudication/queues/{queue_id}/disagreements/{record_id}"
    shown = (await client.get(path, headers=_as(tokens[0]))).json()

    resolved = await client.post(
        f"{path}/resolve",
        json={
            "resolved_labels": {"sentiment": "neutral"},
            "review_event_ids": [
                s["review_event_id"] for s in shown["reviewer_labels"]
            ],
        },
        headers=_as(tokens[0]),
    )
    assert resolved.status_code == 200, resolved.text

    with app.state.engine.connect() as conn:
        stored = conn.execute(
            text(
                "SELECT a.workspace_id, e.workspace_id FROM adjudications a "
                "JOIN review_events e "
                "ON e.id = json_extract(a.metadata, '$.review_event_id')"
            )
        ).one()
    assert tuple(stored) == (workspace_id, workspace_id)


@pytest.mark.asyncio
async def test_another_workspace_cannot_read_a_queues_tasks_or_agreement(
    client, app, tmp_path
):
    workspace_id, tokens, queue = await _start_review(client, app, tmp_path)
    queue_id = queue["queue_id"]
    outsider = _outsider(app, tmp_path)
    with app.state.engine.begin() as conn:
        task_id = conn.execute(
            text(
                "SELECT id FROM review_tasks WHERE queue_id = :q "
                "AND status = 'available' LIMIT 1"
            ),
            {"q": queue_id},
        ).scalar()
        outsider_id = conn.execute(
            text("SELECT id FROM reviewer_profiles WHERE workspace_id != :w"),
            {"w": workspace_id},
        ).scalar()
        conn.execute(
            text(
                "UPDATE review_tasks SET status = 'claimed', claimed_by = :r "
                "WHERE id = :t"
            ),
            {"r": outsider_id, "t": task_id},
        )

    trail = await client.get(
        f"/api/v1/queues/{queue_id}/my-tasks", headers=_as(outsider)
    )
    assert trail.status_code == 404, trail.text
    task = await client.get(f"/api/v1/review-tasks/{task_id}", headers=_as(outsider))
    assert task.status_code == 404, task.text
    agreement = await client.get(
        "/api/v1/quality/agreement",
        params={"workspace_id": workspace_id, "queue_id": queue_id},
        headers=_as(outsider),
    )
    assert agreement.status_code == 404, agreement.text

    own = await client.get(
        "/api/v1/quality/agreement",
        params={"workspace_id": workspace_id, "queue_id": queue_id},
        headers=_as(tokens[0]),
    )
    assert own.status_code == 200, own.text


@pytest.mark.asyncio
async def test_another_workspace_cannot_close_a_queues_copies(client, app, tmp_path):
    _, tokens, queue = await _start_review(client, app, tmp_path)
    close = f"/api/v1/queues/{queue['queue_id']}/close-copies"
    outsider = _outsider(app, tmp_path)

    refused = await client.post(close, headers=_as(outsider))

    assert refused.status_code == 404, refused.text
    own = await client.post(close, headers=_as(tokens[0]))
    assert own.json()["closed"] == queue["total"]


def _task_row(app, task_id):
    with app.state.engine.connect() as conn:
        task = conn.execute(
            text(
                "SELECT status, claimed_by, draft_labels, ai_revealed "
                "FROM review_tasks WHERE id = :id"
            ),
            {"id": task_id},
        ).one()
        events = conn.execute(text("SELECT COUNT(*) FROM review_events")).scalar()
    return tuple(task), events


def _hand_to_outsider(app, task_id, workspace_id):
    """Give a task to the other workspace's reviewer, as a claim made before
    the workspace check would have."""
    with app.state.engine.begin() as conn:
        outsider_id = conn.execute(
            text("SELECT id FROM reviewer_profiles WHERE workspace_id != :w"),
            {"w": workspace_id},
        ).scalar()
        conn.execute(
            text("UPDATE review_tasks SET claimed_by = :r WHERE id = :t"),
            {"r": outsider_id, "t": task_id},
        )


@pytest.mark.asyncio
async def test_another_workspace_cannot_claim_from_a_queue(client, app, tmp_path):
    _, tokens, queue = await _start_review(client, app, tmp_path)
    outsider = _outsider(app, tmp_path)

    claim = await client.post(
        f"/api/v1/queues/{queue['queue_id']}/claim", headers=_as(outsider)
    )

    assert claim.status_code == 404, claim.text
    status = await client.get(
        f"/api/v1/queues/{queue['queue_id']}/status", headers=_as(tokens[0])
    )
    assert status.json()["claimed"] == 0


@pytest.mark.asyncio
async def test_another_workspace_cannot_read_a_queues_status(client, app, tmp_path):
    _, tokens, queue = await _start_review(client, app, tmp_path)
    path = f"/api/v1/queues/{queue['queue_id']}/status"

    refused = await client.get(path, headers=_as(_outsider(app, tmp_path)))

    assert refused.status_code == 404, refused.text
    own = await client.get(path, headers=_as(tokens[0]))
    assert own.json()["total"] == queue["total"]


@pytest.mark.asyncio
async def test_the_queue_list_shows_only_the_callers_workspace(client, app, tmp_path):
    workspace_id, tokens, queue = await _start_review(client, app, tmp_path)
    outsider = _outsider(app, tmp_path)

    own = await client.get("/api/v1/queues", headers=_as(tokens[0]))
    theirs = await client.get("/api/v1/queues", headers=_as(outsider))
    named = await client.get(
        "/api/v1/queues", params={"workspace_id": workspace_id}, headers=_as(outsider)
    )

    assert [q["queue_id"] for q in own.json()["items"]] == [queue["queue_id"]]
    assert theirs.json()["items"] == []
    assert named.status_code == 404, named.text


TASK_ACTIONS = {
    "submit": {"labels": {"sentiment": "positive"}, "auto_claim_next": False},
    "skip": None,
    "release": None,
    "draft": {"draft_labels": {"sentiment": "positive"}},
    "reveal-ai": None,
}


@pytest.mark.asyncio
@pytest.mark.parametrize("action", sorted(TASK_ACTIONS))
async def test_another_workspace_cannot_act_on_a_claimed_task(
    client, app, tmp_path, action
):
    workspace_id, _, queue = await _start_review(
        client, app, tmp_path, policy="hide_agent_outputs_by_default"
    )
    outsider = _outsider(app, tmp_path)
    with app.state.engine.begin() as conn:
        task_id = conn.execute(
            text(
                "SELECT id FROM review_tasks WHERE queue_id = :q "
                "AND status = 'available' LIMIT 1"
            ),
            {"q": queue["queue_id"]},
        ).scalar()
        conn.execute(
            text("UPDATE review_tasks SET status = 'claimed' WHERE id = :t"),
            {"t": task_id},
        )
    _hand_to_outsider(app, task_id, workspace_id)
    before = _task_row(app, task_id)

    refused = await client.post(
        f"/api/v1/review-tasks/{task_id}/{action}",
        json=TASK_ACTIONS[action],
        headers=_as(outsider),
    )

    assert refused.status_code == 404, refused.text
    assert _task_row(app, task_id) == before


@pytest.mark.asyncio
async def test_another_workspace_cannot_correct_a_review(client, app, tmp_path):
    workspace_id, tokens, queue = await _start_review(client, app, tmp_path)
    task = await _claim(client, queue["queue_id"], tokens[0])
    await client.post(
        f"/api/v1/review-tasks/{task['id']}/submit",
        json={"labels": {"sentiment": "positive"}, "auto_claim_next": False},
        headers=_as(tokens[0]),
    )
    outsider = _outsider(app, tmp_path)
    _hand_to_outsider(app, task["id"], workspace_id)
    before = _task_row(app, task["id"])

    refused = await client.post(
        f"/api/v1/review-tasks/{task['id']}/correct",
        json={"labels": {"sentiment": "negative"}, "decision": "edit"},
        headers=_as(outsider),
    )

    assert refused.status_code == 404, refused.text
    assert _task_row(app, task["id"]) == before

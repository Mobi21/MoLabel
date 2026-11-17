"""Queues and a reviewer's own tasks, as the review GUI reads them."""

from __future__ import annotations

import pytest
import pytest_asyncio

from tests.integration.review_flow import (
    FIRST_REVIEWER,
    OFFLINE_SENTIMENT,
    _as,
    _claim,
    _review_all,
    _start_review,
    review_app,
    review_client,
)


@pytest.fixture()
def app(tmp_path):
    return review_app(tmp_path)


@pytest_asyncio.fixture()
async def client(app):
    async with review_client(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Queues and a reviewer's tasks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_queue_lists_its_kind_schema_and_the_callers_progress(
    client, app, tmp_path
):
    _, tokens, queue = await _start_review(client, app, tmp_path)

    assert queue["kind"] == "review"
    assert queue["task_schema_title"] == "Sentiment Demo"
    assert queue["blind_review_policy"] == "show_agent_outputs"
    assert (queue["total"], queue["my_remaining"], queue["my_submitted"]) == (12, 6, 0)

    await _review_all(client, queue["queue_id"], tokens[0], FIRST_REVIEWER)
    after = await client.get("/api/v1/queues", headers=_as(tokens[0]))
    mine = after.json()["items"][0]
    assert (mine["available"], mine["my_remaining"], mine["my_submitted"]) == (6, 0, 6)
    theirs = (await client.get("/api/v1/queues", headers=_as(tokens[1]))).json()
    assert theirs["items"][0]["my_remaining"] == 6


@pytest.mark.asyncio
async def test_my_tasks_lists_submissions_in_order_with_the_held_claim_last(
    client, app, tmp_path
):
    _, tokens, queue = await _start_review(client, app, tmp_path)
    queue_id = queue["queue_id"]
    submitted_ids = []
    for _ in range(2):
        task = await _claim(client, queue_id, tokens[0])
        await client.post(
            f"/api/v1/review-tasks/{task['id']}/submit",
            json={"decision": "accept", "labels": {}, "auto_claim_next": False},
            headers=_as(tokens[0]),
        )
        submitted_ids.append(task["id"])
    held = await _claim(client, queue_id, tokens[0])

    trail = await client.get(
        f"/api/v1/queues/{queue_id}/my-tasks", headers=_as(tokens[0])
    )
    items = trail.json()["items"]
    assert [item["task_id"] for item in items] == [*submitted_ids, held["id"]]
    assert [item["status"] for item in items] == ["submitted", "submitted", "claimed"]
    assert items[0]["decision"] == "accept"

    others = await client.get(
        f"/api/v1/queues/{queue_id}/my-tasks", headers=_as(tokens[1])
    )
    assert others.json()["items"] == []


@pytest.mark.asyncio
async def test_a_submitted_task_reads_back_with_its_counted_review(
    client, app, tmp_path
):
    _, tokens, queue = await _start_review(client, app, tmp_path)
    task = await _claim(client, queue["queue_id"], tokens[0])
    proposal = task["agent_output"]["labels"]
    await client.post(
        f"/api/v1/review-tasks/{task['id']}/submit",
        json={"decision": "accept", "labels": proposal, "auto_claim_next": False},
        headers=_as(tokens[0]),
    )
    await client.post(
        f"/api/v1/review-tasks/{task['id']}/correct",
        json={"decision": "edit", "labels": {"sentiment": "neutral"}},
        headers=_as(tokens[0]),
    )

    path = f"/api/v1/review-tasks/{task['id']}"
    body = (await client.get(path, headers=_as(tokens[0]))).json()
    assert body["status"] == "submitted"
    assert body["agent_output"]["labels"] == proposal
    assert body["review"]["decision"] == "edit"
    assert body["review"]["labels"] == {"sentiment": "neutral"}

    assert (await client.get(path, headers=_as(tokens[1]))).status_code == 404


@pytest.mark.asyncio
async def test_reading_a_blind_task_shows_no_proposal_until_revealed(
    client, app, tmp_path
):
    _, tokens, queue = await _start_review(
        client, app, tmp_path, policy="hide_agent_outputs_by_default"
    )
    task = await _claim(client, queue["queue_id"], tokens[0])
    assert task["agent_output"] is None
    path = f"/api/v1/review-tasks/{task['id']}"

    unrevealed = (await client.get(path, headers=_as(tokens[0]))).json()
    assert unrevealed["agent_output"] is None
    await client.post(f"{path}/reveal-ai", headers=_as(tokens[0]))
    revealed = (await client.get(path, headers=_as(tokens[0]))).json()
    assert revealed["ai_revealed"] is True
    assert (
        revealed["agent_output"]["labels"]["sentiment"]
        == OFFLINE_SENTIMENT[task["record_external_id"]]
    )

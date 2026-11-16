"""Adjudicating the disagreements of a review queue."""

from __future__ import annotations

import json

import pytest
import pytest_asyncio
from sqlalchemy import text

from tests.integration.review_flow import (
    OFFLINE_SENTIMENT,
    SENTIMENT_RECORDS,
    _as,
    _claim,
    _external_ids,
    _label_all,
    _review_both,
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
# Adjudication
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_queue_lists_the_record_its_reviewers_disagree_on(
    client, app, tmp_path
):
    _, tokens, queue = await _start_review(client, app, tmp_path)
    queue_id = queue["queue_id"]
    await _review_both(client, queue_id, tokens)

    listed = await client.get(
        f"/api/v1/adjudication/queues/{queue_id}/disagreements",
        headers=_as(tokens[0]),
    )
    body = listed.json()
    assert (body["total"], body["unresolved"]) == (1, 1)
    (item,) = body["items"]
    assert item["record_external_id"] == "r3"
    assert (item["fields_in_conflict"], item["status"]) == (["sentiment"], "pending")

    detail = await client.get(
        f"/api/v1/adjudication/queues/{queue_id}/disagreements/{item['record_id']}",
        headers=_as(tokens[0]),
    )
    shown = detail.json()
    assert sorted(s["labels"]["sentiment"] for s in shown["reviewer_labels"]) == [
        "negative",
        "neutral",
    ]
    assert [a["labels"]["sentiment"] for a in shown["agent_labels"]] == ["neutral"]
    assert sorted(shown["disagreeing_fields"][0]["values"].values()) == [
        "negative",
        "neutral",
    ]
    assert shown["record_text"] == SENTIMENT_RECORDS["r3"]


@pytest.mark.asyncio
async def test_a_resolution_is_stored_and_never_counts_as_a_rater(
    client, app, tmp_path
):
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
            "rationale": "Hedged.",
            "review_event_ids": _event_ids(shown),
        },
        headers=_as(tokens[0]),
    )
    assert resolved.status_code == 200, resolved.text

    reread = (await client.get(path, headers=_as(tokens[1]))).json()
    assert reread["status"] == "resolved"
    assert reread["resolution"]["resolution"] == "resolve"
    assert reread["resolution"]["resolved_labels"] == {"sentiment": "neutral"}
    assert reread["resolution"]["rationale"] == "Hedged."
    with app.state.engine.connect() as conn:
        latest = conn.execute(
            text("SELECT latest_label FROM records WHERE id = :id"), {"id": record_id}
        ).scalar()
    assert json.loads(latest) == {"sentiment": "neutral"}

    again = await client.post(
        f"{path}/resolve",
        json={
            "resolved_labels": {"sentiment": "negative"},
            "review_event_ids": _event_ids(shown),
        },
        headers=_as(tokens[0]),
    )
    assert again.status_code == 409

    listed = await client.get(
        f"/api/v1/adjudication/queues/{queue_id}/disagreements",
        headers=_as(tokens[0]),
    )
    assert listed.json()["unresolved"] == 0
    report = await client.get(
        "/api/v1/quality/agreement",
        params={"workspace_id": workspace_id, "queue_id": queue_id},
        headers=_as(tokens[0]),
    )
    sentiment = report.json()["inter_annotator"]["fields"]["sentiment"]
    assert sentiment["krippendorff_alpha"] == pytest.approx(72 / 94)


@pytest.mark.asyncio
async def test_resolve_needs_labels_that_fit_the_schema(client, app, tmp_path):
    _, tokens, queue = await _start_review(client, app, tmp_path)
    await _review_both(client, queue["queue_id"], tokens)
    record_id = _external_ids(app)["r3"]
    path = (
        f"/api/v1/adjudication/queues/{queue['queue_id']}"
        f"/disagreements/{record_id}/resolve"
    )

    missing = await client.post(path, json={}, headers=_as(tokens[0]))
    assert missing.status_code == 422
    unknown = await client.get(
        f"/api/v1/adjudication/queues/{queue['queue_id']}/disagreements/"
        f"{_external_ids(app)['r1']}",
        headers=_as(tokens[0]),
    )
    assert unknown.status_code == 404


@pytest.mark.asyncio
async def test_a_record_is_not_adjudicated_while_a_blind_copy_is_open(
    client, app, tmp_path
):
    _, tokens, queue = await _start_review(
        client,
        app,
        tmp_path,
        policy="hide_agent_outputs_by_default",
        reviewers=3,
        overlap=3,
    )
    queue_id = queue["queue_id"]
    held = await _claim(client, queue_id, tokens[2])
    assert held["agent_output"] is None
    split = held["record_external_id"]
    other = "negative" if OFFLINE_SENTIMENT[split] != "negative" else "positive"
    await _label_all(client, queue_id, tokens[0], {**OFFLINE_SENTIMENT, split: other})
    await _label_all(client, queue_id, tokens[1], OFFLINE_SENTIMENT)
    base = f"/api/v1/adjudication/queues/{queue_id}/disagreements"
    record_id = _external_ids(app)[split]

    for token in tokens:
        listed = (await client.get(base, headers=_as(token))).json()
        assert listed["items"] == []
        detail = await client.get(f"{base}/{record_id}", headers=_as(token))
        assert detail.status_code == 404, detail.text
    own = await client.get(f"/api/v1/review-tasks/{held['id']}", headers=_as(tokens[2]))
    assert own.json()["agent_output"] is None

    await client.post(
        f"/api/v1/review-tasks/{held['id']}/submit",
        json={
            "labels": {"sentiment": OFFLINE_SENTIMENT[split]},
            "auto_claim_next": False,
        },
        headers=_as(tokens[2]),
    )
    listed = (await client.get(base, headers=_as(tokens[2]))).json()
    assert [item["record_external_id"] for item in listed["items"]] == [split]
    shown = (await client.get(f"{base}/{record_id}", headers=_as(tokens[2]))).json()
    assert [a["labels"]["sentiment"] for a in shown["agent_labels"]] == [
        OFFLINE_SENTIMENT[split]
    ]


def _event_ids(detail):
    return [s["review_event_id"] for s in detail["reviewer_labels"]]


async def _correct_second_review(client, queue_id, token, labels):
    trail = await client.get(f"/api/v1/queues/{queue_id}/my-tasks", headers=_as(token))
    (task,) = [t for t in trail.json()["items"] if t["record_external_id"] == "r3"]
    corrected = await client.post(
        f"/api/v1/review-tasks/{task['task_id']}/correct",
        json={"decision": "edit", "labels": labels},
        headers=_as(token),
    )
    assert corrected.status_code == 200, corrected.text


@pytest.mark.asyncio
async def test_resolve_refuses_a_disagreement_that_changed_since_it_was_read(
    client, app, tmp_path
):
    _, tokens, queue = await _start_review(client, app, tmp_path)
    queue_id = queue["queue_id"]
    await _review_both(client, queue_id, tokens)
    record_id = _external_ids(app)["r3"]
    path = f"/api/v1/adjudication/queues/{queue_id}/disagreements/{record_id}"
    read = (await client.get(path, headers=_as(tokens[0]))).json()
    await _correct_second_review(client, queue_id, tokens[1], {"sentiment": "positive"})

    stale = await client.post(
        f"{path}/resolve",
        json={
            "resolved_labels": {"sentiment": "neutral"},
            "review_event_ids": _event_ids(read),
        },
        headers=_as(tokens[0]),
    )
    assert stale.status_code == 409, stale.text
    with app.state.engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM adjudications")).scalar()
    assert count == 0

    reread = (await client.get(path, headers=_as(tokens[0]))).json()
    assert _event_ids(reread) != _event_ids(read)
    fresh = await client.post(
        f"{path}/resolve",
        json={
            "resolved_labels": {"sentiment": "neutral"},
            "review_event_ids": _event_ids(reread),
        },
        headers=_as(tokens[0]),
    )
    assert fresh.status_code == 200, fresh.text


@pytest.mark.asyncio
async def test_resolve_refuses_a_disagreement_that_is_gone(client, app, tmp_path):
    _, tokens, queue = await _start_review(client, app, tmp_path)
    queue_id = queue["queue_id"]
    await _review_both(client, queue_id, tokens)
    record_id = _external_ids(app)["r3"]
    path = f"/api/v1/adjudication/queues/{queue_id}/disagreements/{record_id}"
    read = (await client.get(path, headers=_as(tokens[0]))).json()
    await _correct_second_review(client, queue_id, tokens[1], {"sentiment": "negative"})

    gone = await client.post(
        f"{path}/resolve",
        json={
            "resolved_labels": {"sentiment": "neutral"},
            "review_event_ids": _event_ids(read),
        },
        headers=_as(tokens[0]),
    )
    assert gone.status_code == 409, gone.text

"""Adjudicating the disagreements of a review queue."""

from __future__ import annotations

import json

import pytest
import pytest_asyncio
from sqlalchemy import text

from tests.integration.review_flow import (
    SENTIMENT_RECORDS,
    _as,
    _external_ids,
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

    resolved = await client.post(
        f"{path}/resolve",
        json={"resolved_labels": {"sentiment": "neutral"}, "rationale": "Hedged."},
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
        json={"resolved_labels": {"sentiment": "negative"}},
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

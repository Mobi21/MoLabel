"""A two-reviewer overlap queue for the review GUI's API tests.

Two reviewers each review six offline-labelled records. The first edits r3
from neutral to negative and accepts the rest, and the second accepts every
proposal, so the reviewers disagree on r3 alone.
"""

from __future__ import annotations

import json

from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from molabel.app.main import create_app
from molabel.core.database import get_engine
from molabel.core.migration_runner import upgrade_database
from tests.integration.test_api_workflows import (
    OFFLINE_SENTIMENT,
    SENTIMENT_RECORDS,
    TEST_SECRET,
    _seed_reviewer,
    _seed_task_schema,
    _seed_workflow,
    _seed_workspace,
)

FIRST_REVIEWER = {**OFFLINE_SENTIMENT, "r3": "negative"}
SECOND_REVIEWER = dict(OFFLINE_SENTIMENT)
NO_PAIRS = "No unit has two or more values to compare."


def review_app(tmp_path):
    """An app on a migrated database in ``tmp_path``."""
    application = create_app()
    engine = get_engine(tmp_path / "review-gui.db")
    upgrade_database(engine)
    application.state.engine = engine
    application.state.app_secret = TEST_SECRET
    return application


def review_client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _as(token):
    return {"Cookie": f"molabel_session={token}"}


async def _start_review(
    client, app, tmp_path, *, policy="show_agent_outputs", reviewers=2, overlap=2
):
    engine = app.state.engine
    workspace_id = _seed_workspace(engine, tmp_path)
    tokens = [_seed_reviewer(engine, workspace_id) for _ in range(reviewers)]
    task_schema_id = _seed_task_schema(engine, workspace_id)
    label_fields = [
        {
            "name": "sentiment",
            "field_type": "categorical",
            "required": True,
            "options": ["positive", "negative", "neutral"],
        },
        {"name": "note", "field_type": "text", "required": False},
    ]
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE task_schemas SET blind_review_policy = :policy, "
                "label_fields = :fields WHERE id = :id"
            ),
            {
                "policy": policy,
                "fields": json.dumps(label_fields),
                "id": str(task_schema_id),
            },
        )
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "reviews.jsonl").write_text(
        "".join(
            json.dumps({"id": record_id, "text": body}) + "\n"
            for record_id, body in SENTIMENT_RECORDS.items()
        ),
        encoding="utf-8",
    )
    workflow_id = _seed_workflow(
        engine,
        workspace_id,
        agent_config={"provider_type": "offline", "prompt_ref": "prompts/default.yaml"},
        review_config={"overlap_count": overlap},
    )
    started = await client.post(
        f"/api/v1/workflows/{workflow_id}/execute", json={}, headers=_as(tokens[0])
    )
    assert started.json()["current_step_id"] == "review", started.text
    queues = await client.get(
        "/api/v1/queues",
        params={"workspace_id": str(workspace_id)},
        headers=_as(tokens[0]),
    )
    (queue,) = queues.json()["items"]
    return str(workspace_id), tokens, queue


async def _claim(client, queue_id, token):
    claim = await client.post(f"/api/v1/queues/{queue_id}/claim", headers=_as(token))
    assert claim.status_code == 200, claim.text
    return claim.json()["task"]


async def _review_all(client, queue_id, token, sentiments):
    while (task := await _claim(client, queue_id, token)) is not None:
        sentiment = sentiments[task["record_external_id"]]
        proposed = task["agent_output"]["labels"]["sentiment"]
        submitted = await client.post(
            f"/api/v1/review-tasks/{task['id']}/submit",
            json={
                "decision": "accept" if sentiment == proposed else "edit",
                "labels": {"sentiment": sentiment},
                "auto_claim_next": False,
            },
            headers=_as(token),
        )
        assert submitted.status_code == 200, submitted.text


async def _review_both(client, queue_id, tokens):
    await _review_all(client, queue_id, tokens[0], FIRST_REVIEWER)
    await _review_all(client, queue_id, tokens[1], SECOND_REVIEWER)


def _external_ids(app):
    with app.state.engine.connect() as conn:
        return dict(conn.execute(text("SELECT external_id, id FROM records")).all())

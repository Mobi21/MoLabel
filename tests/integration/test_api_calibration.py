"""Calibration queues on a gold set: blind copies, and reviewers scored on gold."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import text

from tests.integration.review_flow import (
    OFFLINE_SENTIMENT,
    _as,
    _claim,
    _external_ids,
    _label_all,
    review_app,
    review_client,
)
from tests.integration.test_api_gold_sets import (
    GOLD,
    _create,
    _outsider,
    _promote,
    _reviewed_and_adjudicated,
)

GOLD_SENTIMENT = {**OFFLINE_SENTIMENT, "r3": "negative"}
CALIBRATE = {"gold_set": GOLD, "min_reviewers": 2}


@pytest.fixture()
def app(tmp_path):
    return review_app(tmp_path)


@pytest_asyncio.fixture()
async def client(app):
    async with review_client(app) as c:
        yield c


def _insert_workflow(app, workspace_id, slug, steps):
    workflow_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    with app.state.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO workflow_definitions (id, workflow_slug, version, name, "
                "steps, is_template, file_path, is_active, workspace_id, created_at, "
                "updated_at) VALUES (:id, :slug, 1, :slug, :steps, 0, :path, 1, :w, "
                ":now, :now)"
            ),
            {
                "id": workflow_id,
                "slug": slug,
                "path": f"workbench/workflows/{slug}.yaml",
                "steps": json.dumps(steps),
                "w": workspace_id,
                "now": now,
            },
        )
    return workflow_id


def _calibrate_step(**config):
    return {
        "step_id": "calibrate",
        "step_type": "human_calibration",
        "config": {**CALIBRATE, **config},
    }


async def _gold_and_calibration_queue(client, app, tmp_path, steps=None):
    """A gold set promoted from a two-reviewer queue, and a calibration run on it."""
    workspace_id, tokens, review_queue, _ = await _reviewed_and_adjudicated(
        client, app, tmp_path
    )
    await _create(client, tokens[0])
    await _promote(client, tokens[0], {"queue_id": review_queue})
    workflow_id = _insert_workflow(
        app, workspace_id, "calibration", steps or [_calibrate_step()]
    )
    run = await client.post(
        f"/api/v1/workflows/{workflow_id}/execute", json={}, headers=_as(tokens[0])
    )
    assert run.status_code == 202, run.text
    assert run.json()["current_step_id"] == "calibrate", run.text
    queues = await client.get(
        "/api/v1/queues", params={"workspace_id": workspace_id}, headers=_as(tokens[0])
    )
    (queue,) = [q for q in queues.json()["items"] if q["kind"] == "calibrate"]
    return workspace_id, tokens, review_queue, queue


def _latest_labels(app):
    with app.state.engine.connect() as conn:
        return dict(conn.execute(text("SELECT id, latest_label FROM records")).all())


@pytest.mark.asyncio
async def test_a_calibration_step_queues_every_gold_item_once_per_reviewer(
    client, app, tmp_path
):
    _, tokens, _, queue = await _gold_and_calibration_queue(client, app, tmp_path)

    assert queue["total"] == 12
    with app.state.engine.connect() as conn:
        flags = conn.execute(
            text(
                "SELECT DISTINCT is_calibration, agent_output_ids FROM review_tasks "
                "WHERE queue_id = :q"
            ),
            {"q": queue["queue_id"]},
        ).all()
    assert [tuple(row) for row in flags] == [(1, None)]


@pytest.mark.asyncio
async def test_a_calibration_copy_hides_the_ai_proposal_and_refuses_reveal(
    client, app, tmp_path
):
    _, tokens, _, queue = await _gold_and_calibration_queue(client, app, tmp_path)

    task = await _claim(client, queue["queue_id"], tokens[0])

    assert task["agent_output"] is None
    assert "gold" not in json.dumps(task["record_view"])
    revealed = await client.post(
        f"/api/v1/review-tasks/{task['id']}/reveal-ai", headers=_as(tokens[0])
    )
    assert revealed.status_code == 409
    assert revealed.json()["error"]["code"] == "AI_HIDDEN_IN_CALIBRATION"


@pytest.mark.asyncio
async def test_show_ai_proposal_binds_the_runs_proposals(client, app, tmp_path):
    steps = [
        {
            "step_id": "ingest",
            "step_type": "data_ingest",
            "config": {"source": "data/reviews.jsonl"},
        },
        {
            "step_id": "agent_label",
            "step_type": "agent_run",
            "config": {
                "provider_type": "offline",
                "prompt_ref": "prompts/default.yaml",
            },
        },
        _calibrate_step(show_ai_proposal=True),
    ]
    _, tokens, _, queue = await _gold_and_calibration_queue(
        client, app, tmp_path, steps=steps
    )

    task = await _claim(client, queue["queue_id"], tokens[0])

    assert (
        task["agent_output"]["labels"]["sentiment"]
        == (OFFLINE_SENTIMENT[task["record_external_id"]])
    )


@pytest.mark.asyncio
async def test_reviewers_are_scored_against_gold_and_labels_stay_put(
    client, app, tmp_path
):
    _, tokens, _, queue = await _gold_and_calibration_queue(client, app, tmp_path)
    queue_id = queue["queue_id"]
    before = _latest_labels(app)
    close = {**GOLD_SENTIMENT, "r3": "neutral"}
    await _label_all(client, queue_id, tokens[0], close)
    await _label_all(
        client, queue_id, tokens[1], dict.fromkeys(GOLD_SENTIMENT, "negative")
    )

    report = await client.get(
        f"/api/v1/calibration/queues/{queue_id}", headers=_as(tokens[0])
    )

    assert report.status_code == 200, report.text
    body = report.json()
    assert (body["gold_set_id"], body["items"]) == (GOLD, 6)
    assert body["gold_version"] == body["queue_gold_version"] == 2
    scores = {r["reviewer_id"]: r for r in body["reviewers"]}
    first, second = _reviewer_ids_by_token(app, tokens)
    # Against gold (positive 2, negative 3, neutral 1) the first reviewer
    # gives positive 2, negative 2, neutral 2 and misses r3: p_o = 5/6,
    # p_e = (2*2 + 2*3 + 2*1) / 36 = 1/3, so kappa = (5/6 - 1/3) / (2/3).
    sentiment = scores[first]["fields"]["sentiment"]
    assert sentiment["accuracy"] == pytest.approx(5 / 6)
    assert sentiment["cohen_kappa"] == pytest.approx(0.75)
    assert scores[first]["exact_match"] == pytest.approx(5 / 6)
    assert scores[first]["items_answered"] == 6
    # Always "negative": p_o = 3/6 and p_e = 6*3/36 = 1/2, so kappa = 0.
    assert scores[second]["fields"]["sentiment"]["accuracy"] == pytest.approx(0.5)
    assert scores[second]["fields"]["sentiment"]["cohen_kappa"] == pytest.approx(0)
    assert scores[second]["reviewer_name"] == "Workflow Reviewer"
    assert _latest_labels(app) == before


def _reviewer_ids_by_token(app, tokens):
    with app.state.engine.connect() as conn:
        ids = [
            str(r[0])
            for r in conn.execute(
                text("SELECT id FROM reviewer_profiles ORDER BY created_at")
            )
        ]
    return ids[: len(tokens)]


@pytest.mark.asyncio
async def test_the_report_warns_when_gold_moved_on_since_the_queue(
    client, app, tmp_path
):
    workspace_id, tokens, review_queue, queue = await _gold_and_calibration_queue(
        client, app, tmp_path
    )
    with app.state.engine.begin() as conn:
        conn.execute(text("DELETE FROM adjudications"))
    path = tmp_path / "gold" / GOLD / "gold.jsonl"
    lines = path.read_text("utf-8").splitlines()
    path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    await client.post(f"/api/v1/gold-sets/{GOLD}/dedupe", headers=_as(tokens[0]))
    header = (tmp_path / "gold" / GOLD / "gold.yaml").read_text("utf-8")
    (tmp_path / "gold" / GOLD / "gold.yaml").write_text(
        header.replace("version: 2", "version: 3"), encoding="utf-8"
    )

    body = (
        await client.get(
            f"/api/v1/calibration/queues/{queue['queue_id']}", headers=_as(tokens[0])
        )
    ).json()

    assert body["items"] == 5
    assert any("version 3" in w for w in body["warnings"])
    assert any("1 of the queue's records" in w for w in body["warnings"])


@pytest.mark.asyncio
async def test_a_calibration_queue_never_feeds_gold(client, app, tmp_path):
    _, tokens, _, queue = await _gold_and_calibration_queue(client, app, tmp_path)

    resp = await client.post(
        f"/api/v1/gold-sets/{GOLD}/promote",
        json={"queue_id": queue["queue_id"]},
        headers=_as(tokens[0]),
    )

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "GOLD_SOURCE_IS_CALIBRATION"


@pytest.mark.asyncio
async def test_a_review_queue_has_no_calibration_report(client, app, tmp_path):
    _, tokens, review_queue, _ = await _gold_and_calibration_queue(
        client, app, tmp_path
    )

    resp = await client.get(
        f"/api/v1/calibration/queues/{review_queue}", headers=_as(tokens[0])
    )

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_A_CALIBRATION_QUEUE"


@pytest.mark.asyncio
async def test_another_workspace_cannot_read_a_calibration_report(
    client, app, tmp_path
):
    _, _, _, queue = await _gold_and_calibration_queue(client, app, tmp_path)
    outsider = _outsider(app, tmp_path)

    resp = await client.get(
        f"/api/v1/calibration/queues/{queue['queue_id']}", headers=_as(outsider)
    )

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_a_step_naming_a_missing_set_is_refused_before_any_step_runs(
    client, app, tmp_path
):
    workspace_id, tokens, _, _ = await _reviewed_and_adjudicated(client, app, tmp_path)
    workflow_id = _insert_workflow(
        app, workspace_id, "calibration", [_calibrate_step(gold_set="no-such-set")]
    )
    with app.state.engine.connect() as conn:
        executions = conn.execute(text("SELECT count(*) FROM workflow_executions"))
        before = executions.scalar()

    resp = await client.post(
        f"/api/v1/workflows/{workflow_id}/execute", json={}, headers=_as(tokens[0])
    )

    assert resp.status_code == 404
    error = resp.json()["error"]
    assert error["code"] == "GOLD_SET_NOT_FOUND"
    assert error["details"] == {"gold_set_id": "no-such-set", "step_id": "calibrate"}
    with app.state.engine.connect() as conn:
        after = conn.execute(text("SELECT count(*) FROM workflow_executions")).scalar()
    assert after == before


@pytest.mark.asyncio
async def test_a_set_whose_records_this_workspace_lacks_is_refused(
    client, app, tmp_path
):
    workspace_id, tokens, _, _ = await _reviewed_and_adjudicated(client, app, tmp_path)
    await _create(client, tokens[0])
    workflow_id = _insert_workflow(
        app, workspace_id, "calibration", [_calibrate_step()]
    )

    resp = await client.post(
        f"/api/v1/workflows/{workflow_id}/execute", json={}, headers=_as(tokens[0])
    )

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CALIBRATION_GOLD_SET_EMPTY"


@pytest.mark.asyncio
async def test_an_item_finds_its_record_by_dataset_and_external_id(
    client, app, tmp_path
):
    workspace_id, tokens, review_queue, _ = await _reviewed_and_adjudicated(
        client, app, tmp_path
    )
    await _create(client, tokens[0])
    await _promote(client, tokens[0], {"queue_id": review_queue})
    path = tmp_path / "gold" / GOLD / "gold.jsonl"
    lines = [json.loads(line) for line in path.read_text("utf-8").splitlines()]
    for line in lines:
        line["input_ref"]["record_id"] = str(uuid.uuid4())
    path.write_text("".join(json.dumps(line) + "\n" for line in lines), "utf-8")
    workflow_id = _insert_workflow(
        app, workspace_id, "calibration", [_calibrate_step(min_reviewers=1)]
    )

    run = await client.post(
        f"/api/v1/workflows/{workflow_id}/execute", json={}, headers=_as(tokens[0])
    )

    assert run.status_code == 202, run.text
    with app.state.engine.connect() as conn:
        queued = {
            str(r[0])
            for r in conn.execute(
                text("SELECT record_id FROM review_tasks WHERE is_calibration = 1")
            )
        }
    assert queued == set(_external_ids(app).values())

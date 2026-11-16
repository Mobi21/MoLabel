"""Agreement measured from a queue's review events."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from tests.integration.review_flow import (
    FIRST_REVIEWER,
    NO_PAIRS,
    SECOND_REVIEWER,
    _as,
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
# Agreement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agreement_rates_each_reviewer_and_skips_fields_without_pairs(
    client, app, tmp_path
):
    workspace_id, tokens, queue = await _start_review(client, app, tmp_path)
    await _review_both(client, queue["queue_id"], tokens)

    report = await client.get(
        "/api/v1/quality/agreement",
        params={"workspace_id": workspace_id, "queue_id": queue["queue_id"]},
        headers=_as(tokens[0]),
    )
    assert report.status_code == 200, report.text
    body = report.json()
    assert (body["record_count"], body["reviewer_count"]) == (6, 2)

    # Two reviewers per record: pos 4, neg 5, neu 3 of n = 12, one split pair
    # (r3). D_o = 2/12, D_e = (144 - 50) / 132, alpha = 1 - D_o / D_e = 72/94.
    inter = body["inter_annotator"]
    assert inter["fields"]["sentiment"]["krippendorff_alpha"] == pytest.approx(72 / 94)
    assert inter["pooled"]["krippendorff_alpha"] == pytest.approx(72 / 94)
    assert inter["skipped_fields"] == {"note": NO_PAIRS}

    # Twelve human-agent pairs, r3's first-reviewer pair split: pos 8, neg 9,
    # neu 7 of n = 24, D_o = 2/24, D_e = (576 - 194) / 552, alpha = 336/382.
    human_agent = body["human_agent"]
    assert human_agent["fields"]["sentiment"]["percent_agreement"] == pytest.approx(
        11 / 12
    )
    assert human_agent["fields"]["sentiment"]["krippendorff_alpha"] == pytest.approx(
        336 / 382
    )
    assert human_agent["skipped_fields"] == {"note": NO_PAIRS}


def _copy_queue_to_new_schema(app, queue):
    """A second queue on the same records, under a copy of the task schema."""
    queue_id, task_schema_id = str(uuid.uuid4()), str(uuid.uuid4())
    with app.state.engine.begin() as conn:

        def copy(table, row, **changes):
            values = {**row._mapping, **changes}
            conn.execute(
                text(
                    f"INSERT INTO {table} ({', '.join(values)}) "
                    f"VALUES ({', '.join(':' + c for c in values)})"
                ),
                values,
            )

        schema = conn.execute(
            text("SELECT * FROM task_schemas WHERE id = :id"),
            {"id": queue["task_schema_id"]},
        ).one()
        copy("task_schemas", schema, id=task_schema_id, task_schema_slug="copy")
        for task in conn.execute(
            text("SELECT * FROM review_tasks WHERE queue_id = :q"),
            {"q": queue["queue_id"]},
        ).all():
            copy(
                "review_tasks",
                task,
                id=str(uuid.uuid4()),
                queue_id=queue_id,
                task_schema_id=task_schema_id,
                status="available",
                claimed_by=None,
                claimed_at=None,
                submitted_at=None,
                shown_agent_output_id=None,
            )
    return queue_id, task_schema_id


@pytest.mark.asyncio
async def test_agreement_over_two_task_schemas_needs_a_schema_or_queue(
    client, app, tmp_path
):
    workspace_id, tokens, queue = await _start_review(client, app, tmp_path)
    await _review_both(client, queue["queue_id"], tokens)
    other_queue, other_schema = _copy_queue_to_new_schema(app, queue)
    await _label_all(client, other_queue, tokens[0], FIRST_REVIEWER)
    await _label_all(client, other_queue, tokens[1], SECOND_REVIEWER)

    async def agreement(**scope):
        return await client.get(
            "/api/v1/quality/agreement",
            params={"workspace_id": workspace_id, **scope},
            headers=_as(tokens[0]),
        )

    mixed = await agreement()
    assert mixed.status_code == 422, mixed.text

    for scope in (
        {"task_schema_id": queue["task_schema_id"]},
        {"task_schema_id": other_schema},
        {"queue_id": other_queue},
    ):
        body = (await agreement(**scope)).json()
        assert (body["record_count"], body["reviewer_count"]) == (6, 2), scope
        sentiment = body["inter_annotator"]["fields"]["sentiment"]
        assert sentiment["krippendorff_alpha"] == pytest.approx(72 / 94), scope

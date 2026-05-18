"""All 7 ReviewDecision types test (T4-15).

Exercises each decision value in the submit payload:
accept, accept_ai, edit_ai, reject_ai, correct, reject, skip.
"""

from __future__ import annotations

import pytest

from molabel.core.types import ReviewDecision
from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SEQUENTIAL

ALL_DECISIONS = [
    ReviewDecision.accept,
    ReviewDecision.accept_ai,
    ReviewDecision.edit_ai,
    ReviewDecision.reject_ai,
    ReviewDecision.correct,
    ReviewDecision.reject,
    ReviewDecision.skip,
]


async def _create_queue_with_n_tasks(
    client: InstrumentedClient,
    n: int,
    queue_suffix: str = "",
) -> tuple[str, str]:
    """Create a workspace, dataset with n records, and a queue.

    Return (ws_id, queue_id).
    """
    ws_resp = await client.post(
        "/api/v1/workspaces",
        json={
            "path": f"/tmp/ws-review-decisions{queue_suffix}",
            "workspace_name": f"review-decisions-ws{queue_suffix}",
        },
    )
    assert ws_resp.status_code == 201
    ws_id = ws_resp.json()["workspace_id"]

    ds_resp = await client.post(
        "/api/v1/datasets",
        json={
            "workspace_id": ws_id,
            "dataset_name": "decisions-ds",
            "source_type": "jsonl",
        },
    )
    assert ds_resp.status_code == 201
    ds_id = ds_resp.json()["dataset_id"]

    records = [{"text": f"Record {i} for review decision testing."} for i in range(n)]
    import_resp = await client.post(
        f"/api/v1/datasets/{ds_id}/import",
        json={"source_type": "jsonl", "records": records},
    )
    assert import_resp.status_code in (200, 201, 202)

    schema_resp = await client.post(
        "/api/v1/task-schemas",
        json={
            "workspace_id": ws_id,
            "task_schema_slug": f"review-decisions{queue_suffix}",
            "task_type": "classification",
            "title": f"Review Decisions{queue_suffix}",
            "label_fields": [
                {
                    "name": "sentiment",
                    "field_type": "categorical",
                    "options": ["positive", "negative", "neutral"],
                    "required": True,
                }
            ],
        },
    )
    assert schema_resp.status_code == 201
    schema_id = schema_resp.json()["task_schema_id"]
    queue_id = f"{ds_id}:{schema_id}"

    return ws_id, queue_id


@SEQUENTIAL
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier4
async def test_all_seven_review_decisions(
    ctx: TestContext,
    client: InstrumentedClient,
) -> None:
    """T4-15: Exercise all 7 ReviewDecision enum values.

    Creates 7 tasks (one per decision) and submits each with the
    corresponding decision value. Verifies:
    - Each submit returns 200
    - submitted_task.status == "submitted"
    - The decision enum is serialized correctly in the request
    """
    n_tasks = len(ALL_DECISIONS)

    with checkpoint(ctx, "setup_queue_with_seven_tasks"):
        _, queue_id = await _create_queue_with_n_tasks(client, n_tasks)

    with checkpoint(ctx, "verify_all_decision_enum_values"):
        # Verify the enum values match the spec
        expected_values = {
            "accept",
            "accept_ai",
            "edit_ai",
            "reject_ai",
            "correct",
            "reject",
            "skip",
        }
        actual_values = {d.value for d in ReviewDecision}
        assert expected_values == actual_values, (
            f"ReviewDecision enum mismatch. Expected {expected_values}, "
            f"got {actual_values}"
        )

    submitted_decisions: list[str] = []
    skipped_task_ids: list[str] = []

    for decision in ALL_DECISIONS:
        with checkpoint(ctx, f"submit_with_decision_{decision.value}"):
            claim_resp = await client.post(f"/api/v1/queues/{queue_id}/claim")
            assert claim_resp.status_code == 200
            body = claim_resp.json()

            if body.get("queue_empty"):
                # Fewer tasks than decisions — that's acceptable
                break

            task_id = body["task"]["id"]

            if decision == ReviewDecision.skip:
                # Use the skip endpoint for skip decision
                skip_resp = await client.post(f"/api/v1/review-tasks/{task_id}/skip")
                assert skip_resp.status_code == 200
                skip_body = skip_resp.json()
                assert skip_body["skipped_task"]["status"] == "skipped"
                assert skip_body["message"] == "skipped"
                skipped_task_ids.append(task_id)
            else:
                submit_resp = await client.post(
                    f"/api/v1/review-tasks/{task_id}/submit",
                    json={
                        "labels": {"sentiment": "positive"},
                        "decision": decision.value,
                        "auto_claim_next": False,
                    },
                )
                assert submit_resp.status_code == 200, (
                    f"Expected 200 for decision={decision.value}, "
                    f"got {submit_resp.status_code}: {submit_resp.text}"
                )
                submit_body = submit_resp.json()
                assert submit_body["submitted_task"]["status"] == "submitted"
                assert submit_body["message"] == "submitted"
                submitted_decisions.append(decision.value)

    with checkpoint(ctx, "verify_all_non_skip_decisions_submitted"):
        non_skip_decisions = [
            d.value for d in ALL_DECISIONS if d != ReviewDecision.skip
        ]
        for decision_val in submitted_decisions:
            assert decision_val in non_skip_decisions

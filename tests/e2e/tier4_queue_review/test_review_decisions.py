"""Review decision vocabulary test (T4-15).

Submits each canonical decision (accept, edit, reject) and each deprecated
alias, and skips one task through the skip endpoint.
"""

from __future__ import annotations

import pytest

from molabel.core.types import DeprecatedReviewDecision, ReviewDecision
from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SEQUENTIAL

CANONICAL_DECISIONS = [decision.value for decision in ReviewDecision]
DEPRECATED_DECISIONS = [decision.value for decision in DeprecatedReviewDecision]
SUBMIT_DECISIONS = CANONICAL_DECISIONS + DEPRECATED_DECISIONS


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
async def test_review_decision_vocabulary(
    ctx: TestContext,
    client: InstrumentedClient,
) -> None:
    """T4-15: Submit every canonical decision and deprecated alias, then skip."""
    with checkpoint(ctx, "setup_queue"):
        _, queue_id = await _create_queue_with_n_tasks(
            client, len(SUBMIT_DECISIONS) + 1
        )

    with checkpoint(ctx, "verify_canonical_decision_values"):
        assert set(CANONICAL_DECISIONS) == {"accept", "edit", "reject"}

    for decision in SUBMIT_DECISIONS:
        with checkpoint(ctx, f"submit_with_decision_{decision}"):
            claim_resp = await client.post(f"/api/v1/queues/{queue_id}/claim")
            assert claim_resp.status_code == 200
            body = claim_resp.json()
            if body.get("queue_empty"):
                break
            task_id = body["task"]["id"]

            submit_resp = await client.post(
                f"/api/v1/review-tasks/{task_id}/submit",
                json={
                    "labels": {"sentiment": "positive"},
                    "decision": decision,
                    "auto_claim_next": False,
                },
            )
            assert submit_resp.status_code == 200, submit_resp.text
            submit_body = submit_resp.json()
            assert submit_body["submitted_task"]["status"] == "submitted"
            assert bool(submit_body["deprecations"]) == (
                decision in DEPRECATED_DECISIONS
            )

    with checkpoint(ctx, "skip_uses_the_skip_endpoint"):
        claim_resp = await client.post(f"/api/v1/queues/{queue_id}/claim")
        assert claim_resp.status_code == 200
        body = claim_resp.json()
        if not body.get("queue_empty"):
            skip_resp = await client.post(
                f"/api/v1/review-tasks/{body['task']['id']}/skip"
            )
            assert skip_resp.status_code == 200
            assert skip_resp.json()["skipped_task"]["status"] == "skipped"

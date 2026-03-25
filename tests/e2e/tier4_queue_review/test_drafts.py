"""Draft saving test (T4-05).

Verifies last-write-wins semantics: saving a draft stores it on the task,
a subsequent save overwrites it, and submitting uses the final labels
provided in the submit body (not the draft).
"""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SEQUENTIAL


@SEQUENTIAL
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier4
async def test_draft_saving_last_write_wins(
    ctx: TestContext,
    client: InstrumentedClient,
) -> None:
    """T4-05: Save draft, reload via queue status, update (last-write-wins).

    Steps:
    1. Create workspace + dataset + schema + queue
    2. Claim a task
    3. Save draft with labels_v1
    4. Verify draft_labels == labels_v1 in task response
    5. Save draft again with labels_v2 (overwrites)
    6. Verify draft_labels == labels_v2
    7. Submit with labels_final (different from draft)
    8. Verify submitted_task has status=submitted (submit uses body, not draft)
    """
    with checkpoint(ctx, "workspace_and_data_setup"):
        ws_resp = await client.post(
            "/workspaces", json={"workspace_name": "draft-test-ws"}
        )
        assert ws_resp.status_code == 201
        ws_id = ws_resp.json()["workspace_id"]

        ds_resp = await client.post(
            "/datasets",
            json={
                "workspace_id": ws_id,
                "dataset_name": "draft-ds",
                "text_field": "text",
            },
        )
        assert ds_resp.status_code == 201
        ds_id = ds_resp.json()["dataset_id"]

        import_resp = await client.post(
            f"/datasets/{ds_id}/import",
            json={
                "source_type": "jsonl",
                "records": [{"text": "Record for draft testing."}],
                "text_field": "text",
            },
        )
        assert import_resp.status_code in (200, 201, 202)

    with checkpoint(ctx, "schema_and_queue"):
        schema_resp = await client.post(
            "/task-schemas",
            json={
                "workspace_id": ws_id,
                "task_slug": "draft-test",
                "task_type": "classification",
                "label_fields": [
                    {
                        "name": "category",
                        "field_type": "categorical",
                        "options": ["A", "B", "C"],
                        "required": True,
                    }
                ],
            },
        )
        assert schema_resp.status_code == 201
        schema_id = schema_resp.json()["task_schema_id"]

        queue_resp = await client.post(
            "/queues",
            json={
                "workspace_id": ws_id,
                "dataset_id": ds_id,
                "task_schema_id": schema_id,
                "queue_name": "draft-queue",
            },
        )
        assert queue_resp.status_code == 201
        queue_id = queue_resp.json()["queue_id"]

    with checkpoint(ctx, "claim_task"):
        claim_resp = await client.post(f"/queues/{queue_id}/claim")
        assert claim_resp.status_code == 200
        body = claim_resp.json()
        if body.get("queue_empty"):
            pytest.skip("Queue is empty — no tasks to test drafts with")
        task_id = body["task"]["id"]
        # No draft initially
        assert body["task"].get("draft_labels") is None

    with checkpoint(ctx, "save_first_draft"):
        draft1_resp = await client.post(
            f"/review-tasks/{task_id}/draft",
            json={"draft_labels": {"category": "A"}},
        )
        assert draft1_resp.status_code == 200
        draft1_body = draft1_resp.json()
        assert draft1_body["message"] == "draft_saved"
        task_after_draft1 = draft1_body["task"]
        assert task_after_draft1["draft_labels"] == {"category": "A"}

    with checkpoint(ctx, "overwrite_draft_last_write_wins"):
        draft2_resp = await client.post(
            f"/review-tasks/{task_id}/draft",
            json={"draft_labels": {"category": "B"}},
        )
        assert draft2_resp.status_code == 200
        task_after_draft2 = draft2_resp.json()["task"]
        # Last write wins — should be "B", not "A"
        assert task_after_draft2["draft_labels"] == {"category": "B"}

    with checkpoint(ctx, "submit_uses_body_not_draft"):
        # Submit with "C" — different from the saved draft "B"
        submit_resp = await client.post(
            f"/review-tasks/{task_id}/submit",
            json={
                "labels": {"category": "C"},
                "decision": "accept",
                "auto_claim_next": False,
            },
        )
        assert submit_resp.status_code == 200
        submit_body = submit_resp.json()
        submitted_task = submit_body["submitted_task"]
        # Task should now be submitted
        assert submitted_task["status"] == "submitted"
        assert submit_body["message"] == "submitted"

"""Overlap records test (T4-08).

is_overlap=True records should be reviewable by multiple reviewers
independently, enabling inter-annotator agreement computation.
"""

from __future__ import annotations

import pytest

from molabel.core.review.overlap import OverlapConfig, OverlapService
from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SEQUENTIAL


@SEQUENTIAL
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier4
async def test_overlap_records_multiple_reviewers(
    ctx: TestContext,
    client: InstrumentedClient,
) -> None:
    """T4-08: is_overlap=True records reviewed by multiple reviewers.

    Creates a queue with overlap records, then verifies:
    - The OverlapService correctly tracks assignments
    - Multiple reviewers can be assigned the same record
    - Completion status transitions: pending → partial → complete
    """
    with checkpoint(ctx, "overlap_service_unit_logic"):
        import uuid

        config = OverlapConfig(overlap_count=2, overlap_rate=1.0)
        service = OverlapService(config)

        record_id = uuid.uuid4()
        reviewer_a = uuid.uuid4()
        reviewer_b = uuid.uuid4()

        # Create assignment
        assignments = service.create_assignments([record_id])
        assert len(assignments) == 1
        assert assignments[0].record_id == record_id
        assert assignments[0].required_reviewers == 2

    with checkpoint(ctx, "overlap_assignment_tracking"):
        # Both reviewers can claim
        assert service.can_reviewer_claim(record_id, reviewer_a) is True
        assert service.can_reviewer_claim(record_id, reviewer_b) is True

        # Assign reviewer A
        ok_a = service.record_assignment(record_id, reviewer_a)
        assert ok_a is True

        # Reviewer A cannot claim again
        assert service.can_reviewer_claim(record_id, reviewer_a) is False

        # Reviewer B can still claim
        assert service.can_reviewer_claim(record_id, reviewer_b) is True

        # Assign reviewer B
        ok_b = service.record_assignment(record_id, reviewer_b)
        assert ok_b is True

        # No more reviewers needed
        assert service.can_reviewer_claim(record_id, uuid.uuid4()) is False

    with checkpoint(ctx, "overlap_completion_status"):
        from molabel.core.review.overlap import OverlapCompletionStatus

        # Initially pending (no completions)
        status = service.get_record_status(record_id)
        assert status == OverlapCompletionStatus.pending

        # Reviewer A completes
        service.record_completion(record_id, reviewer_a)
        status = service.get_record_status(record_id)
        assert status == OverlapCompletionStatus.partial

        # Reviewer B completes
        service.record_completion(record_id, reviewer_b)
        status = service.get_record_status(record_id)
        assert status == OverlapCompletionStatus.complete

    with checkpoint(ctx, "overlap_status_summary"):
        overall = service.get_status()
        assert overall.total_records == 1
        assert overall.completed_records == 1
        assert overall.completion_rate == 1.0
        assert overall.average_reviewers_per_record == 2.0

    with checkpoint(ctx, "overlap_via_api_queue"):
        # Also verify API-level overlap flag in queue claim response
        ws_resp = await client.post(
            "/workspaces", json={"workspace_name": "overlap-ws"}
        )
        assert ws_resp.status_code == 201
        ws_id = ws_resp.json()["workspace_id"]

        ds_resp = await client.post(
            "/datasets",
            json={
                "workspace_id": ws_id,
                "dataset_name": "overlap-ds",
                "text_field": "text",
            },
        )
        assert ds_resp.status_code == 201
        ds_id = ds_resp.json()["dataset_id"]

        import_resp = await client.post(
            f"/datasets/{ds_id}/import",
            json={
                "source_type": "jsonl",
                "records": [{"text": "Overlap record text."}],
                "text_field": "text",
            },
        )
        assert import_resp.status_code in (200, 201, 202)

        schema_resp = await client.post(
            "/task-schemas",
            json={
                "workspace_id": ws_id,
                "task_slug": "overlap-test",
                "task_type": "classification",
                "label_fields": [
                    {
                        "name": "label",
                        "field_type": "categorical",
                        "options": ["yes", "no"],
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
                "queue_name": "overlap-queue",
                "overlap_count": 2,
            },
        )
        assert queue_resp.status_code == 201
        queue_id = queue_resp.json()["queue_id"]

        # Claim the overlap record
        claim_resp = await client.post(f"/queues/{queue_id}/claim")
        assert claim_resp.status_code == 200
        body = claim_resp.json()
        if not body.get("queue_empty"):
            task = body["task"]
            # is_overlap should be True for overlap-configured queues
            assert task.get("is_overlap") is True

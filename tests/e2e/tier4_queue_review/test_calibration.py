"""Calibration queue test (T4-09).

is_calibration=True records have known ground truth (gold labels).
The CalibrationService computes reviewer alignment against those labels.
"""

from __future__ import annotations

import uuid

import pytest

from molabel.core.review.calibration import (
    CalibrationConfig,
    CalibrationItem,
    CalibrationService,
    CalibrationStatus,
)
from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SEQUENTIAL


@SEQUENTIAL
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier4
async def test_calibration_reviewer_alignment(
    ctx: TestContext,
    client: InstrumentedClient,
) -> None:
    """T4-09: is_calibration=True with known ground truth; reviewer alignment measured.

    Uses the CalibrationService directly (pure unit layer) to verify:
    - Perfect reviewer scores 1.0
    - Partial reviewer scores < 1.0
    - Threshold-based pass/fail
    Then exercises the API queue with calibration flag.
    """
    schema_id = uuid.uuid4()
    record_ids = [uuid.uuid4() for _ in range(5)]

    with checkpoint(ctx, "setup_calibration_service"):
        config = CalibrationConfig(min_reviewers=1, pass_threshold=0.8, item_count=5)
        service = CalibrationService(config)

        # 5 gold-standard items: all "positive"
        items = [
            CalibrationItem(
                record_id=rid,
                gold_labels={"sentiment": "positive"},
                task_schema_id=schema_id,
            )
            for rid in record_ids
        ]
        service.set_items(items)

    with checkpoint(ctx, "perfect_reviewer_passes"):
        reviewer_perfect = uuid.uuid4()
        # Submit all-correct answers
        for item in items:
            service.record_submission(
                reviewer_perfect, item.record_id, {"sentiment": "positive"}
            )

        result_perfect = service.evaluate_reviewer(reviewer_perfect)
        assert result_perfect.items_attempted == 5
        assert result_perfect.items_correct == 5
        assert result_perfect.accuracy == 1.0
        assert result_perfect.status == CalibrationStatus.passed
        assert result_perfect.field_scores.get("sentiment") == 1.0

    with checkpoint(ctx, "partial_reviewer_fails"):
        reviewer_partial = uuid.uuid4()
        # Submit 3/5 correct
        for i, item in enumerate(items):
            label = "positive" if i < 3 else "negative"
            service.record_submission(
                reviewer_partial, item.record_id, {"sentiment": label}
            )

        result_partial = service.evaluate_reviewer(reviewer_partial)
        assert result_partial.items_attempted == 5
        assert result_partial.items_correct == 3
        assert result_partial.accuracy == pytest.approx(0.6, rel=1e-3)
        assert result_partial.status == CalibrationStatus.failed
        assert len(result_partial.incorrect_items) == 2

    with checkpoint(ctx, "borderline_reviewer_just_passes"):
        reviewer_border = uuid.uuid4()
        # Submit 4/5 correct (80% == pass threshold)
        for i, item in enumerate(items):
            label = "positive" if i < 4 else "negative"
            service.record_submission(
                reviewer_border, item.record_id, {"sentiment": label}
            )

        result_border = service.evaluate_reviewer(reviewer_border)
        assert result_border.accuracy == pytest.approx(0.8, rel=1e-3)
        assert result_border.status == CalibrationStatus.passed

    with checkpoint(ctx, "incomplete_reviewer_is_in_progress"):
        reviewer_incomplete = uuid.uuid4()
        # Submit only 2 out of 5
        for item in items[:2]:
            service.record_submission(
                reviewer_incomplete, item.record_id, {"sentiment": "positive"}
            )

        result_incomplete = service.evaluate_reviewer(reviewer_incomplete)
        assert result_incomplete.status == CalibrationStatus.in_progress
        assert service.has_completed_calibration(reviewer_incomplete) is False

    with checkpoint(ctx, "service_aggregate_state"):
        assert service.has_enough_reviewers() is True  # >= 1 min_reviewers passed
        passed = service.get_passed_reviewers()
        assert reviewer_perfect in passed
        assert reviewer_border in passed
        assert reviewer_partial not in passed

    with checkpoint(ctx, "calibration_api_queue"):
        # Verify API-level calibration flag
        ws_resp = await client.post(
            "/api/v1/workspaces",
            json={"path": "/tmp/ws-calibration-ws", "workspace_name": "calibration-ws"},
        )
        assert ws_resp.status_code == 201
        ws_id = ws_resp.json()["workspace_id"]

        ds_resp = await client.post(
            "/api/v1/datasets",
            json={
                "workspace_id": ws_id,
                "dataset_name": "calib-ds",
                "source_type": "jsonl",
            },
        )
        assert ds_resp.status_code == 201
        ds_id = ds_resp.json()["dataset_id"]

        import_resp = await client.post(
            f"/api/v1/datasets/{ds_id}/import",
            json={
                "source_type": "jsonl",
                "records": [{"text": "Calibration record."}],
            },
        )
        assert import_resp.status_code in (200, 201, 202)

        schema_resp = await client.post(
            "/api/v1/task-schemas",
            json={
                "workspace_id": ws_id,
                "task_schema_slug": "calibration-test",
                "title": "Calibration Test",
                "task_type": "classification",
                "label_fields": [
                    {
                        "name": "sentiment",
                        "field_type": "categorical",
                        "options": ["positive", "negative"],
                        "required": True,
                    }
                ],
            },
        )
        assert schema_resp.status_code == 201
        schema_id_api = schema_resp.json()["task_schema_id"]
        queue_id = f"{ds_id}:{schema_id_api}"

        claim_resp = await client.post(f"/api/v1/queues/{queue_id}/claim")
        assert claim_resp.status_code == 200
        body = claim_resp.json()
        if not body.get("queue_empty"):
            task = body["task"]
            assert task.get("is_calibration") is True

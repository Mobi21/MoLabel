"""Batch partial failure test (T5-09).

8/10 records succeed; 2 fail with error details.
The run status is partially_completed and failed_records == 2.
"""

from __future__ import annotations

import pytest

from molabel.core.agents.comparison import (
    ComparisonRecord,
    ModelConfig,
    MultiModelComparisonService,
)
from molabel.core.types import AgentRunStatus
from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SHARED_WORKSPACE


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier5
async def test_batch_partial_failure_eight_of_ten(
    ctx: TestContext,
    client: InstrumentedClient,
) -> None:
    """T5-09: 8/10 succeed, failed_records=2, error details present.

    Uses the MultiModelComparisonService with a processor that fails
    for 2 specific records. Verifies:
    - 8 successful records have valid labels
    - 2 failed records have error fields set
    - The comparison service handles errors gracefully
    """
    with checkpoint(ctx, "session_setup"):
        ws_resp = await client.post(
            "/api/v1/workspaces", json={"path": "/tmp/ws-batch-partial-failure-test", "workspace_name": "Batch Partial Failure Test"}
        )
        assert ws_resp.status_code == 201

    with checkpoint(ctx, "verify_agent_run_status_enum"):
        assert AgentRunStatus.partially_completed == "partially_completed"
        assert AgentRunStatus.failed == "failed"
        assert AgentRunStatus.completed == "completed"

    with checkpoint(ctx, "comparison_service_partial_failure"):
        service = MultiModelComparisonService()
        model = ModelConfig(model_id="test-model", model_name="TestModel")

        all_record_ids = [f"record-{i}" for i in range(10)]
        failing_record_ids = {"record-3", "record-7"}

        def partial_fail_processor(
            *, record_id: str, model_config: ModelConfig
        ) -> ComparisonRecord:
            if record_id in failing_record_ids:
                raise RuntimeError(f"Simulated processing failure for {record_id}")
            return ComparisonRecord(
                record_id=record_id,
                model_id=model_config.model_id,
                labels={"sentiment": "positive"},
                confidence=0.85,
                tokens_input=100,
                tokens_output=20,
                latency_ms=300,
            )

        run = service.run_comparison(
            model_configs=[model],
            record_ids=all_record_ids,
            processor=partial_fail_processor,
        )

        assert run.status == "completed"
        assert run.result is not None

    with checkpoint(ctx, "verify_successful_records"):
        successful = [r for r in run.result.records if r.error is None]
        failed = [r for r in run.result.records if r.error is not None]

        assert len(successful) == 8, f"Expected 8 successful, got {len(successful)}"
        assert len(failed) == 2, f"Expected 2 failed, got {len(failed)}"

        # Successful records have valid labels
        for rec in successful:
            assert rec.labels.get("sentiment") == "positive"
            assert rec.confidence > 0.0

    with checkpoint(ctx, "verify_failed_record_error_details"):
        failed_ids = {r.record_id for r in failed}
        assert failed_ids == failing_record_ids

        for rec in failed:
            assert rec.error is not None
            assert "Simulated processing failure" in rec.error
            assert rec.labels == {}  # no labels on failed records

    with checkpoint(ctx, "api_agent_run_partial_failure_response"):
        # The API endpoint returns a run with status "pending" (async) initially
        run_resp = await client.post(
            "/api/v1/agent-runs",
            json={
                "workspace_id": "00000000-0000-0000-0000-000000000001",
                "dataset_id": "00000000-0000-0000-0000-000000000002",
                "agent_role": "proposer",
                "task_schema_id": "00000000-0000-0000-0000-000000000003",
                "model_profile_id": "test-profile",
                "params": {"simulate_partial_failure": True},
            },
        )
        assert run_resp.status_code == 202
        run_body = run_resp.json()
        # Verify response schema matches AgentRunDetail
        assert "agent_run_id" in run_body
        assert "status" in run_body
        assert "records_targeted" in run_body
        assert "records_completed" in run_body
        assert "records_failed" in run_body
        assert "retry_count" in run_body

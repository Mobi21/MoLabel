"""Validation runs test (T6-08).

Multiple threshold configurations tested via ValidationRunService.
Verifies overall pass/fail based on gate results.
"""

from __future__ import annotations

import uuid

import pytest

from molabel.core.quality.validation_run_service import (
    GateConfig,
    GateResult,
    ValidationRunService,
)
from molabel.core.types import ValidationStatus
from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SHARED_WORKSPACE


def _make_gate_result(
    gate_id: str,
    passed: bool,
    metric_value: float | None = None,
    threshold: float | None = None,
) -> GateResult:
    return GateResult(
        gate_id=gate_id,
        gate_name=f"Gate-{gate_id}",
        passed=passed,
        status="passed" if passed else "failed",
        metric_value=metric_value,
        threshold=threshold,
    )


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier6
async def test_validation_runs_multiple_threshold_configs(
    ctx: TestContext,
    client: InstrumentedClient,
) -> None:
    """T6-08: Multiple threshold configs; overall pass/fail status."""
    service = ValidationRunService()

    with checkpoint(ctx, "run_lifecycle_pending_to_running"):
        run = service.create_run(
            run_id=str(uuid.uuid4()),
            target_type="dataset",
            target_id="dataset-test-01",
        )
        assert run.status == ValidationStatus.pending

        running_run = service.start_run(run)
        assert running_run.status == ValidationStatus.running
        assert running_run.started_at is not None

    with checkpoint(ctx, "all_gates_pass"):
        gate_results_all_pass = [
            _make_gate_result(
                "min_agreement", passed=True, metric_value=0.9, threshold=0.8
            ),
            _make_gate_result(
                "min_coverage", passed=True, metric_value=0.95, threshold=0.9
            ),
            _make_gate_result(
                "min_confidence", passed=True, metric_value=0.85, threshold=0.7
            ),
        ]

        gate_configs = [
            GateConfig(gate_id="min_agreement", required=True),
            GateConfig(gate_id="min_coverage", required=True),
            GateConfig(gate_id="min_confidence", required=True),
        ]

        final_pass = service.execute_gates_from_results(
            running_run,
            gate_results=gate_results_all_pass,
            gate_configs=gate_configs,
        )

        assert final_pass.status == ValidationStatus.passed
        assert final_pass.passed_count == 3
        assert final_pass.failed_count == 0
        assert final_pass.total_count == 3
        assert "All 3 gates passed" in final_pass.summary

    with checkpoint(ctx, "required_gate_fails"):
        gate_results_one_fail = [
            _make_gate_result(
                "min_agreement", passed=True, metric_value=0.9, threshold=0.8
            ),
            _make_gate_result(
                "min_coverage", passed=False, metric_value=0.7, threshold=0.9
            ),
            _make_gate_result(
                "min_confidence", passed=True, metric_value=0.85, threshold=0.7
            ),
        ]

        final_fail = service.execute_gates_from_results(
            running_run,
            gate_results=gate_results_one_fail,
            gate_configs=gate_configs,
        )

        assert final_fail.status == ValidationStatus.failed
        assert final_fail.failed_count == 1
        assert final_fail.passed_count == 2

    with checkpoint(ctx, "optional_gate_failure_gives_warning"):
        optional_gate_configs = [
            GateConfig(gate_id="min_agreement", required=True),
            GateConfig(gate_id="optional_gate", required=False),  # not required
        ]
        gate_results_optional_fail = [
            _make_gate_result("min_agreement", passed=True),
            GateResult(
                gate_id="optional_gate",
                gate_name="Optional Gate",
                passed=False,
                status="warning",
                metric_value=0.6,
                threshold=0.8,
            ),
        ]

        final_warning = service.execute_gates_from_results(
            running_run,
            gate_results=gate_results_optional_fail,
            gate_configs=optional_gate_configs,
        )

        assert final_warning.status == ValidationStatus.warning

    with checkpoint(ctx, "strict_threshold_fails_borderline"):
        # min_agreement threshold of 0.95 — metric is 0.9 → fail
        strict_gate_results = [
            _make_gate_result(
                "min_agreement", passed=False, metric_value=0.9, threshold=0.95
            ),
        ]
        strict_gate_configs = [GateConfig(gate_id="min_agreement", required=True)]

        final_strict = service.execute_gates_from_results(
            running_run,
            gate_results=strict_gate_results,
            gate_configs=strict_gate_configs,
        )
        assert final_strict.status == ValidationStatus.failed

    with checkpoint(ctx, "lenient_threshold_passes_same_metric"):
        # min_agreement threshold of 0.85 — metric is 0.9 → pass
        lenient_gate_results = [
            _make_gate_result(
                "min_agreement", passed=True, metric_value=0.9, threshold=0.85
            ),
        ]
        lenient_gate_configs = [GateConfig(gate_id="min_agreement", required=True)]

        final_lenient = service.execute_gates_from_results(
            running_run,
            gate_results=lenient_gate_results,
            gate_configs=lenient_gate_configs,
        )
        assert final_lenient.status == ValidationStatus.passed

    with checkpoint(ctx, "completed_at_set_after_finalization"):
        assert final_pass.completed_at is not None
        assert final_fail.completed_at is not None

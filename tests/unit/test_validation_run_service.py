"""Tests for the validation run lifecycle service (QA-010)."""

from __future__ import annotations

from typing import Any

import pytest

from molabel.core.quality.validation_run_service import (
    GateConfig,
    GateResult,
    ValidationGatePlugin,
    ValidationRunService,
)
from molabel.core.types import ValidationStatus


class _PassingPlugin:
    """A test plugin that always passes."""

    def execute_gate(
        self,
        *,
        gate_id: str,
        target_type: str,
        target_id: str,
        config: dict[str, Any],
        context: dict[str, Any],
    ) -> GateResult:
        return GateResult(
            gate_id=gate_id,
            gate_name=f"Gate {gate_id}",
            passed=True,
            status="passed",
            message="All checks passed.",
        )


class _FailingPlugin:
    """A test plugin that always fails."""

    def execute_gate(
        self,
        *,
        gate_id: str,
        target_type: str,
        target_id: str,
        config: dict[str, Any],
        context: dict[str, Any],
    ) -> GateResult:
        return GateResult(
            gate_id=gate_id,
            gate_name=f"Gate {gate_id}",
            passed=False,
            status="failed",
            message="Check failed.",
        )


class _WarningPlugin:
    """A test plugin that returns warnings."""

    def execute_gate(
        self,
        *,
        gate_id: str,
        target_type: str,
        target_id: str,
        config: dict[str, Any],
        context: dict[str, Any],
    ) -> GateResult:
        return GateResult(
            gate_id=gate_id,
            gate_name=f"Gate {gate_id}",
            passed=False,
            status="warning",
            message="Warning: threshold close.",
        )


class _ExplodingPlugin:
    """A test plugin that raises an exception."""

    def execute_gate(
        self,
        *,
        gate_id: str,
        target_type: str,
        target_id: str,
        config: dict[str, Any],
        context: dict[str, Any],
    ) -> GateResult:
        raise RuntimeError("Boom!")


def test_create_run() -> None:
    service = ValidationRunService()
    run = service.create_run(
        run_id="run-1",
        target_type="dataset",
        target_id="ds-1",
    )

    assert run.run_id == "run-1"
    assert run.target_type == "dataset"
    assert run.target_id == "ds-1"
    assert run.status == ValidationStatus.pending
    assert run.total_count == 0


def test_start_run() -> None:
    service = ValidationRunService()
    run = service.create_run(
        run_id="run-1",
        target_type="dataset",
        target_id="ds-1",
    )
    started = service.start_run(run)

    assert started.status == ValidationStatus.running
    assert started.started_at is not None


def test_start_run_rejects_non_pending() -> None:
    service = ValidationRunService()
    run = service.create_run(
        run_id="run-1",
        target_type="dataset",
        target_id="ds-1",
    )
    started = service.start_run(run)

    with pytest.raises(ValueError, match="Cannot start run"):
        service.start_run(started)


def test_all_gates_pass() -> None:
    service = ValidationRunService()
    run = service.create_run(run_id="run-1", target_type="dataset", target_id="ds-1")
    run = service.start_run(run)

    result = service.execute_gates(
        run,
        gate_configs=[
            GateConfig(gate_id="g1", gate_name="Agreement", plugin_id="checker"),
            GateConfig(gate_id="g2", gate_name="Coverage", plugin_id="checker"),
        ],
        plugins={"checker": _PassingPlugin()},
    )

    assert result.status == ValidationStatus.passed
    assert result.passed_count == 2
    assert result.failed_count == 0
    assert result.total_count == 2
    assert result.completed_at is not None
    assert "passed" in result.summary.lower()


def test_required_gate_failure() -> None:
    service = ValidationRunService()
    run = service.create_run(run_id="run-1", target_type="dataset", target_id="ds-1")
    run = service.start_run(run)

    result = service.execute_gates(
        run,
        gate_configs=[
            GateConfig(
                gate_id="g1",
                gate_name="Agreement",
                plugin_id="passer",
                required=True,
            ),
            GateConfig(
                gate_id="g2",
                gate_name="Coverage",
                plugin_id="failer",
                required=True,
            ),
        ],
        plugins={
            "passer": _PassingPlugin(),
            "failer": _FailingPlugin(),
        },
    )

    assert result.status == ValidationStatus.failed
    assert result.passed_count == 1
    assert result.failed_count == 1


def test_optional_gate_failure_produces_warning() -> None:
    service = ValidationRunService()
    run = service.create_run(run_id="run-1", target_type="dataset", target_id="ds-1")
    run = service.start_run(run)

    result = service.execute_gates(
        run,
        gate_configs=[
            GateConfig(
                gate_id="g1",
                gate_name="Agreement",
                plugin_id="passer",
                required=True,
            ),
            GateConfig(
                gate_id="g2",
                gate_name="Drift",
                plugin_id="failer",
                required=False,
            ),
        ],
        plugins={
            "passer": _PassingPlugin(),
            "failer": _FailingPlugin(),
        },
    )

    assert result.status == ValidationStatus.warning
    assert result.passed_count == 1
    assert result.failed_count == 1


def test_warning_gate_produces_warning_status() -> None:
    service = ValidationRunService()
    run = service.create_run(run_id="run-1", target_type="dataset", target_id="ds-1")
    run = service.start_run(run)

    result = service.execute_gates(
        run,
        gate_configs=[
            GateConfig(gate_id="g1", plugin_id="passer"),
            GateConfig(gate_id="g2", plugin_id="warner"),
        ],
        plugins={"passer": _PassingPlugin(), "warner": _WarningPlugin()},
    )

    assert result.status == ValidationStatus.warning
    assert result.warning_count == 1


def test_missing_plugin_produces_error() -> None:
    service = ValidationRunService()
    run = service.create_run(run_id="run-1", target_type="dataset", target_id="ds-1")
    run = service.start_run(run)

    result = service.execute_gates(
        run,
        gate_configs=[
            GateConfig(gate_id="g1", gate_name="Check", plugin_id="nonexistent"),
        ],
        plugins={},
    )

    assert result.status == ValidationStatus.failed
    assert result.gate_results[0].status == "error"
    assert "not found" in result.gate_results[0].message.lower()


def test_plugin_exception_produces_error() -> None:
    service = ValidationRunService()
    run = service.create_run(run_id="run-1", target_type="dataset", target_id="ds-1")
    run = service.start_run(run)

    result = service.execute_gates(
        run,
        gate_configs=[
            GateConfig(gate_id="g1", plugin_id="exploder"),
        ],
        plugins={"exploder": _ExplodingPlugin()},
    )

    assert result.status == ValidationStatus.failed
    assert result.gate_results[0].status == "error"
    assert "boom" in result.gate_results[0].message.lower()


def test_execute_gates_from_results() -> None:
    service = ValidationRunService()
    run = service.create_run(run_id="run-1", target_type="dataset", target_id="ds-1")
    run = service.start_run(run)

    result = service.execute_gates_from_results(
        run,
        gate_results=[
            GateResult(gate_id="g1", passed=True, status="passed", message="OK"),
            GateResult(gate_id="g2", passed=False, status="failed", message="Bad"),
        ],
        gate_configs=[
            GateConfig(gate_id="g1", required=True),
            GateConfig(gate_id="g2", required=True),
        ],
    )

    assert result.status == ValidationStatus.failed
    assert result.passed_count == 1
    assert result.failed_count == 1
    assert result.total_count == 2


def test_execute_gates_from_results_all_pass() -> None:
    service = ValidationRunService()
    run = service.create_run(run_id="run-1", target_type="dataset", target_id="ds-1")
    run = service.start_run(run)

    result = service.execute_gates_from_results(
        run,
        gate_results=[
            GateResult(gate_id="g1", passed=True, status="passed"),
            GateResult(gate_id="g2", passed=True, status="passed"),
        ],
    )

    assert result.status == ValidationStatus.passed
    assert result.passed_count == 2


def test_plugin_protocol_check() -> None:
    """Verify that test plugins conform to the protocol."""
    assert isinstance(_PassingPlugin(), ValidationGatePlugin)
    assert isinstance(_FailingPlugin(), ValidationGatePlugin)
    assert isinstance(_WarningPlugin(), ValidationGatePlugin)


def test_dict_gate_config_normalization() -> None:
    service = ValidationRunService()
    run = service.create_run(run_id="run-1", target_type="dataset", target_id="ds-1")
    run = service.start_run(run)

    result = service.execute_gates(
        run,
        gate_configs=[
            {"gate_id": "g1", "plugin_id": "checker"},
        ],
        plugins={"checker": _PassingPlugin()},
    )

    assert result.status == ValidationStatus.passed
    assert result.total_count == 1

"""Validation run lifecycle service (QA-010).

Manages validation run state transitions:
pending -> running -> {passed, failed, warning}.
Creates validation runs, executes gates via plugin instances, and aggregates
gate results into overall status.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from molabel.core.types import ValidationStatus


class GateResult(BaseModel):
    """Result of a single validation gate execution."""

    gate_id: str
    gate_name: str = ""
    passed: bool = False
    status: str = "pending"
    """One of: pending, running, passed, failed, warning, error."""
    metric_value: float | None = None
    threshold: float | None = None
    message: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class ValidationRunState(BaseModel):
    """In-memory representation of a validation run's current state.

    This is a pure-computation projection of the database ValidationRun
    model, suitable for service-level logic without SQLAlchemy dependency.
    """

    run_id: str
    target_type: str
    target_id: str
    status: ValidationStatus = ValidationStatus.pending
    gate_results: list[GateResult] = Field(default_factory=list)
    passed_count: int = 0
    failed_count: int = 0
    warning_count: int = 0
    total_count: int = 0
    summary: str = ""
    started_at: datetime | None = None
    completed_at: datetime | None = None


@runtime_checkable
class ValidationGatePlugin(Protocol):
    """Protocol for validation gate plugins that execute checks."""

    def execute_gate(
        self,
        *,
        gate_id: str,
        target_type: str,
        target_id: str,
        config: dict[str, Any],
        context: dict[str, Any],
    ) -> GateResult:
        """Execute a single validation gate and return the result."""
        ...


class GateConfig(BaseModel):
    """Configuration for a single validation gate."""

    gate_id: str
    gate_name: str = ""
    plugin_id: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    required: bool = True
    """If True, a gate failure causes the overall run to fail.
    If False, a gate failure produces a warning."""


class ValidationRunService:
    """Manage validation run lifecycle and gate execution.

    This service is pure computation: it takes data in and returns results.
    It does not directly access the database; callers persist results.
    """

    def create_run(
        self,
        *,
        run_id: str,
        target_type: str,
        target_id: str,
    ) -> ValidationRunState:
        """Create a new validation run in pending state.

        Parameters
        ----------
        run_id:
            Unique identifier for this validation run.
        target_type:
            Type of target being validated (e.g. "dataset", "release", "export").
        target_id:
            ID of the target being validated.

        Returns
        -------
        ValidationRunState in pending status.
        """
        return ValidationRunState(
            run_id=run_id,
            target_type=target_type,
            target_id=target_id,
            status=ValidationStatus.pending,
        )

    def start_run(self, run: ValidationRunState) -> ValidationRunState:
        """Transition a run from pending to running.

        Parameters
        ----------
        run:
            The current run state (must be pending).

        Returns
        -------
        Updated ValidationRunState in running status.

        Raises
        ------
        ValueError
            If the run is not in pending status.
        """
        if run.status != ValidationStatus.pending:
            raise ValueError(
                f"Cannot start run in status '{run.status}'. "
                "Only pending runs can be started."
            )
        return run.model_copy(
            update={
                "status": ValidationStatus.running,
                "started_at": datetime.now(UTC),
            }
        )

    def execute_gates(
        self,
        run: ValidationRunState,
        *,
        gate_configs: Sequence[GateConfig | dict[str, Any]],
        plugins: dict[str, ValidationGatePlugin] | None = None,
        context: dict[str, Any] | None = None,
    ) -> ValidationRunState:
        """Execute all configured gates and aggregate results.

        Parameters
        ----------
        run:
            The current run state (should be running).
        gate_configs:
            List of gate configurations to execute.
        plugins:
            Map of plugin_id to ValidationGatePlugin instances.
        context:
            Additional context passed to gate plugins.

        Returns
        -------
        Updated ValidationRunState with gate results and final status.
        """
        plugins = plugins or {}
        context = context or {}
        normalized_configs = [self._normalize_gate_config(g) for g in gate_configs]

        gate_results: list[GateResult] = []
        for gate_config in normalized_configs:
            result = self._execute_single_gate(
                run=run,
                gate_config=gate_config,
                plugins=plugins,
                context=context,
            )
            gate_results.append(result)

        return self._finalize_run(run, gate_results, normalized_configs)

    def execute_gates_from_results(
        self,
        run: ValidationRunState,
        *,
        gate_results: Sequence[GateResult | dict[str, Any]],
        gate_configs: Sequence[GateConfig | dict[str, Any]] | None = None,
    ) -> ValidationRunState:
        """Finalize a run from pre-computed gate results.

        Useful when gates have already been executed externally and
        results just need to be aggregated.

        Parameters
        ----------
        run:
            The current run state.
        gate_results:
            Pre-computed gate results.
        gate_configs:
            Optional gate configs for required/optional classification.

        Returns
        -------
        Updated ValidationRunState with final status.
        """
        normalized_results = [self._normalize_gate_result(r) for r in gate_results]
        normalized_configs = (
            [self._normalize_gate_config(g) for g in gate_configs]
            if gate_configs is not None
            else None
        )
        return self._finalize_run(run, normalized_results, normalized_configs)

    def _execute_single_gate(
        self,
        *,
        run: ValidationRunState,
        gate_config: GateConfig,
        plugins: dict[str, ValidationGatePlugin],
        context: dict[str, Any],
    ) -> GateResult:
        plugin = plugins.get(gate_config.plugin_id)
        if plugin is None:
            return GateResult(
                gate_id=gate_config.gate_id,
                gate_name=gate_config.gate_name,
                passed=False,
                status="error",
                message=f"Plugin '{gate_config.plugin_id}' not found.",
            )

        try:
            result = plugin.execute_gate(
                gate_id=gate_config.gate_id,
                target_type=run.target_type,
                target_id=run.target_id,
                config=gate_config.config,
                context=context,
            )
            return result
        except Exception as e:
            return GateResult(
                gate_id=gate_config.gate_id,
                gate_name=gate_config.gate_name,
                passed=False,
                status="error",
                message=f"Gate execution failed: {e}",
            )

    def _finalize_run(
        self,
        run: ValidationRunState,
        gate_results: Sequence[GateResult],
        gate_configs: Sequence[GateConfig] | None,
    ) -> ValidationRunState:
        """Aggregate gate results and determine overall run status."""
        passed_count = 0
        failed_count = 0
        warning_count = 0

        # Build a config lookup for required/optional classification
        config_map: dict[str, GateConfig] = {}
        if gate_configs is not None:
            for gc in gate_configs:
                config_map[gc.gate_id] = gc

        has_required_failure = False

        for result in gate_results:
            if result.passed:
                passed_count += 1
            elif result.status == "warning":
                warning_count += 1
            else:
                failed_count += 1
                # Check if this gate is required
                gc = config_map.get(result.gate_id)
                if gc is None or gc.required:
                    has_required_failure = True

        total_count = len(gate_results)

        if has_required_failure:
            status = ValidationStatus.failed
        elif warning_count > 0 or (failed_count > 0 and not has_required_failure):
            status = ValidationStatus.warning
        else:
            status = ValidationStatus.passed

        if status == ValidationStatus.passed:
            summary = f"All {total_count} gates passed."
        elif status == ValidationStatus.warning:
            summary = (
                f"{passed_count} passed, {warning_count} warnings, "
                f"{failed_count} failed (non-required) out of {total_count} gates."
            )
        else:
            summary = (
                f"{failed_count} gates failed out of {total_count}. "
                f"{passed_count} passed, {warning_count} warnings."
            )

        return run.model_copy(
            update={
                "status": status,
                "gate_results": list(gate_results),
                "passed_count": passed_count,
                "failed_count": failed_count,
                "warning_count": warning_count,
                "total_count": total_count,
                "summary": summary,
                "completed_at": datetime.now(UTC),
            }
        )

    def _normalize_gate_config(self, config: GateConfig | dict[str, Any]) -> GateConfig:
        if isinstance(config, GateConfig):
            return config
        return GateConfig.model_validate(config)

    def _normalize_gate_result(self, result: GateResult | dict[str, Any]) -> GateResult:
        if isinstance(result, GateResult):
            return result
        return GateResult.model_validate(result)

"""Readiness dashboard service (QA-008).

Aggregates quality metrics into a readiness assessment with configurable
gates. Each gate has a name, threshold, current value, and pass/fail
status. Overall readiness = all gates passed.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, Field


class GateStatus(BaseModel):
    """Status of an individual readiness gate."""

    gate_name: str
    description: str = ""
    threshold: float = 0.0
    current_value: float = 0.0
    passed: bool = False
    comparison: str = "gte"
    """Comparison operator: 'gte' (>=), 'lte' (<=), 'gt' (>), 'lt' (<), 'eq' (==)."""


class ReadinessGate(BaseModel):
    """Configuration for a readiness gate."""

    gate_name: str
    metric_key: str
    threshold: float
    comparison: str = "gte"
    """Comparison operator: 'gte' (>=), 'lte' (<=), 'gt' (>), 'lt' (<), 'eq' (==)."""
    description: str = ""


class ReadinessResult(BaseModel):
    """Full readiness assessment output."""

    ready: bool = False
    gates_passed: int = 0
    gates_total: int = 0
    gates: list[GateStatus] = Field(default_factory=list)
    summary: str = ""
    warnings: list[str] = Field(default_factory=list)


class ReadinessDashboardService:
    """Assess data readiness by evaluating configurable quality gates."""

    def __init__(
        self,
        *,
        default_gates: Sequence[ReadinessGate | dict[str, Any]] | None = None,
    ) -> None:
        """Initialize with optional default gate configuration.

        Parameters
        ----------
        default_gates:
            Default set of gates to evaluate if none are provided to ``assess``.
        """
        self.default_gates: list[ReadinessGate] = []
        if default_gates is not None:
            self.default_gates = [self._normalize_gate(g) for g in default_gates]

    def assess(
        self,
        metrics: dict[str, float],
        *,
        gates: Sequence[ReadinessGate | dict[str, Any]] | None = None,
    ) -> ReadinessResult:
        """Evaluate all gates against the provided metrics.

        Parameters
        ----------
        metrics:
            Dictionary of metric keys to their current values.
        gates:
            Gate configurations to evaluate. Uses default_gates if None.

        Returns
        -------
        ReadinessResult with per-gate status and overall readiness.
        """
        gate_configs = (
            [self._normalize_gate(g) for g in gates]
            if gates is not None
            else self.default_gates
        )

        if not gate_configs:
            return ReadinessResult(
                ready=True,
                summary="No gates configured; dataset is ready by default.",
                warnings=["No readiness gates configured."],
            )

        gate_statuses: list[GateStatus] = []
        gates_passed = 0
        warnings: list[str] = []

        for gate in gate_configs:
            current_value = metrics.get(gate.metric_key)
            if current_value is None:
                warnings.append(
                    f"Metric '{gate.metric_key}' not found for gate "
                    f"'{gate.gate_name}'. Treating as 0.0."
                )
                current_value = 0.0

            passed = _evaluate_comparison(
                current_value, gate.threshold, gate.comparison
            )
            if passed:
                gates_passed += 1

            gate_statuses.append(
                GateStatus(
                    gate_name=gate.gate_name,
                    description=gate.description,
                    threshold=gate.threshold,
                    current_value=current_value,
                    passed=passed,
                    comparison=gate.comparison,
                )
            )

        gates_total = len(gate_configs)
        ready = gates_passed == gates_total

        if ready:
            summary = f"All {gates_total} gates passed. Dataset is ready."
        else:
            failed_count = gates_total - gates_passed
            failed_names = [g.gate_name for g in gate_statuses if not g.passed]
            summary = (
                f"{failed_count} of {gates_total} gates failed: "
                f"{', '.join(failed_names)}."
            )

        return ReadinessResult(
            ready=ready,
            gates_passed=gates_passed,
            gates_total=gates_total,
            gates=gate_statuses,
            summary=summary,
            warnings=warnings,
        )

    def _normalize_gate(self, gate: ReadinessGate | dict[str, Any]) -> ReadinessGate:
        if isinstance(gate, ReadinessGate):
            return gate
        return ReadinessGate.model_validate(gate)


def _evaluate_comparison(current: float, threshold: float, comparison: str) -> bool:
    """Evaluate a comparison operation."""
    if comparison == "gte":
        return current >= threshold
    if comparison == "lte":
        return current <= threshold
    if comparison == "gt":
        return current > threshold
    if comparison == "lt":
        return current < threshold
    if comparison == "eq":
        return abs(current - threshold) < 1e-9
    # Default to gte for unknown comparisons
    return current >= threshold

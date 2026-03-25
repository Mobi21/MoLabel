"""Agent vs Human delta analysis service (QA-004).

Compares human labels vs agent labels field-by-field, computes deltas
(agent tends to label X% more as category Y), and identifies systematic biases.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, Field

from molabel.core.utils.canonical import canonical_label_value as _canonical_value


class BiasPattern(BaseModel):
    """A detected systematic bias pattern."""

    field_name: str
    label_value: str
    human_rate: float = 0.0
    agent_rate: float = 0.0
    delta: float = 0.0
    direction: str = ""
    """'agent_overuse' if agent labels this value more, 'agent_underuse' if less."""
    severity: str = "low"
    """low, medium, or high based on the magnitude of the delta."""


class FieldDelta(BaseModel):
    """Per-field comparison of human vs agent label distributions."""

    field_name: str
    human_total: int = 0
    agent_total: int = 0
    human_distribution: dict[str, float] = Field(default_factory=dict)
    agent_distribution: dict[str, float] = Field(default_factory=dict)
    deltas: dict[str, float] = Field(default_factory=dict)
    """Per-value delta: agent_rate - human_rate. Positive = agent uses more."""
    max_absolute_delta: float = 0.0
    biases: list[BiasPattern] = Field(default_factory=list)


class DeltaResult(BaseModel):
    """Full delta analysis output."""

    total_human_labels: int = 0
    total_agent_labels: int = 0
    fields: dict[str, FieldDelta] = Field(default_factory=dict)
    overall_biases: list[BiasPattern] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DeltaRecord(BaseModel):
    """A single label record with source information."""

    record_id: str
    source: str
    labels: dict[str, Any] = Field(default_factory=dict)


class DeltaAnalysisService:
    """Compare human labels vs agent labels and identify systematic biases."""

    def __init__(
        self,
        *,
        bias_threshold: float = 0.1,
        high_bias_threshold: float = 0.3,
    ) -> None:
        """Initialize with configurable bias thresholds.

        Parameters
        ----------
        bias_threshold:
            Minimum absolute delta to flag as a bias (default 10%).
        high_bias_threshold:
            Minimum absolute delta to flag as high severity (default 30%).
        """
        self.bias_threshold = bias_threshold
        self.high_bias_threshold = high_bias_threshold

    def analyze(
        self,
        records: Sequence[DeltaRecord | dict[str, Any]],
        *,
        fields: Sequence[str] | None = None,
    ) -> DeltaResult:
        """Compare human vs agent label distributions.

        Parameters
        ----------
        records:
            Label records to analyze. Each must have a source ("human" or "agent").
        fields:
            If provided, restrict analysis to these field names.

        Returns
        -------
        DeltaResult with per-field deltas and detected bias patterns.
        """
        normalized = [self._normalize_record(r) for r in records]

        human_records = [r for r in normalized if _is_human_source(r.source)]
        agent_records = [r for r in normalized if _is_agent_source(r.source)]

        warnings: list[str] = []
        if not human_records:
            warnings.append("No human-source records found.")
        if not agent_records:
            warnings.append("No agent-source records found.")
        if not human_records or not agent_records:
            return DeltaResult(
                total_human_labels=len(human_records),
                total_agent_labels=len(agent_records),
                warnings=warnings,
            )

        field_names = self._resolve_fields(normalized, fields)
        field_deltas: dict[str, FieldDelta] = {}
        all_biases: list[BiasPattern] = []

        for field in field_names:
            field_delta = self._compute_field_delta(field, human_records, agent_records)
            field_deltas[field] = field_delta
            all_biases.extend(field_delta.biases)

        return DeltaResult(
            total_human_labels=len(human_records),
            total_agent_labels=len(agent_records),
            fields=field_deltas,
            overall_biases=sorted(all_biases, key=lambda b: abs(b.delta), reverse=True),
            warnings=warnings,
        )

    def _compute_field_delta(
        self,
        field: str,
        human_records: Sequence[DeltaRecord],
        agent_records: Sequence[DeltaRecord],
    ) -> FieldDelta:
        human_counter: Counter[str] = Counter()
        agent_counter: Counter[str] = Counter()

        for r in human_records:
            if field in r.labels:
                human_counter[_canonical_value(r.labels[field])] += 1

        for r in agent_records:
            if field in r.labels:
                agent_counter[_canonical_value(r.labels[field])] += 1

        human_total = sum(human_counter.values())
        agent_total = sum(agent_counter.values())

        all_values = sorted(set(human_counter.keys()) | set(agent_counter.keys()))

        human_distribution: dict[str, float] = {}
        agent_distribution: dict[str, float] = {}
        deltas: dict[str, float] = {}
        biases: list[BiasPattern] = []

        for value in all_values:
            h_rate = human_counter[value] / human_total if human_total > 0 else 0.0
            a_rate = agent_counter[value] / agent_total if agent_total > 0 else 0.0
            human_distribution[value] = h_rate
            agent_distribution[value] = a_rate
            delta = a_rate - h_rate
            deltas[value] = delta

            abs_delta = abs(delta)
            if abs_delta >= self.bias_threshold:
                direction = "agent_overuse" if delta > 0 else "agent_underuse"
                severity = self._classify_severity(abs_delta)
                biases.append(
                    BiasPattern(
                        field_name=field,
                        label_value=value,
                        human_rate=h_rate,
                        agent_rate=a_rate,
                        delta=delta,
                        direction=direction,
                        severity=severity,
                    )
                )

        max_absolute_delta = max((abs(d) for d in deltas.values()), default=0.0)

        return FieldDelta(
            field_name=field,
            human_total=human_total,
            agent_total=agent_total,
            human_distribution=human_distribution,
            agent_distribution=agent_distribution,
            deltas=deltas,
            max_absolute_delta=max_absolute_delta,
            biases=sorted(biases, key=lambda b: abs(b.delta), reverse=True),
        )

    def _classify_severity(self, abs_delta: float) -> str:
        if abs_delta >= self.high_bias_threshold:
            return "high"
        if abs_delta >= self.bias_threshold:
            return "medium"
        return "low"

    def _normalize_record(self, record: DeltaRecord | dict[str, Any]) -> DeltaRecord:
        if isinstance(record, DeltaRecord):
            return record
        return DeltaRecord.model_validate(record)

    def _resolve_fields(
        self,
        records: Sequence[DeltaRecord],
        fields: Sequence[str] | None,
    ) -> list[str]:
        if fields is not None:
            return list(dict.fromkeys(fields))
        discovered: set[str] = set()
        for record in records:
            discovered.update(record.labels.keys())
        return sorted(discovered)


def _is_human_source(source: str) -> bool:
    return source in {"human", "import"}


def _is_agent_source(source: str) -> bool:
    return source == "agent"

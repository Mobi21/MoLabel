"""Multi-model comparison service (AG-006, AG-007).

Orchestrates running the same labeling task across N model configurations,
then computes aggregate comparison views: agreement matrices, distribution
charts, cost and latency comparisons, and per-record breakdowns.
"""

from __future__ import annotations

import logging
import math
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from molabel.core.utils.canonical import canonical_label_value

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ModelConfig:
    """Configuration for a single model in a comparison run."""

    model_id: str
    model_name: str
    provider_type: str = "openai_compatible"
    parameters: dict[str, Any] = field(default_factory=dict)
    cost_per_input_token: float = 0.0
    cost_per_output_token: float = 0.0


@dataclass
class ComparisonRecord:
    """Result from a single model for a single record."""

    record_id: str
    model_id: str
    labels: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    tokens_input: int = 0
    tokens_output: int = 0
    latency_ms: int = 0
    error: str | None = None
    raw_response: dict[str, Any] | None = None


@dataclass
class ComparisonResult:
    """Collected outputs from all models for all records."""

    records: list[ComparisonRecord] = field(default_factory=list)
    model_ids: list[str] = field(default_factory=list)
    record_ids: list[str] = field(default_factory=list)

    def records_for_model(self, model_id: str) -> list[ComparisonRecord]:
        """Return all records produced by a specific model."""
        return [r for r in self.records if r.model_id == model_id]

    def records_for_record(self, record_id: str) -> list[ComparisonRecord]:
        """Return all model outputs for a specific record."""
        return [r for r in self.records if r.record_id == record_id]


@dataclass
class ComparisonRun:
    """Top-level container for a multi-model comparison run."""

    run_id: UUID = field(default_factory=uuid4)
    model_configs: list[ModelConfig] = field(default_factory=list)
    record_ids: list[str] = field(default_factory=list)
    result: ComparisonResult | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    status: str = "pending"


# ---------------------------------------------------------------------------
# Aggregate view data classes (AG-007)
# ---------------------------------------------------------------------------


@dataclass
class AgreementMatrix:
    """NxN pairwise agreement matrix across models."""

    model_ids: list[str] = field(default_factory=list)
    matrix: dict[str, dict[str, float]] = field(default_factory=dict)
    pair_counts: dict[str, dict[str, int]] = field(default_factory=dict)


@dataclass
class ModelDistribution:
    """Label distribution for a single model."""

    model_id: str = ""
    field_distributions: dict[str, dict[str, int]] = field(default_factory=dict)
    total_records: int = 0


@dataclass
class CostComparison:
    """Cost comparison across models."""

    model_costs: dict[str, float] = field(default_factory=dict)
    model_input_tokens: dict[str, int] = field(default_factory=dict)
    model_output_tokens: dict[str, int] = field(default_factory=dict)
    cheapest_model: str = ""
    most_expensive_model: str = ""


@dataclass
class LatencyComparison:
    """Latency comparison across models."""

    model_avg_ms: dict[str, float] = field(default_factory=dict)
    model_p50_ms: dict[str, float] = field(default_factory=dict)
    model_p95_ms: dict[str, float] = field(default_factory=dict)
    fastest_model: str = ""
    slowest_model: str = ""


@dataclass
class ComparisonAggregate:
    """Full aggregate comparison view combining all metrics."""

    agreement_matrix: AgreementMatrix = field(default_factory=AgreementMatrix)
    distributions: list[ModelDistribution] = field(default_factory=list)
    cost_comparison: CostComparison = field(default_factory=CostComparison)
    latency_comparison: LatencyComparison = field(default_factory=LatencyComparison)
    per_record_agreement: dict[str, float] = field(default_factory=dict)
    total_records: int = 0
    total_models: int = 0


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


def _percentile(data: list[float], pct: float) -> float:
    """Compute a percentile from a sorted list of values."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_data[int(k)]
    return sorted_data[f] * (c - k) + sorted_data[c] * (k - f)


class MultiModelComparisonService:
    """Orchestrate multi-model comparison runs and compute aggregate views.

    The service is stateless: callers pass in model configs and a processor
    callable, and receive structured comparison results.
    """

    def run_comparison(
        self,
        *,
        model_configs: list[ModelConfig],
        record_ids: list[str],
        processor: Any | None = None,
    ) -> ComparisonRun:
        """Execute a comparison run across N models for the given records.

        Parameters
        ----------
        model_configs:
            List of model configurations to compare.
        record_ids:
            List of record IDs to process.
        processor:
            Optional callable ``(record_id, model_config) -> ComparisonRecord``.
            If None, produces empty records (useful for testing aggregate logic).

        Returns
        -------
        ComparisonRun
            A completed comparison run with results.
        """
        run = ComparisonRun(
            model_configs=list(model_configs),
            record_ids=list(record_ids),
            started_at=datetime.now(UTC),
            status="running",
        )

        all_records: list[ComparisonRecord] = []
        model_ids = [mc.model_id for mc in model_configs]

        for model_config in model_configs:
            for record_id in record_ids:
                if processor is not None:
                    try:
                        result = processor(
                            record_id=record_id,
                            model_config=model_config,
                        )
                        if isinstance(result, ComparisonRecord):
                            all_records.append(result)
                        else:
                            all_records.append(
                                ComparisonRecord(
                                    record_id=record_id,
                                    model_id=model_config.model_id,
                                    labels=result.get("labels", {})
                                    if isinstance(result, dict)
                                    else {},
                                    confidence=result.get("confidence", 0.0)
                                    if isinstance(result, dict)
                                    else 0.0,
                                    tokens_input=result.get("tokens_input", 0)
                                    if isinstance(result, dict)
                                    else 0,
                                    tokens_output=result.get("tokens_output", 0)
                                    if isinstance(result, dict)
                                    else 0,
                                    latency_ms=result.get("latency_ms", 0)
                                    if isinstance(result, dict)
                                    else 0,
                                )
                            )
                    except Exception as exc:
                        logger.warning(
                            "Processor failed for record %s model %s: %s",
                            record_id,
                            model_config.model_id,
                            exc,
                        )
                        all_records.append(
                            ComparisonRecord(
                                record_id=record_id,
                                model_id=model_config.model_id,
                                error=str(exc),
                            )
                        )
                else:
                    all_records.append(
                        ComparisonRecord(
                            record_id=record_id,
                            model_id=model_config.model_id,
                        )
                    )

        run.result = ComparisonResult(
            records=all_records,
            model_ids=model_ids,
            record_ids=list(record_ids),
        )
        run.completed_at = datetime.now(UTC)
        run.status = "completed"
        return run

    def compute_aggregate(
        self,
        result: ComparisonResult,
        model_configs: list[ModelConfig] | None = None,
    ) -> ComparisonAggregate:
        """Compute aggregate comparison views from a ComparisonResult.

        Parameters
        ----------
        result:
            The comparison result containing per-record per-model outputs.
        model_configs:
            Optional model configs for cost calculation. If not provided,
            cost comparison will use raw token counts only.

        Returns
        -------
        ComparisonAggregate
            Full aggregate view with agreement, distributions, cost, latency.
        """
        agreement = self._compute_agreement_matrix(result)
        distributions = self._compute_distributions(result)
        cost = self._compute_cost_comparison(result, model_configs or [])
        latency = self._compute_latency_comparison(result)
        per_record = self._compute_per_record_agreement(result)

        return ComparisonAggregate(
            agreement_matrix=agreement,
            distributions=distributions,
            cost_comparison=cost,
            latency_comparison=latency,
            per_record_agreement=per_record,
            total_records=len(result.record_ids),
            total_models=len(result.model_ids),
        )

    def export_comparison_data(
        self,
        run: ComparisonRun,
    ) -> dict[str, Any]:
        """Export comparison data as a structured dict for serialization.

        Parameters
        ----------
        run:
            A completed comparison run.

        Returns
        -------
        dict
            Structured comparison data suitable for JSON export.
        """
        if run.result is None:
            return {
                "run_id": str(run.run_id),
                "status": run.status,
                "model_configs": [],
                "records": [],
                "aggregate": None,
            }

        aggregate = self.compute_aggregate(run.result, run.model_configs)

        return {
            "run_id": str(run.run_id),
            "status": run.status,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "model_configs": [
                {
                    "model_id": mc.model_id,
                    "model_name": mc.model_name,
                    "provider_type": mc.provider_type,
                }
                for mc in run.model_configs
            ],
            "records": [
                {
                    "record_id": cr.record_id,
                    "model_id": cr.model_id,
                    "labels": cr.labels,
                    "confidence": cr.confidence,
                    "tokens_input": cr.tokens_input,
                    "tokens_output": cr.tokens_output,
                    "latency_ms": cr.latency_ms,
                    "error": cr.error,
                }
                for cr in run.result.records
            ],
            "aggregate": {
                "agreement_matrix": {
                    "model_ids": aggregate.agreement_matrix.model_ids,
                    "matrix": aggregate.agreement_matrix.matrix,
                },
                "cost_comparison": {
                    "model_costs": aggregate.cost_comparison.model_costs,
                    "cheapest_model": aggregate.cost_comparison.cheapest_model,
                    "most_expensive_model": (
                        aggregate.cost_comparison.most_expensive_model
                    ),
                },
                "latency_comparison": {
                    "model_avg_ms": aggregate.latency_comparison.model_avg_ms,
                    "model_p50_ms": aggregate.latency_comparison.model_p50_ms,
                    "model_p95_ms": aggregate.latency_comparison.model_p95_ms,
                    "fastest_model": aggregate.latency_comparison.fastest_model,
                    "slowest_model": aggregate.latency_comparison.slowest_model,
                },
                "total_records": aggregate.total_records,
                "total_models": aggregate.total_models,
            },
        }

    # -- Private helpers --

    def _compute_agreement_matrix(self, result: ComparisonResult) -> AgreementMatrix:
        """Compute NxN pairwise agreement between models."""
        model_ids = result.model_ids
        if len(model_ids) < 2:
            return AgreementMatrix(model_ids=model_ids)

        # Index: record_id -> model_id -> labels
        index: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        for record in result.records:
            if record.error is None:
                index[record.record_id][record.model_id] = record.labels

        matrix: dict[str, dict[str, float]] = {}
        pair_counts: dict[str, dict[str, int]] = {}

        for i, model_a in enumerate(model_ids):
            matrix[model_a] = {}
            pair_counts[model_a] = {}
            for j, model_b in enumerate(model_ids):
                if i == j:
                    matrix[model_a][model_b] = 1.0
                    pair_counts[model_a][model_b] = len(result.record_ids)
                    continue

                agreements = 0
                total = 0
                for record_id in result.record_ids:
                    labels_a = index.get(record_id, {}).get(model_a)
                    labels_b = index.get(record_id, {}).get(model_b)
                    if labels_a is None or labels_b is None:
                        continue
                    total += 1
                    # Compare all fields
                    all_fields = set(labels_a.keys()) | set(labels_b.keys())
                    if not all_fields:
                        agreements += 1
                        continue
                    field_agreements = sum(
                        1
                        for f in all_fields
                        if canonical_label_value(labels_a.get(f))
                        == canonical_label_value(labels_b.get(f))
                    )
                    if field_agreements == len(all_fields):
                        agreements += 1

                rate = agreements / total if total > 0 else 0.0
                matrix[model_a][model_b] = rate
                pair_counts[model_a][model_b] = total

        return AgreementMatrix(
            model_ids=model_ids,
            matrix=matrix,
            pair_counts=pair_counts,
        )

    def _compute_distributions(
        self, result: ComparisonResult
    ) -> list[ModelDistribution]:
        """Compute label distribution per model."""
        distributions: list[ModelDistribution] = []

        for model_id in result.model_ids:
            model_records = result.records_for_model(model_id)
            successful = [r for r in model_records if r.error is None]
            field_dists: dict[str, dict[str, int]] = defaultdict(Counter)

            for record in successful:
                for field_name, value in record.labels.items():
                    canonical = canonical_label_value(value)
                    field_dists[field_name][canonical] += 1

            distributions.append(
                ModelDistribution(
                    model_id=model_id,
                    field_distributions={k: dict(v) for k, v in field_dists.items()},
                    total_records=len(successful),
                )
            )

        return distributions

    def _compute_cost_comparison(
        self,
        result: ComparisonResult,
        model_configs: list[ModelConfig],
    ) -> CostComparison:
        """Compute cost comparison across models."""
        config_map = {mc.model_id: mc for mc in model_configs}
        model_costs: dict[str, float] = {}
        model_input_tokens: dict[str, int] = {}
        model_output_tokens: dict[str, int] = {}

        for model_id in result.model_ids:
            model_records = result.records_for_model(model_id)
            total_input = sum(r.tokens_input for r in model_records)
            total_output = sum(r.tokens_output for r in model_records)
            model_input_tokens[model_id] = total_input
            model_output_tokens[model_id] = total_output

            config = config_map.get(model_id)
            if config:
                cost = (
                    total_input * config.cost_per_input_token
                    + total_output * config.cost_per_output_token
                )
            else:
                cost = 0.0
            model_costs[model_id] = cost

        cheapest = min(model_costs, key=lambda k: model_costs[k]) if model_costs else ""
        most_expensive = (
            max(model_costs, key=lambda k: model_costs[k]) if model_costs else ""
        )

        return CostComparison(
            model_costs=model_costs,
            model_input_tokens=model_input_tokens,
            model_output_tokens=model_output_tokens,
            cheapest_model=cheapest,
            most_expensive_model=most_expensive,
        )

    def _compute_latency_comparison(
        self, result: ComparisonResult
    ) -> LatencyComparison:
        """Compute latency comparison across models."""
        model_avg: dict[str, float] = {}
        model_p50: dict[str, float] = {}
        model_p95: dict[str, float] = {}

        for model_id in result.model_ids:
            model_records = result.records_for_model(model_id)
            latencies = [float(r.latency_ms) for r in model_records if r.error is None]
            if latencies:
                model_avg[model_id] = statistics.mean(latencies)
                model_p50[model_id] = _percentile(latencies, 50.0)
                model_p95[model_id] = _percentile(latencies, 95.0)
            else:
                model_avg[model_id] = 0.0
                model_p50[model_id] = 0.0
                model_p95[model_id] = 0.0

        fastest = min(model_avg, key=lambda k: model_avg[k]) if model_avg else ""
        slowest = max(model_avg, key=lambda k: model_avg[k]) if model_avg else ""

        return LatencyComparison(
            model_avg_ms=model_avg,
            model_p50_ms=model_p50,
            model_p95_ms=model_p95,
            fastest_model=fastest,
            slowest_model=slowest,
        )

    def _compute_per_record_agreement(
        self, result: ComparisonResult
    ) -> dict[str, float]:
        """Compute agreement rate per record across all models."""
        per_record: dict[str, float] = {}

        for record_id in result.record_ids:
            record_outputs = [
                r for r in result.records_for_record(record_id) if r.error is None
            ]
            if len(record_outputs) < 2:
                per_record[record_id] = 1.0 if record_outputs else 0.0
                continue

            pairs = 0
            agreements = 0
            for i in range(len(record_outputs)):
                for j in range(i + 1, len(record_outputs)):
                    pairs += 1
                    labels_a = record_outputs[i].labels
                    labels_b = record_outputs[j].labels
                    all_fields = set(labels_a.keys()) | set(labels_b.keys())
                    if not all_fields:
                        agreements += 1
                        continue
                    field_agrees = sum(
                        1
                        for f in all_fields
                        if canonical_label_value(labels_a.get(f))
                        == canonical_label_value(labels_b.get(f))
                    )
                    if field_agrees == len(all_fields):
                        agreements += 1

            per_record[record_id] = agreements / pairs if pairs > 0 else 0.0

        return per_record

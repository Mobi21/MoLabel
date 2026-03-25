"""Agreement metrics service for QA-001 and QA-002.

The service operates on grouped records containing one or more annotation
payloads per record. It computes overall agreement metrics and human-agent
breakdowns by field and label value.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from molabel.core.utils.canonical import canonical_label_value as _canonical_label


def _is_human_source(source: str) -> bool:
    return source in {"human", "import"}


def _is_agent_source(source: str) -> bool:
    return source == "agent"


def _safe_kappa(observed_agreement: float, expected_agreement: float) -> float:
    """Compute a kappa-style coefficient with sensible edge-case handling."""
    if observed_agreement >= 1.0 and expected_agreement >= 1.0:
        return 1.0
    denominator = 1.0 - expected_agreement
    if denominator <= 0.0:
        return 1.0 if observed_agreement >= 1.0 else 0.0
    return (observed_agreement - expected_agreement) / denominator


class AgreementAnnotation(BaseModel):
    """A single label assignment for a record."""

    source: str
    labels: dict[str, Any] = Field(default_factory=dict)


class AgreementRecord(BaseModel):
    """A record with one or more annotations attached."""

    record_id: str
    annotations: list[AgreementAnnotation] = Field(default_factory=list)


class AgreementValueBreakdown(BaseModel):
    """Human-agent breakdown for a specific label value."""

    comparisons: int = 0
    agreements: int = 0
    agreement_rate: float = 0.0
    human_count: int = 0
    agent_count: int = 0


class AgreementFieldBreakdown(BaseModel):
    """Human-agent breakdown for a specific field."""

    comparisons: int = 0
    agreements: int = 0
    agreement_rate: float = 0.0
    by_label_value: dict[str, AgreementValueBreakdown] = Field(default_factory=dict)
    confusion_matrix: dict[str, dict[str, int]] = Field(default_factory=dict)


class AgreementMetricSummary(BaseModel):
    """Aggregate agreement metrics for a population of labels."""

    comparisons: int = 0
    agreements: int = 0
    percent_agreement: float = 0.0
    cohen_kappa: float = 0.0
    fleiss_kappa: float = 0.0
    krippendorff_alpha: float = 0.0


class AgreementAnalysisResult(BaseModel):
    """Full agreement analysis output."""

    analysis_type: str
    overall: AgreementMetricSummary
    human_agent: AgreementMetricSummary | None = None
    human_agent_by_field: dict[str, AgreementFieldBreakdown] = Field(
        default_factory=dict
    )
    confusion_matrix: dict[str, dict[str, int]] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


@runtime_checkable
class AgreementRecordSource(Protocol):
    """Protocol for services that load grouped agreement records."""

    def load_agreement_records(
        self,
        *,
        record_ids: Sequence[str],
        review_queue_ids: Sequence[str],
        agent_run_ids: Sequence[str],
        analysis_type: str,
        config: dict[str, Any],
    ) -> Sequence[AgreementRecord | dict[str, Any]]:
        """Load agreement records for analysis."""


class AgreementMetricsService:
    """Compute QA-001/QA-002 agreement metrics from grouped annotations."""

    def analyze(
        self,
        records: Sequence[AgreementRecord | dict[str, Any]],
        *,
        analysis_type: str = "both",
        fields: Sequence[str] | None = None,
    ) -> AgreementAnalysisResult:
        """Compute agreement metrics for the supplied records."""
        normalized_records = [self._normalize_record(record) for record in records]
        field_names = self._resolve_fields(normalized_records, fields)
        warnings: list[str] = []

        overall_source_filter = self._overall_source_filter(analysis_type)
        if analysis_type == "human_agent":
            overall, human_agent_by_field, confusion_matrix = (
                self._compute_human_agent_breakdown(normalized_records, field_names)
            )
            human_agent_summary = overall
            if overall.comparisons == 0:
                warnings.append("No human-agent comparisons were available.")
            return AgreementAnalysisResult(
                analysis_type=analysis_type,
                overall=overall,
                human_agent=human_agent_summary,
                human_agent_by_field=human_agent_by_field,
                confusion_matrix=confusion_matrix,
                warnings=warnings,
            )

        overall = self._compute_metric_summary(
            normalized_records,
            field_names,
            source_filter=overall_source_filter,
            warnings=warnings,
        )

        human_agent_summary: AgreementMetricSummary | None = None
        human_agent_by_field: dict[str, AgreementFieldBreakdown] = {}
        confusion_matrix: dict[str, dict[str, int]] = {}
        if analysis_type in {"human_agent", "both"}:
            human_agent_summary, human_agent_by_field, confusion_matrix = (
                self._compute_human_agent_breakdown(normalized_records, field_names)
            )
            if human_agent_summary.comparisons == 0:
                warnings.append("No human-agent comparisons were available.")

        if overall.comparisons == 0:
            warnings.append("No comparable annotations were available.")

        return AgreementAnalysisResult(
            analysis_type=analysis_type,
            overall=overall,
            human_agent=human_agent_summary,
            human_agent_by_field=human_agent_by_field,
            confusion_matrix=confusion_matrix,
            warnings=warnings,
        )

    def _normalize_record(
        self, record: AgreementRecord | dict[str, Any]
    ) -> AgreementRecord:
        if isinstance(record, AgreementRecord):
            return record
        return AgreementRecord.model_validate(record)

    def _resolve_fields(
        self,
        records: Sequence[AgreementRecord],
        fields: Sequence[str] | None,
    ) -> list[str]:
        if fields is not None:
            return list(dict.fromkeys(fields))

        discovered: set[str] = set()
        for record in records:
            for annotation in record.annotations:
                discovered.update(annotation.labels.keys())
        return sorted(discovered)

    @staticmethod
    def _overall_source_filter(analysis_type: str) -> set[str] | None:
        if analysis_type == "human_agent":
            return {"human", "import", "agent"}
        if analysis_type == "inter_annotator":
            return {"human", "import"}
        return None

    def _compute_metric_summary(
        self,
        records: Sequence[AgreementRecord],
        fields: Sequence[str],
        *,
        source_filter: set[str] | None,
        warnings: list[str],
    ) -> AgreementMetricSummary:
        comparisons = 0
        agreements = 0
        label_counts: Counter[str] = Counter()
        endpoint_counts: Counter[str] = Counter()
        item_agreement_rates: list[float] = []
        item_label_counts: Counter[str] = Counter()

        for record in records:
            for field in fields:
                values = [
                    _canonical_label(annotation.labels[field])
                    for annotation in record.annotations
                    if field in annotation.labels
                    and (source_filter is None or annotation.source in source_filter)
                ]
                if len(values) < 2:
                    continue

                counts = Counter(values)
                item_pairs = len(values) * (len(values) - 1) // 2
                item_agreements = sum(
                    count * (count - 1) // 2 for count in counts.values()
                )

                comparisons += item_pairs
                agreements += item_agreements
                item_agreement_rates.append(item_agreements / item_pairs)

                for label, count in counts.items():
                    item_label_counts[label] += count
                    label_counts[label] += count
                    endpoint_counts[label] += count * (len(values) - 1)

        percent_agreement = agreements / comparisons if comparisons else 0.0
        total_endpoints = sum(endpoint_counts.values())
        cohen_expected = (
            sum((count / total_endpoints) ** 2 for count in endpoint_counts.values())
            if total_endpoints
            else 0.0
        )
        total_labels = sum(item_label_counts.values())
        fleiss_expected = (
            sum((count / total_labels) ** 2 for count in item_label_counts.values())
            if total_labels
            else 0.0
        )
        krippendorff_expected = fleiss_expected

        fleiss_observed = (
            sum(item_agreement_rates) / len(item_agreement_rates)
            if item_agreement_rates
            else 0.0
        )
        krippendorff_observed = percent_agreement

        if comparisons == 0:
            return AgreementMetricSummary()

        summary = AgreementMetricSummary(
            comparisons=comparisons,
            agreements=agreements,
            percent_agreement=percent_agreement,
            cohen_kappa=_safe_kappa(percent_agreement, cohen_expected),
            fleiss_kappa=_safe_kappa(fleiss_observed, fleiss_expected),
            krippendorff_alpha=_safe_kappa(
                krippendorff_observed,
                krippendorff_expected,
            ),
        )

        if not label_counts:
            warnings.append("Agreement analysis had no label values to compare.")
        return summary

    def _compute_human_agent_breakdown(
        self,
        records: Sequence[AgreementRecord],
        fields: Sequence[str],
    ) -> tuple[
        AgreementMetricSummary,
        dict[str, AgreementFieldBreakdown],
        dict[str, dict[str, int]],
    ]:
        overall_comparisons = 0
        overall_agreements = 0
        field_breakdowns: dict[str, AgreementFieldBreakdown] = {}
        confusion_matrix: dict[str, dict[str, int]] = defaultdict(dict)
        endpoint_counts: Counter[str] = Counter()
        label_counts: Counter[str] = Counter()

        for record in records:
            for field in fields:
                human_values = [
                    _canonical_label(annotation.labels[field])
                    for annotation in record.annotations
                    if field in annotation.labels
                    and _is_human_source(annotation.source)
                ]
                agent_values = [
                    _canonical_label(annotation.labels[field])
                    for annotation in record.annotations
                    if field in annotation.labels
                    and _is_agent_source(annotation.source)
                ]
                if not human_values or not agent_values:
                    continue

                breakdown = field_breakdowns.setdefault(
                    field,
                    AgreementFieldBreakdown(),
                )

                item_agreements = 0
                for human_value in human_values:
                    for agent_value in agent_values:
                        overall_comparisons += 1
                        breakdown.comparisons += 1
                        endpoint_counts[human_value] += 1
                        endpoint_counts[agent_value] += 1
                        label_counts[human_value] += 1
                        label_counts[agent_value] += 1

                        if human_value == agent_value:
                            overall_agreements += 1
                            breakdown.agreements += 1
                            item_agreements += 1

                        confusion_matrix.setdefault(human_value, {})
                        confusion_matrix[human_value][agent_value] = (
                            confusion_matrix[human_value].get(agent_value, 0) + 1
                        )

                        if human_value == agent_value:
                            bucket = breakdown.by_label_value.setdefault(
                                human_value,
                                AgreementValueBreakdown(),
                            )
                            bucket.comparisons += 1
                            bucket.agreements += 1
                            bucket.human_count += 1
                            bucket.agent_count += 1
                        else:
                            human_bucket = breakdown.by_label_value.setdefault(
                                human_value,
                                AgreementValueBreakdown(),
                            )
                            human_bucket.comparisons += 1
                            human_bucket.human_count += 1

                            agent_bucket = breakdown.by_label_value.setdefault(
                                agent_value,
                                AgreementValueBreakdown(),
                            )
                            agent_bucket.comparisons += 1
                            agent_bucket.agent_count += 1

        for field_breakdown in field_breakdowns.values():
            if field_breakdown.comparisons:
                field_breakdown.agreement_rate = (
                    field_breakdown.agreements / field_breakdown.comparisons
                )
            for value_breakdown in field_breakdown.by_label_value.values():
                if value_breakdown.comparisons:
                    value_breakdown.agreement_rate = (
                        value_breakdown.agreements / value_breakdown.comparisons
                    )

        total_endpoints = sum(endpoint_counts.values())
        expected_agreement = (
            sum((count / total_endpoints) ** 2 for count in endpoint_counts.values())
            if total_endpoints
            else 0.0
        )
        observed_agreement = (
            overall_agreements / overall_comparisons if overall_comparisons else 0.0
        )
        overall = AgreementMetricSummary(
            comparisons=overall_comparisons,
            agreements=overall_agreements,
            percent_agreement=observed_agreement,
            cohen_kappa=_safe_kappa(observed_agreement, expected_agreement),
            fleiss_kappa=_safe_kappa(observed_agreement, expected_agreement),
            krippendorff_alpha=_safe_kappa(observed_agreement, expected_agreement),
        )
        if not label_counts:
            return (
                overall,
                field_breakdowns,
                {
                    human: dict(agent_counts)
                    for human, agent_counts in confusion_matrix.items()
                },
            )
        return (
            overall,
            field_breakdowns,
            {
                human: dict(agent_counts)
                for human, agent_counts in confusion_matrix.items()
            },
        )

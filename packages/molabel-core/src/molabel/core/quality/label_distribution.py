"""Label distribution service (QA-003).

Computes label distributions per field, per dataset, and per label source
(human vs agent). Returns counts, percentages, and frequency distributions.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, Field

from molabel.core.utils.canonical import canonical_label_value as _canonical_value


class LabelDistribution(BaseModel):
    """Distribution of a single label value within a field."""

    value: str
    count: int = 0
    percentage: float = 0.0


class FieldDistribution(BaseModel):
    """Distribution breakdown for a single field."""

    field_name: str
    total_labels: int = 0
    unique_values: int = 0
    distributions: list[LabelDistribution] = Field(default_factory=list)
    entropy: float = 0.0


class DistributionResult(BaseModel):
    """Full label distribution analysis output."""

    total_records: int = 0
    fields: dict[str, FieldDistribution] = Field(default_factory=dict)
    by_source: dict[str, dict[str, FieldDistribution]] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class DistributionRecord(BaseModel):
    """A single record with labels and source metadata."""

    record_id: str
    source: str
    labels: dict[str, Any] = Field(default_factory=dict)
    dataset_id: str | None = None


class LabelDistributionService:
    """Compute label distributions per field, dataset, and source."""

    def analyze(
        self,
        records: Sequence[DistributionRecord | dict[str, Any]],
        *,
        fields: Sequence[str] | None = None,
        source_filter: str | None = None,
        dataset_filter: str | None = None,
    ) -> DistributionResult:
        """Compute label distributions for the supplied records.

        Parameters
        ----------
        records:
            Label records to analyze.
        fields:
            If provided, restrict analysis to these field names.
        source_filter:
            If provided, only include records from this source (e.g. "human", "agent").
        dataset_filter:
            If provided, only include records from this dataset.

        Returns
        -------
        DistributionResult with per-field and per-source breakdowns.
        """
        normalized = [self._normalize_record(r) for r in records]

        # Apply filters
        if source_filter is not None:
            normalized = [r for r in normalized if r.source == source_filter]
        if dataset_filter is not None:
            normalized = [r for r in normalized if r.dataset_id == dataset_filter]

        if not normalized:
            return DistributionResult(
                warnings=["No records matched the given filters."],
            )

        field_names = self._resolve_fields(normalized, fields)
        total_records = len(normalized)

        # Compute overall distributions
        overall_fields = self._compute_field_distributions(normalized, field_names)

        # Compute per-source distributions
        source_groups: dict[str, list[DistributionRecord]] = {}
        for record in normalized:
            source_groups.setdefault(record.source, []).append(record)

        by_source: dict[str, dict[str, FieldDistribution]] = {}
        for source, source_records in sorted(source_groups.items()):
            by_source[source] = self._compute_field_distributions(
                source_records, field_names
            )

        return DistributionResult(
            total_records=total_records,
            fields=overall_fields,
            by_source=by_source,
        )

    def _normalize_record(
        self, record: DistributionRecord | dict[str, Any]
    ) -> DistributionRecord:
        if isinstance(record, DistributionRecord):
            return record
        return DistributionRecord.model_validate(record)

    def _resolve_fields(
        self,
        records: Sequence[DistributionRecord],
        fields: Sequence[str] | None,
    ) -> list[str]:
        if fields is not None:
            return list(dict.fromkeys(fields))
        discovered: set[str] = set()
        for record in records:
            discovered.update(record.labels.keys())
        return sorted(discovered)

    def _compute_field_distributions(
        self,
        records: Sequence[DistributionRecord],
        field_names: list[str],
    ) -> dict[str, FieldDistribution]:
        result: dict[str, FieldDistribution] = {}
        for field in field_names:
            counter: Counter[str] = Counter()
            for record in records:
                if field in record.labels:
                    value = record.labels[field]
                    counter[_canonical_value(value)] += 1

            total = sum(counter.values())
            distributions = [
                LabelDistribution(
                    value=value,
                    count=count,
                    percentage=count / total if total > 0 else 0.0,
                )
                for value, count in counter.most_common()
            ]

            entropy = self._compute_entropy(counter, total)

            result[field] = FieldDistribution(
                field_name=field,
                total_labels=total,
                unique_values=len(counter),
                distributions=distributions,
                entropy=entropy,
            )
        return result

    @staticmethod
    def _compute_entropy(counter: Counter[str], total: int) -> float:
        """Compute Shannon entropy of the distribution."""
        if total == 0:
            return 0.0
        import math

        entropy = 0.0
        for count in counter.values():
            if count > 0:
                p = count / total
                entropy -= p * math.log2(p)
        return entropy

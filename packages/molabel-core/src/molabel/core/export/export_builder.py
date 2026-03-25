"""Export builder configuration (EX-004, EX-005).

Provides a builder-pattern API for configuring which data to include in
an export and what filters to apply.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from molabel.core.types import Record, ReviewEvent


@dataclass(frozen=True)
class InclusionFlags:
    """Boolean flags controlling what data appears in the export."""

    record_data: bool = True
    labels: bool = True
    agent_labels: bool = False
    review_metadata: bool = False
    adjudication_history: bool = False
    provenance: bool = False


@dataclass(frozen=True)
class ExportFilters:
    """Filter criteria applied before packaging.

    All filters are conjunctive — a record must satisfy every active
    filter to be included.
    """

    min_agreement: float | None = None
    """Exclude records whose agreement score is below this threshold."""

    exclude_flagged: bool = False
    """Exclude records that have any flag set."""

    include_fields: list[str] | None = None
    """If set, only these fields appear in the output."""

    exclude_fields: list[str] | None = None
    """If set, these fields are removed from the output."""


@dataclass(frozen=True)
class ExportConfig:
    """Complete export configuration built by ExportBuilder."""

    inclusion: InclusionFlags = field(default_factory=InclusionFlags)
    filters: ExportFilters = field(default_factory=ExportFilters)
    extra: dict[str, Any] = field(default_factory=dict)


class ExportBuilder:
    """Fluent builder for constructing ExportConfig instances (EX-004).

    Usage::

        config = (
            ExportBuilder()
            .include_labels()
            .include_agent_labels()
            .include_provenance()
            .min_agreement(0.85)
            .exclude_flagged()
            .include_fields(["text", "sentiment"])
            .build()
        )
    """

    def __init__(self) -> None:
        self._record_data: bool = True
        self._labels: bool = True
        self._agent_labels: bool = False
        self._review_metadata: bool = False
        self._adjudication_history: bool = False
        self._provenance: bool = False

        self._min_agreement: float | None = None
        self._exclude_flagged: bool = False
        self._include_field_list: list[str] | None = None
        self._exclude_field_list: list[str] | None = None

        self._extra: dict[str, Any] = {}

    # -- Inclusion flags --

    def include_record_data(self, value: bool = True) -> ExportBuilder:
        """Include the raw record data in the export."""
        self._record_data = value
        return self

    def include_labels(self, value: bool = True) -> ExportBuilder:
        """Include human labels in the export."""
        self._labels = value
        return self

    def include_agent_labels(self, value: bool = True) -> ExportBuilder:
        """Include agent-produced labels in the export."""
        self._agent_labels = value
        return self

    def include_review_metadata(self, value: bool = True) -> ExportBuilder:
        """Include review event metadata (reviewer, decision, duration)."""
        self._review_metadata = value
        return self

    def include_adjudication_history(self, value: bool = True) -> ExportBuilder:
        """Include adjudication resolution history."""
        self._adjudication_history = value
        return self

    def include_provenance(self, value: bool = True) -> ExportBuilder:
        """Include full provenance chain for each record."""
        self._provenance = value
        return self

    # -- Filters --

    def min_agreement(self, threshold: float) -> ExportBuilder:
        """Exclude records below this agreement threshold (EX-005)."""
        self._min_agreement = threshold
        return self

    def exclude_flagged(self, value: bool = True) -> ExportBuilder:
        """Exclude records that have been flagged (EX-005)."""
        self._exclude_flagged = value
        return self

    def include_fields(self, fields: list[str]) -> ExportBuilder:
        """Only include these fields in the output (EX-005)."""
        self._include_field_list = list(fields)
        return self

    def exclude_fields(self, fields: list[str]) -> ExportBuilder:
        """Remove these fields from the output (EX-005)."""
        self._exclude_field_list = list(fields)
        return self

    def extra_config(self, key: str, value: Any) -> ExportBuilder:
        """Set an arbitrary extra configuration key."""
        self._extra[key] = value
        return self

    # -- Build --

    def build(self) -> ExportConfig:
        """Construct the immutable ExportConfig."""
        return ExportConfig(
            inclusion=InclusionFlags(
                record_data=self._record_data,
                labels=self._labels,
                agent_labels=self._agent_labels,
                review_metadata=self._review_metadata,
                adjudication_history=self._adjudication_history,
                provenance=self._provenance,
            ),
            filters=ExportFilters(
                min_agreement=self._min_agreement,
                exclude_flagged=self._exclude_flagged,
                include_fields=self._include_field_list,
                exclude_fields=self._exclude_field_list,
            ),
            extra=dict(self._extra),
        )


def apply_filters(
    records: list[Record],
    labels: dict[str, list[ReviewEvent]],
    filters: ExportFilters,
    *,
    agreement_scores: dict[str, float] | None = None,
) -> tuple[list[Record], dict[str, list[ReviewEvent]]]:
    """Apply ExportFilters to a record set, returning the filtered subset.

    Parameters
    ----------
    records:
        The full list of records to filter.
    labels:
        Mapping of record ID (str) to review events.
    filters:
        The filter criteria.
    agreement_scores:
        Optional mapping of record ID (str) to agreement score.
        Required when ``filters.min_agreement`` is set.

    Returns
    -------
    A ``(filtered_records, filtered_labels)`` tuple.
    """
    agreement_scores = agreement_scores or {}
    filtered_records: list[Record] = []
    filtered_labels: dict[str, list[ReviewEvent]] = {}

    for record in records:
        rid = str(record.id)

        # Min-agreement filter
        if filters.min_agreement is not None:
            score = agreement_scores.get(rid)
            if score is None or score < filters.min_agreement:
                continue

        # Exclude-flagged filter
        if filters.exclude_flagged and record.flags:
            continue

        filtered_records.append(record)
        filtered_labels[rid] = labels.get(rid, [])

    return filtered_records, filtered_labels


def apply_field_filters(
    row: dict[str, Any],
    filters: ExportFilters,
) -> dict[str, Any]:
    """Apply include/exclude field filters to a single export row.

    Parameters
    ----------
    row:
        The row dict to filter.
    filters:
        The filter criteria with include_fields / exclude_fields.

    Returns
    -------
    A new dict with only the permitted fields.
    """
    result = dict(row)

    if filters.include_fields is not None:
        result = {k: v for k, v in result.items() if k in filters.include_fields}

    if filters.exclude_fields is not None:
        result = {k: v for k, v in result.items() if k not in filters.exclude_fields}

    return result

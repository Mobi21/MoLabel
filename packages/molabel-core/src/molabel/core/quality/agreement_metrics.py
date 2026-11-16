"""Agreement metrics for grouped annotations.

A unit is one field of one record, and its values are the canonical labels the
annotations in scope gave that field. An annotation without the field is a
missing value. A unit with fewer than two values cannot be paired and is left
out. Values are compared as nominal categories.

``comparisons`` and ``agreements`` count value pairs within units, and
``percent_agreement`` is their ratio. The chance-corrected coefficients are:

- ``krippendorff_alpha``. Krippendorff's alpha with the nominal metric, built
  from the coincidence matrix of pairable values (Krippendorff 2011).
- ``fleiss_kappa``. Fleiss' kappa (Fleiss 1971), defined only when every unit
  holds the same number of values.
- ``cohen_kappa``. Cohen's kappa (Cohen 1960) for exactly two raters, each with
  its own marginals. Raters are told apart by annotation source, so it needs one
  value from each of the same two sources in every unit.

The ``human_agent`` summary pairs each human value in a unit with each agent
value. Every pair is a two-rater unit, with the human side and the agent as
the raters. A metric the data leave undefined is None, and ``null_reasons``
says why. ``docs/guides/agreement-metrics.md`` gives the formulas.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from molabel.core.utils.canonical import canonical_label_value as _canonical_label

Rating = tuple[str, str]
"""A (rater, canonical value) pair. The rater is the annotation source."""

NO_PAIRABLE_VALUES = "No unit has two or more values to compare."
SINGLE_CATEGORY = (
    "Every compared value is the same label, so chance alone predicts full "
    "agreement and the coefficient is 0/0."
)
SHARED_SOURCE = (
    "Cohen's kappa needs one value from each of two raters per unit. Raters are "
    "told apart by annotation source, and a unit holds two values from one source."
)


@dataclass(frozen=True)
class _Undefined:
    reason: str


def _is_human_source(source: str) -> bool:
    return source in {"human", "import"}


def _is_agent_source(source: str) -> bool:
    return source == "agent"


def _sum_of_squares(counts: Counter[str]) -> int:
    return sum(count * count for count in counts.values())


def _krippendorff_alpha_nominal(units: Sequence[Sequence[str]]) -> float | _Undefined:
    """1 - (n - 1) * sum of o_ck over c != k / sum of n_c * n_k over c != k."""
    totals: Counter[str] = Counter()
    mismatched_coincidences = 0.0
    for values in units:
        counts = Counter(values)
        totals.update(counts)
        size = len(values)
        mismatched_coincidences += (size * size - _sum_of_squares(counts)) / (size - 1)
    if len(totals) < 2:
        return _Undefined(SINGLE_CATEGORY)
    n = sum(totals.values())
    expected_mismatches = n * n - _sum_of_squares(totals)
    return 1.0 - (n - 1) * mismatched_coincidences / expected_mismatches


def _fleiss_kappa(units: Sequence[Sequence[str]]) -> float | _Undefined:
    """(P - P_e) / (1 - P_e) with every unit rated the same number of times."""
    sizes = {len(values) for values in units}
    if len(sizes) > 1:
        return _Undefined(
            "Fleiss' kappa needs the same number of values in every unit, and "
            f"units hold {min(sizes)} to {max(sizes)}. Use krippendorff_alpha."
        )
    raters = sizes.pop()
    totals: Counter[str] = Counter()
    matched_pairs = 0
    for values in units:
        counts = Counter(values)
        totals.update(counts)
        matched_pairs += _sum_of_squares(counts) - raters
    if len(totals) < 2:
        return _Undefined(SINGLE_CATEGORY)
    ratings = len(units) * raters
    observed = matched_pairs / (ratings * (raters - 1))
    expected = sum((count / ratings) ** 2 for count in totals.values())
    return (observed - expected) / (1.0 - expected)


def _cohen_kappa(units: Sequence[Sequence[Rating]]) -> float | _Undefined:
    """(p_o - p_e) / (1 - p_e), with p_e from each rater's own marginals."""
    for unit in units:
        if len({rater for rater, _ in unit}) < len(unit):
            return _Undefined(SHARED_SOURCE)
    raters = sorted({rater for unit in units for rater, _ in unit})
    if len(raters) != 2:
        return _Undefined(
            "Cohen's kappa is defined for exactly two raters, and the values come "
            f"from {len(raters)} sources ({', '.join(raters)}). Use fleiss_kappa "
            "or krippendorff_alpha."
        )
    first, second = raters
    pairs = [(by_rater[first], by_rater[second]) for by_rater in map(dict, units)]
    first_counts = Counter(value for value, _ in pairs)
    second_counts = Counter(value for _, value in pairs)
    if len(first_counts.keys() | second_counts.keys()) < 2:
        return _Undefined(SINGLE_CATEGORY)
    n = len(pairs)
    observed = sum(a == b for a, b in pairs) / n
    expected = sum(first_counts[c] * second_counts[c] for c in first_counts) / (n * n)
    return (observed - expected) / (1.0 - expected)


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
    """Aggregate agreement metrics for a population of labels.

    A metric the data leave undefined is None, and ``null_reasons`` maps its
    field name to the reason.
    """

    comparisons: int = 0
    agreements: int = 0
    percent_agreement: float | None = None
    cohen_kappa: float | None = None
    fleiss_kappa: float | None = None
    krippendorff_alpha: float | None = None
    null_reasons: dict[str, str] = Field(default_factory=dict)


_METRIC_FIELDS = (
    "percent_agreement",
    "cohen_kappa",
    "fleiss_kappa",
    "krippendorff_alpha",
)


def _summarize(units: Sequence[Sequence[Rating]]) -> AgreementMetricSummary:
    if not units:
        return AgreementMetricSummary(
            null_reasons=dict.fromkeys(_METRIC_FIELDS, NO_PAIRABLE_VALUES)
        )
    values = [[value for _, value in unit] for unit in units]
    comparisons = sum(len(unit) * (len(unit) - 1) // 2 for unit in values)
    agreements = sum(
        count * (count - 1) // 2 for unit in values for count in Counter(unit).values()
    )
    metrics: dict[str, float | _Undefined] = {
        "percent_agreement": agreements / comparisons,
        "cohen_kappa": _cohen_kappa(units),
        "fleiss_kappa": _fleiss_kappa(values),
        "krippendorff_alpha": _krippendorff_alpha_nominal(values),
    }
    return AgreementMetricSummary.model_validate(
        {
            "comparisons": comparisons,
            "agreements": agreements,
            **{
                name: metric
                for name, metric in metrics.items()
                if not isinstance(metric, _Undefined)
            },
            "null_reasons": {
                name: metric.reason
                for name, metric in metrics.items()
                if isinstance(metric, _Undefined)
            },
        }
    )


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

        overall = _summarize(
            self._units(
                normalized_records,
                field_names,
                source_filter=overall_source_filter,
            )
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

    @staticmethod
    def _units(
        records: Sequence[AgreementRecord],
        fields: Sequence[str],
        *,
        source_filter: set[str] | None,
    ) -> list[list[Rating]]:
        units: list[list[Rating]] = []
        for record in records:
            for field in fields:
                unit = [
                    (annotation.source, _canonical_label(annotation.labels[field]))
                    for annotation in record.annotations
                    if field in annotation.labels
                    and (source_filter is None or annotation.source in source_filter)
                ]
                if len(unit) >= 2:
                    units.append(unit)
        return units

    def _compute_human_agent_breakdown(
        self,
        records: Sequence[AgreementRecord],
        fields: Sequence[str],
    ) -> tuple[
        AgreementMetricSummary,
        dict[str, AgreementFieldBreakdown],
        dict[str, dict[str, int]],
    ]:
        pair_units: list[list[Rating]] = []
        field_breakdowns: dict[str, AgreementFieldBreakdown] = {}
        confusion_matrix: dict[str, dict[str, int]] = {}

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

                for human_value in human_values:
                    for agent_value in agent_values:
                        pair_units.append(
                            [("human", human_value), ("agent", agent_value)]
                        )
                        breakdown.comparisons += 1
                        if human_value == agent_value:
                            breakdown.agreements += 1

                        row = confusion_matrix.setdefault(human_value, {})
                        row[agent_value] = row.get(agent_value, 0) + 1

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

        return _summarize(pair_units), field_breakdowns, confusion_matrix

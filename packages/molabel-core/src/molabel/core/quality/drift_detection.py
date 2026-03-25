"""Drift detection service (QA-007).

Compares label distributions between two time periods or snapshots using
chi-squared tests and KL divergence. Detects which fields have drifted
and by how much, returning severity levels.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from molabel.core.utils.canonical import canonical_label_value as _canonical_value


class DriftSeverity(StrEnum):
    """Severity level for detected drift."""

    none = "none"
    low = "low"
    medium = "medium"
    high = "high"


class FieldDrift(BaseModel):
    """Drift analysis for a single field between reference and current."""

    field_name: str
    chi_squared: float = 0.0
    chi_squared_p_value: float = 1.0
    kl_divergence: float = 0.0
    severity: DriftSeverity = DriftSeverity.none
    reference_distribution: dict[str, float] = Field(default_factory=dict)
    current_distribution: dict[str, float] = Field(default_factory=dict)
    shifted_values: list[str] = Field(default_factory=list)
    """Values whose proportions changed the most."""


class DriftResult(BaseModel):
    """Full drift detection output."""

    fields: dict[str, FieldDrift] = Field(default_factory=dict)
    max_shift: float = 0.0
    drift_detected: bool = False
    affected_fields: list[str] = Field(default_factory=list)
    overall_severity: DriftSeverity = DriftSeverity.none
    warnings: list[str] = Field(default_factory=list)


class DriftRecord(BaseModel):
    """A single label record for drift analysis."""

    record_id: str
    labels: dict[str, Any] = Field(default_factory=dict)


class DriftDetectionService:
    """Compare label distributions between two populations for drift.

    This service is compatible with the interface expected by
    ``DriftDetectionExecutor`` in ``quality_steps.py``, which calls
    ``drift_service.detect(record_ids=..., reference=..., config=...)``.
    The pure-computation ``analyze`` method works on in-memory data.
    """

    def __init__(
        self,
        *,
        drift_threshold: float = 0.1,
        medium_threshold: float = 0.2,
        high_threshold: float = 0.4,
        shift_value_threshold: float = 0.05,
    ) -> None:
        """Initialize with configurable thresholds.

        Parameters
        ----------
        drift_threshold:
            Minimum KL divergence to consider drift detected (default 0.1).
        medium_threshold:
            KL divergence threshold for medium severity (default 0.2).
        high_threshold:
            KL divergence threshold for high severity (default 0.4).
        shift_value_threshold:
            Minimum absolute proportion change for a value to be listed as shifted.
        """
        self.drift_threshold = drift_threshold
        self.medium_threshold = medium_threshold
        self.high_threshold = high_threshold
        self.shift_value_threshold = shift_value_threshold

    def analyze(
        self,
        reference: Sequence[DriftRecord | dict[str, Any]],
        current: Sequence[DriftRecord | dict[str, Any]],
        *,
        fields: Sequence[str] | None = None,
    ) -> DriftResult:
        """Compare two populations of label records for drift.

        Parameters
        ----------
        reference:
            Reference (baseline) label records.
        current:
            Current label records to compare against the reference.
        fields:
            If provided, restrict analysis to these field names.

        Returns
        -------
        DriftResult with per-field drift metrics and severity levels.
        """
        ref_normalized = [self._normalize_record(r) for r in reference]
        cur_normalized = [self._normalize_record(r) for r in current]

        warnings: list[str] = []
        if not ref_normalized:
            warnings.append("No reference records provided.")
        if not cur_normalized:
            warnings.append("No current records provided.")
        if not ref_normalized or not cur_normalized:
            return DriftResult(warnings=warnings)

        field_names = self._resolve_fields(ref_normalized, cur_normalized, fields)
        field_drifts: dict[str, FieldDrift] = {}
        max_shift = 0.0
        affected_fields: list[str] = []
        max_severity = DriftSeverity.none

        for field in field_names:
            field_drift = self._compute_field_drift(
                field, ref_normalized, cur_normalized
            )
            field_drifts[field] = field_drift

            if field_drift.kl_divergence > max_shift:
                max_shift = field_drift.kl_divergence

            if field_drift.severity != DriftSeverity.none:
                affected_fields.append(field)

            if _severity_rank(field_drift.severity) > _severity_rank(max_severity):
                max_severity = field_drift.severity

        drift_detected = max_shift >= self.drift_threshold

        return DriftResult(
            fields=field_drifts,
            max_shift=max_shift,
            drift_detected=drift_detected,
            affected_fields=affected_fields,
            overall_severity=max_severity,
            warnings=warnings,
        )

    def detect(
        self,
        *,
        record_ids: Sequence[str] | None = None,
        reference: Any = None,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Workflow-compatible interface for DriftDetectionExecutor.

        This method is called by quality_steps.py DriftDetectionExecutor.
        It expects pre-loaded data in config for pure-computation mode.

        Parameters
        ----------
        record_ids:
            IDs of current records (used when a data loader is available).
        reference:
            Reference snapshot or step ID.
        config:
            Configuration dict that may contain 'reference_records' and
            'current_records' keys for in-memory analysis.

        Returns
        -------
        Dict with 'max_shift' and 'affected_fields' keys.
        """
        config = config or {}
        ref_data = config.get("reference_records", [])
        cur_data = config.get("current_records", [])
        fields = config.get("fields")

        result = self.analyze(ref_data, cur_data, fields=fields)
        return {
            "max_shift": result.max_shift,
            "affected_fields": result.affected_fields,
            "drift_detected": result.drift_detected,
            "overall_severity": result.overall_severity.value,
        }

    def _compute_field_drift(
        self,
        field: str,
        reference: Sequence[DriftRecord],
        current: Sequence[DriftRecord],
    ) -> FieldDrift:
        ref_counter: Counter[str] = Counter()
        cur_counter: Counter[str] = Counter()

        for r in reference:
            if field in r.labels:
                ref_counter[_canonical_value(r.labels[field])] += 1

        for r in current:
            if field in r.labels:
                cur_counter[_canonical_value(r.labels[field])] += 1

        ref_total = sum(ref_counter.values())
        cur_total = sum(cur_counter.values())

        if ref_total == 0 or cur_total == 0:
            return FieldDrift(
                field_name=field,
                severity=DriftSeverity.none,
            )

        all_values = sorted(set(ref_counter.keys()) | set(cur_counter.keys()))

        ref_dist: dict[str, float] = {}
        cur_dist: dict[str, float] = {}
        for value in all_values:
            ref_dist[value] = ref_counter[value] / ref_total
            cur_dist[value] = cur_counter[value] / cur_total

        chi_squared = self._chi_squared_statistic(
            ref_counter, cur_counter, ref_total, cur_total, all_values
        )
        chi_squared_p_value = self._chi_squared_p_value(chi_squared, len(all_values))
        kl_divergence = self._kl_divergence(ref_dist, cur_dist, all_values)

        shifted_values = [
            v
            for v in all_values
            if abs(cur_dist.get(v, 0.0) - ref_dist.get(v, 0.0))
            >= self.shift_value_threshold
        ]

        severity = self._classify_severity(kl_divergence)

        return FieldDrift(
            field_name=field,
            chi_squared=chi_squared,
            chi_squared_p_value=chi_squared_p_value,
            kl_divergence=kl_divergence,
            severity=severity,
            reference_distribution=ref_dist,
            current_distribution=cur_dist,
            shifted_values=shifted_values,
        )

    def _classify_severity(self, kl_divergence: float) -> DriftSeverity:
        if kl_divergence >= self.high_threshold:
            return DriftSeverity.high
        if kl_divergence >= self.medium_threshold:
            return DriftSeverity.medium
        if kl_divergence >= self.drift_threshold:
            return DriftSeverity.low
        return DriftSeverity.none

    @staticmethod
    def _chi_squared_statistic(
        ref_counter: Counter[str],
        cur_counter: Counter[str],
        ref_total: int,
        cur_total: int,
        all_values: Sequence[str],
    ) -> float:
        """Compute the chi-squared test statistic."""
        chi2 = 0.0
        combined_total = ref_total + cur_total
        for value in all_values:
            observed_ref = ref_counter.get(value, 0)
            observed_cur = cur_counter.get(value, 0)
            combined_count = observed_ref + observed_cur

            expected_ref = combined_count * ref_total / combined_total
            expected_cur = combined_count * cur_total / combined_total

            if expected_ref > 0:
                chi2 += (observed_ref - expected_ref) ** 2 / expected_ref
            if expected_cur > 0:
                chi2 += (observed_cur - expected_cur) ** 2 / expected_cur

        return chi2

    @staticmethod
    def _chi_squared_p_value(chi2: float, num_categories: int) -> float:
        """Approximate chi-squared p-value.

        Uses the regularized incomplete gamma function.

        Uses a simple approximation adequate for drift detection purposes.
        For exact values, scipy.stats.chi2.sf would be used, but we avoid
        the dependency.
        """
        df = max(num_categories - 1, 1)
        if chi2 <= 0:
            return 1.0

        # Wilson-Hilferty approximation for chi-squared CDF
        z = ((chi2 / df) ** (1 / 3) - (1 - 2 / (9 * df))) / math.sqrt(2 / (9 * df))
        # Standard normal CDF approximation
        p_value = 0.5 * math.erfc(z / math.sqrt(2))
        return max(0.0, min(1.0, p_value))

    @staticmethod
    def _kl_divergence(
        ref_dist: dict[str, float],
        cur_dist: dict[str, float],
        all_values: Sequence[str],
    ) -> float:
        """Compute symmetrized KL divergence (Jensen-Shannon style).

        Uses a smoothed version to handle zero probabilities.
        """
        epsilon = 1e-10
        kl_forward = 0.0
        kl_backward = 0.0

        for value in all_values:
            p = ref_dist.get(value, 0.0) + epsilon
            q = cur_dist.get(value, 0.0) + epsilon
            kl_forward += p * math.log(p / q)
            kl_backward += q * math.log(q / p)

        # Return symmetrized KL divergence
        return (kl_forward + kl_backward) / 2.0

    def _normalize_record(self, record: DriftRecord | dict[str, Any]) -> DriftRecord:
        if isinstance(record, DriftRecord):
            return record
        return DriftRecord.model_validate(record)

    def _resolve_fields(
        self,
        reference: Sequence[DriftRecord],
        current: Sequence[DriftRecord],
        fields: Sequence[str] | None,
    ) -> list[str]:
        if fields is not None:
            return list(dict.fromkeys(fields))
        discovered: set[str] = set()
        for record in reference:
            discovered.update(record.labels.keys())
        for record in current:
            discovered.update(record.labels.keys())
        return sorted(discovered)


def _severity_rank(severity: DriftSeverity) -> int:
    """Return numeric rank for severity comparison."""
    return {"none": 0, "low": 1, "medium": 2, "high": 3}.get(severity.value, 0)

"""Agent performance analytics service (AG-015).

Computes per-field accuracy, trends over time, error patterns,
confidence calibration curves, cost tracking, and prompt version comparisons.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from molabel.core.utils.canonical import canonical_label_value

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class FieldAccuracy:
    """Per-field accuracy metrics against ground truth."""

    field_name: str
    total: int = 0
    correct: int = 0
    accuracy: float = 0.0
    error_count: int = 0
    most_common_errors: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AccuracyTrend:
    """Accuracy measurement for a time bucket."""

    bucket_start: datetime = field(default_factory=lambda: datetime.now(UTC))
    bucket_end: datetime = field(default_factory=lambda: datetime.now(UTC))
    bucket_label: str = ""
    total: int = 0
    correct: int = 0
    accuracy: float = 0.0


@dataclass
class ErrorPattern:
    """A common misclassification pattern."""

    field_name: str
    agent_label: str
    correct_label: str
    count: int = 0
    percentage: float = 0.0
    example_record_ids: list[str] = field(default_factory=list)


@dataclass
class CalibrationPoint:
    """A single point on a confidence calibration curve."""

    confidence_bucket: float
    bucket_lower: float = 0.0
    bucket_upper: float = 0.0
    predicted_confidence: float = 0.0
    actual_accuracy: float = 0.0
    sample_count: int = 0


@dataclass
class CostReport:
    """Cost tracking for agent runs."""

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    cost_per_record: float = 0.0
    cost_per_correct_record: float = 0.0
    records_processed: int = 0
    by_run: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class PromptVersionComparison:
    """Accuracy comparison between two prompt versions."""

    version_a: str
    version_b: str
    accuracy_a: float = 0.0
    accuracy_b: float = 0.0
    accuracy_delta: float = 0.0
    records_a: int = 0
    records_b: int = 0
    field_deltas: dict[str, float] = field(default_factory=dict)
    improvement: bool = False


@dataclass
class PerformanceReport:
    """Full performance analytics report."""

    field_accuracies: list[FieldAccuracy] = field(default_factory=list)
    overall_accuracy: float = 0.0
    total_records: int = 0
    total_correct: int = 0
    trends: list[AccuracyTrend] = field(default_factory=list)
    error_patterns: list[ErrorPattern] = field(default_factory=list)
    calibration_curve: list[CalibrationPoint] = field(default_factory=list)
    cost_report: CostReport = field(default_factory=CostReport)
    prompt_comparisons: list[PromptVersionComparison] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Input record type
# ---------------------------------------------------------------------------


@dataclass
class AnalyticsRecord:
    """A record with agent output and ground truth for analytics."""

    record_id: str
    agent_labels: dict[str, Any] = field(default_factory=dict)
    ground_truth_labels: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    tokens_input: int = 0
    tokens_output: int = 0
    latency_ms: int = 0
    cost: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    prompt_version: str = ""
    run_id: str = ""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class PerformanceAnalyticsService:
    """Compute agent performance analytics from labeled records with ground truth.

    All methods are pure computation: they take data in and return results
    with no side effects or database access.
    """

    def compute_report(
        self,
        records: list[AnalyticsRecord | dict[str, Any]],
        *,
        fields: list[str] | None = None,
        time_buckets: int = 10,
        calibration_bins: int = 10,
        cost_per_input_token: float = 0.0,
        cost_per_output_token: float = 0.0,
    ) -> PerformanceReport:
        """Compute a full performance report.

        Parameters
        ----------
        records:
            List of records with agent labels and ground truth.
        fields:
            Specific fields to analyze (None = all fields).
        time_buckets:
            Number of time buckets for trend analysis.
        calibration_bins:
            Number of bins for confidence calibration.
        cost_per_input_token:
            Cost per input token for cost calculation.
        cost_per_output_token:
            Cost per output token for cost calculation.

        Returns
        -------
        PerformanceReport
            Full analytics report.
        """
        normalized = [self._normalize_record(r) for r in records]
        resolved_fields = self._resolve_fields(normalized, fields)

        field_accuracies = self._compute_field_accuracies(normalized, resolved_fields)
        overall_total = sum(fa.total for fa in field_accuracies)
        overall_correct = sum(fa.correct for fa in field_accuracies)
        overall_accuracy = overall_correct / overall_total if overall_total > 0 else 0.0

        trends = self._compute_trends(normalized, resolved_fields, time_buckets)
        error_patterns = self._extract_error_patterns(normalized, resolved_fields)
        calibration = self._compute_calibration_curve(
            normalized, resolved_fields, calibration_bins
        )
        cost_report = self._compute_cost_report(
            normalized, cost_per_input_token, cost_per_output_token
        )

        return PerformanceReport(
            field_accuracies=field_accuracies,
            overall_accuracy=overall_accuracy,
            total_records=len(normalized),
            total_correct=overall_correct,
            trends=trends,
            error_patterns=error_patterns,
            calibration_curve=calibration,
            cost_report=cost_report,
        )

    def compare_prompt_versions(
        self,
        records_a: list[AnalyticsRecord | dict[str, Any]],
        records_b: list[AnalyticsRecord | dict[str, Any]],
        version_a: str,
        version_b: str,
        *,
        fields: list[str] | None = None,
    ) -> PromptVersionComparison:
        """Compare accuracy between two prompt versions.

        Parameters
        ----------
        records_a:
            Records from prompt version A.
        records_b:
            Records from prompt version B.
        version_a:
            Version identifier for A.
        version_b:
            Version identifier for B.
        fields:
            Specific fields to compare (None = all fields).

        Returns
        -------
        PromptVersionComparison
            Accuracy delta between versions.
        """
        norm_a = [self._normalize_record(r) for r in records_a]
        norm_b = [self._normalize_record(r) for r in records_b]

        all_fields_a = self._resolve_fields(norm_a, fields)
        all_fields_b = self._resolve_fields(norm_b, fields)
        all_fields = sorted(set(all_fields_a) | set(all_fields_b))

        acc_a = self._compute_field_accuracies(norm_a, all_fields)
        acc_b = self._compute_field_accuracies(norm_b, all_fields)

        total_a = sum(fa.total for fa in acc_a)
        correct_a = sum(fa.correct for fa in acc_a)
        accuracy_a = correct_a / total_a if total_a > 0 else 0.0

        total_b = sum(fa.total for fa in acc_b)
        correct_b = sum(fa.correct for fa in acc_b)
        accuracy_b = correct_b / total_b if total_b > 0 else 0.0

        field_acc_a = {fa.field_name: fa.accuracy for fa in acc_a}
        field_acc_b = {fa.field_name: fa.accuracy for fa in acc_b}

        field_deltas: dict[str, float] = {}
        for f in all_fields:
            delta = field_acc_b.get(f, 0.0) - field_acc_a.get(f, 0.0)
            field_deltas[f] = round(delta, 6)

        return PromptVersionComparison(
            version_a=version_a,
            version_b=version_b,
            accuracy_a=round(accuracy_a, 6),
            accuracy_b=round(accuracy_b, 6),
            accuracy_delta=round(accuracy_b - accuracy_a, 6),
            records_a=len(norm_a),
            records_b=len(norm_b),
            field_deltas=field_deltas,
            improvement=accuracy_b > accuracy_a,
        )

    # -- Private helpers --

    def _normalize_record(
        self, record: AnalyticsRecord | dict[str, Any]
    ) -> AnalyticsRecord:
        """Normalize a record to AnalyticsRecord."""
        if isinstance(record, AnalyticsRecord):
            return record
        return AnalyticsRecord(
            record_id=str(record.get("record_id", "")),
            agent_labels=record.get("agent_labels", {}),
            ground_truth_labels=record.get("ground_truth_labels", {}),
            confidence=float(record.get("confidence", 0.0)),
            tokens_input=int(record.get("tokens_input", 0)),
            tokens_output=int(record.get("tokens_output", 0)),
            latency_ms=int(record.get("latency_ms", 0)),
            cost=float(record.get("cost", 0.0)),
            created_at=record.get("created_at", datetime.now(UTC)),
            prompt_version=str(record.get("prompt_version", "")),
            run_id=str(record.get("run_id", "")),
        )

    def _resolve_fields(
        self,
        records: list[AnalyticsRecord],
        fields: list[str] | None,
    ) -> list[str]:
        """Resolve which fields to analyze."""
        if fields:
            return list(fields)
        discovered: set[str] = set()
        for record in records:
            discovered.update(record.agent_labels.keys())
            discovered.update(record.ground_truth_labels.keys())
        return sorted(discovered)

    def _compute_field_accuracies(
        self,
        records: list[AnalyticsRecord],
        fields: list[str],
    ) -> list[FieldAccuracy]:
        """Compute per-field accuracy."""
        results: list[FieldAccuracy] = []

        for field_name in fields:
            total = 0
            correct = 0
            error_transitions: Counter[tuple[str, str]] = Counter()

            for record in records:
                agent_val = record.agent_labels.get(field_name)
                truth_val = record.ground_truth_labels.get(field_name)

                if agent_val is None or truth_val is None:
                    continue

                total += 1
                agent_str = canonical_label_value(agent_val)
                truth_str = canonical_label_value(truth_val)

                if agent_str == truth_str:
                    correct += 1
                else:
                    error_transitions[(agent_str, truth_str)] += 1

            accuracy = correct / total if total > 0 else 0.0
            most_common = [
                {
                    "agent_label": agent,
                    "correct_label": truth,
                    "count": count,
                }
                for (agent, truth), count in error_transitions.most_common(5)
            ]

            results.append(
                FieldAccuracy(
                    field_name=field_name,
                    total=total,
                    correct=correct,
                    accuracy=round(accuracy, 6),
                    error_count=total - correct,
                    most_common_errors=most_common,
                )
            )

        return results

    def _compute_trends(
        self,
        records: list[AnalyticsRecord],
        fields: list[str],
        num_buckets: int,
    ) -> list[AccuracyTrend]:
        """Compute accuracy trends over time."""
        if not records:
            return []

        # Sort by created_at
        sorted_records = sorted(records, key=lambda r: r.created_at)
        if len(sorted_records) < 2:
            # Single record: one bucket
            r = sorted_records[0]
            is_correct = self._is_record_correct(r, fields)
            return [
                AccuracyTrend(
                    bucket_start=r.created_at,
                    bucket_end=r.created_at,
                    bucket_label="all",
                    total=1,
                    correct=1 if is_correct else 0,
                    accuracy=1.0 if is_correct else 0.0,
                )
            ]

        min_time = sorted_records[0].created_at
        max_time = sorted_records[-1].created_at

        # Compute total seconds range
        total_seconds = (max_time - min_time).total_seconds()
        if total_seconds <= 0:
            is_correct_count = sum(
                1 for r in sorted_records if self._is_record_correct(r, fields)
            )
            return [
                AccuracyTrend(
                    bucket_start=min_time,
                    bucket_end=max_time,
                    bucket_label="all",
                    total=len(sorted_records),
                    correct=is_correct_count,
                    accuracy=is_correct_count / len(sorted_records),
                )
            ]

        actual_buckets = min(num_buckets, len(sorted_records))
        bucket_seconds = total_seconds / actual_buckets

        trends: list[AccuracyTrend] = []
        for i in range(actual_buckets):
            bucket_start = min_time + timedelta(seconds=i * bucket_seconds)
            bucket_end = min_time + timedelta(seconds=(i + 1) * bucket_seconds)

            bucket_records = [
                r
                for r in sorted_records
                if (bucket_start <= r.created_at < bucket_end)
                or (i == actual_buckets - 1 and r.created_at == max_time)
            ]

            if not bucket_records:
                continue

            total = len(bucket_records)
            correct = sum(
                1 for r in bucket_records if self._is_record_correct(r, fields)
            )

            trends.append(
                AccuracyTrend(
                    bucket_start=bucket_start,
                    bucket_end=bucket_end,
                    bucket_label=f"bucket_{i + 1}",
                    total=total,
                    correct=correct,
                    accuracy=round(correct / total, 6) if total > 0 else 0.0,
                )
            )

        return trends

    def _extract_error_patterns(
        self,
        records: list[AnalyticsRecord],
        fields: list[str],
    ) -> list[ErrorPattern]:
        """Extract common misclassification patterns."""
        patterns: list[ErrorPattern] = []

        for field_name in fields:
            transitions: dict[tuple[str, str], list[str]] = defaultdict(list)
            total_errors = 0

            for record in records:
                agent_val = record.agent_labels.get(field_name)
                truth_val = record.ground_truth_labels.get(field_name)
                if agent_val is None or truth_val is None:
                    continue

                agent_str = canonical_label_value(agent_val)
                truth_str = canonical_label_value(truth_val)
                if agent_str != truth_str:
                    total_errors += 1
                    transitions[(agent_str, truth_str)].append(record.record_id)

            for (agent_label, correct_label), record_ids in sorted(
                transitions.items(), key=lambda x: len(x[1]), reverse=True
            ):
                count = len(record_ids)
                if count >= 2:  # At least 2 occurrences
                    patterns.append(
                        ErrorPattern(
                            field_name=field_name,
                            agent_label=agent_label,
                            correct_label=correct_label,
                            count=count,
                            percentage=round(count / total_errors, 4)
                            if total_errors
                            else 0.0,
                            example_record_ids=record_ids[:5],
                        )
                    )

        return patterns

    def _compute_calibration_curve(
        self,
        records: list[AnalyticsRecord],
        fields: list[str],
        num_bins: int,
    ) -> list[CalibrationPoint]:
        """Compute confidence calibration curve."""
        if not records or num_bins <= 0:
            return []

        bin_width = 1.0 / num_bins
        bins: dict[int, list[tuple[float, bool]]] = defaultdict(list)

        for record in records:
            confidence = max(0.0, min(1.0, record.confidence))
            is_correct = self._is_record_correct(record, fields)
            bin_index = min(int(confidence / bin_width), num_bins - 1)
            bins[bin_index].append((confidence, is_correct))

        points: list[CalibrationPoint] = []
        for bin_idx in range(num_bins):
            bucket_lower = bin_idx * bin_width
            bucket_upper = (bin_idx + 1) * bin_width
            bucket_center = (bucket_lower + bucket_upper) / 2.0

            entries = bins.get(bin_idx, [])
            if not entries:
                continue

            avg_confidence = sum(c for c, _ in entries) / len(entries)
            actual_accuracy = sum(1 for _, correct in entries if correct) / len(entries)

            points.append(
                CalibrationPoint(
                    confidence_bucket=round(bucket_center, 3),
                    bucket_lower=round(bucket_lower, 3),
                    bucket_upper=round(bucket_upper, 3),
                    predicted_confidence=round(avg_confidence, 6),
                    actual_accuracy=round(actual_accuracy, 6),
                    sample_count=len(entries),
                )
            )

        return points

    def _compute_cost_report(
        self,
        records: list[AnalyticsRecord],
        cost_per_input_token: float,
        cost_per_output_token: float,
    ) -> CostReport:
        """Compute cost metrics."""
        total_input = sum(r.tokens_input for r in records)
        total_output = sum(r.tokens_output for r in records)
        total_tokens = total_input + total_output

        # Use record-level cost if available, otherwise compute from tokens
        if any(r.cost > 0 for r in records):
            total_cost = sum(r.cost for r in records)
        else:
            total_cost = (
                total_input * cost_per_input_token
                + total_output * cost_per_output_token
            )

        cost_per_record = total_cost / len(records) if records else 0.0

        # Per-run breakdown
        by_run: dict[str, dict[str, Any]] = {}
        run_groups: dict[str, list[AnalyticsRecord]] = defaultdict(list)
        for record in records:
            if record.run_id:
                run_groups[record.run_id].append(record)

        for run_id, run_records in run_groups.items():
            run_input = sum(r.tokens_input for r in run_records)
            run_output = sum(r.tokens_output for r in run_records)
            if any(r.cost > 0 for r in run_records):
                run_cost = sum(r.cost for r in run_records)
            else:
                run_cost = (
                    run_input * cost_per_input_token
                    + run_output * cost_per_output_token
                )
            by_run[run_id] = {
                "records": len(run_records),
                "input_tokens": run_input,
                "output_tokens": run_output,
                "cost": round(run_cost, 6),
            }

        # Count correct records across all fields
        all_fields = sorted(
            set().union(*(r.agent_labels.keys() for r in records if r.agent_labels))
        )
        correct_count = sum(
            1 for r in records if self._is_record_correct(r, all_fields)
        )
        cost_per_correct = total_cost / correct_count if correct_count > 0 else 0.0

        return CostReport(
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            total_tokens=total_tokens,
            total_cost=round(total_cost, 6),
            cost_per_record=round(cost_per_record, 6),
            cost_per_correct_record=round(cost_per_correct, 6),
            records_processed=len(records),
            by_run=by_run,
        )

    def _is_record_correct(self, record: AnalyticsRecord, fields: list[str]) -> bool:
        """Check if a record's agent labels match ground truth for all fields."""
        if not fields:
            return True
        matched_fields = 0
        total_fields = 0
        for field_name in fields:
            agent_val = record.agent_labels.get(field_name)
            truth_val = record.ground_truth_labels.get(field_name)
            if agent_val is None or truth_val is None:
                continue
            total_fields += 1
            if canonical_label_value(agent_val) == canonical_label_value(truth_val):
                matched_fields += 1
        if total_fields == 0:
            return True  # No comparable fields
        return matched_fields == total_fields


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

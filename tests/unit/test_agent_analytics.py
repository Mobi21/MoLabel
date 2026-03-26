"""Tests for agent performance analytics (AG-015)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from molabel.core.agents.analytics import (
    AnalyticsRecord,
    PerformanceAnalyticsService,
)


@pytest.fixture()
def service() -> PerformanceAnalyticsService:
    return PerformanceAnalyticsService()


@pytest.fixture()
def sample_records() -> list[AnalyticsRecord]:
    """10 records with known accuracy patterns."""
    now = datetime.now(UTC)
    records = []
    for i in range(10):
        # 7 correct, 3 wrong for sentiment
        agent_label = "positive" if i < 7 else "negative"
        truth_label = "positive"
        records.append(
            AnalyticsRecord(
                record_id=f"r{i}",
                agent_labels={"sentiment": agent_label},
                ground_truth_labels={"sentiment": truth_label},
                confidence=0.9 if i < 7 else 0.3,
                tokens_input=100,
                tokens_output=20,
                cost=0.001,
                created_at=now + timedelta(hours=i),
                prompt_version="v1",
                run_id="run-1",
            )
        )
    return records


# ---------------------------------------------------------------------------
# Per-field accuracy
# ---------------------------------------------------------------------------


class TestFieldAccuracy:
    def test_perfect_accuracy(self, service: PerformanceAnalyticsService) -> None:
        """All-correct records produce 100% accuracy."""
        records = [
            AnalyticsRecord(
                record_id=f"r{i}",
                agent_labels={"s": "pos"},
                ground_truth_labels={"s": "pos"},
            )
            for i in range(5)
        ]
        report = service.compute_report(records)
        assert report.overall_accuracy == 1.0
        assert report.field_accuracies[0].accuracy == 1.0
        assert report.field_accuracies[0].error_count == 0

    def test_zero_accuracy(self, service: PerformanceAnalyticsService) -> None:
        """All-wrong records produce 0% accuracy."""
        records = [
            AnalyticsRecord(
                record_id=f"r{i}",
                agent_labels={"s": "neg"},
                ground_truth_labels={"s": "pos"},
            )
            for i in range(5)
        ]
        report = service.compute_report(records)
        assert report.overall_accuracy == 0.0

    def test_partial_accuracy(
        self,
        service: PerformanceAnalyticsService,
        sample_records: list[AnalyticsRecord],
    ) -> None:
        """Mixed correct/wrong produces expected accuracy."""
        report = service.compute_report(sample_records)
        assert report.overall_accuracy == pytest.approx(0.7)
        assert report.total_records == 10

    def test_multiple_fields(self, service: PerformanceAnalyticsService) -> None:
        """Accuracy is computed per-field independently."""
        records = [
            AnalyticsRecord(
                record_id="r1",
                agent_labels={"sentiment": "pos", "toxicity": "low"},
                ground_truth_labels={"sentiment": "pos", "toxicity": "high"},
            )
        ]
        report = service.compute_report(records)
        accs = {fa.field_name: fa.accuracy for fa in report.field_accuracies}
        assert accs["sentiment"] == 1.0
        assert accs["toxicity"] == 0.0

    def test_most_common_errors(self, service: PerformanceAnalyticsService) -> None:
        """Error breakdown shows the most common misclassifications."""
        records = [
            AnalyticsRecord(
                record_id=f"r{i}",
                agent_labels={"s": "neg"},
                ground_truth_labels={"s": "pos"},
            )
            for i in range(5)
        ]
        report = service.compute_report(records)
        errors = report.field_accuracies[0].most_common_errors
        assert len(errors) > 0
        assert errors[0]["agent_label"] == "neg"
        assert errors[0]["correct_label"] == "pos"


# ---------------------------------------------------------------------------
# Trends over time
# ---------------------------------------------------------------------------


class TestAccuracyTrends:
    def test_trends_computed(
        self,
        service: PerformanceAnalyticsService,
        sample_records: list[AnalyticsRecord],
    ) -> None:
        """Trends are computed from time-sorted records."""
        report = service.compute_report(sample_records, time_buckets=5)
        assert len(report.trends) > 0
        assert all(t.total > 0 for t in report.trends)

    def test_single_record_trend(self, service: PerformanceAnalyticsService) -> None:
        """A single record produces one trend bucket."""
        records = [
            AnalyticsRecord(
                record_id="r1",
                agent_labels={"s": "pos"},
                ground_truth_labels={"s": "pos"},
            )
        ]
        report = service.compute_report(records)
        assert len(report.trends) == 1
        assert report.trends[0].accuracy == 1.0

    def test_empty_records_no_trends(
        self, service: PerformanceAnalyticsService
    ) -> None:
        """No records produce no trends."""
        report = service.compute_report([])
        assert report.trends == []


# ---------------------------------------------------------------------------
# Error patterns
# ---------------------------------------------------------------------------


class TestErrorPatterns:
    def test_extract_common_misclassifications(
        self,
        service: PerformanceAnalyticsService,
        sample_records: list[AnalyticsRecord],
    ) -> None:
        """Error patterns detect repeated misclassifications."""
        report = service.compute_report(sample_records)
        assert len(report.error_patterns) > 0
        pattern = report.error_patterns[0]
        assert pattern.field_name == "sentiment"
        assert pattern.count >= 2

    def test_no_errors_no_patterns(self, service: PerformanceAnalyticsService) -> None:
        """Perfect accuracy produces no error patterns."""
        records = [
            AnalyticsRecord(
                record_id=f"r{i}",
                agent_labels={"s": "pos"},
                ground_truth_labels={"s": "pos"},
            )
            for i in range(5)
        ]
        report = service.compute_report(records)
        assert report.error_patterns == []


# ---------------------------------------------------------------------------
# Confidence calibration
# ---------------------------------------------------------------------------


class TestCalibrationCurve:
    def test_calibration_curve_bins(
        self,
        service: PerformanceAnalyticsService,
        sample_records: list[AnalyticsRecord],
    ) -> None:
        """Calibration curve produces bins with sample counts."""
        report = service.compute_report(sample_records, calibration_bins=5)
        assert len(report.calibration_curve) > 0
        assert all(p.sample_count > 0 for p in report.calibration_curve)

    def test_well_calibrated_model(self, service: PerformanceAnalyticsService) -> None:
        """A well-calibrated model has actual accuracy near predicted confidence."""
        # High confidence + correct, low confidence + wrong
        records = []
        for i in range(50):
            correct = i < 40  # 80% correct
            records.append(
                AnalyticsRecord(
                    record_id=f"r{i}",
                    agent_labels={"s": "pos" if correct else "neg"},
                    ground_truth_labels={"s": "pos"},
                    confidence=0.85 if correct else 0.15,
                )
            )
        report = service.compute_report(records, calibration_bins=5)
        # Should have at least 2 calibration points
        assert len(report.calibration_curve) >= 2


# ---------------------------------------------------------------------------
# Cost tracking
# ---------------------------------------------------------------------------


class TestCostReport:
    def test_cost_from_tokens(self, service: PerformanceAnalyticsService) -> None:
        """Cost is computed from token counts when per-token pricing is given."""
        records = [
            AnalyticsRecord(
                record_id="r1",
                agent_labels={"s": "pos"},
                ground_truth_labels={"s": "pos"},
                tokens_input=1000,
                tokens_output=200,
                cost=0.0,
            )
        ]
        report = service.compute_report(
            records,
            cost_per_input_token=0.00003,
            cost_per_output_token=0.00006,
        )
        expected_cost = 1000 * 0.00003 + 200 * 0.00006
        assert report.cost_report.total_cost == pytest.approx(expected_cost, rel=1e-4)

    def test_cost_from_record_level(self, service: PerformanceAnalyticsService) -> None:
        """Record-level cost is used when available."""
        records = [
            AnalyticsRecord(
                record_id="r1",
                agent_labels={"s": "pos"},
                ground_truth_labels={"s": "pos"},
                cost=0.05,
            )
        ]
        report = service.compute_report(records)
        assert report.cost_report.total_cost == pytest.approx(0.05)

    def test_cost_per_correct_record(
        self,
        service: PerformanceAnalyticsService,
        sample_records: list[AnalyticsRecord],
    ) -> None:
        """Cost per correct record accounts for accuracy."""
        report = service.compute_report(sample_records)
        assert (
            report.cost_report.cost_per_correct_record
            > report.cost_report.cost_per_record
        )

    def test_per_run_breakdown(
        self,
        service: PerformanceAnalyticsService,
        sample_records: list[AnalyticsRecord],
    ) -> None:
        """Cost is broken down by run_id."""
        report = service.compute_report(sample_records)
        assert "run-1" in report.cost_report.by_run


# ---------------------------------------------------------------------------
# Prompt version comparison
# ---------------------------------------------------------------------------


class TestPromptVersionComparison:
    def test_improvement_detected(self, service: PerformanceAnalyticsService) -> None:
        """Version comparison detects improvement."""
        records_v1 = [
            AnalyticsRecord(
                record_id=f"r{i}",
                agent_labels={"s": "pos" if i < 6 else "neg"},
                ground_truth_labels={"s": "pos"},
            )
            for i in range(10)
        ]
        records_v2 = [
            AnalyticsRecord(
                record_id=f"r{i}",
                agent_labels={"s": "pos" if i < 9 else "neg"},
                ground_truth_labels={"s": "pos"},
            )
            for i in range(10)
        ]
        comparison = service.compare_prompt_versions(records_v1, records_v2, "v1", "v2")
        assert comparison.improvement is True
        assert comparison.accuracy_delta > 0
        assert comparison.accuracy_b > comparison.accuracy_a
        assert comparison.records_a == 10
        assert comparison.records_b == 10

    def test_regression_detected(self, service: PerformanceAnalyticsService) -> None:
        """Version comparison detects regression."""
        records_v1 = [
            AnalyticsRecord(
                record_id=f"r{i}",
                agent_labels={"s": "pos"},
                ground_truth_labels={"s": "pos"},
            )
            for i in range(10)
        ]
        records_v2 = [
            AnalyticsRecord(
                record_id=f"r{i}",
                agent_labels={"s": "neg"},
                ground_truth_labels={"s": "pos"},
            )
            for i in range(10)
        ]
        comparison = service.compare_prompt_versions(records_v1, records_v2, "v1", "v2")
        assert comparison.improvement is False
        assert comparison.accuracy_delta < 0

    def test_field_deltas(self, service: PerformanceAnalyticsService) -> None:
        """Per-field accuracy deltas are computed."""
        records_v1 = [
            AnalyticsRecord(
                record_id="r1",
                agent_labels={"s": "pos", "t": "low"},
                ground_truth_labels={"s": "pos", "t": "high"},
            )
        ]
        records_v2 = [
            AnalyticsRecord(
                record_id="r1",
                agent_labels={"s": "pos", "t": "high"},
                ground_truth_labels={"s": "pos", "t": "high"},
            )
        ]
        comparison = service.compare_prompt_versions(records_v1, records_v2, "v1", "v2")
        assert comparison.field_deltas["s"] == 0.0  # both correct
        assert comparison.field_deltas["t"] > 0  # v2 improved toxicity

    def test_dict_input_records(self, service: PerformanceAnalyticsService) -> None:
        """Records can be passed as dicts."""
        records = [
            {
                "record_id": "r1",
                "agent_labels": {"s": "pos"},
                "ground_truth_labels": {"s": "pos"},
                "confidence": 0.9,
            }
        ]
        report = service.compute_report(records)
        assert report.overall_accuracy == 1.0

    def test_empty_records_report(self, service: PerformanceAnalyticsService) -> None:
        """Empty input produces a zeroed-out report."""
        report = service.compute_report([])
        assert report.overall_accuracy == 0.0
        assert report.total_records == 0

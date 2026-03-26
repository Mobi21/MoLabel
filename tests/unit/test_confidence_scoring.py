"""Tests for confidence scoring and active learning priority (AG-008, AG-014)."""

from __future__ import annotations

import pytest

from molabel.core.agents.confidence import (
    ActiveLearningPrioritizer,
    ConfidenceConfig,
    ConfidenceScorer,
    ConfidenceSignal,
    ConfidenceSignalType,
    PriorityStrategy,
)

# ---------------------------------------------------------------------------
# AG-008: Multi-signal confidence scoring
# ---------------------------------------------------------------------------


class TestConfidenceScorer:
    def test_single_self_reported_signal(self) -> None:
        """A single self-reported signal produces a composite equal to its value."""
        scorer = ConfidenceScorer()
        result = scorer.score(self_reported=0.85)
        assert result.composite_score == pytest.approx(0.85)
        assert result.signal_count == 1
        assert result.is_reliable is True

    def test_all_three_signals_equal_weight(self) -> None:
        """Three signals with equal weights produce their average."""
        scorer = ConfidenceScorer()
        result = scorer.score(
            self_reported=0.9,
            self_consistency=0.8,
            logprobs=0.7,
        )
        expected = (0.9 + 0.8 + 0.7) / 3
        assert result.composite_score == pytest.approx(expected, abs=1e-5)
        assert result.signal_count == 3

    def test_custom_weights(self) -> None:
        """Custom weights shift the composite toward the higher-weighted signal."""
        config = ConfidenceConfig(
            weights={
                ConfidenceSignalType.self_reported: 1.0,
                ConfidenceSignalType.self_consistency: 2.0,
                ConfidenceSignalType.logprobs: 1.0,
            }
        )
        scorer = ConfidenceScorer(config)
        result = scorer.score(
            self_reported=0.5,
            self_consistency=1.0,
            logprobs=0.5,
        )
        expected = (0.5 * 1.0 + 1.0 * 2.0 + 0.5 * 1.0) / 4.0
        assert result.composite_score == pytest.approx(expected, abs=1e-5)

    def test_no_signals_returns_zero(self) -> None:
        """No signals produces 0.0 and is unreliable."""
        scorer = ConfidenceScorer()
        result = scorer.score()
        assert result.composite_score == 0.0
        assert result.is_reliable is False
        assert result.signal_count == 0

    def test_clamping_out_of_range(self) -> None:
        """Values outside [0, 1] are clamped."""
        scorer = ConfidenceScorer()
        result = scorer.score(self_reported=1.5)
        assert result.composite_score == pytest.approx(1.0)

        result = scorer.score(self_reported=-0.5)
        assert result.composite_score == pytest.approx(0.0)

    def test_extra_signals(self) -> None:
        """Extra custom signals are included in the composite."""
        scorer = ConfidenceScorer()
        extra = [
            ConfidenceSignal(
                signal_type="custom_embedding",
                value=0.9,
                weight=2.0,
            )
        ]
        result = scorer.score(self_reported=0.5, extra_signals=extra)
        expected = (0.5 * 1.0 + 0.9 * 2.0) / 3.0
        assert result.composite_score == pytest.approx(expected, abs=1e-5)
        assert result.signal_count == 2

    def test_min_signals_reliability(self) -> None:
        """Results with fewer than min_signals are marked unreliable."""
        config = ConfidenceConfig(min_signals=2)
        scorer = ConfidenceScorer(config)
        result = scorer.score(self_reported=0.9)
        assert result.is_reliable is False

        result = scorer.score(self_reported=0.9, self_consistency=0.8)
        assert result.is_reliable is True

    def test_self_consistency_all_agree(self) -> None:
        """All runs with identical labels produce consistency of 1.0."""
        scorer = ConfidenceScorer()
        labels = [
            {"sentiment": "positive"},
            {"sentiment": "positive"},
            {"sentiment": "positive"},
        ]
        assert scorer.compute_self_consistency(labels) == 1.0

    def test_self_consistency_partial_agreement(self) -> None:
        """Partial agreement produces a value between 0 and 1."""
        scorer = ConfidenceScorer()
        labels = [
            {"sentiment": "positive"},
            {"sentiment": "negative"},
            {"sentiment": "positive"},
        ]
        result = scorer.compute_self_consistency(labels)
        assert 0.0 < result < 1.0
        assert result == pytest.approx(2 / 3)

    def test_self_consistency_single_run(self) -> None:
        """A single run returns 1.0 (no comparison possible)."""
        scorer = ConfidenceScorer()
        assert scorer.compute_self_consistency([{"sentiment": "positive"}]) == 1.0

    def test_logprobs_to_confidence(self) -> None:
        """Logprobs are converted to a confidence score."""
        scorer = ConfidenceScorer()
        logprobs = [
            {"logprob": -0.1},
            {"logprob": -0.05},
            {"logprob": -0.2},
        ]
        result = scorer.logprobs_to_confidence(logprobs)
        assert 0.0 < result <= 1.0

    def test_logprobs_to_confidence_empty(self) -> None:
        """Empty logprobs return 0.0."""
        scorer = ConfidenceScorer()
        assert scorer.logprobs_to_confidence([]) == 0.0

    def test_logprobs_to_confidence_high_prob(self) -> None:
        """Very high logprobs (near 0) produce confidence near 1.0."""
        scorer = ConfidenceScorer()
        logprobs = [{"logprob": -0.001}, {"logprob": -0.001}]
        result = scorer.logprobs_to_confidence(logprobs)
        assert result > 0.99

    def test_explanation_includes_all_signals(self) -> None:
        """The explanation string mentions all provided signals."""
        scorer = ConfidenceScorer()
        result = scorer.score(self_reported=0.8, logprobs=0.7)
        assert "self_reported" in result.explanation
        assert "logprobs" in result.explanation


# ---------------------------------------------------------------------------
# AG-014: Active learning queue priority
# ---------------------------------------------------------------------------


class TestActiveLearningPrioritizer:
    @pytest.fixture()
    def prioritizer(self) -> ActiveLearningPrioritizer:
        return ActiveLearningPrioritizer()

    @pytest.fixture()
    def sample_records(self) -> list[dict]:
        return [
            {"record_id": "r1", "confidence": 0.9, "labels": {"s": "pos"}},
            {"record_id": "r2", "confidence": 0.3, "labels": {"s": "neg"}},
            {"record_id": "r3", "confidence": 0.5, "labels": {"s": "pos"}},
            {"record_id": "r4", "confidence": 0.1, "labels": {"s": "neutral"}},
        ]

    def test_low_confidence_first(
        self, prioritizer: ActiveLearningPrioritizer, sample_records: list[dict]
    ) -> None:
        """Low confidence records are prioritized first."""
        result = prioritizer.prioritize(
            sample_records, PriorityStrategy.low_confidence_first
        )
        assert result.strategy == "low_confidence_first"
        assert result.total_records == 4
        # Lowest confidence (r4=0.1) should be first
        assert result.records[0].record_id == "r4"
        # Highest confidence (r1=0.9) should be last
        assert result.records[-1].record_id == "r1"

    def test_uncertainty_sampling(
        self, prioritizer: ActiveLearningPrioritizer, sample_records: list[dict]
    ) -> None:
        """Uncertainty sampling prioritizes records near 0.5 confidence."""
        result = prioritizer.prioritize(
            sample_records, PriorityStrategy.uncertainty_sampling
        )
        assert result.strategy == "uncertainty_sampling"
        # r3 (confidence=0.5) should have highest priority
        assert result.records[0].record_id == "r3"

    def test_stratified_sampling(
        self, prioritizer: ActiveLearningPrioritizer, sample_records: list[dict]
    ) -> None:
        """Stratified sampling boosts underrepresented label categories."""
        result = prioritizer.prioritize(
            sample_records, PriorityStrategy.stratified_sampling
        )
        assert result.strategy == "stratified_sampling"
        assert result.total_records == 4
        # "neutral" is rarest (1 record) so r4 should be high priority
        record_order = [r.record_id for r in result.records]
        r4_idx = record_order.index("r4")
        # r4 should be in the top half
        assert r4_idx < 2

    def test_disagreement_first(self, prioritizer: ActiveLearningPrioritizer) -> None:
        """Disagreement-first prioritizes records with high disagreement scores."""
        records = [
            {"record_id": "r1", "confidence": 0.9, "disagreement_score": 0.1},
            {"record_id": "r2", "confidence": 0.3, "disagreement_score": 0.9},
            {"record_id": "r3", "confidence": 0.5, "disagreement_score": 0.5},
        ]
        result = prioritizer.prioritize(records, PriorityStrategy.disagreement_first)
        assert result.records[0].record_id == "r2"

    def test_empty_records(self, prioritizer: ActiveLearningPrioritizer) -> None:
        """Empty record list produces empty result."""
        result = prioritizer.prioritize([], PriorityStrategy.low_confidence_first)
        assert result.total_records == 0
        assert result.records == []

    def test_unknown_strategy_falls_back(
        self, prioritizer: ActiveLearningPrioritizer
    ) -> None:
        """Unknown strategy string falls back to low_confidence_first."""
        records = [
            {"record_id": "r1", "confidence": 0.9},
            {"record_id": "r2", "confidence": 0.1},
        ]
        result = prioritizer.prioritize(records, "nonexistent_strategy")
        assert result.records[0].record_id == "r2"

    def test_all_same_confidence(self, prioritizer: ActiveLearningPrioritizer) -> None:
        """Records with equal confidence get equal priority."""
        records = [
            {"record_id": "r1", "confidence": 0.5},
            {"record_id": "r2", "confidence": 0.5},
        ]
        result = prioritizer.prioritize(records, PriorityStrategy.low_confidence_first)
        assert result.records[0].priority_score == result.records[1].priority_score

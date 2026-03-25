"""Queue ordering strategies tests (T4-11 through T4-14).

Tests:
- T4-11: low_confidence — lowest confidence records come first
- T4-12: uncertainty_sampling — records near decision boundary (confidence ~0.5) first
- T4-13: stratified_sampling — even class distribution in prioritized order
- T4-14: disagreement_first — records with high disagreement score first
"""

from __future__ import annotations

import pytest

from molabel.core.agents.confidence import ActiveLearningPrioritizer, PriorityStrategy
from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SEQUENTIAL

# ---------------------------------------------------------------------------
# T4-11: low_confidence ordering
# ---------------------------------------------------------------------------


@SEQUENTIAL
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier4
async def test_ordering_low_confidence(
    ctx: TestContext,
    client: InstrumentedClient,
) -> None:
    """T4-11: low_confidence_first — records with lowest confidence come first."""
    with checkpoint(ctx, "prioritize_low_confidence"):
        prioritizer = ActiveLearningPrioritizer()

        records = [
            {"record_id": "r1", "confidence": 0.9},
            {"record_id": "r2", "confidence": 0.1},
            {"record_id": "r3", "confidence": 0.5},
            {"record_id": "r4", "confidence": 0.05},
            {"record_id": "r5", "confidence": 0.8},
        ]

        result = prioritizer.prioritize(
            records, strategy=PriorityStrategy.low_confidence_first
        )
        assert result.strategy == "low_confidence_first"
        assert result.total_records == 5

        prioritized_ids = [r.record_id for r in result.records]
        # r4 (0.05) and r2 (0.1) should lead — lowest confidence highest priority
        assert prioritized_ids[0] == "r4"
        assert prioritized_ids[1] == "r2"
        # r1 (0.9) and r5 (0.8) should be last
        assert prioritized_ids[-1] == "r1" or prioritized_ids[-2] == "r1"

    with checkpoint(ctx, "priority_scores_inverse_confidence"):
        for pr in result.records:
            expected_priority = 1.0 - pr.confidence
            assert abs(pr.priority_score - expected_priority) < 1e-6


# ---------------------------------------------------------------------------
# T4-12: uncertainty_sampling
# ---------------------------------------------------------------------------


@SEQUENTIAL
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier4
async def test_ordering_uncertainty_sampling(
    ctx: TestContext,
    client: InstrumentedClient,
) -> None:
    """T4-12: uncertainty_sampling — records near 0.5 confidence come first."""
    with checkpoint(ctx, "prioritize_uncertainty"):
        prioritizer = ActiveLearningPrioritizer()

        records = [
            {"record_id": "r1", "confidence": 0.0},  # minimum uncertainty
            {"record_id": "r2", "confidence": 0.5},  # maximum uncertainty
            {"record_id": "r3", "confidence": 1.0},  # minimum uncertainty
            {"record_id": "r4", "confidence": 0.48},  # near boundary
            {"record_id": "r5", "confidence": 0.9},  # low uncertainty
        ]

        result = prioritizer.prioritize(
            records, strategy=PriorityStrategy.uncertainty_sampling
        )
        assert result.strategy == "uncertainty_sampling"
        assert result.total_records == 5

        prioritized_ids = [r.record_id for r in result.records]
        # r2 (0.5) and r4 (0.48) should be first (highest uncertainty)
        assert "r2" in prioritized_ids[:2]
        assert "r4" in prioritized_ids[:2]

    with checkpoint(ctx, "boundary_records_max_uncertainty"):
        # Score for 0.5 confidence should be 1.0 (maximum uncertainty)
        mid_record = next(r for r in result.records if r.record_id == "r2")
        assert mid_record.priority_score == pytest.approx(1.0, abs=1e-9)

        # Scores for 0.0 and 1.0 should be ~0 (minimum uncertainty)
        zero_record = next(r for r in result.records if r.record_id == "r1")
        assert zero_record.priority_score == pytest.approx(0.0, abs=1e-9)

        one_record = next(r for r in result.records if r.record_id == "r3")
        assert one_record.priority_score == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# T4-13: stratified_sampling
# ---------------------------------------------------------------------------


@SEQUENTIAL
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier4
async def test_ordering_stratified_sampling(
    ctx: TestContext,
    client: InstrumentedClient,
) -> None:
    """T4-13: stratified_sampling — underrepresented classes get higher priority."""
    with checkpoint(ctx, "prioritize_stratified"):
        prioritizer = ActiveLearningPrioritizer()

        # 3 "positive", 1 "negative" (imbalanced)
        records = [
            {"record_id": "r1", "confidence": 0.9, "labels": {"sentiment": "positive"}},
            {"record_id": "r2", "confidence": 0.8, "labels": {"sentiment": "positive"}},
            {"record_id": "r3", "confidence": 0.7, "labels": {"sentiment": "positive"}},
            {"record_id": "r4", "confidence": 0.6, "labels": {"sentiment": "negative"}},
        ]

        result = prioritizer.prioritize(
            records, strategy=PriorityStrategy.stratified_sampling
        )
        assert result.strategy == "stratified_sampling"
        assert result.total_records == 4

        prioritized_ids = [r.record_id for r in result.records]
        # The "negative" class is underrepresented → r4 should have higher priority
        r4_pos = prioritized_ids.index("r4")
        # r4 should be in the top half (first 2 positions)
        assert r4_pos < 2, (
            f"r4 (negative minority class) should be prioritized, got position {r4_pos}"
        )

    with checkpoint(ctx, "metadata_includes_label_group"):
        negative_record = next(r for r in result.records if r.record_id == "r4")
        assert negative_record.metadata.get("label_group") == "negative"
        assert "group_priority" in negative_record.metadata


# ---------------------------------------------------------------------------
# T4-14: disagreement_first
# ---------------------------------------------------------------------------


@SEQUENTIAL
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier4
async def test_ordering_disagreement_first(
    ctx: TestContext,
    client: InstrumentedClient,
) -> None:
    """T4-14: disagreement_first — records with high disagreement score first."""
    with checkpoint(ctx, "prioritize_disagreement"):
        prioritizer = ActiveLearningPrioritizer()

        records = [
            {"record_id": "r1", "confidence": 0.8, "disagreement_score": 0.1},
            {"record_id": "r2", "confidence": 0.5, "disagreement_score": 0.9},
            {"record_id": "r3", "confidence": 0.9, "disagreement_score": 0.0},
            {"record_id": "r4", "confidence": 0.3, "disagreement_score": 0.7},
        ]

        result = prioritizer.prioritize(
            records, strategy=PriorityStrategy.disagreement_first
        )
        assert result.strategy == "disagreement_first"
        assert result.total_records == 4

        prioritized_ids = [r.record_id for r in result.records]
        # r2 (disagreement 0.9) and r4 (disagreement 0.7) should lead
        assert "r2" in prioritized_ids[:2]
        assert "r4" in prioritized_ids[:2]

    with checkpoint(ctx, "disagreement_metadata"):
        r2_record = next(r for r in result.records if r.record_id == "r2")
        assert r2_record.metadata.get("disagreement_score") == pytest.approx(
            0.9, abs=1e-9
        )

        # r3 with zero disagreement and high confidence should be last
        r3_record = next(r for r in result.records if r.record_id == "r3")
        assert r3_record.priority_score < r2_record.priority_score

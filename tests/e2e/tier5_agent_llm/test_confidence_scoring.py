"""Confidence scoring tests (T5-05, T5-06).

T5-05: Self-reported confidence — float in [0, 1] returned per output.
T5-06: Self-consistency — 3 samples, consistency score computed from agreement.
"""

from __future__ import annotations

import pytest

from molabel.core.agents.confidence import ConfidenceScorer
from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SHARED_WORKSPACE

# ---------------------------------------------------------------------------
# T5-05: Self-reported confidence
# ---------------------------------------------------------------------------


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier5
async def test_self_reported_confidence_in_range(
    ctx: TestContext,
    client: InstrumentedClient,
) -> None:
    """T5-05: self_reported confidence is a float in [0, 1]."""
    with checkpoint(ctx, "confidence_scorer_self_reported"):
        scorer = ConfidenceScorer()

        # High confidence
        result_high = scorer.score(self_reported=0.95)
        assert result_high.composite_score == pytest.approx(0.95, abs=1e-6)
        assert 0.0 <= result_high.composite_score <= 1.0
        assert result_high.is_reliable is True
        assert result_high.signal_count == 1

        # Low confidence
        result_low = scorer.score(self_reported=0.1)
        assert result_low.composite_score == pytest.approx(0.1, abs=1e-6)
        assert 0.0 <= result_low.composite_score <= 1.0

        # Boundary values
        result_zero = scorer.score(self_reported=0.0)
        assert result_zero.composite_score == pytest.approx(0.0, abs=1e-6)

        result_one = scorer.score(self_reported=1.0)
        assert result_one.composite_score == pytest.approx(1.0, abs=1e-6)

    with checkpoint(ctx, "out_of_range_values_clamped"):
        # Values outside [0, 1] should be clamped
        result_over = scorer.score(self_reported=1.5)
        assert result_over.composite_score <= 1.0

        result_under = scorer.score(self_reported=-0.5)
        assert result_under.composite_score >= 0.0

    with checkpoint(ctx, "no_signals_returns_unreliable"):
        result_empty = scorer.score()
        assert result_empty.composite_score == 0.0
        assert result_empty.is_reliable is False
        assert result_empty.signal_count == 0

    with checkpoint(ctx, "multi_signal_weighted_composite"):
        result_multi = scorer.score(self_reported=0.8, logprobs=0.6)
        # Equal weights → composite = (0.8 + 0.6) / 2 = 0.7
        assert result_multi.composite_score == pytest.approx(0.7, abs=1e-6)
        assert result_multi.signal_count == 2

    with checkpoint(ctx, "explanation_field_populated"):
        result_explain = scorer.score(self_reported=0.75)
        assert "self_reported" in result_explain.explanation
        assert "0.750" in result_explain.explanation


# ---------------------------------------------------------------------------
# T5-06: Self-consistency scoring
# ---------------------------------------------------------------------------


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier5
async def test_self_consistency_three_samples(
    ctx: TestContext,
    client: InstrumentedClient,
) -> None:
    """T5-06: 3 samples from same record; consistency score computed."""
    with checkpoint(ctx, "perfect_consistency_all_agree"):
        scorer = ConfidenceScorer()

        # 3 runs all agree → consistency = 1.0
        run_labels = [
            {"sentiment": "positive"},
            {"sentiment": "positive"},
            {"sentiment": "positive"},
        ]

        consistency = scorer.compute_self_consistency(run_labels)
        assert consistency == pytest.approx(1.0, abs=1e-9)

    with checkpoint(ctx, "full_disagreement_minimum_consistency"):
        # 3 runs all disagree
        all_different = [
            {"sentiment": "positive"},
            {"sentiment": "negative"},
            {"sentiment": "neutral"},
        ]

        consistency_bad = scorer.compute_self_consistency(all_different)
        # Each value appears once in 3 → majority = 1/3 per field
        assert consistency_bad == pytest.approx(1 / 3, abs=1e-9)

    with checkpoint(ctx, "two_of_three_agree"):
        # 2/3 agree → consistency = 2/3
        two_agree = [
            {"sentiment": "positive"},
            {"sentiment": "positive"},
            {"sentiment": "negative"},
        ]

        consistency_two = scorer.compute_self_consistency(two_agree)
        assert consistency_two == pytest.approx(2 / 3, abs=1e-9)

    with checkpoint(ctx, "single_run_returns_full_consistency"):
        # Only 1 run → cannot compare → return 1.0 (no disagreement)
        single = [{"sentiment": "positive"}]
        consistency_single = scorer.compute_self_consistency(single)
        assert consistency_single == pytest.approx(1.0, abs=1e-9)

    with checkpoint(ctx, "empty_runs_returns_full_consistency"):
        consistency_empty = scorer.compute_self_consistency([])
        assert consistency_empty == pytest.approx(1.0, abs=1e-9)

    with checkpoint(ctx, "composite_with_self_consistency"):
        # Use consistency score as input signal
        result = scorer.score(self_reported=0.7, self_consistency=1.0)
        # Weighted average: (0.7 + 1.0) / 2 = 0.85
        assert result.composite_score == pytest.approx(0.85, abs=1e-6)
        assert result.signal_count == 2

"""Delta analysis test (T6-09).

Snapshot comparison, improvement/regression per metric.
Uses DeltaAnalysisService (QA-004) with human and agent source records.
"""

from __future__ import annotations

import pytest

from molabel.core.quality.delta_analysis import (
    DeltaAnalysisService,
    DeltaRecord,
)
from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SHARED_WORKSPACE


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier6
async def test_delta_analysis_snapshot_comparison(
    ctx: TestContext,
    client: InstrumentedClient,
) -> None:
    """T6-09: Snapshot comparison, improvement/regression per metric."""
    service = DeltaAnalysisService(bias_threshold=0.1, high_bias_threshold=0.3)

    with checkpoint(ctx, "no_bias_when_distributions_identical"):
        # Human and agent use identical distributions → no bias detected
        human_records = [
            DeltaRecord(
                record_id=f"h{i}",
                source="human",
                labels={"sentiment": "positive" if i < 50 else "negative"},
            )
            for i in range(100)
        ]
        agent_records = [
            DeltaRecord(
                record_id=f"a{i}",
                source="agent",
                labels={"sentiment": "positive" if i < 50 else "negative"},
            )
            for i in range(100)
        ]

        result = service.analyze(human_records + agent_records)
        assert result.total_human_labels == 100
        assert result.total_agent_labels == 100

        sentiment_field = result.fields.get("sentiment")
        assert sentiment_field is not None
        assert sentiment_field.max_absolute_delta < 0.01
        assert len(sentiment_field.biases) == 0

    with checkpoint(ctx, "agent_overuse_detected"):
        # Human: 50% positive; Agent: 80% positive → delta = +0.30 for positive
        human_bal = [
            DeltaRecord(
                record_id=f"hb{i}",
                source="human",
                labels={"sentiment": "positive" if i < 50 else "negative"},
            )
            for i in range(100)
        ]
        agent_skewed = [
            DeltaRecord(
                record_id=f"as{i}",
                source="agent",
                labels={"sentiment": "positive" if i < 80 else "negative"},
            )
            for i in range(100)
        ]

        result_skewed = service.analyze(human_bal + agent_skewed)
        sentiment_skewed = result_skewed.fields.get("sentiment")
        assert sentiment_skewed is not None
        assert sentiment_skewed.max_absolute_delta >= 0.3

        # positive delta should be agent_overuse
        pos_delta = sentiment_skewed.deltas.get("positive")
        assert pos_delta is not None
        assert pos_delta == pytest.approx(0.30, abs=1e-9)

        # There should be a bias pattern for positive
        bias_values = [b.label_value for b in sentiment_skewed.biases]
        assert "positive" in bias_values

        pos_bias = next(
            b for b in sentiment_skewed.biases if b.label_value == "positive"
        )
        assert pos_bias.direction == "agent_overuse"
        assert pos_bias.severity == "high"

    with checkpoint(ctx, "agent_underuse_detected"):
        # Human: 70% negative; Agent: 20% negative → agent underuses negative
        human_neg = [
            DeltaRecord(
                record_id=f"hn{i}",
                source="human",
                labels={"sentiment": "negative" if i < 70 else "positive"},
            )
            for i in range(100)
        ]
        agent_pos = [
            DeltaRecord(
                record_id=f"ap{i}",
                source="agent",
                labels={"sentiment": "negative" if i < 20 else "positive"},
            )
            for i in range(100)
        ]

        result_neg = service.analyze(human_neg + agent_pos)
        sentiment_neg = result_neg.fields.get("sentiment")
        assert sentiment_neg is not None

        neg_delta = sentiment_neg.deltas.get("negative")
        assert neg_delta is not None
        assert neg_delta < 0  # agent uses negative less

        neg_bias = next(
            (b for b in sentiment_neg.biases if b.label_value == "negative"), None
        )
        assert neg_bias is not None
        assert neg_bias.direction == "agent_underuse"

    with checkpoint(ctx, "human_agent_rates_computed_correctly"):
        human_rates = [
            DeltaRecord(
                record_id=f"hr{i}",
                source="human",
                labels={"category": "A" if i < 60 else "B"},
            )
            for i in range(100)
        ]
        agent_rates = [
            DeltaRecord(
                record_id=f"ar{i}",
                source="agent",
                labels={"category": "A" if i < 40 else "B"},
            )
            for i in range(100)
        ]

        result_rates = service.analyze(human_rates + agent_rates)
        cat_field = result_rates.fields.get("category")
        assert cat_field is not None

        assert cat_field.human_distribution["a"] == pytest.approx(0.60, abs=1e-9)
        assert cat_field.agent_distribution["a"] == pytest.approx(0.40, abs=1e-9)
        assert cat_field.deltas["a"] == pytest.approx(-0.20, abs=1e-9)

    with checkpoint(ctx, "multi_field_analysis"):
        multi_records = [
            DeltaRecord(
                record_id=f"mh{i}",
                source="human",
                labels={
                    "sentiment": "positive" if i < 60 else "negative",
                    "category": "A" if i < 50 else "B",
                },
            )
            for i in range(100)
        ] + [
            DeltaRecord(
                record_id=f"ma{i}",
                source="agent",
                labels={
                    "sentiment": "positive" if i < 90 else "negative",
                    "category": "A" if i < 50 else "B",
                },
            )
            for i in range(100)
        ]

        result_multi = service.analyze(multi_records)
        assert "sentiment" in result_multi.fields
        assert "category" in result_multi.fields

        # Sentiment has large bias; category has none
        sentiment_f = result_multi.fields["sentiment"]
        category_f = result_multi.fields["category"]
        assert sentiment_f.max_absolute_delta > category_f.max_absolute_delta

    with checkpoint(ctx, "overall_biases_sorted_by_magnitude"):
        result_sorted = service.analyze(human_bal + agent_skewed)
        if len(result_sorted.overall_biases) >= 2:
            for i in range(len(result_sorted.overall_biases) - 1):
                assert abs(result_sorted.overall_biases[i].delta) >= abs(
                    result_sorted.overall_biases[i + 1].delta
                )

    with checkpoint(ctx, "field_filter_restricts_analysis"):
        all_recs = [
            DeltaRecord(
                record_id=f"ff{i}",
                source="human" if i < 50 else "agent",
                labels={"sentiment": "positive", "category": "A", "urgency": "high"},
            )
            for i in range(100)
        ]

        result_filtered = service.analyze(all_recs, fields=["sentiment"])
        assert "sentiment" in result_filtered.fields
        assert "category" not in result_filtered.fields
        assert "urgency" not in result_filtered.fields

    with checkpoint(ctx, "missing_source_returns_warnings"):
        only_human = [
            DeltaRecord(
                record_id=f"oh{i}",
                source="human",
                labels={"sentiment": "positive"},
            )
            for i in range(10)
        ]

        result_missing = service.analyze(only_human)
        assert any("agent" in w.lower() for w in result_missing.warnings)
        assert result_missing.total_agent_labels == 0

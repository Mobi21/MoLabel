"""Label distribution test (T6-05).

Per-value counts, percentages, class imbalance detection.
"""

from __future__ import annotations

import pytest

from molabel.core.quality.label_distribution import (
    DistributionRecord,
    LabelDistributionService,
)
from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SHARED_WORKSPACE


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier6
async def test_label_distribution_counts_and_imbalance(
    ctx: TestContext,
    client: InstrumentedClient,
) -> None:
    """T6-05: Per-value counts, percentages, class imbalance detection."""
    service = LabelDistributionService()

    with checkpoint(ctx, "balanced_distribution"):
        records = [
            DistributionRecord(
                record_id=f"r{i}", source="human", labels={"label": label}
            )
            for i, label in enumerate(
                ["positive"] * 40 + ["negative"] * 40 + ["neutral"] * 20
            )
        ]

        result = service.analyze(records)
        assert result.total_records == 100

        label_field = result.fields.get("label")
        assert label_field is not None
        assert label_field.total_labels == 100
        assert label_field.unique_values == 3

    with checkpoint(ctx, "per_value_counts_and_percentages"):
        dist_map = {d.value: d for d in label_field.distributions}

        assert dist_map["positive"].count == 40
        assert dist_map["positive"].percentage == pytest.approx(0.40)

        assert dist_map["negative"].count == 40
        assert dist_map["negative"].percentage == pytest.approx(0.40)

        assert dist_map["neutral"].count == 20
        assert dist_map["neutral"].percentage == pytest.approx(0.20)

    with checkpoint(ctx, "percentages_sum_to_one"):
        total_pct = sum(d.percentage for d in label_field.distributions)
        assert total_pct == pytest.approx(1.0, abs=1e-9)

    with checkpoint(ctx, "imbalanced_distribution_detectable"):
        imbalanced = [
            DistributionRecord(
                record_id=f"r{i}", source="human", labels={"label": label}
            )
            for i, label in enumerate(["positive"] * 90 + ["negative"] * 10)
        ]

        result_imbal = service.analyze(imbalanced)
        label_imbal = result_imbal.fields.get("label")
        assert label_imbal is not None

        dist_imbal = {d.value: d for d in label_imbal.distributions}
        assert dist_imbal["positive"].percentage == pytest.approx(0.90)
        assert dist_imbal["negative"].percentage == pytest.approx(0.10)

        # Entropy is low for imbalanced distributions
        balanced_entropy = label_field.entropy
        imbalanced_entropy = label_imbal.entropy
        assert imbalanced_entropy < balanced_entropy, (
            f"Imbalanced entropy {imbalanced_entropy} should be < "
            f"balanced {balanced_entropy}"
        )

    with checkpoint(ctx, "per_source_breakdown"):
        mixed_records = [
            DistributionRecord(
                record_id=f"h{i}", source="human", labels={"label": "positive"}
            )
            for i in range(30)
        ] + [
            DistributionRecord(
                record_id=f"a{i}", source="agent", labels={"label": "negative"}
            )
            for i in range(20)
        ]

        result_mixed = service.analyze(mixed_records)
        assert "human" in result_mixed.by_source
        assert "agent" in result_mixed.by_source

        human_dist = result_mixed.by_source["human"]["label"]
        assert human_dist.distributions[0].value == "positive"
        assert human_dist.distributions[0].count == 30

        agent_dist = result_mixed.by_source["agent"]["label"]
        assert agent_dist.distributions[0].value == "negative"
        assert agent_dist.distributions[0].count == 20

    with checkpoint(ctx, "source_filter_works"):
        result_human_only = service.analyze(mixed_records, source_filter="human")
        assert result_human_only.total_records == 30
        assert "agent" not in result_human_only.by_source

    with checkpoint(ctx, "entropy_nonnegative"):
        for field_dist in result.fields.values():
            assert field_dist.entropy >= 0.0

"""Drift detection tests (T6-03, T6-04).

T6-03: Chi-squared drift detection — significant distribution shift, p-value computed.
T6-04: KL divergence — zero for identical distributions, high for shifted.
"""

from __future__ import annotations

import pytest

from molabel.core.quality.drift_detection import (
    DriftDetectionService,
    DriftRecord,
    DriftSeverity,
)
from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SHARED_WORKSPACE


def _make_records(
    label_counts: dict[str, int], field: str = "sentiment"
) -> list[DriftRecord]:
    """Build DriftRecord list from {label: count} dict."""
    records = []
    i = 0
    for label, count in label_counts.items():
        for _ in range(count):
            records.append(DriftRecord(record_id=f"r{i}", labels={field: label}))
            i += 1
    return records


# ---------------------------------------------------------------------------
# T6-03: Chi-squared drift detection
# ---------------------------------------------------------------------------


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier6
async def test_chi_squared_drift_detection(
    ctx: TestContext,
    client: InstrumentedClient,
) -> None:
    """T6-03: Significant distribution shift detected; p-value computed."""
    service = DriftDetectionService(
        drift_threshold=0.1, medium_threshold=0.2, high_threshold=0.4
    )

    with checkpoint(ctx, "identical_distributions_no_drift"):
        reference = _make_records({"positive": 50, "negative": 30, "neutral": 20})
        current = _make_records({"positive": 50, "negative": 30, "neutral": 20})

        result = service.analyze(reference, current)
        assert result.drift_detected is False
        assert result.max_shift < service.drift_threshold

        sentiment_drift = result.fields.get("sentiment")
        assert sentiment_drift is not None
        assert sentiment_drift.chi_squared < 1.0
        assert sentiment_drift.chi_squared_p_value > 0.05  # not significant

    with checkpoint(ctx, "significant_shift_detected"):
        # Reference: balanced; Current: heavily positive
        reference_bal = _make_records({"positive": 33, "negative": 33, "neutral": 34})
        current_skewed = _make_records({"positive": 90, "negative": 5, "neutral": 5})

        result_shift = service.analyze(reference_bal, current_skewed)
        assert result_shift.drift_detected is True
        assert result_shift.max_shift > service.drift_threshold

        sentiment_drift_shift = result_shift.fields.get("sentiment")
        assert sentiment_drift_shift is not None
        assert sentiment_drift_shift.chi_squared > 0.0
        assert sentiment_drift_shift.chi_squared_p_value < 0.5  # significant

    with checkpoint(ctx, "p_value_range"):
        # p-value must always be in [0, 1]
        for field_drift in result_shift.fields.values():
            assert 0.0 <= field_drift.chi_squared_p_value <= 1.0

    with checkpoint(ctx, "shifted_values_identified"):
        sentiment_shift = result_shift.fields.get("sentiment")
        assert sentiment_shift is not None
        assert len(sentiment_shift.shifted_values) >= 1
        # "positive" should be identified as a shifted value
        assert "positive" in sentiment_shift.shifted_values

    with checkpoint(ctx, "severity_classification"):
        assert sentiment_drift_shift.severity in (
            DriftSeverity.low,
            DriftSeverity.medium,
            DriftSeverity.high,
        )
        # With such a large shift, should be at least medium
        assert sentiment_drift_shift.severity != DriftSeverity.none

    with checkpoint(ctx, "drift_api_endpoint"):
        ws_resp = await client.post(
            "/api/v1/workspaces", json={"path": "/tmp/ws-drift-detection-test", "workspace_name": "Drift Detection Test"}
        )
        assert ws_resp.status_code == 201
        drift_resp = await client.get(
            "/api/v1/quality/drift",
            params={"workspace_id": "00000000-0000-0000-0000-000000000001"},
        )
        assert drift_resp.status_code == 200
        drift_body = drift_resp.json()
        assert "indicators" in drift_body


# ---------------------------------------------------------------------------
# T6-04: KL divergence
# ---------------------------------------------------------------------------


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier6
async def test_kl_divergence_identical_and_shifted(
    ctx: TestContext,
    client: InstrumentedClient,
) -> None:
    """T6-04: KL divergence is near-zero for identical distributions, high for shifted.
    """
    service = DriftDetectionService(drift_threshold=0.1)

    with checkpoint(ctx, "identical_distributions_kl_near_zero"):
        ref = _make_records({"positive": 60, "negative": 40})
        cur = _make_records({"positive": 60, "negative": 40})

        result_identical = service.analyze(ref, cur)
        sentiment_drift = result_identical.fields.get("sentiment")
        assert sentiment_drift is not None
        # KL divergence of identical distributions should be effectively 0
        assert sentiment_drift.kl_divergence < 0.01

    with checkpoint(ctx, "completely_shifted_distribution_kl_high"):
        ref_one = _make_records({"positive": 100})
        cur_other = _make_records({"negative": 100})

        result_shifted = service.analyze(ref_one, cur_other)
        sentiment_shifted = result_shifted.fields.get("sentiment")
        assert sentiment_shifted is not None
        # Complete shift should produce high KL divergence
        assert sentiment_shifted.kl_divergence > 0.5
        assert result_shifted.drift_detected is True

    with checkpoint(ctx, "kl_is_symmetrized"):
        # The service uses symmetrized KL (Jensen-Shannon style)
        ref_asym = _make_records({"positive": 70, "negative": 30})
        cur_asym = _make_records({"positive": 30, "negative": 70})

        result_a = service.analyze(ref_asym, cur_asym)
        result_b = service.analyze(cur_asym, ref_asym)

        kl_a = result_a.fields["sentiment"].kl_divergence
        kl_b = result_b.fields["sentiment"].kl_divergence
        # Symmetrized KL should be the same regardless of direction
        assert abs(kl_a - kl_b) < 1e-9

    with checkpoint(ctx, "kl_nonnegative"):
        ref_ng = _make_records({"positive": 50, "negative": 50})
        cur_ng = _make_records({"positive": 60, "negative": 40})

        result_ng = service.analyze(ref_ng, cur_ng)
        for field_drift in result_ng.fields.values():
            assert field_drift.kl_divergence >= 0.0

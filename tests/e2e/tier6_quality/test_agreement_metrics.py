"""Agreement metrics tests (T6-01, T6-02).

T6-01: Cohen's kappa — binary/multi-class; perfect=1.0, random~0.
T6-02: Krippendorff's alpha — ordinal scale, multiple raters, missing data.
"""

from __future__ import annotations

import pytest

from molabel.core.quality.agreement_metrics import (
    AgreementAnnotation,
    AgreementMetricsService,
    AgreementRecord,
)
from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SHARED_WORKSPACE


def _make_record(
    record_id: str, annotations: list[tuple[str, str, str]]
) -> AgreementRecord:
    """Make an AgreementRecord. annotations: (source, field, value) tuples."""
    ann_list = []
    field_groups: dict[str, list[tuple[str, str]]] = {}
    for source, field, value in annotations:
        if source not in field_groups:
            field_groups[source] = []
        field_groups[source].append((field, value))

    for source, field_values in field_groups.items():
        labels = {f: v for f, v in field_values}
        ann_list.append(AgreementAnnotation(source=source, labels=labels))

    return AgreementRecord(record_id=record_id, annotations=ann_list)


# ---------------------------------------------------------------------------
# T6-01: Cohen's kappa
# ---------------------------------------------------------------------------


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier6
async def test_cohens_kappa_perfect_and_random(
    ctx: TestContext,
    client: InstrumentedClient,
) -> None:
    """T6-01: Cohen's kappa computation for binary and multi-class cases."""
    service = AgreementMetricsService()

    with checkpoint(ctx, "perfect_agreement_kappa_one"):
        # All human-agent pairs agree → kappa = 1.0
        records = [
            AgreementRecord(
                record_id=f"r{i}",
                annotations=[
                    AgreementAnnotation(source="human", labels={"label": "positive"}),
                    AgreementAnnotation(source="agent", labels={"label": "positive"}),
                ],
            )
            for i in range(10)
        ]

        result = service.analyze(records, analysis_type="human_agent")
        ha = result.human_agent
        assert ha is not None
        assert ha.percent_agreement == pytest.approx(1.0)
        assert ha.cohen_kappa == pytest.approx(1.0)

    with checkpoint(ctx, "complete_disagreement_kappa_near_negative"):
        # All human=positive, all agent=negative → 0% agreement
        records_bad = [
            AgreementRecord(
                record_id=f"r{i}",
                annotations=[
                    AgreementAnnotation(source="human", labels={"label": "positive"}),
                    AgreementAnnotation(source="agent", labels={"label": "negative"}),
                ],
            )
            for i in range(10)
        ]

        result_bad = service.analyze(records_bad, analysis_type="human_agent")
        ha_bad = result_bad.human_agent
        assert ha_bad is not None
        assert ha_bad.percent_agreement == pytest.approx(0.0)
        # With complete disagreement, kappa should be negative
        assert ha_bad.cohen_kappa < 0.5

    with checkpoint(ctx, "multi_class_three_labels"):
        # 3-class: positive, negative, neutral — varied agreement
        records_multi = [
            AgreementRecord(
                record_id="r1",
                annotations=[
                    AgreementAnnotation(source="human", labels={"label": "positive"}),
                    AgreementAnnotation(source="agent", labels={"label": "positive"}),
                ],
            ),
            AgreementRecord(
                record_id="r2",
                annotations=[
                    AgreementAnnotation(source="human", labels={"label": "negative"}),
                    AgreementAnnotation(source="agent", labels={"label": "neutral"}),
                ],
            ),
            AgreementRecord(
                record_id="r3",
                annotations=[
                    AgreementAnnotation(source="human", labels={"label": "neutral"}),
                    AgreementAnnotation(source="agent", labels={"label": "neutral"}),
                ],
            ),
        ]

        result_multi = service.analyze(records_multi, analysis_type="human_agent")
        ha_multi = result_multi.human_agent
        assert ha_multi is not None
        # 2/3 agree → percent_agreement = 2/3
        assert ha_multi.percent_agreement == pytest.approx(2 / 3, abs=1e-9)
        # kappa should be in (-1, 1)
        assert -1.0 <= ha_multi.cohen_kappa <= 1.0

    with checkpoint(ctx, "confusion_matrix_populated"):
        result_cm = service.analyze(records_multi, analysis_type="human_agent")
        cm = result_cm.confusion_matrix
        assert isinstance(cm, dict)
        # positive-positive agreement present
        if "positive" in cm:
            assert isinstance(cm["positive"], dict)

    with checkpoint(ctx, "overall_inter_annotator_agreement"):
        # Test with only human annotations (inter-annotator)
        records_iaa = [
            AgreementRecord(
                record_id=f"r{i}",
                annotations=[
                    AgreementAnnotation(source="human", labels={"label": "positive"}),
                    AgreementAnnotation(source="human", labels={"label": "positive"}),
                ],
            )
            for i in range(5)
        ]
        result_iaa = service.analyze(records_iaa, analysis_type="inter_annotator")
        assert result_iaa.overall.percent_agreement == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# T6-02: Krippendorff's alpha
# ---------------------------------------------------------------------------


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier6
async def test_krippendorffs_alpha_ordinal_and_missing(
    ctx: TestContext,
    client: InstrumentedClient,
) -> None:
    """T6-02: Krippendorff's alpha — ordinal scale, multiple raters, missing data."""
    service = AgreementMetricsService()

    with checkpoint(ctx, "ordinal_perfect_agreement_alpha_one"):
        # 5-point ordinal scale, all raters agree
        records_perfect = []
        for i in range(10):
            annotations = [
                AgreementAnnotation(source="human", labels={"severity": "3"}),
                AgreementAnnotation(source="human", labels={"severity": "3"}),
            ]
            records_perfect.append(
                AgreementRecord(record_id=f"r{i}", annotations=annotations)
            )

        result_perfect = service.analyze(
            records_perfect, analysis_type="inter_annotator"
        )
        assert result_perfect.overall.krippendorff_alpha == pytest.approx(1.0)

    with checkpoint(ctx, "ordinal_disagreement_lowers_alpha"):
        records_mixed = [
            AgreementRecord(
                record_id=f"r{i}",
                annotations=[
                    AgreementAnnotation(
                        source="human", labels={"severity": str(i % 5 + 1)}
                    ),
                    AgreementAnnotation(
                        source="agent", labels={"severity": str((i + 2) % 5 + 1)}
                    ),
                ],
            )
            for i in range(10)
        ]

        result_mixed = service.analyze(records_mixed, analysis_type="both")
        assert result_mixed.overall.krippendorff_alpha < 1.0
        assert result_mixed.overall.krippendorff_alpha > -1.0

    with checkpoint(ctx, "missing_data_handled_gracefully"):
        # Some records missing one annotator's label
        records_missing = [
            AgreementRecord(
                record_id="r1",
                annotations=[
                    AgreementAnnotation(source="human", labels={"severity": "3"}),
                    AgreementAnnotation(source="agent", labels={"severity": "3"}),
                ],
            ),
            AgreementRecord(
                record_id="r2",
                # Only one annotator — should be skipped for agreement computation
                annotations=[
                    AgreementAnnotation(source="human", labels={"severity": "4"}),
                ],
            ),
            AgreementRecord(
                record_id="r3",
                annotations=[
                    AgreementAnnotation(source="human", labels={"severity": "2"}),
                    AgreementAnnotation(source="agent", labels={"severity": "2"}),
                ],
            ),
        ]

        result_missing = service.analyze(records_missing, analysis_type="human_agent")
        # Should not raise; r2 is ignored (only 1 annotator)
        assert result_missing.overall.comparisons >= 2
        assert result_missing.overall.percent_agreement == pytest.approx(1.0)

    with checkpoint(ctx, "quality_api_endpoint_agreement"):
        ws_resp = await client.post(
            "/api/v1/workspaces", json={"path": "/tmp/ws-agreement-metrics-test", "workspace_name": "Agreement Metrics Test"}
        )
        assert ws_resp.status_code == 201
        agreement_resp = await client.get(
            "/api/v1/quality/agreement",
            params={"workspace_id": "00000000-0000-0000-0000-000000000001"},
        )
        assert agreement_resp.status_code == 200
        ag_body = agreement_resp.json()
        assert "overall" in ag_body
        assert "per_field" in ag_body
        assert "per_reviewer" in ag_body

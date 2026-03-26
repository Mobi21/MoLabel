"""Focused tests for the agreement metrics service."""

from __future__ import annotations

import pytest

from molabel.core.quality.agreement_metrics import (
    AgreementAnnotation,
    AgreementMetricsService,
    AgreementRecord,
)


def _record(
    record_id: str,
    human: dict[str, object],
    agent: dict[str, object],
) -> AgreementRecord:
    return AgreementRecord(
        record_id=record_id,
        annotations=[
            AgreementAnnotation(source="human", labels=human),
            AgreementAnnotation(source="agent", labels=agent),
        ],
    )


def test_computes_core_agreement_metrics() -> None:
    service = AgreementMetricsService()
    result = service.analyze(
        [
            _record("r1", {"sentiment": "positive"}, {"sentiment": "positive"}),
            _record("r2", {"sentiment": "positive"}, {"sentiment": "negative"}),
            _record("r3", {"sentiment": "negative"}, {"sentiment": "negative"}),
        ],
        analysis_type="both",
    )

    assert result.overall.comparisons == 3
    assert result.overall.agreements == 2
    assert result.overall.percent_agreement == pytest.approx(2 / 3)
    assert result.overall.cohen_kappa == pytest.approx(1 / 3)
    assert result.overall.fleiss_kappa == pytest.approx(1 / 3)
    assert result.overall.krippendorff_alpha == pytest.approx(1 / 3)


def test_breaks_human_agent_agreement_down_by_field_and_value() -> None:
    service = AgreementMetricsService()
    result = service.analyze(
        [
            AgreementRecord(
                record_id="r1",
                annotations=[
                    AgreementAnnotation(
                        source="human",
                        labels={"sentiment": "positive", "tone": "formal"},
                    ),
                    AgreementAnnotation(
                        source="agent",
                        labels={"sentiment": "positive", "tone": "formal"},
                    ),
                ],
            ),
            AgreementRecord(
                record_id="r2",
                annotations=[
                    AgreementAnnotation(
                        source="human",
                        labels={"sentiment": "positive", "tone": "informal"},
                    ),
                    AgreementAnnotation(
                        source="agent",
                        labels={"sentiment": "negative", "tone": "informal"},
                    ),
                ],
            ),
            AgreementRecord(
                record_id="r3",
                annotations=[
                    AgreementAnnotation(
                        source="human",
                        labels={"sentiment": "negative", "tone": "formal"},
                    ),
                    AgreementAnnotation(
                        source="agent",
                        labels={"sentiment": "negative", "tone": "informal"},
                    ),
                ],
            ),
        ],
        analysis_type="both",
    )

    assert result.human_agent is not None
    assert result.human_agent.percent_agreement == pytest.approx(2 / 3)

    sentiment = result.human_agent_by_field["sentiment"]
    assert sentiment.comparisons == 3
    assert sentiment.agreements == 2
    assert sentiment.agreement_rate == pytest.approx(2 / 3)
    assert sentiment.by_label_value["positive"].comparisons == 2
    assert sentiment.by_label_value["positive"].agreements == 1
    assert sentiment.by_label_value["negative"].comparisons == 2
    assert sentiment.by_label_value["negative"].agreements == 1

    tone = result.human_agent_by_field["tone"]
    assert tone.comparisons == 3
    assert tone.agreements == 2
    assert tone.by_label_value["formal"].comparisons == 2
    assert tone.by_label_value["formal"].agreements == 1
    assert tone.by_label_value["informal"].comparisons == 2
    assert tone.by_label_value["informal"].agreements == 1

    assert result.confusion_matrix["positive"]["positive"] == 1
    assert result.confusion_matrix["positive"]["negative"] == 1
    assert result.confusion_matrix["negative"]["negative"] == 1


def test_human_agent_metrics_ignore_human_human_pairs() -> None:
    service = AgreementMetricsService()
    result = service.analyze(
        [
            AgreementRecord(
                record_id="r1",
                annotations=[
                    AgreementAnnotation(
                        source="human",
                        labels={"sentiment": "positive"},
                    ),
                    AgreementAnnotation(
                        source="human",
                        labels={"sentiment": "positive"},
                    ),
                    AgreementAnnotation(
                        source="agent",
                        labels={"sentiment": "negative"},
                    ),
                ],
            )
        ],
        analysis_type="human_agent",
    )

    assert result.overall.comparisons == 2
    assert result.overall.agreements == 0
    assert result.overall.percent_agreement == pytest.approx(0.0)
    assert result.overall.cohen_kappa == pytest.approx(-1.0)
    assert result.human_agent is not None
    assert result.human_agent.percent_agreement == pytest.approx(0.0)

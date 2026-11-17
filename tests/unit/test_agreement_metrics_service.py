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
    # Human says positive 2/3, agent 1/3: p_e = 4/9, kappa = (2/3 - 4/9) / (5/9).
    assert result.overall.cohen_kappa == pytest.approx(2 / 5)
    # Pooled marginals 1/2 each: P_e = 1/2, kappa = (2/3 - 1/2) / (1/2).
    assert result.overall.fleiss_kappa == pytest.approx(1 / 3)
    # n = 6 values, 2 mismatching coincidences: alpha = 1 - 5 * 2 / (6 * 6 - 18).
    assert result.overall.krippendorff_alpha == pytest.approx(4 / 9)


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
    # Humans only say positive and the agent only negative, so p_e = 0.
    assert result.overall.cohen_kappa == pytest.approx(0.0)
    assert result.human_agent is not None
    assert result.human_agent.percent_agreement == pytest.approx(0.0)


def _three_rater_record(
    record_id: str, human: str, agent: str, imported: str
) -> AgreementRecord:
    return AgreementRecord(
        record_id=record_id,
        annotations=[
            AgreementAnnotation(source="human", labels={"sentiment": human}),
            AgreementAnnotation(source="agent", labels={"sentiment": agent}),
            AgreementAnnotation(source="import", labels={"sentiment": imported}),
        ],
    )


def test_perfect_agreement_across_categories_scores_one() -> None:
    result = AgreementMetricsService().analyze(
        [
            _record("r1", {"sentiment": "positive"}, {"sentiment": "positive"}),
            _record("r2", {"sentiment": "negative"}, {"sentiment": "negative"}),
        ]
    )

    assert result.overall.cohen_kappa == pytest.approx(1.0)
    assert result.overall.fleiss_kappa == pytest.approx(1.0)
    assert result.overall.krippendorff_alpha == pytest.approx(1.0)
    assert result.overall.null_reasons == {}


def test_single_category_leaves_chance_corrected_metrics_null() -> None:
    result = AgreementMetricsService().analyze(
        [
            _record("r1", {"sentiment": "positive"}, {"sentiment": "positive"}),
            _record("r2", {"sentiment": "positive"}, {"sentiment": "positive"}),
        ]
    )

    assert result.overall.percent_agreement == pytest.approx(1.0)
    assert result.overall.cohen_kappa is None
    assert result.overall.fleiss_kappa is None
    assert result.overall.krippendorff_alpha is None
    assert set(result.overall.null_reasons) == {
        "cohen_kappa",
        "fleiss_kappa",
        "krippendorff_alpha",
    }


def test_no_pairable_values_leaves_every_metric_null() -> None:
    result = AgreementMetricsService().analyze(
        [
            AgreementRecord(
                record_id="r1",
                annotations=[
                    AgreementAnnotation(source="human", labels={"sentiment": "a"})
                ],
            ),
            AgreementRecord(
                record_id="r2",
                annotations=[
                    AgreementAnnotation(source="agent", labels={"sentiment": "b"})
                ],
            ),
        ]
    )

    assert result.overall.comparisons == 0
    assert result.overall.percent_agreement is None
    assert result.overall.cohen_kappa is None
    assert result.overall.fleiss_kappa is None
    assert result.overall.krippendorff_alpha is None
    assert set(result.overall.null_reasons) == {
        "percent_agreement",
        "cohen_kappa",
        "fleiss_kappa",
        "krippendorff_alpha",
    }
    assert "No comparable annotations were available." in result.warnings


def test_cohen_kappa_is_null_for_more_than_two_raters() -> None:
    result = AgreementMetricsService().analyze(
        [
            _three_rater_record("r1", "positive", "positive", "negative"),
            _three_rater_record("r2", "negative", "negative", "negative"),
        ]
    )

    assert result.overall.cohen_kappa is None
    assert "cohen_kappa" in result.overall.null_reasons
    assert result.overall.fleiss_kappa is not None
    assert result.overall.krippendorff_alpha is not None


def test_cohen_kappa_is_null_when_two_ratings_share_a_source() -> None:
    result = AgreementMetricsService().analyze(
        [
            AgreementRecord(
                record_id=f"r{index}",
                annotations=[
                    AgreementAnnotation(source="human", labels={"sentiment": first}),
                    AgreementAnnotation(source="human", labels={"sentiment": second}),
                ],
            )
            for index, (first, second) in enumerate(
                [("positive", "positive"), ("positive", "negative")]
            )
        ],
        analysis_type="inter_annotator",
    )

    assert result.overall.cohen_kappa is None
    assert "cohen_kappa" in result.overall.null_reasons
    assert result.overall.krippendorff_alpha is not None


def test_cohen_kappa_tells_two_humans_apart_by_rater_id() -> None:
    cells = {("yes", "yes"): 4, ("yes", "no"): 1, ("no", "yes"): 2, ("no", "no"): 3}
    pairs = [pair for pair, count in cells.items() for _ in range(count)]

    result = AgreementMetricsService().analyze(
        [
            AgreementRecord(
                record_id=f"r{index}",
                annotations=[
                    AgreementAnnotation(
                        source="human", rater_id="reviewer-a", labels={"code": a}
                    ),
                    AgreementAnnotation(
                        source="human", rater_id="reviewer-b", labels={"code": b}
                    ),
                ],
            )
            for index, (a, b) in enumerate(pairs)
        ],
        analysis_type="inter_annotator",
    )

    # p_o = 7/10. A says yes 5 times, B 6 times: p_e = 0.5 * 0.6 + 0.5 * 0.4 = 0.5.
    assert result.overall.cohen_kappa == pytest.approx((0.7 - 0.5) / (1 - 0.5))
    assert result.overall.null_reasons == {}


def test_null_labels_are_missing_values() -> None:
    units = [("a", "a", None), ("a", "b", None), ("b", "b", "b"), ("a", None, None)]

    result = AgreementMetricsService().analyze(
        [
            AgreementRecord(
                record_id=f"u{index}",
                annotations=[
                    AgreementAnnotation(
                        source="human", rater_id=rater, labels={"code": value}
                    )
                    for rater, value in zip(("r1", "r2", "r3"), unit, strict=True)
                ],
            )
            for index, unit in enumerate(units)
        ],
        analysis_type="inter_annotator",
    )

    # Pairable units are [a a], [a b] and [b b b]. The last unit keeps one value.
    assert result.overall.comparisons == 1 + 1 + 3
    assert result.overall.agreements == 1 + 0 + 3
    # n = 7 with a = 3, b = 4. Only [a b] mismatches: alpha = 1 - 6 * 2 / (49 - 25).
    assert result.overall.krippendorff_alpha == pytest.approx(0.5)
    assert "fleiss_kappa" in result.overall.null_reasons


def test_null_agent_label_is_not_a_human_agent_pair() -> None:
    result = AgreementMetricsService().analyze(
        [
            _record("r1", {"sentiment": "positive"}, {"sentiment": None}),
            _record("r2", {"sentiment": "positive"}, {"sentiment": "positive"}),
            _record("r3", {"sentiment": "negative"}, {"sentiment": "negative"}),
        ],
        analysis_type="human_agent",
    )

    assert result.human_agent is not None
    assert result.human_agent.comparisons == 2
    assert result.human_agent.percent_agreement == pytest.approx(1.0)
    assert result.confusion_matrix == {
        "positive": {"positive": 1},
        "negative": {"negative": 1},
    }
    assert set(result.human_agent_by_field["sentiment"].by_label_value) == {
        "positive",
        "negative",
    }


def test_reports_each_field_beside_the_pooled_summary() -> None:
    result = AgreementMetricsService().analyze(
        [
            _record(
                record_id, {"sentiment": s, "topic": t}, {"sentiment": s, "topic": u}
            )
            for record_id, s, t, u in [
                ("r1", "pos", "x", "x"),
                ("r2", "neg", "y", "x"),
                ("r3", "pos", "x", "y"),
                ("r4", "neg", "y", "y"),
            ]
        ],
        analysis_type="both",
    )

    assert result.human_agent is not None
    for fields in (result.fields, result.human_agent_fields):
        assert list(fields) == ["sentiment", "topic"]
        assert fields["sentiment"].cohen_kappa == pytest.approx(1.0)
        assert fields["sentiment"].krippendorff_alpha == pytest.approx(1.0)
        topic = fields["topic"]
        assert topic.percent_agreement == pytest.approx(0.5)
        # Each rater says x half the time: p_e = 1/2, kappa = (1/2 - 1/2) / (1/2).
        assert topic.cohen_kappa == pytest.approx(0.0)
        # n = 8 with x = y = 4 and 4 mismatching coincidences: 1 - 7 * 4 / 32.
        assert topic.krippendorff_alpha == pytest.approx(0.125)
    for pooled in (result.overall, result.human_agent):
        # n = 16 over four labels of 4 each, 4 mismatches: 1 - 15 * 4 / (256 - 64).
        assert pooled.krippendorff_alpha == pytest.approx(0.6875)
        assert pooled.percent_agreement == pytest.approx(6 / 8)

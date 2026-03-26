"""Tests for the agent vs human delta analysis service (QA-004)."""

from __future__ import annotations

import pytest

from molabel.core.quality.delta_analysis import (
    DeltaAnalysisService,
    DeltaRecord,
)


def _record(
    record_id: str,
    source: str,
    labels: dict[str, object],
) -> DeltaRecord:
    return DeltaRecord(record_id=record_id, source=source, labels=labels)


def test_basic_delta_computation() -> None:
    service = DeltaAnalysisService()
    result = service.analyze(
        [
            _record("r1", "human", {"sentiment": "positive"}),
            _record("r2", "human", {"sentiment": "positive"}),
            _record("r3", "human", {"sentiment": "negative"}),
            _record("r4", "agent", {"sentiment": "positive"}),
            _record("r5", "agent", {"sentiment": "negative"}),
            _record("r6", "agent", {"sentiment": "negative"}),
        ]
    )

    assert result.total_human_labels == 3
    assert result.total_agent_labels == 3
    assert "sentiment" in result.fields

    field = result.fields["sentiment"]
    # Human: positive=2/3, negative=1/3
    # Agent:  positive=1/3, negative=2/3
    assert field.human_distribution["positive"] == pytest.approx(2 / 3)
    assert field.agent_distribution["positive"] == pytest.approx(1 / 3)
    # Delta for positive: 1/3 - 2/3 = -1/3 (agent uses less)
    assert field.deltas["positive"] == pytest.approx(-1 / 3)
    # Delta for negative: 2/3 - 1/3 = 1/3 (agent uses more)
    assert field.deltas["negative"] == pytest.approx(1 / 3)
    assert field.max_absolute_delta == pytest.approx(1 / 3)


def test_bias_detection() -> None:
    service = DeltaAnalysisService(bias_threshold=0.1, high_bias_threshold=0.3)
    result = service.analyze(
        [
            _record("r1", "human", {"sentiment": "positive"}),
            _record("r2", "human", {"sentiment": "positive"}),
            _record("r3", "human", {"sentiment": "positive"}),
            _record("r4", "human", {"sentiment": "negative"}),
            # Agent always says positive
            _record("r5", "agent", {"sentiment": "positive"}),
            _record("r6", "agent", {"sentiment": "positive"}),
            _record("r7", "agent", {"sentiment": "positive"}),
            _record("r8", "agent", {"sentiment": "positive"}),
        ]
    )

    field = result.fields["sentiment"]
    assert len(field.biases) > 0

    # negative: human=25%, agent=0% -> delta=-0.25, agent_underuse
    neg_bias = next(b for b in field.biases if b.label_value == "negative")
    assert neg_bias.direction == "agent_underuse"
    assert neg_bias.delta == pytest.approx(-0.25)

    # positive: human=75%, agent=100% -> delta=+0.25, agent_overuse
    pos_bias = next(b for b in field.biases if b.label_value == "positive")
    assert pos_bias.direction == "agent_overuse"
    assert pos_bias.delta == pytest.approx(0.25)


def test_high_severity_bias() -> None:
    service = DeltaAnalysisService(bias_threshold=0.1, high_bias_threshold=0.3)
    result = service.analyze(
        [
            _record("r1", "human", {"sentiment": "positive"}),
            _record("r2", "human", {"sentiment": "positive"}),
            _record("r3", "human", {"sentiment": "positive"}),
            _record("r4", "human", {"sentiment": "positive"}),
            _record("r5", "human", {"sentiment": "positive"}),
            # Agent: all negative
            _record("r6", "agent", {"sentiment": "negative"}),
            _record("r7", "agent", {"sentiment": "negative"}),
            _record("r8", "agent", {"sentiment": "negative"}),
            _record("r9", "agent", {"sentiment": "negative"}),
            _record("r10", "agent", {"sentiment": "negative"}),
        ]
    )

    assert len(result.overall_biases) > 0
    # All biases should be high severity (delta = 1.0)
    for bias in result.overall_biases:
        assert bias.severity == "high"


def test_no_human_records_warning() -> None:
    service = DeltaAnalysisService()
    result = service.analyze(
        [
            _record("r1", "agent", {"sentiment": "positive"}),
            _record("r2", "agent", {"sentiment": "negative"}),
        ]
    )

    assert result.total_human_labels == 0
    assert len(result.warnings) > 0
    assert any("human" in w.lower() for w in result.warnings)


def test_no_agent_records_warning() -> None:
    service = DeltaAnalysisService()
    result = service.analyze(
        [
            _record("r1", "human", {"sentiment": "positive"}),
        ]
    )

    assert result.total_agent_labels == 0
    assert len(result.warnings) > 0
    assert any("agent" in w.lower() for w in result.warnings)


def test_empty_input() -> None:
    service = DeltaAnalysisService()
    result = service.analyze([])

    assert result.total_human_labels == 0
    assert result.total_agent_labels == 0
    assert len(result.fields) == 0


def test_field_filter() -> None:
    service = DeltaAnalysisService()
    result = service.analyze(
        [
            _record("r1", "human", {"sentiment": "positive", "tone": "formal"}),
            _record("r2", "agent", {"sentiment": "negative", "tone": "informal"}),
        ],
        fields=["sentiment"],
    )

    assert "sentiment" in result.fields
    assert "tone" not in result.fields


def test_import_treated_as_human() -> None:
    service = DeltaAnalysisService()
    result = service.analyze(
        [
            _record("r1", "import", {"sentiment": "positive"}),
            _record("r2", "agent", {"sentiment": "positive"}),
        ]
    )

    assert result.total_human_labels == 1
    assert result.total_agent_labels == 1
    field = result.fields["sentiment"]
    assert field.human_total == 1
    assert field.agent_total == 1


def test_overall_biases_sorted_by_magnitude() -> None:
    service = DeltaAnalysisService(bias_threshold=0.05)
    result = service.analyze(
        [
            _record("r1", "human", {"a": "x", "b": "y"}),
            _record("r2", "human", {"a": "x", "b": "y"}),
            _record("r3", "human", {"a": "x", "b": "y"}),
            _record("r4", "agent", {"a": "z", "b": "y"}),
            _record("r5", "agent", {"a": "x", "b": "z"}),
            _record("r6", "agent", {"a": "z", "b": "z"}),
        ]
    )

    # overall_biases should be sorted by |delta| descending
    if len(result.overall_biases) >= 2:
        for i in range(len(result.overall_biases) - 1):
            assert abs(result.overall_biases[i].delta) >= abs(
                result.overall_biases[i + 1].delta
            )

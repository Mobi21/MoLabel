"""Tests for the label distribution service (QA-003)."""

from __future__ import annotations

import math

import pytest

from molabel.core.quality.label_distribution import (
    DistributionRecord,
    LabelDistributionService,
)


def _record(
    record_id: str,
    source: str,
    labels: dict[str, object],
    dataset_id: str | None = None,
) -> DistributionRecord:
    return DistributionRecord(
        record_id=record_id,
        source=source,
        labels=labels,
        dataset_id=dataset_id,
    )


def test_basic_distribution_counts_and_percentages() -> None:
    service = LabelDistributionService()
    result = service.analyze(
        [
            _record("r1", "human", {"sentiment": "positive"}),
            _record("r2", "human", {"sentiment": "positive"}),
            _record("r3", "human", {"sentiment": "negative"}),
            _record("r4", "agent", {"sentiment": "negative"}),
        ]
    )

    assert result.total_records == 4
    assert "sentiment" in result.fields
    field = result.fields["sentiment"]
    assert field.total_labels == 4
    assert field.unique_values == 2

    # distributions are sorted by count descending (most_common)
    dist_map = {d.value: d for d in field.distributions}
    assert dist_map["positive"].count == 2
    assert dist_map["positive"].percentage == pytest.approx(0.5)
    assert dist_map["negative"].count == 2
    assert dist_map["negative"].percentage == pytest.approx(0.5)


def test_distribution_by_source() -> None:
    service = LabelDistributionService()
    result = service.analyze(
        [
            _record("r1", "human", {"sentiment": "positive"}),
            _record("r2", "human", {"sentiment": "negative"}),
            _record("r3", "agent", {"sentiment": "positive"}),
            _record("r4", "agent", {"sentiment": "positive"}),
            _record("r5", "agent", {"sentiment": "positive"}),
        ]
    )

    assert "human" in result.by_source
    assert "agent" in result.by_source

    human_field = result.by_source["human"]["sentiment"]
    assert human_field.total_labels == 2
    human_map = {d.value: d for d in human_field.distributions}
    assert human_map["positive"].count == 1
    assert human_map["negative"].count == 1

    agent_field = result.by_source["agent"]["sentiment"]
    assert agent_field.total_labels == 3
    agent_map = {d.value: d for d in agent_field.distributions}
    assert agent_map["positive"].count == 3
    assert agent_map["positive"].percentage == pytest.approx(1.0)


def test_source_filter() -> None:
    service = LabelDistributionService()
    result = service.analyze(
        [
            _record("r1", "human", {"sentiment": "positive"}),
            _record("r2", "agent", {"sentiment": "negative"}),
        ],
        source_filter="human",
    )

    assert result.total_records == 1
    assert result.fields["sentiment"].total_labels == 1


def test_dataset_filter() -> None:
    service = LabelDistributionService()
    result = service.analyze(
        [
            _record("r1", "human", {"sentiment": "positive"}, dataset_id="ds1"),
            _record("r2", "human", {"sentiment": "negative"}, dataset_id="ds2"),
            _record("r3", "human", {"sentiment": "negative"}, dataset_id="ds1"),
        ],
        dataset_filter="ds1",
    )

    assert result.total_records == 2
    dist_map = {d.value: d for d in result.fields["sentiment"].distributions}
    assert dist_map["positive"].count == 1
    assert dist_map["negative"].count == 1


def test_field_filter() -> None:
    service = LabelDistributionService()
    result = service.analyze(
        [
            _record("r1", "human", {"sentiment": "positive", "tone": "formal"}),
            _record("r2", "human", {"sentiment": "negative", "tone": "informal"}),
        ],
        fields=["sentiment"],
    )

    assert "sentiment" in result.fields
    assert "tone" not in result.fields


def test_empty_input() -> None:
    service = LabelDistributionService()
    result = service.analyze([])

    assert result.total_records == 0
    assert len(result.fields) == 0
    assert len(result.warnings) > 0


def test_entropy_uniform_distribution() -> None:
    service = LabelDistributionService()
    result = service.analyze(
        [
            _record("r1", "human", {"color": "red"}),
            _record("r2", "human", {"color": "green"}),
            _record("r3", "human", {"color": "blue"}),
            _record("r4", "human", {"color": "yellow"}),
        ]
    )

    # Uniform distribution of 4 items: entropy = log2(4) = 2.0
    assert result.fields["color"].entropy == pytest.approx(math.log2(4))


def test_entropy_single_value() -> None:
    service = LabelDistributionService()
    result = service.analyze(
        [
            _record("r1", "human", {"color": "red"}),
            _record("r2", "human", {"color": "red"}),
            _record("r3", "human", {"color": "red"}),
        ]
    )

    # All same value: entropy = 0
    assert result.fields["color"].entropy == pytest.approx(0.0)


def test_dict_input_normalization() -> None:
    service = LabelDistributionService()
    result = service.analyze(
        [
            {"record_id": "r1", "source": "human", "labels": {"sentiment": "positive"}},
            {"record_id": "r2", "source": "agent", "labels": {"sentiment": "negative"}},
        ]
    )

    assert result.total_records == 2
    assert result.fields["sentiment"].total_labels == 2


def test_multiple_fields_discovered() -> None:
    service = LabelDistributionService()
    result = service.analyze(
        [
            _record("r1", "human", {"sentiment": "positive", "tone": "formal"}),
            _record("r2", "human", {"sentiment": "negative"}),
        ]
    )

    assert "sentiment" in result.fields
    assert "tone" in result.fields
    assert result.fields["sentiment"].total_labels == 2
    assert result.fields["tone"].total_labels == 1

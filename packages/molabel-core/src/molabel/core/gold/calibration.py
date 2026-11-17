"""Score each reviewer of a calibration queue against a gold set.

Gold is a second rater. For each reviewer, every gold item the reviewer
answered is a unit with two values per field: the reviewer's and the gold
label. ``AgreementMetricsService`` gives ``percent_agreement``, reported as
``accuracy``, and Cohen's kappa. A field the reviewer left empty where gold
has a label is counted as ``missing``, not compared.
``docs/architecture/gold-sets.md`` explains the choice of kappa.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from pydantic import BaseModel, Field

from molabel.core.gold.model import GoldItem
from molabel.core.quality.agreement_metrics import (
    AgreementAnnotation,
    AgreementMetricsService,
    AgreementMetricSummary,
    AgreementRecord,
)
from molabel.core.quality.review_agreement import (
    ReviewEventLabels,
    counted_review_events,
    rated_labels,
)
from molabel.core.utils.canonical import canonical_label_value

GOLD_RATER = "gold"


@dataclass(frozen=True)
class CalibrationItems:
    """The records of a workspace that a gold set's items point to."""

    gold_set: str
    version: int
    content_hash: str
    task_schema: str
    record_ids: list[str]
    unresolved: list[str]
    """Items whose record this workspace does not hold, by item id."""


class GoldFieldScore(BaseModel):
    """A reviewer against gold on one field, or pooled over every field."""

    accuracy: float | None = None
    cohen_kappa: float | None = None
    compared: int = 0
    missing: int = 0
    null_reasons: dict[str, str] = Field(default_factory=dict)


class ReviewerGoldScore(BaseModel):
    """One reviewer's calibration result."""

    reviewer_id: str
    items_answered: int
    exact_match: float | None = Field(
        default=None,
        description="Share of answered items where every gold field matches",
    )
    pooled: GoldFieldScore
    fields: dict[str, GoldFieldScore] = Field(default_factory=dict)


def _score(summary: AgreementMetricSummary, missing: int) -> GoldFieldScore:
    return GoldFieldScore(
        accuracy=summary.percent_agreement,
        cohen_kappa=summary.cohen_kappa,
        compared=summary.comparisons,
        missing=missing,
        null_reasons={
            name: reason
            for name, reason in summary.null_reasons.items()
            if name in ("percent_agreement", "cohen_kappa")
        },
    )


def score_against_gold(
    gold_by_record: Mapping[str, GoldItem],
    events: Iterable[ReviewEventLabels],
    fields: Sequence[str],
) -> list[ReviewerGoldScore]:
    """Score every reviewer with a counted answer on a gold record, by reviewer id."""
    answers: dict[str, list[tuple[GoldItem, dict]]] = defaultdict(list)
    for event in counted_review_events(events):
        item = gold_by_record.get(event.record_id)
        labels = rated_labels(event)
        if item is not None and labels is not None:
            answers[event.reviewer_id].append((item, labels))

    service = AgreementMetricsService()
    scores = []
    for reviewer_id, answered in sorted(answers.items()):
        records = [
            AgreementRecord(
                record_id=item.item_id,
                annotations=[
                    AgreementAnnotation(
                        source="human", rater_id=reviewer_id, labels=labels
                    ),
                    AgreementAnnotation(
                        source="import", rater_id=GOLD_RATER, labels=item.expected
                    ),
                ],
            )
            for item, labels in answered
        ]
        result = service.analyze(
            records, analysis_type="inter_annotator", fields=fields
        )
        missing = {
            name: sum(
                1
                for item, labels in answered
                if name in item.expected and labels.get(name) is None
            )
            for name in fields
        }
        exact = sum(
            all(
                canonical_label_value(labels.get(name)) == canonical_label_value(value)
                for name, value in item.expected.items()
            )
            for item, labels in answered
        )
        scores.append(
            ReviewerGoldScore(
                reviewer_id=reviewer_id,
                items_answered=len(answered),
                exact_match=exact / len(answered),
                pooled=_score(result.overall, sum(missing.values())),
                fields={
                    name: _score(summary, missing[name])
                    for name, summary in result.fields.items()
                },
            )
        )
    return scores

"""Dataset operations: clustering, disagreement mining, edge-case mining,
challenge-set curation (DT-019).

Provides analytical services for dataset exploration and quality improvement.
DuckDB and Polars are optional dependencies for analytical scans.
"""

from __future__ import annotations

import logging
import uuid
from collections import Counter, defaultdict
from typing import Any

from pydantic import BaseModel

from molabel.core.database import get_session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public result types
# ---------------------------------------------------------------------------


class ClusterResult(BaseModel):
    """Result of a clustering operation."""

    cluster_id: str
    record_ids: list[uuid.UUID]
    size: int
    centroid_summary: dict[str, Any] | None = None
    label: str = ""


class DisagreementResult(BaseModel):
    """A record with detected label disagreement."""

    record_id: uuid.UUID
    disagreement_type: str  # "inter_annotator" | "human_agent"
    fields_in_conflict: list[str]
    label_values: dict[str, list[Any]]
    severity: str = "medium"


class EdgeCaseResult(BaseModel):
    """A record identified as an edge case."""

    record_id: uuid.UUID
    reason: str
    score: float = 0.0
    details: dict[str, Any] = {}


class ChallengeSetResult(BaseModel):
    """Result of challenge-set curation."""

    name: str
    record_ids: list[uuid.UUID]
    selection_criteria: dict[str, Any]
    size: int


class DatasetOperationsResult(BaseModel):
    """Generic result for dataset operations."""

    operation: str
    records_affected: int = 0
    results: list[dict[str, Any]] = []


# ---------------------------------------------------------------------------
# DatasetOperationsService
# ---------------------------------------------------------------------------


class DatasetOperationsService:
    """Provides dataset analysis and curation operations.

    Supports clustering, disagreement mining, edge-case mining, and
    challenge-set curation. Uses DuckDB+Polars for analytical scans
    when available, with fallback to SQLite queries.
    """

    def find_disagreements(
        self,
        engine: Any,
        *,
        dataset_id: uuid.UUID,
        min_events_per_record: int = 2,
    ) -> list[DisagreementResult]:
        """Find records with label disagreements.

        Scans review events for records that have multiple label sources
        with conflicting values.
        """
        from molabel.core.models.record import Record
        from molabel.core.models.review_event import ReviewEvent

        with get_session(engine) as session:
            from sqlmodel import select

            # Get all records in the dataset.
            record_ids = list(
                session.exec(
                    select(Record.id).where(Record.dataset_id == dataset_id)
                ).all()
            )

            if not record_ids:
                return []

            # Get all review events for these records.
            events = list(
                session.exec(
                    select(ReviewEvent).where(
                        ReviewEvent.record_id.in_(record_ids)  # type: ignore[union-attr]
                    )
                ).all()
            )

        # Group events by record.
        events_by_record: dict[uuid.UUID, list[Any]] = defaultdict(list)
        for event in events:
            events_by_record[event.record_id].append(event)

        disagreements: list[DisagreementResult] = []
        for record_id, record_events in events_by_record.items():
            if len(record_events) < min_events_per_record:
                continue

            # Compare labels across events.
            fields_in_conflict: list[str] = []
            label_values: dict[str, list[Any]] = defaultdict(list)

            for event in record_events:
                for field, value in (event.labels or {}).items():
                    label_values[field].append(value)

            for field, values in label_values.items():
                unique_values = set(str(v) for v in values)
                if len(unique_values) > 1:
                    fields_in_conflict.append(field)

            if fields_in_conflict:
                # Determine disagreement type.
                sources = {str(e.source) for e in record_events}
                if "agent" in sources and "human" in sources:
                    dtype = "human_agent"
                else:
                    dtype = "inter_annotator"

                disagreements.append(
                    DisagreementResult(
                        record_id=record_id,
                        disagreement_type=dtype,
                        fields_in_conflict=fields_in_conflict,
                        label_values={k: v for k, v in label_values.items()},
                        severity=self._compute_severity(
                            fields_in_conflict, label_values
                        ),
                    )
                )

        return disagreements

    def find_edge_cases(
        self,
        engine: Any,
        *,
        dataset_id: uuid.UUID,
        confidence_threshold: float = 0.3,
        max_results: int = 100,
    ) -> list[EdgeCaseResult]:
        """Find records that are likely edge cases.

        Identifies records with low confidence, high disagreement, or
        unusual patterns.
        """
        from molabel.core.models.record import Record

        with get_session(engine) as session:
            from sqlmodel import select

            # Low confidence records.
            stmt = (
                select(Record)
                .where(
                    Record.dataset_id == dataset_id,
                    Record.composite_confidence != None,  # noqa: E711
                    Record.composite_confidence < confidence_threshold,
                )
                .order_by(Record.composite_confidence)
                .limit(max_results)
            )
            low_confidence = list(session.exec(stmt).all())

        edge_cases: list[EdgeCaseResult] = []
        for record in low_confidence:
            edge_cases.append(
                EdgeCaseResult(
                    record_id=record.id,
                    reason="low_confidence",
                    score=1.0 - (record.composite_confidence or 0.0),
                    details={
                        "confidence": record.composite_confidence,
                        "threshold": confidence_threshold,
                    },
                )
            )

        # Also check for disagreements.
        disagreements = self.find_disagreements(engine, dataset_id=dataset_id)
        for d in disagreements[:max_results]:
            if d.record_id not in {ec.record_id for ec in edge_cases}:
                edge_cases.append(
                    EdgeCaseResult(
                        record_id=d.record_id,
                        reason="disagreement",
                        score=0.8 if d.severity == "high" else 0.5,
                        details={
                            "disagreement_type": d.disagreement_type,
                            "fields": d.fields_in_conflict,
                        },
                    )
                )

        # Sort by score descending and limit.
        edge_cases.sort(key=lambda x: x.score, reverse=True)
        return edge_cases[:max_results]

    def cluster_records(
        self,
        engine: Any,
        *,
        dataset_id: uuid.UUID,
        field: str,
        n_clusters: int = 5,
    ) -> list[ClusterResult]:
        """Cluster records by label distribution on a field.

        Groups records by their label value for the given field. This
        provides a simple value-based clustering that does not require
        embedding models.
        """
        from molabel.core.models.record import Record
        from molabel.core.models.review_event import ReviewEvent

        with get_session(engine) as session:
            from sqlmodel import select

            record_ids = list(
                session.exec(
                    select(Record.id).where(Record.dataset_id == dataset_id)
                ).all()
            )

            if not record_ids:
                return []

            events = list(
                session.exec(
                    select(ReviewEvent).where(
                        ReviewEvent.record_id.in_(record_ids)  # type: ignore[union-attr]
                    )
                ).all()
            )

        # Group by field value.
        clusters: dict[str, list[uuid.UUID]] = defaultdict(list)
        for event in events:
            labels = event.labels or {}
            if field in labels:
                value = str(labels[field])
                clusters[value].append(event.record_id)

        # Deduplicate record_ids within each cluster.
        results: list[ClusterResult] = []
        for i, (value, rids) in enumerate(
            sorted(clusters.items(), key=lambda x: -len(x[1]))
        ):
            unique_ids = list(dict.fromkeys(rids))
            results.append(
                ClusterResult(
                    cluster_id=f"cluster_{i}",
                    record_ids=unique_ids,
                    size=len(unique_ids),
                    label=value,
                    centroid_summary={"field": field, "value": value},
                )
            )
            if len(results) >= n_clusters:
                break

        return results

    def curate_challenge_set(
        self,
        engine: Any,
        *,
        dataset_id: uuid.UUID,
        name: str = "challenge_set",
        criteria: dict[str, Any] | None = None,
        max_size: int = 100,
    ) -> ChallengeSetResult:
        """Curate a challenge set from difficult records.

        Combines edge cases, disagreements, and low-confidence records
        into a curated challenge set for targeted review.
        """
        criteria = criteria or {}

        # Gather candidates from edge cases.
        edge_cases = self.find_edge_cases(
            engine,
            dataset_id=dataset_id,
            confidence_threshold=criteria.get("confidence_threshold", 0.5),
            max_results=max_size,
        )

        record_ids = [ec.record_id for ec in edge_cases]

        # Deduplicate.
        seen: set[uuid.UUID] = set()
        unique_ids: list[uuid.UUID] = []
        for rid in record_ids:
            if rid not in seen:
                seen.add(rid)
                unique_ids.append(rid)

        final_ids = unique_ids[:max_size]

        return ChallengeSetResult(
            name=name,
            record_ids=final_ids,
            selection_criteria=criteria,
            size=len(final_ids),
        )

    def compute_label_distribution(
        self,
        engine: Any,
        *,
        dataset_id: uuid.UUID,
        field: str,
    ) -> dict[str, int]:
        """Compute label value distribution for a field across a dataset."""
        from molabel.core.models.record import Record
        from molabel.core.models.review_event import ReviewEvent

        with get_session(engine) as session:
            from sqlmodel import select

            record_ids = list(
                session.exec(
                    select(Record.id).where(Record.dataset_id == dataset_id)
                ).all()
            )

            if not record_ids:
                return {}

            events = list(
                session.exec(
                    select(ReviewEvent).where(
                        ReviewEvent.record_id.in_(record_ids)  # type: ignore[union-attr]
                    )
                ).all()
            )

        counter: Counter[str] = Counter()
        for event in events:
            labels = event.labels or {}
            if field in labels:
                value = labels[field]
                if isinstance(value, list):
                    for v in value:
                        counter[str(v)] += 1
                else:
                    counter[str(value)] += 1

        return dict(counter)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_severity(
        fields: list[str],
        label_values: dict[str, list[Any]],
    ) -> str:
        """Compute disagreement severity based on field count and diversity."""
        if len(fields) >= 3:
            return "high"
        for field in fields:
            values = label_values.get(field, [])
            unique = set(str(v) for v in values)
            if len(unique) >= 3:
                return "high"
        if len(fields) >= 2:
            return "medium"
        return "low"

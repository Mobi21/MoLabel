"""Adjudication service (AJ-001 through AJ-005, AJ-007).

Detects disagreements between reviewers, builds an adjudication queue
with severity/type classification, supports resolution workflows, and
produces audit-trail review events.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from molabel.core.types import AdjudicationResolution, ReviewEventSource

# ---------------------------------------------------------------------------
# AJ-001: Disagreement detection
# ---------------------------------------------------------------------------


class DisagreementType(StrEnum):
    """Type of disagreement between reviewers."""

    human_human = "human_human"
    human_agent = "human_agent"


@dataclass(frozen=True)
class Disagreement:
    """A detected disagreement on a single record."""

    record_id: uuid.UUID
    task_schema_id: uuid.UUID
    conflicting_event_ids: list[uuid.UUID]
    disagreement_type: DisagreementType
    fields_in_conflict: list[str]
    reviewer_labels: dict[str, dict[str, Any]] = field(default_factory=dict)
    """Maps reviewer_id (or 'agent') -> their labels for the conflicting fields."""


# ---------------------------------------------------------------------------
# AJ-002: Adjudication queue with severity/type
# ---------------------------------------------------------------------------


class AdjudicationSeverity(StrEnum):
    """Severity level of a disagreement."""

    low = "low"
    medium = "medium"
    high = "high"


class AdjudicationType(StrEnum):
    """Classification of the disagreement type."""

    factual = "factual"
    subjective = "subjective"
    edge_case = "edge_case"
    policy_gap = "policy_gap"


@dataclass
class AdjudicationQueueItem:
    """An item in the adjudication queue."""

    id: uuid.UUID
    record_id: uuid.UUID
    task_schema_id: uuid.UUID
    disagreement: Disagreement
    severity: AdjudicationSeverity = AdjudicationSeverity.medium
    adjudication_type: AdjudicationType = AdjudicationType.factual
    created_at: str = ""
    resolved: bool = False


# ---------------------------------------------------------------------------
# AJ-003: Adjudication resolutions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolvedLabels:
    """Final labels produced by an adjudication resolution."""

    labels: dict[str, Any]
    source_event_ids: list[uuid.UUID]
    """Event IDs that were considered in producing the resolved labels."""


@dataclass(frozen=True)
class ResolutionResult:
    """Result of applying an adjudication resolution."""

    adjudication_id: uuid.UUID
    record_id: uuid.UUID
    resolution: AdjudicationResolution
    resolved_labels: ResolvedLabels | None
    rationale: str | None = None
    review_event_id: uuid.UUID | None = None
    """ID of the review event created for the audit trail (AJ-007)."""


# ---------------------------------------------------------------------------
# AJ-004: Side-by-side comparison data
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceLabel:
    """A label value from a specific source."""

    source_id: str
    """Reviewer ID or 'agent'."""

    source_type: str
    """'human' or 'agent'."""

    event_id: uuid.UUID
    value: Any


@dataclass(frozen=True)
class FieldComparison:
    """Per-field comparison showing each source's label."""

    field_name: str
    sources: list[SourceLabel]
    is_in_conflict: bool


@dataclass(frozen=True)
class ComparisonPanel:
    """Structured data for side-by-side reviewer comparison."""

    record_id: uuid.UUID
    task_schema_id: uuid.UUID
    field_comparisons: list[FieldComparison]
    event_ids: list[uuid.UUID]


# ---------------------------------------------------------------------------
# AJ-005: Policy context
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PolicyExcerpt:
    """A policy excerpt relevant to a disagreement."""

    section_id: str
    title: str
    content: str
    relevance_score: float = 0.0


@dataclass(frozen=True)
class PolicyContext:
    """Policy excerpts attached to a disagreement for adjudicator reference."""

    record_id: uuid.UUID
    field_name: str
    excerpts: list[PolicyExcerpt]


# ---------------------------------------------------------------------------
# Review event data structure (AJ-007)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AdjudicationReviewEvent:
    """Data for a review event created from an adjudication resolution.

    Follows the existing ReviewEvent model patterns but is created as a
    result of adjudication rather than direct review.
    """

    id: uuid.UUID
    record_id: uuid.UUID
    task_schema_id: uuid.UUID
    task_schema_version: int
    adjudicator_id: uuid.UUID
    source: str
    labels: dict[str, Any]
    rationale: str | None = None
    adjudication_id: uuid.UUID | None = None
    conflicting_event_ids: list[uuid.UUID] = field(default_factory=list)
    created_at: str = ""
    workspace_id: uuid.UUID | None = None


# ---------------------------------------------------------------------------
# AdjudicationService
# ---------------------------------------------------------------------------


class AdjudicationService:
    """Service for detecting, queuing, and resolving disagreements.

    Pure computation service that operates on in-memory data. The caller
    is responsible for persistence.
    """

    def __init__(self) -> None:
        self._queue: list[AdjudicationQueueItem] = []
        self._resolutions: dict[uuid.UUID, ResolutionResult] = {}
        self._policy_sections: list[dict[str, Any]] = []

    # ----- AJ-001: Disagreement detection -----

    def detect_disagreements(
        self,
        review_events_by_record: dict[str, list[dict[str, Any]]],
        task_schema_id: uuid.UUID,
    ) -> list[Disagreement]:
        """Compare review events for overlapping records and detect disagreements.

        Detects both human-human and human-agent disagreements at the
        field level.

        Parameters
        ----------
        review_events_by_record:
            Mapping of record_id (str) -> list of review event dicts.
            Each event dict must have keys: ``id``, ``reviewer_id``,
            ``source``, ``labels``.
        task_schema_id:
            The task schema these events belong to.
        """
        disagreements: list[Disagreement] = []

        for record_id_str, events in review_events_by_record.items():
            if len(events) < 2:
                continue

            record_id = uuid.UUID(record_id_str)

            human_events = [e for e in events if e.get("source") in ("human", "import")]
            agent_events = [e for e in events if e.get("source") == "agent"]

            # Detect human-human disagreements
            if len(human_events) >= 2:
                hh_disagreement = self._detect_pairwise_disagreements(
                    record_id=record_id,
                    task_schema_id=task_schema_id,
                    events=human_events,
                    disagreement_type=DisagreementType.human_human,
                )
                if hh_disagreement is not None:
                    disagreements.append(hh_disagreement)

            # Detect human-agent disagreements
            if human_events and agent_events:
                ha_disagreement = self._detect_cross_source_disagreements(
                    record_id=record_id,
                    task_schema_id=task_schema_id,
                    human_events=human_events,
                    agent_events=agent_events,
                )
                if ha_disagreement is not None:
                    disagreements.append(ha_disagreement)

        return disagreements

    def _detect_pairwise_disagreements(
        self,
        record_id: uuid.UUID,
        task_schema_id: uuid.UUID,
        events: list[dict[str, Any]],
        disagreement_type: DisagreementType,
    ) -> Disagreement | None:
        """Detect field-level disagreements among a group of events."""
        all_fields: set[str] = set()
        for event in events:
            all_fields.update(event.get("labels", {}).keys())

        fields_in_conflict: list[str] = []
        for field_name in sorted(all_fields):
            values = set()
            for event in events:
                labels = event.get("labels", {})
                if field_name in labels:
                    val = labels[field_name]
                    values.add(_hashable_value(val))
            if len(values) > 1:
                fields_in_conflict.append(field_name)

        if not fields_in_conflict:
            return None

        event_ids = [uuid.UUID(str(e["id"])) for e in events]
        reviewer_labels: dict[str, dict[str, Any]] = {}
        for event in events:
            key = str(event.get("reviewer_id", "unknown"))
            reviewer_labels[key] = {
                f: event.get("labels", {}).get(f)
                for f in fields_in_conflict
                if f in event.get("labels", {})
            }

        return Disagreement(
            record_id=record_id,
            task_schema_id=task_schema_id,
            conflicting_event_ids=event_ids,
            disagreement_type=disagreement_type,
            fields_in_conflict=fields_in_conflict,
            reviewer_labels=reviewer_labels,
        )

    def _detect_cross_source_disagreements(
        self,
        record_id: uuid.UUID,
        task_schema_id: uuid.UUID,
        human_events: list[dict[str, Any]],
        agent_events: list[dict[str, Any]],
    ) -> Disagreement | None:
        """Detect disagreements between human and agent events."""
        all_events = human_events + agent_events
        all_fields: set[str] = set()
        for event in all_events:
            all_fields.update(event.get("labels", {}).keys())

        fields_in_conflict: list[str] = []
        for field_name in sorted(all_fields):
            human_values = set()
            agent_values = set()
            for event in human_events:
                labels = event.get("labels", {})
                if field_name in labels:
                    human_values.add(_hashable_value(labels[field_name]))
            for event in agent_events:
                labels = event.get("labels", {})
                if field_name in labels:
                    agent_values.add(_hashable_value(labels[field_name]))
            if human_values and agent_values and human_values != agent_values:
                fields_in_conflict.append(field_name)

        if not fields_in_conflict:
            return None

        event_ids = [uuid.UUID(str(e["id"])) for e in all_events]
        reviewer_labels: dict[str, dict[str, Any]] = {}
        for event in human_events:
            key = str(event.get("reviewer_id", "unknown"))
            reviewer_labels[key] = {
                f: event.get("labels", {}).get(f)
                for f in fields_in_conflict
                if f in event.get("labels", {})
            }
        # Combine agent labels under "agent" key
        for event in agent_events:
            reviewer_labels["agent"] = {
                f: event.get("labels", {}).get(f)
                for f in fields_in_conflict
                if f in event.get("labels", {})
            }

        return Disagreement(
            record_id=record_id,
            task_schema_id=task_schema_id,
            conflicting_event_ids=event_ids,
            disagreement_type=DisagreementType.human_agent,
            fields_in_conflict=fields_in_conflict,
            reviewer_labels=reviewer_labels,
        )

    # ----- AJ-002: Adjudication queue with severity -----

    def build_queue(
        self,
        disagreements: list[Disagreement],
    ) -> list[AdjudicationQueueItem]:
        """Build an adjudication queue from detected disagreements.

        Classifies each disagreement by severity and type.
        """
        items: list[AdjudicationQueueItem] = []
        now = datetime.now(UTC).isoformat()

        for disagreement in disagreements:
            severity = self._classify_severity(disagreement)
            adj_type = self._classify_type(disagreement)

            item = AdjudicationQueueItem(
                id=uuid.uuid4(),
                record_id=disagreement.record_id,
                task_schema_id=disagreement.task_schema_id,
                disagreement=disagreement,
                severity=severity,
                adjudication_type=adj_type,
                created_at=now,
            )
            items.append(item)

        # Sort by severity (high first), then by creation time
        severity_order = {
            AdjudicationSeverity.high: 0,
            AdjudicationSeverity.medium: 1,
            AdjudicationSeverity.low: 2,
        }
        items.sort(key=lambda i: (severity_order[i.severity], i.created_at))

        self._queue = items
        return items

    def _classify_severity(self, disagreement: Disagreement) -> AdjudicationSeverity:
        """Classify the severity of a disagreement.

        - high: All fields disagree or major label contradictions
        - medium: Some fields disagree
        - low: Minor/single field disagreement
        """
        conflicting_count = len(disagreement.fields_in_conflict)

        if conflicting_count == 0:
            return AdjudicationSeverity.low

        # Check for contradictory labels (e.g., positive vs negative)
        has_contradiction = self._has_contradictory_values(disagreement)
        if has_contradiction:
            return AdjudicationSeverity.high

        if conflicting_count >= 3:
            return AdjudicationSeverity.high

        if conflicting_count >= 2:
            return AdjudicationSeverity.medium

        return AdjudicationSeverity.low

    def _has_contradictory_values(self, disagreement: Disagreement) -> bool:
        """Check if reviewers gave contradictory labels (not just different)."""
        contradictory_pairs = {
            frozenset({"positive", "negative"}),
            frozenset({"true", "false"}),
            frozenset({"yes", "no"}),
            frozenset({"accept", "reject"}),
            frozenset({"agree", "disagree"}),
        }

        for field_name in disagreement.fields_in_conflict:
            field_values: set[str] = set()
            for labels in disagreement.reviewer_labels.values():
                val = labels.get(field_name)
                if val is not None:
                    field_values.add(str(val).lower().strip())
            for pair in contradictory_pairs:
                if pair.issubset(field_values):
                    return True
        return False

    def _classify_type(self, disagreement: Disagreement) -> AdjudicationType:
        """Classify the type of a disagreement.

        Uses heuristics based on the disagreement characteristics:
        - human_agent disagreements are often edge_case
        - Multi-reviewer human disagreements with many fields are policy_gap
        - Otherwise defaults to factual
        """
        if disagreement.disagreement_type == DisagreementType.human_agent:
            return AdjudicationType.edge_case

        num_reviewers = len(disagreement.reviewer_labels)
        num_fields = len(disagreement.fields_in_conflict)

        if num_reviewers > 2 and num_fields > 2:
            return AdjudicationType.policy_gap

        if num_fields == 1:
            return AdjudicationType.subjective

        return AdjudicationType.factual

    def get_queue(self) -> list[AdjudicationQueueItem]:
        """Return the current adjudication queue."""
        return list(self._queue)

    def get_unresolved_queue(self) -> list[AdjudicationQueueItem]:
        """Return only unresolved items from the queue."""
        return [item for item in self._queue if not item.resolved]

    # ----- AJ-003: Adjudication resolutions -----

    def resolve(
        self,
        queue_item_id: uuid.UUID,
        adjudicator_id: uuid.UUID,
        resolution: AdjudicationResolution,
        resolved_labels: dict[str, Any] | None = None,
        rationale: str | None = None,
        task_schema_version: int = 1,
        workspace_id: uuid.UUID | None = None,
    ) -> ResolutionResult:
        """Apply a resolution to an adjudication queue item.

        Supports resolution types from AdjudicationResolution enum:
        - preserve_disagreement: Keep all labels as-is
        - resolve: Accept specific labels as the resolution
        - downgrade: Mark the record for re-review
        - exclude: Exclude the record from the dataset

        Also creates a review event for the audit trail (AJ-007).
        """
        # Find the queue item
        queue_item: AdjudicationQueueItem | None = None
        for item in self._queue:
            if item.id == queue_item_id:
                queue_item = item
                break

        if queue_item is None:
            msg = f"Queue item {queue_item_id} not found"
            raise ValueError(msg)

        adjudication_id = uuid.uuid4()
        review_event_id: uuid.UUID | None = None
        resolved_labels_obj: ResolvedLabels | None = None

        if resolution == AdjudicationResolution.resolve and resolved_labels is not None:
            resolved_labels_obj = ResolvedLabels(
                labels=resolved_labels,
                source_event_ids=list(queue_item.disagreement.conflicting_event_ids),
            )

            # AJ-007: Create a review event for the audit trail
            review_event_id = uuid.uuid4()
            self._create_adjudication_event(
                event_id=review_event_id,
                queue_item=queue_item,
                adjudicator_id=adjudicator_id,
                adjudication_id=adjudication_id,
                labels=resolved_labels,
                rationale=rationale,
                task_schema_version=task_schema_version,
                workspace_id=workspace_id,
            )
        elif resolution == AdjudicationResolution.preserve_disagreement:
            resolved_labels_obj = None
        elif resolution == AdjudicationResolution.exclude:
            resolved_labels_obj = ResolvedLabels(
                labels={},
                source_event_ids=list(queue_item.disagreement.conflicting_event_ids),
            )

        queue_item.resolved = True

        result = ResolutionResult(
            adjudication_id=adjudication_id,
            record_id=queue_item.record_id,
            resolution=resolution,
            resolved_labels=resolved_labels_obj,
            rationale=rationale,
            review_event_id=review_event_id,
        )
        self._resolutions[adjudication_id] = result
        return result

    def _create_adjudication_event(
        self,
        event_id: uuid.UUID,
        queue_item: AdjudicationQueueItem,
        adjudicator_id: uuid.UUID,
        adjudication_id: uuid.UUID,
        labels: dict[str, Any],
        rationale: str | None,
        task_schema_version: int,
        workspace_id: uuid.UUID | None,
    ) -> AdjudicationReviewEvent:
        """Create a review event from an adjudication resolution (AJ-007).

        The event is append-only: it never modifies existing events.
        """
        now = datetime.now(UTC).isoformat()
        event = AdjudicationReviewEvent(
            id=event_id,
            record_id=queue_item.record_id,
            task_schema_id=queue_item.task_schema_id,
            task_schema_version=task_schema_version,
            adjudicator_id=adjudicator_id,
            source=ReviewEventSource.human.value,
            labels=labels,
            rationale=rationale,
            adjudication_id=adjudication_id,
            conflicting_event_ids=list(queue_item.disagreement.conflicting_event_ids),
            created_at=now,
            workspace_id=workspace_id,
        )
        return event

    def get_resolution(self, adjudication_id: uuid.UUID) -> ResolutionResult | None:
        """Look up a resolution by adjudication ID."""
        return self._resolutions.get(adjudication_id)

    # ----- AJ-004: Side-by-side comparison data -----

    def build_comparison(
        self,
        disagreement: Disagreement,
        events: list[dict[str, Any]],
    ) -> ComparisonPanel:
        """Structure data for side-by-side reviewer comparison.

        Builds per-field alignment showing each source's label value.
        """
        # Collect all field names from all events
        all_fields: set[str] = set()
        for event in events:
            all_fields.update(event.get("labels", {}).keys())

        # Build event lookup by ID
        event_by_id: dict[str, dict[str, Any]] = {}
        for event in events:
            event_by_id[str(event["id"])] = event

        field_comparisons: list[FieldComparison] = []
        for field_name in sorted(all_fields):
            sources: list[SourceLabel] = []
            for event in events:
                labels = event.get("labels", {})
                if field_name not in labels:
                    continue
                source_type = "agent" if event.get("source") == "agent" else "human"
                source_id = (
                    "agent"
                    if source_type == "agent"
                    else str(event.get("reviewer_id", "unknown"))
                )
                sources.append(
                    SourceLabel(
                        source_id=source_id,
                        source_type=source_type,
                        event_id=uuid.UUID(str(event["id"])),
                        value=labels[field_name],
                    )
                )

            is_in_conflict = field_name in disagreement.fields_in_conflict
            field_comparisons.append(
                FieldComparison(
                    field_name=field_name,
                    sources=sources,
                    is_in_conflict=is_in_conflict,
                )
            )

        return ComparisonPanel(
            record_id=disagreement.record_id,
            task_schema_id=disagreement.task_schema_id,
            field_comparisons=field_comparisons,
            event_ids=[uuid.UUID(str(e["id"])) for e in events],
        )

    # ----- AJ-005: Policy context -----

    def set_policy_sections(self, sections: list[dict[str, Any]]) -> None:
        """Set available policy sections for context matching.

        Each section should have keys: ``section_id``, ``title``,
        ``content``, and optionally ``keywords`` (list of strings).
        """
        self._policy_sections = list(sections)

    def get_policy_context(
        self,
        disagreement: Disagreement,
    ) -> list[PolicyContext]:
        """Attach policy excerpts relevant to the disagreement.

        Matches disagreement fields and values against policy section
        keywords to surface relevant guidelines.
        """
        contexts: list[PolicyContext] = []

        for field_name in disagreement.fields_in_conflict:
            matching_excerpts = self._match_policy_sections(
                field_name=field_name,
                disagreement=disagreement,
            )
            if matching_excerpts:
                contexts.append(
                    PolicyContext(
                        record_id=disagreement.record_id,
                        field_name=field_name,
                        excerpts=matching_excerpts,
                    )
                )

        return contexts

    def _match_policy_sections(
        self,
        field_name: str,
        disagreement: Disagreement,
    ) -> list[PolicyExcerpt]:
        """Match policy sections to a disagreement field."""
        excerpts: list[PolicyExcerpt] = []

        # Collect all values for this field across reviewers
        field_values: set[str] = set()
        for labels in disagreement.reviewer_labels.values():
            val = labels.get(field_name)
            if val is not None:
                field_values.add(str(val).lower())

        search_terms = {field_name.lower()} | field_values

        for section in self._policy_sections:
            keywords = {k.lower() for k in section.get("keywords", [])}
            title_lower = section.get("title", "").lower()
            content_lower = section.get("content", "").lower()

            # Score based on keyword matches and content matches
            score = 0.0
            for term in search_terms:
                if term in keywords:
                    score += 1.0
                if term in title_lower:
                    score += 0.5
                if term in content_lower:
                    score += 0.25

            if score > 0:
                excerpts.append(
                    PolicyExcerpt(
                        section_id=section.get("section_id", ""),
                        title=section.get("title", ""),
                        content=section.get("content", ""),
                        relevance_score=score,
                    )
                )

        # Sort by relevance score descending
        excerpts.sort(key=lambda e: -e.relevance_score)
        return excerpts


def _hashable_value(val: Any) -> Any:
    """Convert a value to a hashable form for set comparison.

    Recursively handles nested dicts and lists.
    """
    if isinstance(val, dict):
        return tuple(sorted((k, _hashable_value(v)) for k, v in val.items()))
    if isinstance(val, list):
        return tuple(_hashable_value(v) for v in val)
    return val

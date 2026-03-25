"""Agent feedback loop (AG-009 to AG-012).

Correction analysis, prompt refinement, and retry logic.

Manages the full feedback cycle:
- AG-009: Accumulate corrections and extract patterns for prompt refinement
- AG-010: Present refinements for human review (accept/modify/reject)
- AG-011: Correction batch lifecycle state machine
- AG-012: Error handling with retry queue and disk persistence
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from molabel.core.types import CorrectionBatchStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# AG-009: Correction patterns and refinement suggestions
# ---------------------------------------------------------------------------


@dataclass
class Correction:
    """A single human correction of an agent label."""

    record_id: str
    field_name: str
    agent_label: Any = None
    human_label: Any = None
    rationale: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class CorrectionPattern:
    """A detected pattern in corrections indicating systematic agent error."""

    pattern_type: str  # e.g. "systematic_bias", "boundary_confusion", "missing_context"
    description: str
    affected_field: str = ""
    frequency: int = 0
    confidence: float = 0.0
    examples: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RefinementSuggestion:
    """A suggested prompt refinement derived from correction patterns."""

    suggestion_id: UUID = field(default_factory=uuid4)
    pattern: CorrectionPattern | None = None
    patch_text: str = ""
    target_layer: str = "patch"
    rationale: str = ""
    estimated_impact: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class CorrectionBatch:
    """A batch of corrections being accumulated for analysis."""

    batch_id: UUID = field(default_factory=uuid4)
    corrections: list[Correction] = field(default_factory=list)
    status: CorrectionBatchStatus = CorrectionBatchStatus.accumulating
    threshold: int = 25
    patterns: list[CorrectionPattern] = field(default_factory=list)
    suggestions: list[RefinementSuggestion] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    analyzed_at: datetime | None = None
    error_message: str | None = None


# ---------------------------------------------------------------------------
# AG-010: Refinement review
# ---------------------------------------------------------------------------


class ReviewDecisionType(StrEnum):
    """Decision types for refinement review."""

    accept = "accept"
    modify = "modify"
    reject = "reject"


@dataclass
class ReviewDecisionOnRefinement:
    """A human decision on a refinement suggestion."""

    suggestion_id: UUID = field(default_factory=uuid4)
    decision: str = ReviewDecisionType.reject
    modified_patch_text: str | None = None
    reviewer_notes: str = ""
    decided_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class RefinementReview:
    """Collection of review decisions on refinement suggestions."""

    batch_id: UUID = field(default_factory=uuid4)
    decisions: list[ReviewDecisionOnRefinement] = field(default_factory=list)
    reviewed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    new_prompt_version: str | None = None


# ---------------------------------------------------------------------------
# AG-011: Correction batch lifecycle state machine
# ---------------------------------------------------------------------------

_VALID_TRANSITIONS: dict[CorrectionBatchStatus, set[CorrectionBatchStatus]] = {
    CorrectionBatchStatus.accumulating: {CorrectionBatchStatus.ready_for_analysis},
    CorrectionBatchStatus.ready_for_analysis: {
        CorrectionBatchStatus.analyzed,
        CorrectionBatchStatus.accumulating,  # reset if analysis fails
    },
    CorrectionBatchStatus.analyzed: {CorrectionBatchStatus.refinements_pending},
    CorrectionBatchStatus.refinements_pending: {
        CorrectionBatchStatus.applied,
        CorrectionBatchStatus.dismissed,
    },
    CorrectionBatchStatus.applied: set(),  # terminal
    CorrectionBatchStatus.dismissed: set(),  # terminal
}


class InvalidStateTransitionError(RuntimeError):
    """Raised when a batch state transition is not valid."""

    def __init__(
        self, current: CorrectionBatchStatus, target: CorrectionBatchStatus
    ) -> None:
        super().__init__(
            f"Invalid transition from '{current}' to '{target}'. "
            f"Valid targets: {_VALID_TRANSITIONS.get(current, set())}"
        )
        self.current = current
        self.target = target


# ---------------------------------------------------------------------------
# AG-012: Error handling and retry
# ---------------------------------------------------------------------------


@dataclass
class FailedBatch:
    """A correction batch that failed during processing."""

    batch_id: UUID = field(default_factory=uuid4)
    error_message: str = ""
    failed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    original_batch: CorrectionBatch | None = None


@dataclass
class RetryRecord:
    """Tracks retry attempts for a failed batch."""

    batch_id: UUID = field(default_factory=uuid4)
    attempt_number: int = 0
    max_attempts: int = 3
    last_error: str = ""
    last_attempt_at: datetime | None = None
    next_retry_at: datetime | None = None
    is_exhausted: bool = False


class FeedbackNotificationType(StrEnum):
    """Types of feedback loop notifications."""

    batch_ready = "batch_ready"
    analysis_complete = "analysis_complete"
    refinements_pending = "refinements_pending"
    refinements_applied = "refinements_applied"
    batch_failed = "batch_failed"
    retry_scheduled = "retry_scheduled"
    retry_exhausted = "retry_exhausted"


@dataclass
class FeedbackNotification:
    """Notification data for feedback loop events."""

    notification_type: str
    batch_id: UUID = field(default_factory=uuid4)
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class FeedbackLoopService:
    """Manage the agent feedback loop lifecycle.

    Orchestrates correction accumulation, pattern extraction, refinement
    suggestion generation, human review, and error handling with retry logic.
    """

    def __init__(
        self,
        *,
        batch_threshold: int = 25,
        max_retry_attempts: int = 3,
        persistence_dir: Path | None = None,
        max_completed_batches: int = 500,
        max_notifications: int = 1000,
    ) -> None:
        self._batch_threshold = max(1, batch_threshold)
        self._max_retry_attempts = max(1, max_retry_attempts)
        self._persistence_dir = persistence_dir
        self._max_completed_batches = max_completed_batches
        self._max_notifications = max_notifications
        self._batches: dict[UUID, CorrectionBatch] = {}
        self._failed_batches: dict[UUID, FailedBatch] = {}
        self._retry_records: dict[UUID, RetryRecord] = {}
        self._notifications: list[FeedbackNotification] = []

    @property
    def batch_threshold(self) -> int:
        """Number of corrections needed to trigger analysis."""
        return self._batch_threshold

    @property
    def notifications(self) -> list[FeedbackNotification]:
        """All notifications emitted by this service."""
        return list(self._notifications)

    # -- AG-009: Correction accumulation and analysis --

    def get_or_create_batch(self, batch_id: UUID | None = None) -> CorrectionBatch:
        """Get an existing accumulating batch or create a new one.

        Parameters
        ----------
        batch_id:
            Optional specific batch ID. If None, returns the first
            accumulating batch or creates a new one.

        Returns
        -------
        CorrectionBatch
            The batch in accumulating state.
        """
        if batch_id and batch_id in self._batches:
            return self._batches[batch_id]

        # Find first accumulating batch
        for batch in self._batches.values():
            if batch.status == CorrectionBatchStatus.accumulating:
                return batch

        # Create new batch
        batch = CorrectionBatch(threshold=self._batch_threshold)
        self._batches[batch.batch_id] = batch
        return batch

    def add_correction(
        self,
        batch_id: UUID | None = None,
        *,
        record_id: str,
        field_name: str,
        agent_label: Any = None,
        human_label: Any = None,
        rationale: str = "",
    ) -> tuple[CorrectionBatch, bool]:
        """Add a correction to a batch.

        Parameters
        ----------
        batch_id:
            Batch to add to (None for auto-selection).
        record_id:
            The record being corrected.
        field_name:
            The label field being corrected.
        agent_label:
            The agent's original label.
        human_label:
            The human's corrected label.
        rationale:
            Why the correction was made.

        Returns
        -------
        tuple[CorrectionBatch, bool]
            The batch and whether it reached the threshold (ready for analysis).
        """
        batch = self.get_or_create_batch(batch_id)

        correction = Correction(
            record_id=record_id,
            field_name=field_name,
            agent_label=agent_label,
            human_label=human_label,
            rationale=rationale,
        )
        batch.corrections.append(correction)

        is_ready = len(batch.corrections) >= batch.threshold
        if is_ready and batch.status == CorrectionBatchStatus.accumulating:
            self._transition(batch, CorrectionBatchStatus.ready_for_analysis)
            self._emit_notification(
                FeedbackNotificationType.batch_ready,
                batch.batch_id,
                f"Batch {batch.batch_id} reached threshold "
                f"({len(batch.corrections)} corrections).",
            )

        return batch, is_ready

    def analyze_batch(self, batch_id: UUID) -> CorrectionBatch:
        """Analyze a batch of corrections to extract patterns and generate suggestions.

        Parameters
        ----------
        batch_id:
            The batch to analyze.

        Returns
        -------
        CorrectionBatch
            The batch with patterns and suggestions populated.

        Raises
        ------
        KeyError
            If the batch does not exist.
        InvalidStateTransitionError
            If the batch is not in ready_for_analysis state.
        """
        batch = self._get_batch(batch_id)

        if batch.status != CorrectionBatchStatus.ready_for_analysis:
            raise InvalidStateTransitionError(
                batch.status, CorrectionBatchStatus.analyzed
            )

        try:
            patterns = self._extract_patterns(batch.corrections)
            suggestions = self._generate_suggestions(patterns)

            batch.patterns = patterns
            batch.suggestions = suggestions
            batch.analyzed_at = datetime.now(UTC)
            self._transition(batch, CorrectionBatchStatus.analyzed)

            if suggestions:
                self._transition(batch, CorrectionBatchStatus.refinements_pending)
                self._emit_notification(
                    FeedbackNotificationType.refinements_pending,
                    batch.batch_id,
                    f"Generated {len(suggestions)} refinement suggestions.",
                    {"suggestion_count": len(suggestions)},
                )
            else:
                self._emit_notification(
                    FeedbackNotificationType.analysis_complete,
                    batch.batch_id,
                    "Analysis complete but no refinement suggestions generated.",
                )

        except Exception as exc:
            batch.error_message = str(exc)
            self._handle_batch_failure(batch, str(exc))
            raise

        return batch

    # -- AG-010: Refinement review --

    def review_refinements(
        self,
        batch_id: UUID,
        decisions: list[ReviewDecisionOnRefinement],
    ) -> RefinementReview:
        """Apply review decisions to a batch's refinement suggestions.

        Parameters
        ----------
        batch_id:
            The batch with refinements to review.
        decisions:
            List of accept/modify/reject decisions.

        Returns
        -------
        RefinementReview
            The review result with applied decisions.
        """
        batch = self._get_batch(batch_id)

        if batch.status != CorrectionBatchStatus.refinements_pending:
            raise InvalidStateTransitionError(
                batch.status, CorrectionBatchStatus.applied
            )

        accepted_patches: list[str] = []
        for decision in decisions:
            if decision.decision == ReviewDecisionType.accept:
                # Find corresponding suggestion
                for suggestion in batch.suggestions:
                    if suggestion.suggestion_id == decision.suggestion_id:
                        accepted_patches.append(suggestion.patch_text)
                        break
            elif (
                decision.decision == ReviewDecisionType.modify
                and decision.modified_patch_text
            ):
                accepted_patches.append(decision.modified_patch_text)

        has_accepted = any(
            d.decision in (ReviewDecisionType.accept, ReviewDecisionType.modify)
            for d in decisions
        )

        # Compute a version hash from accepted patches
        new_version = None
        if accepted_patches:
            combined = "\n".join(accepted_patches)
            new_version = hashlib.sha256(combined.encode()).hexdigest()[:12]

        if has_accepted:
            self._transition(batch, CorrectionBatchStatus.applied)
            self._emit_notification(
                FeedbackNotificationType.refinements_applied,
                batch.batch_id,
                f"Applied {len(accepted_patches)} refinements.",
                {"accepted_count": len(accepted_patches)},
            )
        else:
            self._transition(batch, CorrectionBatchStatus.dismissed)

        review = RefinementReview(
            batch_id=batch_id,
            decisions=decisions,
            new_prompt_version=new_version,
        )
        return review

    def get_pending_suggestions(self, batch_id: UUID) -> list[RefinementSuggestion]:
        """Get all pending refinement suggestions for a batch.

        Parameters
        ----------
        batch_id:
            The batch to query.

        Returns
        -------
        list[RefinementSuggestion]
            Suggestions awaiting review.
        """
        batch = self._get_batch(batch_id)
        if batch.status != CorrectionBatchStatus.refinements_pending:
            return []
        return list(batch.suggestions)

    # -- AG-011: State machine --

    def get_batch_status(self, batch_id: UUID) -> CorrectionBatchStatus:
        """Get the current status of a batch.

        Parameters
        ----------
        batch_id:
            The batch to query.

        Returns
        -------
        CorrectionBatchStatus
            Current status.
        """
        return self._get_batch(batch_id).status

    def get_valid_transitions(
        self, status: CorrectionBatchStatus
    ) -> set[CorrectionBatchStatus]:
        """Get valid target states for a given current state.

        Parameters
        ----------
        status:
            The current batch status.

        Returns
        -------
        set[CorrectionBatchStatus]
            Valid target states.
        """
        return set(_VALID_TRANSITIONS.get(status, set()))

    # -- AG-012: Error handling and retry --

    def get_failed_batches(self) -> list[FailedBatch]:
        """Return all failed batches."""
        return list(self._failed_batches.values())

    def get_retry_record(self, batch_id: UUID) -> RetryRecord | None:
        """Get retry record for a batch, or None."""
        return self._retry_records.get(batch_id)

    def retry_failed_batch(self, batch_id: UUID) -> CorrectionBatch | None:
        """Retry analysis of a failed batch.

        Parameters
        ----------
        batch_id:
            The batch to retry.

        Returns
        -------
        CorrectionBatch or None
            The re-analyzed batch, or None if retries are exhausted.
        """
        retry = self._retry_records.get(batch_id)
        if retry is None:
            retry = RetryRecord(
                batch_id=batch_id,
                max_attempts=self._max_retry_attempts,
            )
            self._retry_records[batch_id] = retry

        if retry.is_exhausted:
            self._emit_notification(
                FeedbackNotificationType.retry_exhausted,
                batch_id,
                f"Batch {batch_id} exhausted all {retry.max_attempts} retry attempts.",
            )
            return None

        retry.attempt_number += 1
        retry.last_attempt_at = datetime.now(UTC)

        if retry.attempt_number >= retry.max_attempts:
            retry.is_exhausted = True

        # Reset batch to ready_for_analysis
        batch = self._batches.get(batch_id)
        if batch is None:
            # Recover from failed batch
            failed = self._failed_batches.get(batch_id)
            if failed and failed.original_batch:
                batch = failed.original_batch
                self._batches[batch_id] = batch
            else:
                retry.last_error = "Batch data not found"
                return None

        batch.status = CorrectionBatchStatus.ready_for_analysis
        batch.error_message = None

        try:
            result = self.analyze_batch(batch_id)
            # Success: remove from failed
            self._failed_batches.pop(batch_id, None)
            return result
        except Exception as exc:
            retry.last_error = str(exc)
            self._emit_notification(
                FeedbackNotificationType.retry_scheduled
                if not retry.is_exhausted
                else FeedbackNotificationType.retry_exhausted,
                batch_id,
                f"Retry attempt {retry.attempt_number} failed: {exc}",
                {"attempt": retry.attempt_number, "max_attempts": retry.max_attempts},
            )
            return None

    def persist_batch(self, batch_id: UUID) -> Path | None:
        """Persist a batch's corrections to disk in JSON format.

        Parameters
        ----------
        batch_id:
            The batch to persist.

        Returns
        -------
        Path or None
            Path to the written file, or None if persistence is not configured.
        """
        if self._persistence_dir is None:
            return None

        batch = self._get_batch(batch_id)
        self._persistence_dir.mkdir(parents=True, exist_ok=True)

        file_path = self._persistence_dir / f"batch_{batch_id}.json"
        data = {
            "batch_id": str(batch.batch_id),
            "status": batch.status.value,
            "threshold": batch.threshold,
            "created_at": batch.created_at.isoformat(),
            "analyzed_at": batch.analyzed_at.isoformat() if batch.analyzed_at else None,
            "error_message": batch.error_message,
            "corrections": [
                {
                    "record_id": c.record_id,
                    "field_name": c.field_name,
                    "agent_label": c.agent_label,
                    "human_label": c.human_label,
                    "rationale": c.rationale,
                    "created_at": c.created_at.isoformat(),
                }
                for c in batch.corrections
            ],
            "patterns": [
                {
                    "pattern_type": p.pattern_type,
                    "description": p.description,
                    "affected_field": p.affected_field,
                    "frequency": p.frequency,
                    "confidence": p.confidence,
                    "examples": p.examples,
                }
                for p in batch.patterns
            ],
            "suggestions": [
                {
                    "suggestion_id": str(s.suggestion_id),
                    "patch_text": s.patch_text,
                    "target_layer": s.target_layer,
                    "rationale": s.rationale,
                    "estimated_impact": s.estimated_impact,
                }
                for s in batch.suggestions
            ],
        }

        file_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        return file_path

    def load_batch(self, file_path: Path) -> CorrectionBatch:
        """Load a batch from a persisted JSON file.

        Parameters
        ----------
        file_path:
            Path to the batch JSON file.

        Returns
        -------
        CorrectionBatch
            The loaded batch, registered in the service.
        """
        data = json.loads(file_path.read_text(encoding="utf-8"))

        corrections = [
            Correction(
                record_id=c["record_id"],
                field_name=c["field_name"],
                agent_label=c.get("agent_label"),
                human_label=c.get("human_label"),
                rationale=c.get("rationale", ""),
                created_at=datetime.fromisoformat(c["created_at"])
                if "created_at" in c
                else datetime.now(UTC),
            )
            for c in data.get("corrections", [])
        ]

        patterns = [
            CorrectionPattern(
                pattern_type=p["pattern_type"],
                description=p["description"],
                affected_field=p.get("affected_field", ""),
                frequency=p.get("frequency", 0),
                confidence=p.get("confidence", 0.0),
                examples=p.get("examples", []),
            )
            for p in data.get("patterns", [])
        ]

        suggestions = [
            RefinementSuggestion(
                suggestion_id=UUID(s["suggestion_id"]),
                patch_text=s["patch_text"],
                target_layer=s.get("target_layer", "patch"),
                rationale=s.get("rationale", ""),
                estimated_impact=s.get("estimated_impact", 0.0),
            )
            for s in data.get("suggestions", [])
        ]

        batch = CorrectionBatch(
            batch_id=UUID(data["batch_id"]),
            corrections=corrections,
            status=CorrectionBatchStatus(data["status"]),
            threshold=data.get("threshold", self._batch_threshold),
            patterns=patterns,
            suggestions=suggestions,
            created_at=datetime.fromisoformat(data["created_at"])
            if "created_at" in data
            else datetime.now(UTC),
            analyzed_at=datetime.fromisoformat(data["analyzed_at"])
            if data.get("analyzed_at")
            else None,
            error_message=data.get("error_message"),
        )

        self._batches[batch.batch_id] = batch
        return batch

    # -- Private helpers --

    def _get_batch(self, batch_id: UUID) -> CorrectionBatch:
        """Get batch by ID or raise KeyError."""
        batch = self._batches.get(batch_id)
        if batch is None:
            raise KeyError(f"Batch '{batch_id}' not found")
        return batch

    def _transition(
        self, batch: CorrectionBatch, target: CorrectionBatchStatus
    ) -> None:
        """Transition a batch to a new state with validation."""
        valid_targets = _VALID_TRANSITIONS.get(batch.status, set())
        if target not in valid_targets:
            raise InvalidStateTransitionError(batch.status, target)
        batch.status = target

    def _extract_patterns(
        self, corrections: list[Correction]
    ) -> list[CorrectionPattern]:
        """Extract error patterns from a batch of corrections."""
        patterns: list[CorrectionPattern] = []

        # Group corrections by field
        by_field: dict[str, list[Correction]] = defaultdict(list)
        for correction in corrections:
            by_field[correction.field_name].append(correction)

        for field_name, field_corrections in by_field.items():
            # Detect systematic bias: frequent agent_label -> human_label mappings
            transition_counts: Counter[tuple[str, str]] = Counter()
            for c in field_corrections:
                agent_str = (
                    str(c.agent_label) if c.agent_label is not None else "__null__"
                )
                human_str = (
                    str(c.human_label) if c.human_label is not None else "__null__"
                )
                if agent_str != human_str:
                    transition_counts[(agent_str, human_str)] += 1

            for (agent_val, human_val), count in transition_counts.most_common(5):
                if count >= 2:  # At least 2 occurrences to be a pattern
                    ratio = count / len(field_corrections)
                    patterns.append(
                        CorrectionPattern(
                            pattern_type="systematic_bias",
                            description=(
                                f"Agent consistently labels '{agent_val}' "
                                f"when correct label is '{human_val}' "
                                f"for field '{field_name}' "
                                f"({count}/{len(field_corrections)}"
                                f" corrections, {ratio:.0%})"
                            ),
                            affected_field=field_name,
                            frequency=count,
                            confidence=min(ratio * 2, 1.0),  # Scale up for confidence
                            examples=[
                                {
                                    "record_id": c.record_id,
                                    "agent_label": c.agent_label,
                                    "human_label": c.human_label,
                                    "rationale": c.rationale,
                                }
                                for c in field_corrections
                                if str(c.agent_label) == agent_val
                                and str(c.human_label) == human_val
                            ][:3],
                        )
                    )

            # Detect high error rate on a field
            error_rate = len(field_corrections) / max(len(corrections), 1)
            if error_rate > 0.3 and len(field_corrections) >= 3:
                patterns.append(
                    CorrectionPattern(
                        pattern_type="high_error_field",
                        description=(
                            f"Field '{field_name}' has a high correction rate: "
                            f"{len(field_corrections)}/"
                            f"{len(corrections)} ({error_rate:.0%})"
                        ),
                        affected_field=field_name,
                        frequency=len(field_corrections),
                        confidence=min(error_rate, 1.0),
                    )
                )

        return patterns

    def _generate_suggestions(
        self, patterns: list[CorrectionPattern]
    ) -> list[RefinementSuggestion]:
        """Generate prompt refinement suggestions from detected patterns."""
        suggestions: list[RefinementSuggestion] = []

        for pattern in patterns:
            if pattern.pattern_type == "systematic_bias":
                # Build a clarification patch
                examples_text = ""
                for ex in pattern.examples[:2]:
                    examples_text += (
                        f"\n- When input resembles record {ex['record_id']}, "
                        f"the correct label is '{ex['human_label']}', "
                        f"not '{ex['agent_label']}'."
                    )

                patch = (
                    f"IMPORTANT CLARIFICATION for field '{pattern.affected_field}': "
                    f"{pattern.description}. "
                    f"Pay special attention to distinguish these cases correctly."
                    f"{examples_text}"
                )

                suggestions.append(
                    RefinementSuggestion(
                        pattern=pattern,
                        patch_text=patch,
                        target_layer="patch",
                        rationale=pattern.description,
                        estimated_impact=pattern.confidence * 0.5,
                    )
                )

            elif pattern.pattern_type == "high_error_field":
                patch = (
                    f"NOTE: The field '{pattern.affected_field}'"
                    f" has been frequently corrected by human"
                    f" reviewers. Please be extra careful and"
                    f" precise when labeling this field."
                    f" Consider the full context before deciding."
                )
                suggestions.append(
                    RefinementSuggestion(
                        pattern=pattern,
                        patch_text=patch,
                        target_layer="patch",
                        rationale=pattern.description,
                        estimated_impact=pattern.confidence * 0.3,
                    )
                )

        return suggestions

    def _handle_batch_failure(self, batch: CorrectionBatch, error: str) -> None:
        """Handle a batch analysis failure."""
        failed = FailedBatch(
            batch_id=batch.batch_id,
            error_message=error,
            original_batch=batch,
        )
        self._failed_batches[batch.batch_id] = failed

        self._emit_notification(
            FeedbackNotificationType.batch_failed,
            batch.batch_id,
            f"Batch analysis failed: {error}",
            {"error": error},
        )

    def _emit_notification(
        self,
        notification_type: str | FeedbackNotificationType,
        batch_id: UUID,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Emit a feedback loop notification."""
        self._notifications.append(
            FeedbackNotification(
                notification_type=str(notification_type),
                batch_id=batch_id,
                message=message,
                details=details or {},
            )
        )
        # Evict oldest notifications if over the limit.
        if len(self._notifications) > self._max_notifications:
            self._notifications = self._notifications[-self._max_notifications :]
        # Evict oldest completed/dismissed batches if over the limit.
        terminal = {"applied", "dismissed"}
        completed_ids = [
            bid for bid, b in self._batches.items() if b.status in terminal
        ]
        if len(completed_ids) > self._max_completed_batches:
            for bid in completed_ids[
                : len(completed_ids) - self._max_completed_batches
            ]:
                self._batches.pop(bid, None)

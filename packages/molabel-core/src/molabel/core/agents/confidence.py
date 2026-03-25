"""Confidence scoring and active learning queue priority (AG-008, AG-014).

Multi-signal confidence scoring combines self-reported confidence,
self-consistency across repeated runs, and log-probability signals into
a composite score. Active learning strategies use these scores to
prioritise records for human review.
"""

from __future__ import annotations

import logging
import math
from collections import Counter
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from molabel.core.utils.canonical import canonical_label_value

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# AG-008: Multi-signal confidence scoring
# ---------------------------------------------------------------------------


class ConfidenceSignalType(StrEnum):
    """Types of confidence signals that can be combined."""

    self_reported = "self_reported"
    self_consistency = "self_consistency"
    logprobs = "logprobs"


@dataclass
class ConfidenceSignal:
    """A single confidence signal with its value and source."""

    signal_type: str
    value: float
    weight: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConfidenceConfig:
    """Configuration for confidence score computation."""

    weights: dict[str, float] = field(default_factory=dict)
    min_signals: int = 1
    default_weight: float = 1.0
    normalize: bool = True

    def __post_init__(self) -> None:
        if not self.weights:
            self.weights = {
                ConfidenceSignalType.self_reported: 1.0,
                ConfidenceSignalType.self_consistency: 1.0,
                ConfidenceSignalType.logprobs: 1.0,
            }


@dataclass
class ConfidenceResult:
    """Result of a composite confidence score computation."""

    composite_score: float
    signals: list[ConfidenceSignal] = field(default_factory=list)
    signal_count: int = 0
    is_reliable: bool = True
    explanation: str = ""


class ConfidenceScorer:
    """Combine multiple confidence signals into a composite score.

    Supports configurable weights per signal type and validates that
    a minimum number of signals are present before producing a reliable
    composite score.
    """

    def __init__(self, config: ConfidenceConfig | None = None) -> None:
        self._config = config or ConfidenceConfig()

    @property
    def config(self) -> ConfidenceConfig:
        """The active confidence configuration."""
        return self._config

    def score(
        self,
        *,
        self_reported: float | None = None,
        self_consistency: float | None = None,
        logprobs: float | None = None,
        extra_signals: list[ConfidenceSignal] | None = None,
    ) -> ConfidenceResult:
        """Compute a composite confidence score from available signals.

        Parameters
        ----------
        self_reported:
            Confidence value self-reported by the agent (0.0-1.0).
        self_consistency:
            Agreement rate across N repeated runs (0.0-1.0).
        logprobs:
            Token log-probability based confidence (0.0-1.0).
        extra_signals:
            Additional custom signals.

        Returns
        -------
        ConfidenceResult
            Composite score in [0.0, 1.0] with metadata.
        """
        signals: list[ConfidenceSignal] = []

        if self_reported is not None:
            clamped = _clamp(self_reported)
            weight = self._config.weights.get(
                ConfidenceSignalType.self_reported, self._config.default_weight
            )
            signals.append(
                ConfidenceSignal(
                    signal_type=ConfidenceSignalType.self_reported,
                    value=clamped,
                    weight=weight,
                )
            )

        if self_consistency is not None:
            clamped = _clamp(self_consistency)
            weight = self._config.weights.get(
                ConfidenceSignalType.self_consistency, self._config.default_weight
            )
            signals.append(
                ConfidenceSignal(
                    signal_type=ConfidenceSignalType.self_consistency,
                    value=clamped,
                    weight=weight,
                )
            )

        if logprobs is not None:
            clamped = _clamp(logprobs)
            weight = self._config.weights.get(
                ConfidenceSignalType.logprobs, self._config.default_weight
            )
            signals.append(
                ConfidenceSignal(
                    signal_type=ConfidenceSignalType.logprobs,
                    value=clamped,
                    weight=weight,
                )
            )

        if extra_signals:
            for sig in extra_signals:
                sig.value = _clamp(sig.value)
                sig.weight = (
                    sig.weight if sig.weight > 0 else self._config.default_weight
                )
                signals.append(sig)

        if not signals:
            return ConfidenceResult(
                composite_score=0.0,
                signals=[],
                signal_count=0,
                is_reliable=False,
                explanation="No confidence signals provided.",
            )

        is_reliable = len(signals) >= self._config.min_signals

        total_weight = sum(s.weight for s in signals)
        if total_weight <= 0:
            composite = 0.0
        else:
            composite = sum(s.value * s.weight for s in signals) / total_weight

        if self._config.normalize:
            composite = _clamp(composite)

        parts = [f"{s.signal_type}={s.value:.3f}(w={s.weight:.2f})" for s in signals]
        explanation = f"Composite from {len(signals)} signals: {', '.join(parts)}"

        return ConfidenceResult(
            composite_score=round(composite, 6),
            signals=signals,
            signal_count=len(signals),
            is_reliable=is_reliable,
            explanation=explanation,
        )

    def compute_self_consistency(
        self,
        run_labels: list[dict[str, Any]],
    ) -> float:
        """Compute self-consistency from N repeated runs.

        Parameters
        ----------
        run_labels:
            List of label dicts from N runs of the same record.

        Returns
        -------
        float
            Agreement rate in [0.0, 1.0]. 1.0 means all runs agree.
        """
        if len(run_labels) < 2:
            return 1.0

        all_fields: set[str] = set()
        for labels in run_labels:
            all_fields.update(labels.keys())

        if not all_fields:
            return 1.0

        field_consistencies: list[float] = []
        for field_name in all_fields:
            values = []
            for labels in run_labels:
                if field_name in labels:
                    values.append(canonical_label_value(labels[field_name]))

            if len(values) < 2:
                continue

            # Majority agreement rate
            counts = Counter(values)
            most_common_count = counts.most_common(1)[0][1]
            field_consistencies.append(most_common_count / len(values))

        if not field_consistencies:
            return 1.0

        return sum(field_consistencies) / len(field_consistencies)

    def logprobs_to_confidence(
        self,
        logprobs: list[dict[str, Any]],
    ) -> float:
        """Convert token log-probabilities to a confidence score.

        Parameters
        ----------
        logprobs:
            List of token logprob dicts, each with at minimum a ``logprob`` key.

        Returns
        -------
        float
            Confidence score in [0.0, 1.0].
        """
        if not logprobs:
            return 0.0

        probs: list[float] = []
        for entry in logprobs:
            lp = entry.get("logprob")
            if lp is not None:
                try:
                    prob = math.exp(float(lp))
                    probs.append(_clamp(prob))
                except (ValueError, OverflowError):
                    continue

        if not probs:
            return 0.0

        # Geometric mean of token probabilities
        log_sum = sum(math.log(max(p, 1e-10)) for p in probs)
        geo_mean = math.exp(log_sum / len(probs))
        return _clamp(geo_mean)


# ---------------------------------------------------------------------------
# AG-014: Active learning queue priority
# ---------------------------------------------------------------------------


class PriorityStrategy(StrEnum):
    """Strategies for prioritizing records in the review queue."""

    low_confidence_first = "low_confidence_first"
    uncertainty_sampling = "uncertainty_sampling"
    stratified_sampling = "stratified_sampling"
    disagreement_first = "disagreement_first"


@dataclass
class PrioritizedRecord:
    """A record with computed priority for review queue ordering."""

    record_id: str
    priority_score: float = 0.0
    strategy: str = ""
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PriorityResult:
    """Result of a priority computation for a set of records."""

    records: list[PrioritizedRecord] = field(default_factory=list)
    strategy: str = ""
    total_records: int = 0


class ActiveLearningPrioritizer:
    """Compute review queue priorities using active learning strategies.

    Each strategy takes a list of records with confidence scores and returns
    a priority-ordered list. Higher priority_score means the record should
    be reviewed sooner.
    """

    def prioritize(
        self,
        records: list[dict[str, Any]],
        strategy: str | PriorityStrategy = PriorityStrategy.low_confidence_first,
    ) -> PriorityResult:
        """Prioritize records according to the specified strategy.

        Parameters
        ----------
        records:
            List of dicts with at minimum ``record_id`` and ``confidence``.
            May also include ``labels``, ``disagreement_score``, and
            ``label_distribution`` for certain strategies.
        strategy:
            The prioritization strategy to use.

        Returns
        -------
        PriorityResult
            Priority-ordered list of records (highest priority first).
        """
        strategy_str = (
            strategy.value if isinstance(strategy, PriorityStrategy) else str(strategy)
        )

        handlers = {
            PriorityStrategy.low_confidence_first: self._low_confidence_first,
            PriorityStrategy.uncertainty_sampling: self._uncertainty_sampling,
            PriorityStrategy.stratified_sampling: self._stratified_sampling,
            PriorityStrategy.disagreement_first: self._disagreement_first,
        }

        try:
            strategy_enum = PriorityStrategy(strategy_str)
        except ValueError:
            logger.warning(
                "Unknown strategy '%s', falling back to low_confidence_first",
                strategy_str,
            )
            strategy_enum = PriorityStrategy.low_confidence_first

        handler = handlers[strategy_enum]
        prioritized = handler(records)

        # Sort by priority_score descending (highest priority first)
        prioritized.sort(key=lambda r: r.priority_score, reverse=True)

        return PriorityResult(
            records=prioritized,
            strategy=strategy_str,
            total_records=len(prioritized),
        )

    def _low_confidence_first(
        self, records: list[dict[str, Any]]
    ) -> list[PrioritizedRecord]:
        """Lower confidence gets higher priority."""
        result: list[PrioritizedRecord] = []
        for record in records:
            confidence = float(record.get("confidence", 0.0))
            result.append(
                PrioritizedRecord(
                    record_id=str(record["record_id"]),
                    priority_score=1.0 - _clamp(confidence),
                    strategy=PriorityStrategy.low_confidence_first,
                    confidence=confidence,
                )
            )
        return result

    def _uncertainty_sampling(
        self, records: list[dict[str, Any]]
    ) -> list[PrioritizedRecord]:
        """Prioritize records near the decision boundary.

        Records with confidence closest to 0.5 get the
        highest priority score.
        """
        result: list[PrioritizedRecord] = []
        for record in records:
            confidence = float(record.get("confidence", 0.5))
            # Maximum uncertainty at 0.5, minimum at 0.0 and 1.0
            uncertainty = 1.0 - abs(2.0 * _clamp(confidence) - 1.0)
            result.append(
                PrioritizedRecord(
                    record_id=str(record["record_id"]),
                    priority_score=uncertainty,
                    strategy=PriorityStrategy.uncertainty_sampling,
                    confidence=confidence,
                )
            )
        return result

    def _stratified_sampling(
        self, records: list[dict[str, Any]]
    ) -> list[PrioritizedRecord]:
        """Sample evenly across label categories, prioritizing underrepresented ones."""
        # Group records by their predicted label
        label_groups: dict[str, list[dict[str, Any]]] = {}
        for record in records:
            labels = record.get("labels", {})
            # Use first label field value as stratification key
            if labels:
                key = canonical_label_value(next(iter(labels.values())))
            else:
                key = "__unlabeled__"
            label_groups.setdefault(key, []).append(record)

        if not label_groups:
            return []

        # Smaller groups get higher priority (underrepresented classes)
        max_group_size = max(len(g) for g in label_groups.values())
        group_priority: dict[str, float] = {}
        for label, group in label_groups.items():
            # Inverse proportion: smallest group gets priority 1.0
            group_priority[label] = (
                1.0 - (len(group) / max_group_size) if max_group_size > 1 else 0.5
            )

        result: list[PrioritizedRecord] = []
        for record in records:
            labels = record.get("labels", {})
            if labels:
                key = canonical_label_value(next(iter(labels.values())))
            else:
                key = "__unlabeled__"

            confidence = float(record.get("confidence", 0.0))
            # Combine group rarity with low confidence
            base_priority = group_priority.get(key, 0.5)
            priority = 0.5 * base_priority + 0.5 * (1.0 - _clamp(confidence))

            result.append(
                PrioritizedRecord(
                    record_id=str(record["record_id"]),
                    priority_score=priority,
                    strategy=PriorityStrategy.stratified_sampling,
                    confidence=confidence,
                    metadata={"label_group": key, "group_priority": base_priority},
                )
            )
        return result

    def _disagreement_first(
        self, records: list[dict[str, Any]]
    ) -> list[PrioritizedRecord]:
        """Records with higher disagreement scores get higher priority."""
        result: list[PrioritizedRecord] = []
        for record in records:
            confidence = float(record.get("confidence", 0.0))
            disagreement = float(record.get("disagreement_score", 0.0))
            # Combine disagreement with low confidence
            priority = 0.6 * _clamp(disagreement) + 0.4 * (1.0 - _clamp(confidence))
            result.append(
                PrioritizedRecord(
                    record_id=str(record["record_id"]),
                    priority_score=priority,
                    strategy=PriorityStrategy.disagreement_first,
                    confidence=confidence,
                    metadata={"disagreement_score": disagreement},
                )
            )
        return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp a value to [lo, hi]."""
    return max(lo, min(hi, float(value)))

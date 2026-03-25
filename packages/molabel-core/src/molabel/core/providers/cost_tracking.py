"""Cost estimation and tracking (PV-012, PV-013).

Provides:
- Pre-run cost estimation based on token counts and provider pricing.
- Actual cost tracking with estimate-vs-actual deltas.
- Running totals and budget alert computation.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from molabel.core.types import CostEstimate

logger = logging.getLogger(__name__)


class CostEntry(BaseModel):
    """A single cost tracking entry for one completion call."""

    model_profile_id: UUID | None = None
    model_id: str = ""
    tokens_input: int = 0
    tokens_output: int = 0
    estimated_cost: CostEstimate | None = None
    actual_cost: CostEstimate | None = None
    delta: float | None = None
    """Difference between actual and estimated total cost (actual - estimated)."""
    created_at: datetime | None = None


class BudgetAlert(BaseModel):
    """Alert raised when cost thresholds are exceeded."""

    alert_type: str
    """One of: warning, limit_reached, limit_exceeded."""
    message: str
    current_total: float
    budget_limit: float
    percentage_used: float


class RunCostSummary(BaseModel):
    """Cost summary for an entire agent run."""

    agent_run_id: UUID | None = None
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_estimated_cost: float = 0.0
    total_actual_cost: float = 0.0
    total_delta: float = 0.0
    entry_count: int = 0
    currency: str = "USD"


class CostTracker:
    """Tracks costs across completion calls within an agent run.

    Usage::

        tracker = CostTracker(budget_limit=5.0)

        # Before a call: estimate
        estimate = tracker.estimate(provider, input_tokens, output_tokens, model)

        # After a call: record actual
        tracker.record(
            model_id="gpt-4o",
            tokens_input=150,
            tokens_output=50,
            actual_cost=actual_estimate,
            estimated_cost=estimate,
        )

        # Check budget
        alert = tracker.check_budget()
        summary = tracker.get_summary()
    """

    def __init__(
        self,
        *,
        budget_limit: float | None = None,
        warning_threshold: float = 0.8,
        agent_run_id: UUID | None = None,
    ) -> None:
        self._budget_limit = budget_limit
        self._warning_threshold = warning_threshold
        self._agent_run_id = agent_run_id
        self._entries: list[CostEntry] = []

    def estimate(
        self,
        provider: Any,
        input_tokens: int,
        output_tokens: int,
        model: str,
    ) -> CostEstimate:
        """Get a pre-run cost estimate from a provider.

        Args:
            provider: A ``ModelProviderPlugin`` implementation.
            input_tokens: Estimated input token count.
            output_tokens: Estimated output token count.
            model: Model identifier.

        Returns:
            CostEstimate with projected costs.
        """
        return provider.estimate_cost(input_tokens, output_tokens, model)

    def estimate_batch(
        self,
        provider: Any,
        records_count: int,
        avg_input_tokens: int,
        avg_output_tokens: int,
        model: str,
    ) -> CostEstimate:
        """Estimate total cost for a batch of records.

        Args:
            provider: A ``ModelProviderPlugin`` implementation.
            records_count: Number of records to process.
            avg_input_tokens: Average input tokens per record.
            avg_output_tokens: Average output tokens per record.
            model: Model identifier.

        Returns:
            CostEstimate for the entire batch.
        """
        total_input = records_count * avg_input_tokens
        total_output = records_count * avg_output_tokens
        return provider.estimate_cost(total_input, total_output, model)

    def record(
        self,
        *,
        model_id: str = "",
        model_profile_id: UUID | None = None,
        tokens_input: int = 0,
        tokens_output: int = 0,
        actual_cost: CostEstimate | None = None,
        estimated_cost: CostEstimate | None = None,
    ) -> CostEntry:
        """Record the actual cost of a completed call.

        Args:
            model_id: Model identifier used.
            model_profile_id: UUID of the model profile.
            tokens_input: Actual input tokens consumed.
            tokens_output: Actual output tokens consumed.
            actual_cost: Actual cost computed from token counts.
            estimated_cost: Pre-call estimate for comparison.

        Returns:
            The recorded CostEntry.
        """
        delta = None
        if actual_cost and estimated_cost:
            delta = actual_cost.total_cost - estimated_cost.total_cost

        entry = CostEntry(
            model_profile_id=model_profile_id,
            model_id=model_id,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            estimated_cost=estimated_cost,
            actual_cost=actual_cost,
            delta=delta,
            created_at=datetime.now(UTC),
        )
        self._entries.append(entry)
        return entry

    def check_budget(self) -> BudgetAlert | None:
        """Check if the running total exceeds budget thresholds.

        Returns a BudgetAlert if a threshold is crossed, else None.
        """
        if self._budget_limit is None:
            return None

        total = self.running_total()
        pct = total / self._budget_limit if self._budget_limit > 0 else 0.0

        if pct >= 1.0:
            return BudgetAlert(
                alert_type="limit_exceeded",
                message=(
                    f"Budget limit of ${self._budget_limit:.4f} exceeded. "
                    f"Current total: ${total:.4f} ({pct:.0%})"
                ),
                current_total=total,
                budget_limit=self._budget_limit,
                percentage_used=pct,
            )
        if pct >= self._warning_threshold:
            return BudgetAlert(
                alert_type="warning",
                message=(
                    f"Approaching budget limit. "
                    f"${total:.4f} of ${self._budget_limit:.4f} used ({pct:.0%})"
                ),
                current_total=total,
                budget_limit=self._budget_limit,
                percentage_used=pct,
            )
        return None

    def running_total(self) -> float:
        """Return the running total actual cost."""
        return sum(
            e.actual_cost.total_cost for e in self._entries if e.actual_cost is not None
        )

    def get_summary(self) -> RunCostSummary:
        """Return a summary of all tracked costs."""
        total_input = sum(e.tokens_input for e in self._entries)
        total_output = sum(e.tokens_output for e in self._entries)
        total_estimated = sum(
            e.estimated_cost.total_cost
            for e in self._entries
            if e.estimated_cost is not None
        )
        total_actual = sum(
            e.actual_cost.total_cost for e in self._entries if e.actual_cost is not None
        )

        return RunCostSummary(
            agent_run_id=self._agent_run_id,
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            total_estimated_cost=total_estimated,
            total_actual_cost=total_actual,
            total_delta=total_actual - total_estimated,
            entry_count=len(self._entries),
        )

    @property
    def entries(self) -> list[CostEntry]:
        """Return a copy of all cost entries."""
        return list(self._entries)

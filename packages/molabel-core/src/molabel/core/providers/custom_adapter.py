"""Custom provider adapter base class (PV-006).

Provides a base implementation for user-defined model providers.
Users subclass ``CustomAdapter`` and override the methods they need,
while getting sensible defaults for everything else.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from molabel.core.providers.base import (
    ProviderError,
    compute_cost,
    make_metadata,
)
from molabel.core.types import (
    CompletionChunk,
    CompletionResult,
    CostEstimate,
    HealthStatus,
    Message,
    ModelInfo,
    PluginMetadata,
)

logger = logging.getLogger(__name__)


class CustomAdapter:
    """Base class for user-defined model provider plugins.

    Subclass this and override the methods you need. At minimum you
    should override ``complete()`` and ``check_health()``.

    Args:
        plugin_id: Unique plugin identifier for this custom provider.
        description: Human-readable description.
        provider_name: Display name for the provider.
        cost_per_input_token: Per-input-token cost (USD).
        cost_per_output_token: Per-output-token cost (USD).
    """

    def __init__(
        self,
        *,
        plugin_id: str = "molabel.providers.custom",
        description: str = "Custom model provider",
        provider_name: str = "Custom",
        cost_per_input_token: float | None = None,
        cost_per_output_token: float | None = None,
    ) -> None:
        self._plugin_id = plugin_id
        self._description = description
        self._provider_name = provider_name
        self._cost_per_input = cost_per_input_token
        self._cost_per_output = cost_per_output_token

    # -- ModelProviderPlugin protocol --

    @property
    def metadata(self) -> PluginMetadata:
        return make_metadata(self._plugin_id, self._description)

    @property
    def provider_type(self) -> str:
        return "custom"

    def check_health(self) -> HealthStatus:
        """Override to implement health checks for your provider."""
        return HealthStatus(is_healthy=True)

    def list_models(self) -> list[ModelInfo]:
        """Override to return available models from your provider."""
        return []

    def supports_structured_output(self) -> bool:
        """Override if your provider supports native structured output."""
        return False

    def supports_logprobs(self) -> bool:
        """Override if your provider supports log-probabilities."""
        return False

    def complete(
        self,
        messages: list[Message],
        model: str,
        *,
        output_schema: dict[str, Any] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
        logprobs: bool = False,
        top_logprobs: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> CompletionResult:
        """Override to implement completion logic for your provider.

        The default raises ``ProviderError`` to indicate the method is
        not implemented.
        """
        raise ProviderError(
            "CustomAdapter.complete() must be overridden",
            provider="custom",
        )

    async def stream_complete(
        self,
        messages: list[Message],
        model: str,
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> AsyncIterator[CompletionChunk]:
        """Override to implement streaming completion.

        The default yields a single chunk from ``complete()``.
        """
        result = self.complete(
            messages,
            model,
            temperature=temperature,
            max_tokens=max_tokens,
            stop=stop,
            extra=extra,
        )
        yield CompletionChunk(
            delta=result.content,
            finish_reason=result.finish_reason,
            tokens_so_far=result.tokens_output,
        )

    def estimate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        model: str,
    ) -> CostEstimate:
        return compute_cost(
            input_tokens,
            output_tokens,
            self._cost_per_input,
            self._cost_per_output,
        )

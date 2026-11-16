"""Offline provider: deterministic keyword heuristics instead of a model.

It needs no API key, no network, and no model download, so a workflow can
run from import to export on any machine. The same messages and output
schema always give the same labels.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from typing import Any

from molabel.core.providers.base import ProviderError, make_metadata
from molabel.core.types import (
    CompletionChunk,
    CompletionResult,
    CostEstimate,
    HealthStatus,
    Message,
    ModelInfo,
    PluginMetadata,
    ProviderType,
)

OFFLINE_MODEL_ID = "offline-heuristic"
OFFLINE_CONFIDENCE = 0.0

_SIMPLEST_VALUES: dict[str, Any] = {
    "string": "",
    "number": 0,
    "integer": 0,
    "array": [],
    "object": {},
}


def _mentions(text: str, value: object) -> bool:
    """Whether ``value`` appears in ``text`` as a whole phrase, ignoring case.

    Underscores and hyphens in ``value`` match any run of whitespace, so the
    option ``billing_issue`` matches "billing issue". A word boundary applies
    only at an edge of ``value`` that is a word character, so ``C++`` and
    ``(urgent)`` match as written while ``cat`` does not match "category".
    """
    words = [word for word in re.split(r"[\s_-]+", str(value)) if word]
    if not words:
        return False
    phrase = r"[\s_-]+".join(re.escape(word) for word in words)
    start = r"(?<!\w)" if re.match(r"\w", words[0]) else ""
    end = r"(?!\w)" if re.search(r"\w$", words[-1]) else ""
    return re.search(start + phrase + end, text, re.IGNORECASE) is not None


def _label_value(name: str, prop: dict[str, Any], text: str) -> Any:
    options = prop.get("enum")
    if options:
        return next((o for o in options if _mentions(text, o)), options[0])
    prop_type = prop.get("type")
    if prop_type == "boolean":
        return _mentions(text, name)
    if prop_type == "array":
        item_options = prop.get("items", {}).get("enum") or []
        return [o for o in item_options if isinstance(o, str) and _mentions(text, o)]
    return _SIMPLEST_VALUES.get(prop_type)


def offline_labels(text: str, output_schema: dict[str, Any]) -> dict[str, Any]:
    """Label ``text`` for every property in ``output_schema``.

    A property with options takes the first option, in schema order, that
    the text mentions, and the first option when none is mentioned. A
    multi-select takes every mentioned option. A boolean is true when the
    text mentions the field name. Any other property takes the simplest
    value of its type.
    """
    return {
        name: _label_value(name, prop, text)
        for name, prop in output_schema.get("properties", {}).items()
    }


class OfflineAdapter:
    """Provider adapter that labels with keyword heuristics, not a model."""

    @property
    def metadata(self) -> PluginMetadata:
        return make_metadata(
            "molabel.providers.offline",
            "Offline keyword heuristics; no API key or network",
        )

    @property
    def provider_type(self) -> str:
        return ProviderType.offline

    def check_health(self) -> HealthStatus:
        return HealthStatus(is_healthy=True, latency_ms=0)

    def list_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                model_id=OFFLINE_MODEL_ID,
                display_name="Offline heuristic (no LLM)",
                supports_structured_output=True,
                supports_logprobs=False,
                cost_per_input_token=0.0,
                cost_per_output_token=0.0,
            )
        ]

    def supports_structured_output(self) -> bool:
        return True

    def supports_logprobs(self) -> bool:
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
        if output_schema is None:
            raise ProviderError(
                "The offline provider only produces structured output; "
                "call it with an output_schema",
                provider=ProviderType.offline,
            )
        text = "\n".join(m.content for m in messages if m.role == "user")
        labels = offline_labels(text, output_schema)
        return CompletionResult(
            content=json.dumps(labels, sort_keys=True),
            parsed=labels,
            finish_reason="stop",
            model_id=model or OFFLINE_MODEL_ID,
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
        result = self.complete(messages, model)
        yield CompletionChunk(delta=result.content, finish_reason="stop")

    def estimate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        model: str,
    ) -> CostEstimate:
        return CostEstimate(input_cost=0.0, output_cost=0.0, total_cost=0.0)

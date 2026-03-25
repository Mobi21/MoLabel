"""Shared base utilities for provider adapters."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx

from molabel.core.types import (
    CompletionResult,
    CostEstimate,
    HealthStatus,
    Message,
    PluginMetadata,
)

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    """Raised when a provider call fails.

    Attributes:
        status_code: HTTP status code if applicable, else ``None``.
        provider: The provider type that raised the error.
        retriable: Whether the caller should retry the request.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        provider: str = "",
        retriable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.provider = provider
        self.retriable = retriable


def resolve_api_key(auth_ref: str | None) -> str | None:
    """Resolve an API key from an environment variable reference.

    Args:
        auth_ref: The name of the environment variable containing the key.
                  If ``None`` or empty, returns ``None``.

    Returns:
        The API key string, or ``None`` if not set.
    """
    if not auth_ref:
        return None
    return os.environ.get(auth_ref)


def build_headers(
    api_key: str | None,
    *,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build standard HTTP headers for API calls."""
    headers: dict[str, str] = {
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if extra_headers:
        headers.update(extra_headers)
    return headers


def messages_to_dicts(messages: list[Message]) -> list[dict[str, Any]]:
    """Convert ``Message`` instances to plain dicts for JSON serialization."""
    result: list[dict[str, Any]] = []
    for m in messages:
        d: dict[str, Any] = {"role": m.role, "content": m.content}
        if m.name is not None:
            d["name"] = m.name
        if m.tool_calls is not None:
            d["tool_calls"] = m.tool_calls
        result.append(d)
    return result


def parse_openai_response(
    data: dict[str, Any],
    start_time: float,
) -> CompletionResult:
    """Parse an OpenAI-format chat completion response into CompletionResult."""
    choices = data.get("choices", [])
    if not choices:
        return CompletionResult(
            content="",
            finish_reason="error",
            latency_ms=int((time.monotonic() - start_time) * 1000),
            model_id=data.get("model", ""),
        )

    choice = choices[0]
    message = choice.get("message", {})
    content = message.get("content", "") or ""
    finish_reason = choice.get("finish_reason", "stop")

    usage = data.get("usage", {})
    tokens_input = usage.get("prompt_tokens", 0)
    tokens_output = usage.get("completion_tokens", 0)

    # Handle structured output (parsed field)
    parsed = None
    if message.get("parsed"):
        parsed = message["parsed"]
    elif message.get("refusal"):
        content = message["refusal"]
        finish_reason = "content_filter"

    # Handle logprobs
    logprobs_data = choice.get("logprobs")
    logprobs_list = None
    if logprobs_data and logprobs_data.get("content"):
        logprobs_list = logprobs_data["content"]

    return CompletionResult(
        content=content,
        parsed=parsed,
        finish_reason=finish_reason,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        latency_ms=int((time.monotonic() - start_time) * 1000),
        model_id=data.get("model", ""),
        logprobs=logprobs_list,
    )


def build_openai_request_body(
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
    stream: bool = False,
) -> dict[str, Any]:
    """Build a request body in OpenAI chat completion format."""
    body: dict[str, Any] = {
        "model": model,
        "messages": messages_to_dicts(messages),
        "temperature": temperature,
        "stream": stream,
    }
    if max_tokens is not None:
        body["max_tokens"] = max_tokens
    if stop:
        body["stop"] = stop
    if logprobs:
        body["logprobs"] = True
        if top_logprobs is not None:
            body["top_logprobs"] = top_logprobs
    if output_schema is not None:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": output_schema.get("title", "response"),
                "strict": True,
                "schema": output_schema,
            },
        }
    if extra:
        body.update(extra)
    return body


def make_metadata(
    plugin_id: str,
    description: str,
) -> PluginMetadata:
    """Create standard provider plugin metadata."""
    return PluginMetadata(
        plugin_id=plugin_id,
        version="0.1.0",
        compatible_core=">=0.1,<1.0",
        description=description,
        author="MoLabel",
        tags=["provider"],
    )


def compute_cost(
    input_tokens: int,
    output_tokens: int,
    cost_per_input: float | None,
    cost_per_output: float | None,
) -> CostEstimate:
    """Compute a cost estimate from per-token pricing."""
    input_cost = (cost_per_input or 0.0) * input_tokens
    output_cost = (cost_per_output or 0.0) * output_tokens
    return CostEstimate(
        input_cost=input_cost,
        output_cost=output_cost,
        total_cost=input_cost + output_cost,
    )


async def check_endpoint_health(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 10.0,
) -> HealthStatus:
    """Probe an HTTP endpoint and return health status."""
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, headers=headers)
            latency = int((time.monotonic() - start) * 1000)
            if resp.status_code < 400:
                return HealthStatus(is_healthy=True, latency_ms=latency)
            return HealthStatus(
                is_healthy=False,
                latency_ms=latency,
                error=f"HTTP {resp.status_code}",
            )
    except httpx.TimeoutException:
        return HealthStatus(
            is_healthy=False,
            latency_ms=int((time.monotonic() - start) * 1000),
            error="Connection timed out",
        )
    except httpx.ConnectError as exc:
        return HealthStatus(
            is_healthy=False,
            latency_ms=int((time.monotonic() - start) * 1000),
            error=f"Connection failed: {exc}",
        )
    except Exception as exc:
        return HealthStatus(
            is_healthy=False,
            latency_ms=int((time.monotonic() - start) * 1000),
            error=str(exc),
        )

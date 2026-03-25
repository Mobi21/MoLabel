"""Anthropic direct provider adapter (PV-005).

Implements the Anthropic Messages API directly (not via OpenAI
compatibility). Supports Claude models with tool use for structured
output enforcement.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from molabel.core.providers.base import (
    ProviderError,
    compute_cost,
    make_metadata,
    resolve_api_key,
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

_ANTHROPIC_BASE = "https://api.anthropic.com/v1"
_ANTHROPIC_VERSION = "2023-06-01"

# Pricing (USD per token) for Anthropic models.
_ANTHROPIC_PRICING: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-20250514": (3.0e-6, 15.0e-6),
    "claude-3-5-sonnet-20241022": (3.0e-6, 15.0e-6),
    "claude-3-5-haiku-20241022": (0.8e-6, 4.0e-6),
    "claude-3-opus-20240229": (15.0e-6, 75.0e-6),
}


class AnthropicAdapter:
    """Provider adapter for the Anthropic Messages API.

    Args:
        auth_ref: Environment variable name for the Anthropic API key.
        default_model: Fallback model identifier.
        http_client: Optional pre-configured httpx.AsyncClient for testing.
    """

    def __init__(
        self,
        *,
        auth_ref: str | None = "ANTHROPIC_API_KEY",
        default_model: str = "claude-sonnet-4-20250514",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._auth_ref = auth_ref
        self._default_model = default_model
        self._http_client = http_client

    def _headers(self) -> dict[str, str]:
        api_key = resolve_api_key(self._auth_ref)
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "anthropic-version": _ANTHROPIC_VERSION,
        }
        if api_key:
            headers["x-api-key"] = api_key
        return headers

    # -- ModelProviderPlugin protocol --

    @property
    def metadata(self) -> PluginMetadata:
        return make_metadata(
            "molabel.providers.anthropic",
            "Anthropic Claude API provider adapter",
        )

    @property
    def provider_type(self) -> str:
        return "anthropic"

    def check_health(self) -> HealthStatus:
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            return HealthStatus(is_healthy=True)
        return asyncio.run(self._async_health_check())

    async def _async_health_check(self) -> HealthStatus:
        """Check if the Anthropic API is reachable.

        We probe with a minimal messages request since Anthropic
        does not expose a /models endpoint.
        """
        start = time.monotonic()
        api_key = resolve_api_key(self._auth_ref)
        if not api_key:
            return HealthStatus(
                is_healthy=False,
                error="ANTHROPIC_API_KEY not set",
            )
        # A lightweight check: just verify auth with a tiny request.
        try:
            client = self._http_client or httpx.AsyncClient(timeout=10.0)
            owns_client = self._http_client is None
            try:
                resp = await client.post(
                    f"{_ANTHROPIC_BASE}/messages",
                    headers=self._headers(),
                    json={
                        "model": self._default_model,
                        "max_tokens": 1,
                        "messages": [{"role": "user", "content": "hi"}],
                    },
                )
                latency = int((time.monotonic() - start) * 1000)
                if resp.status_code < 400 or resp.status_code == 400:
                    # 400 means the API is reachable (might be invalid request)
                    return HealthStatus(is_healthy=True, latency_ms=latency)
                if resp.status_code == 401:
                    return HealthStatus(
                        is_healthy=False,
                        latency_ms=latency,
                        error="Invalid API key",
                    )
                return HealthStatus(
                    is_healthy=False,
                    latency_ms=latency,
                    error=f"HTTP {resp.status_code}",
                )
            finally:
                if owns_client:
                    await client.aclose()
        except Exception as exc:
            return HealthStatus(
                is_healthy=False,
                latency_ms=int((time.monotonic() - start) * 1000),
                error=str(exc),
            )

    def list_models(self) -> list[ModelInfo]:
        models: list[ModelInfo] = []
        for model_id, (inp_cost, out_cost) in _ANTHROPIC_PRICING.items():
            models.append(
                ModelInfo(
                    model_id=model_id,
                    display_name=model_id.replace("-", " ").title(),
                    context_window=200000,
                    supports_structured_output=True,
                    supports_logprobs=False,
                    cost_per_input_token=inp_cost,
                    cost_per_output_token=out_cost,
                )
            )
        return models

    def supports_structured_output(self) -> bool:
        """Anthropic supports structured output via tool_use."""
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
        import asyncio

        return asyncio.run(
            self._async_complete(
                messages,
                model,
                output_schema=output_schema,
                temperature=temperature,
                max_tokens=max_tokens,
                stop=stop,
                extra=extra,
            )
        )

    async def _async_complete(
        self,
        messages: list[Message],
        model: str,
        *,
        output_schema: dict[str, Any] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> CompletionResult:
        # Convert MoLabel messages to Anthropic format
        system_prompt = ""
        api_messages: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "system":
                system_prompt = m.content
            else:
                api_messages.append({"role": m.role, "content": m.content})

        body: dict[str, Any] = {
            "model": model or self._default_model,
            "messages": api_messages,
            "max_tokens": max_tokens or 4096,
            "temperature": temperature,
        }
        if system_prompt:
            body["system"] = system_prompt
        if stop:
            body["stop_sequences"] = stop

        # Structured output via tool_use
        if output_schema is not None:
            tool_name = output_schema.get("title", "structured_output")
            body["tools"] = [
                {
                    "name": tool_name,
                    "description": "Return structured output matching the schema.",
                    "input_schema": output_schema,
                }
            ]
            body["tool_choice"] = {"type": "tool", "name": tool_name}

        if extra:
            body.update(extra)

        url = f"{_ANTHROPIC_BASE}/messages"
        start = time.monotonic()

        client = self._http_client or httpx.AsyncClient(timeout=120.0)
        owns_client = self._http_client is None
        try:
            resp = await client.post(url, json=body, headers=self._headers())
            if resp.status_code >= 400:
                raise ProviderError(
                    f"Anthropic API error: {resp.status_code} {resp.text}",
                    status_code=resp.status_code,
                    provider="anthropic",
                    retriable=resp.status_code in {429, 500, 529},
                )
            data = resp.json()
            return self._parse_response(data, start, output_schema is not None)
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"Anthropic HTTP error: {exc}",
                provider="anthropic",
                retriable=True,
            ) from exc
        finally:
            if owns_client:
                await client.aclose()

    def _parse_response(
        self,
        data: dict[str, Any],
        start_time: float,
        has_tool_use: bool,
    ) -> CompletionResult:
        """Parse Anthropic Messages API response."""
        content_blocks = data.get("content", [])
        text_content = ""
        parsed = None

        for block in content_blocks:
            if block.get("type") == "text":
                text_content += block.get("text", "")
            elif block.get("type") == "tool_use" and has_tool_use:
                parsed = block.get("input", {})

        usage = data.get("usage", {})
        stop_reason = data.get("stop_reason", "end_turn")
        finish_map = {
            "end_turn": "stop",
            "max_tokens": "length",
            "stop_sequence": "stop",
            "tool_use": "tool_calls",
        }

        return CompletionResult(
            content=text_content if not parsed else json.dumps(parsed),
            parsed=parsed,
            finish_reason=finish_map.get(stop_reason, stop_reason),
            tokens_input=usage.get("input_tokens", 0),
            tokens_output=usage.get("output_tokens", 0),
            latency_ms=int((time.monotonic() - start_time) * 1000),
            model_id=data.get("model", ""),
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
        system_prompt = ""
        api_messages: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "system":
                system_prompt = m.content
            else:
                api_messages.append({"role": m.role, "content": m.content})

        body: dict[str, Any] = {
            "model": model or self._default_model,
            "messages": api_messages,
            "max_tokens": max_tokens or 4096,
            "temperature": temperature,
            "stream": True,
        }
        if system_prompt:
            body["system"] = system_prompt
        if stop:
            body["stop_sequences"] = stop
        if extra:
            body.update(extra)

        url = f"{_ANTHROPIC_BASE}/messages"
        client = self._http_client or httpx.AsyncClient(timeout=120.0)
        owns_client = self._http_client is None
        tokens_so_far = 0

        try:
            async with client.stream(
                "POST", url, json=body, headers=self._headers()
            ) as response:
                if response.status_code >= 400:
                    text = await response.aread()
                    raise ProviderError(
                        f"Anthropic stream error: {response.status_code}",
                        status_code=response.status_code,
                        provider="anthropic",
                    )
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        event_data = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue
                    event_type = event_data.get("type", "")
                    if event_type == "content_block_delta":
                        delta = event_data.get("delta", {})
                        text = delta.get("text", "")
                        if text:
                            tokens_so_far += 1
                            yield CompletionChunk(
                                delta=text,
                                tokens_so_far=tokens_so_far,
                            )
                    elif event_type == "message_stop":
                        yield CompletionChunk(
                            delta="",
                            finish_reason="stop",
                            tokens_so_far=tokens_so_far,
                        )
        finally:
            if owns_client:
                await client.aclose()

    def estimate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        model: str,
    ) -> CostEstimate:
        pricing = _ANTHROPIC_PRICING.get(model)
        inp_cost = pricing[0] if pricing else None
        out_cost = pricing[1] if pricing else None
        return compute_cost(input_tokens, output_tokens, inp_cost, out_cost)

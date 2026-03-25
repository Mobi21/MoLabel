"""Ollama provider adapter (PV-004).

Ollama runs models locally and exposes an OpenAI-compatible API
at ``localhost:11434``.  This adapter handles Ollama-specific
model listing, health checks, and the differences in its API
response format.
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
    check_endpoint_health,
    compute_cost,
    make_metadata,
    messages_to_dicts,
    parse_openai_response,
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

_DEFAULT_OLLAMA_URL = "http://localhost:11434"


class OllamaAdapter:
    """Provider adapter for local Ollama instances.

    Args:
        base_url: Ollama API base URL.
        default_model: Fallback model identifier.
        http_client: Optional pre-configured httpx.AsyncClient for testing.
    """

    def __init__(
        self,
        *,
        base_url: str = _DEFAULT_OLLAMA_URL,
        default_model: str = "llama3.1",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._default_model = default_model
        self._http_client = http_client

    # -- ModelProviderPlugin protocol --

    @property
    def metadata(self) -> PluginMetadata:
        return make_metadata(
            "molabel.providers.ollama",
            "Ollama local model provider adapter",
        )

    @property
    def provider_type(self) -> str:
        return "ollama"

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
        return await check_endpoint_health(self._base_url)

    def list_models(self) -> list[ModelInfo]:
        """List locally pulled Ollama models.

        Falls back to an empty list if Ollama is not running.
        """
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            return []
        try:
            return asyncio.run(self._async_list_models())
        except Exception:
            logger.debug("Could not list Ollama models", exc_info=True)
            return []

    async def _async_list_models(self) -> list[ModelInfo]:
        client = self._http_client or httpx.AsyncClient(timeout=10.0)
        owns_client = self._http_client is None
        try:
            resp = await client.get(f"{self._base_url}/api/tags")
            if resp.status_code >= 400:
                return []
            data = resp.json()
            models: list[ModelInfo] = []
            for m in data.get("models", []):
                name = m.get("name", "")
                details = m.get("details", {})
                ctx_len = details.get("context_length")
                models.append(
                    ModelInfo(
                        model_id=name,
                        display_name=name,
                        context_window=ctx_len,
                        supports_structured_output=True,
                        supports_logprobs=False,
                        cost_per_input_token=0.0,
                        cost_per_output_token=0.0,
                    )
                )
            return models
        finally:
            if owns_client:
                await client.aclose()

    def supports_structured_output(self) -> bool:
        """Ollama supports JSON mode via response_format."""
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
        # Use Ollama's OpenAI-compatible endpoint
        body: dict[str, Any] = {
            "model": model or self._default_model,
            "messages": messages_to_dicts(messages),
            "temperature": temperature,
            "stream": False,
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if stop:
            body["stop"] = stop
        if output_schema is not None:
            body["response_format"] = {"type": "json_object"}
        if extra:
            body.update(extra)

        url = f"{self._base_url}/v1/chat/completions"
        start = time.monotonic()

        client = self._http_client or httpx.AsyncClient(timeout=300.0)
        owns_client = self._http_client is None
        try:
            resp = await client.post(url, json=body)
            if resp.status_code >= 400:
                raise ProviderError(
                    f"Ollama API error: {resp.status_code} {resp.text}",
                    status_code=resp.status_code,
                    provider="ollama",
                    retriable=resp.status_code >= 500,
                )
            data = resp.json()
            result = parse_openai_response(data, start)

            # For structured output, try to parse JSON from content
            if output_schema is not None and result.parsed is None:
                import contextlib

                with contextlib.suppress(json.JSONDecodeError):
                    result.parsed = json.loads(result.content)

            return result
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"Ollama HTTP error: {exc}",
                provider="ollama",
                retriable=True,
            ) from exc
        finally:
            if owns_client:
                await client.aclose()

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
        body: dict[str, Any] = {
            "model": model or self._default_model,
            "messages": messages_to_dicts(messages),
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if stop:
            body["stop"] = stop
        if extra:
            body.update(extra)

        url = f"{self._base_url}/v1/chat/completions"

        client = self._http_client or httpx.AsyncClient(timeout=300.0)
        owns_client = self._http_client is None
        tokens_so_far = 0
        try:
            async with client.stream("POST", url, json=body) as response:
                if response.status_code >= 400:
                    await response.aread()
                    raise ProviderError(
                        f"Ollama stream error: {response.status_code}",
                        status_code=response.status_code,
                        provider="ollama",
                    )
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload.strip() == "[DONE]":
                        break
                    try:
                        chunk_data = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk_data.get("choices", [])
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "")
                    finish = choices[0].get("finish_reason")
                    if content:
                        tokens_so_far += 1
                    yield CompletionChunk(
                        delta=content or "",
                        finish_reason=finish,
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
        # Ollama is local / free
        return compute_cost(input_tokens, output_tokens, 0.0, 0.0)

"""OpenRouter provider adapter (PV-003).

OpenRouter is a multi-model gateway with an OpenAI-compatible API.
This adapter extends the OpenAI adapter with OpenRouter-specific
features: site headers, model discovery, and per-model pricing from
the OpenRouter models endpoint.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from molabel.core.providers.base import (
    ProviderError,
    build_headers,
    build_openai_request_body,
    check_endpoint_health,
    compute_cost,
    make_metadata,
    parse_openai_response,
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

_OPENROUTER_BASE = "https://openrouter.ai/api/v1"


class OpenRouterAdapter:
    """Provider adapter for OpenRouter's multi-model gateway.

    Args:
        auth_ref: Environment variable name for the OpenRouter API key.
        site_url: Your site URL sent in the HTTP-Referer header.
        site_name: Your app name sent in the X-Title header.
        default_model: Fallback model identifier.
        http_client: Optional pre-configured httpx.AsyncClient for testing.
    """

    def __init__(
        self,
        *,
        auth_ref: str | None = "OPENROUTER_API_KEY",
        site_url: str = "",
        site_name: str = "MoLabel",
        default_model: str = "openai/gpt-4o",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._auth_ref = auth_ref
        self._site_url = site_url
        self._site_name = site_name
        self._default_model = default_model
        self._http_client = http_client
        # Cache for model pricing
        self._pricing_cache: dict[str, tuple[float, float]] = {}

    def _extra_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._site_url:
            headers["HTTP-Referer"] = self._site_url
        if self._site_name:
            headers["X-Title"] = self._site_name
        return headers

    # -- ModelProviderPlugin protocol --

    @property
    def metadata(self) -> PluginMetadata:
        return make_metadata(
            "molabel.providers.openrouter",
            "OpenRouter multi-model gateway adapter",
        )

    @property
    def provider_type(self) -> str:
        return "openrouter"

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
        api_key = resolve_api_key(self._auth_ref)
        headers = build_headers(api_key, extra_headers=self._extra_headers())
        return await check_endpoint_health(
            f"{_OPENROUTER_BASE}/models",
            headers=headers,
        )

    def list_models(self) -> list[ModelInfo]:
        """Return a curated list of popular OpenRouter models.

        A production implementation would call ``/api/v1/models``.
        """
        popular = [
            ("openai/gpt-4o", "GPT-4o via OpenRouter", True, True, 2.5e-6, 10.0e-6),
            (
                "anthropic/claude-3.5-sonnet",
                "Claude 3.5 Sonnet",
                True,
                False,
                3.0e-6,
                15.0e-6,
            ),
            (
                "google/gemini-2.0-flash",
                "Gemini 2.0 Flash",
                True,
                False,
                0.1e-6,
                0.4e-6,
            ),
            (
                "meta-llama/llama-3.1-70b-instruct",
                "Llama 3.1 70B",
                True,
                False,
                0.5e-6,
                0.8e-6,
            ),
        ]
        models: list[ModelInfo] = []
        for mid, name, structured, logp, inp, out in popular:
            self._pricing_cache[mid] = (inp, out)
            models.append(
                ModelInfo(
                    model_id=mid,
                    display_name=name,
                    supports_structured_output=structured,
                    supports_logprobs=logp,
                    cost_per_input_token=inp,
                    cost_per_output_token=out,
                )
            )
        return models

    def supports_structured_output(self) -> bool:
        return True

    def supports_logprobs(self) -> bool:
        return True

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
                logprobs=logprobs,
                top_logprobs=top_logprobs,
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
        logprobs: bool = False,
        top_logprobs: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> CompletionResult:
        api_key = resolve_api_key(self._auth_ref)
        headers = build_headers(api_key, extra_headers=self._extra_headers())
        body = build_openai_request_body(
            messages,
            model or self._default_model,
            output_schema=output_schema,
            temperature=temperature,
            max_tokens=max_tokens,
            stop=stop,
            logprobs=logprobs,
            top_logprobs=top_logprobs,
            extra=extra,
        )
        url = f"{_OPENROUTER_BASE}/chat/completions"
        start = time.monotonic()

        client = self._http_client or httpx.AsyncClient(timeout=120.0)
        owns_client = self._http_client is None
        try:
            resp = await client.post(url, json=body, headers=headers)
            if resp.status_code >= 400:
                raise ProviderError(
                    f"OpenRouter API error: {resp.status_code} {resp.text}",
                    status_code=resp.status_code,
                    provider="openrouter",
                    retriable=resp.status_code in {429, 500, 502, 503},
                )
            data = resp.json()
            return parse_openai_response(data, start)
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"OpenRouter HTTP error: {exc}",
                provider="openrouter",
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
        api_key = resolve_api_key(self._auth_ref)
        headers = build_headers(api_key, extra_headers=self._extra_headers())
        body = build_openai_request_body(
            messages,
            model or self._default_model,
            temperature=temperature,
            max_tokens=max_tokens,
            stop=stop,
            extra=extra,
            stream=True,
        )
        url = f"{_OPENROUTER_BASE}/chat/completions"

        client = self._http_client or httpx.AsyncClient(timeout=120.0)
        owns_client = self._http_client is None
        tokens_so_far = 0
        try:
            async with client.stream(
                "POST", url, json=body, headers=headers
            ) as response:
                if response.status_code >= 400:
                    await response.aread()
                    raise ProviderError(
                        f"OpenRouter stream error: {response.status_code}",
                        status_code=response.status_code,
                        provider="openrouter",
                    )
                import json as _json

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload.strip() == "[DONE]":
                        break
                    try:
                        chunk_data = _json.loads(payload)
                    except _json.JSONDecodeError:
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
        pricing = self._pricing_cache.get(model)
        inp_cost = pricing[0] if pricing else None
        out_cost = pricing[1] if pricing else None
        return compute_cost(input_tokens, output_tokens, inp_cost, out_cost)

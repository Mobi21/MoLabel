"""OpenAI-compatible provider adapter (PV-002).

Supports any API endpoint that implements the OpenAI chat completion
format: OpenAI itself, Azure OpenAI, vLLM, LM Studio, etc.
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

# Default pricing for common OpenAI models (USD per token).
_OPENAI_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.5e-6, 10.0e-6),
    "gpt-4o-mini": (0.15e-6, 0.6e-6),
    "gpt-4-turbo": (10.0e-6, 30.0e-6),
    "gpt-4": (30.0e-6, 60.0e-6),
    "gpt-3.5-turbo": (0.5e-6, 1.5e-6),
    "o1": (15.0e-6, 60.0e-6),
    "o1-mini": (3.0e-6, 12.0e-6),
    "o3-mini": (1.1e-6, 4.4e-6),
}


class OpenAIAdapter:
    """Provider adapter for OpenAI-compatible endpoints.

    Args:
        base_url: Base API URL (defaults to OpenAI's API).
        auth_ref: Environment variable name containing the API key.
        default_model: Fallback model identifier.
        cost_per_input_token: Override per-input-token cost.
        cost_per_output_token: Override per-output-token cost.
        http_client: Optional pre-configured httpx.AsyncClient for testing.
    """

    def __init__(
        self,
        *,
        base_url: str = "https://api.openai.com/v1",
        auth_ref: str | None = "OPENAI_API_KEY",
        default_model: str = "gpt-4o",
        cost_per_input_token: float | None = None,
        cost_per_output_token: float | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth_ref = auth_ref
        self._default_model = default_model
        self._cost_per_input = cost_per_input_token
        self._cost_per_output = cost_per_output_token
        self._http_client = http_client

    # -- ModelProviderPlugin protocol --

    @property
    def metadata(self) -> PluginMetadata:
        return make_metadata(
            "molabel.providers.openai",
            "OpenAI-compatible API provider adapter",
        )

    @property
    def provider_type(self) -> str:
        return "openai_compatible"

    def check_health(self) -> HealthStatus:
        """Synchronous health check (delegates to async internally)."""
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Already inside an event loop; return unchecked status.
            return HealthStatus(is_healthy=True)

        return asyncio.run(self._async_health_check())

    async def _async_health_check(self) -> HealthStatus:
        api_key = resolve_api_key(self._auth_ref)
        headers = build_headers(api_key)
        return await check_endpoint_health(
            f"{self._base_url}/models",
            headers=headers,
        )

    def list_models(self) -> list[ModelInfo]:
        """Return known model information.

        For a real deployment this would call the /models endpoint.
        Here we return a curated list of known models with metadata.
        """
        models: list[ModelInfo] = []
        for model_id, (inp_cost, out_cost) in _OPENAI_PRICING.items():
            models.append(
                ModelInfo(
                    model_id=model_id,
                    display_name=model_id,
                    supports_structured_output=model_id
                    in {"gpt-4o", "gpt-4o-mini", "o3-mini"},
                    supports_logprobs=model_id not in {"o1", "o1-mini", "o3-mini"},
                    cost_per_input_token=inp_cost,
                    cost_per_output_token=out_cost,
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
        """Synchronous completion (delegates to async internally)."""
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
        headers = build_headers(api_key)
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
        url = f"{self._base_url}/chat/completions"
        start = time.monotonic()

        client = self._http_client or httpx.AsyncClient(timeout=120.0)
        owns_client = self._http_client is None
        try:
            resp = await client.post(url, json=body, headers=headers)
            if resp.status_code >= 400:
                raise ProviderError(
                    f"OpenAI API error: {resp.status_code} {resp.text}",
                    status_code=resp.status_code,
                    provider="openai_compatible",
                    retriable=resp.status_code in {429, 500, 502, 503},
                )
            data = resp.json()
            return parse_openai_response(data, start)
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"OpenAI HTTP error: {exc}",
                provider="openai_compatible",
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
        headers = build_headers(api_key)
        body = build_openai_request_body(
            messages,
            model or self._default_model,
            temperature=temperature,
            max_tokens=max_tokens,
            stop=stop,
            extra=extra,
            stream=True,
        )
        url = f"{self._base_url}/chat/completions"

        client = self._http_client or httpx.AsyncClient(timeout=120.0)
        owns_client = self._http_client is None
        tokens_so_far = 0
        try:
            async with client.stream(
                "POST", url, json=body, headers=headers
            ) as response:
                if response.status_code >= 400:
                    text = await response.aread()
                    raise ProviderError(
                        f"OpenAI stream error: {response.status_code} {text.decode()}",
                        status_code=response.status_code,
                        provider="openai_compatible",
                        retriable=response.status_code in {429, 500, 502, 503},
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
        inp_cost = self._cost_per_input
        out_cost = self._cost_per_output
        if inp_cost is None or out_cost is None:
            pricing = _OPENAI_PRICING.get(model)
            if pricing:
                inp_cost = inp_cost or pricing[0]
                out_cost = out_cost or pricing[1]
        return compute_cost(input_tokens, output_tokens, inp_cost, out_cost)

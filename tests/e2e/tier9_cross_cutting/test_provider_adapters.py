"""Tier 9 — Cross-Cutting: Provider Adapters (T9-10).

Tests:
    T9-10: All 5 provider adapters (openai_compatible, openrouter, ollama,
           anthropic, custom) instantiate without error and list_models()
           returns a list (may be empty without credentials).
"""

from __future__ import annotations

import pytest

from molabel.core.types import ProviderType
from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import INDEPENDENT


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier9
async def test_provider_adapters(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T9-10: All provider adapters instantiate and list_models() returns a list."""

    with checkpoint(ctx, "provider_type_enum_has_5_values"):
        all_types = list(ProviderType)
        assert len(all_types) == 5, (
            f"Expected 5 ProviderType values, got {len(all_types)}: "
            f"{[t.value for t in all_types]}"
        )

    # --- OpenAI-compatible adapter ---
    with checkpoint(ctx, "openai_adapter_instantiates"):
        from molabel.core.providers.openai_adapter import OpenAIAdapter

        adapter = OpenAIAdapter()
        assert adapter is not None

    with checkpoint(ctx, "openai_adapter_list_models"):
        from molabel.core.providers.openai_adapter import OpenAIAdapter

        adapter = OpenAIAdapter()
        models = adapter.list_models()
        assert isinstance(models, list), (
            f"list_models() must return a list, got: {type(models)}"
        )

    # --- OpenRouter adapter ---
    with checkpoint(ctx, "openrouter_adapter_instantiates"):
        from molabel.core.providers.openrouter_adapter import OpenRouterAdapter

        adapter = OpenRouterAdapter()
        assert adapter is not None

    with checkpoint(ctx, "openrouter_adapter_list_models"):
        from molabel.core.providers.openrouter_adapter import OpenRouterAdapter

        adapter = OpenRouterAdapter()
        models = adapter.list_models()
        assert isinstance(models, list), (
            f"list_models() must return a list, got: {type(models)}"
        )

    # --- Ollama adapter ---
    with checkpoint(ctx, "ollama_adapter_instantiates"):
        from molabel.core.providers.ollama_adapter import OllamaAdapter

        adapter = OllamaAdapter()
        assert adapter is not None

    with checkpoint(ctx, "ollama_adapter_list_models"):
        from molabel.core.providers.ollama_adapter import OllamaAdapter

        adapter = OllamaAdapter()
        models = adapter.list_models()
        assert isinstance(models, list), (
            f"list_models() must return a list, got: {type(models)}"
        )

    # --- Anthropic adapter ---
    with checkpoint(ctx, "anthropic_adapter_instantiates"):
        from molabel.core.providers.anthropic_adapter import AnthropicAdapter

        adapter = AnthropicAdapter()
        assert adapter is not None

    with checkpoint(ctx, "anthropic_adapter_list_models"):
        from molabel.core.providers.anthropic_adapter import AnthropicAdapter

        adapter = AnthropicAdapter()
        models = adapter.list_models()
        assert isinstance(models, list), (
            f"list_models() must return a list, got: {type(models)}"
        )

    # --- Custom adapter ---
    with checkpoint(ctx, "custom_adapter_instantiates"):
        from molabel.core.providers.custom_adapter import CustomAdapter

        adapter = CustomAdapter()
        assert adapter is not None

    with checkpoint(ctx, "custom_adapter_list_models"):
        from molabel.core.providers.custom_adapter import CustomAdapter

        adapter = CustomAdapter()
        models = adapter.list_models()
        assert isinstance(models, list), (
            f"list_models() must return a list, got: {type(models)}"
        )

    # --- Provider detection via API ---
    with checkpoint(ctx, "providers_api_returns_list"):
        resp = await client.get("/api/v1/providers")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "providers" in body, f"Expected 'providers' key in response: {body}"
        assert isinstance(body["providers"], list)

    with checkpoint(ctx, "provider_scan_returns_list"):
        resp = await client.post("/api/v1/providers/scan")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "providers" in body
        assert isinstance(body["providers"], list)

    # --- Health check endpoint accepts all 5 provider types ---
    with checkpoint(ctx, "health_check_all_provider_types"):
        for ptype in ProviderType:
            resp = await client.get(f"/api/v1/providers/health/{ptype.value}")
            assert resp.status_code == 200, (
                f"Expected 200 for provider health check {ptype.value}, "
                f"got {resp.status_code}: {resp.text}"
            )
            body = resp.json()
            assert "provider_type" in body
            assert "health" in body
            assert body["provider_type"] == ptype.value

    # --- Models endpoint accepts known provider types ---
    with checkpoint(ctx, "models_endpoint_all_provider_types"):
        for ptype in [
            ProviderType.openai_compatible,
            ProviderType.openrouter,
            ProviderType.ollama,
            ProviderType.anthropic,
        ]:
            resp = await client.get(f"/api/v1/providers/models/{ptype.value}")
            assert resp.status_code == 200, (
                f"Expected 200 for models/{ptype.value}, "
                f"got {resp.status_code}: {resp.text}"
            )
            body = resp.json()
            assert "provider_type" in body
            assert "models" in body
            assert isinstance(body["models"], list)

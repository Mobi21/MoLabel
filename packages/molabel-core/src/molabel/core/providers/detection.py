"""Provider auto-detection (PV-007, PV-016).

Scans for available model providers by checking local endpoints
(Ollama), environment variables (API keys), and returning health
status for each discovered provider.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from pydantic import BaseModel

from molabel.core.providers.base import resolve_api_key
from molabel.core.types import HealthStatus, ProviderType

logger = logging.getLogger(__name__)


class DiscoveredProvider(BaseModel):
    """A provider discovered during auto-detection."""

    provider_type: str
    name: str
    health: HealthStatus
    auth_ref: str | None = None
    base_url: str | None = None
    suggested_models: list[str] = []
    detected_at: datetime | None = None


class ProviderDetector:
    """Scans the environment for available model providers.

    Checks:
    - Ollama at localhost:11434
    - OPENAI_API_KEY environment variable
    - ANTHROPIC_API_KEY environment variable
    - OPENROUTER_API_KEY environment variable
    - HF_TOKEN for HuggingFace Hub access
    """

    # Map of env var name -> (provider_type, display_name, suggested_models)
    _ENV_PROVIDERS: list[tuple[str, str, str, list[str]]] = [
        (
            "OPENAI_API_KEY",
            ProviderType.openai_compatible,
            "OpenAI",
            ["gpt-4o", "gpt-4o-mini"],
        ),
        (
            "ANTHROPIC_API_KEY",
            ProviderType.anthropic,
            "Anthropic",
            ["claude-sonnet-4-20250514", "claude-3-5-haiku-20241022"],
        ),
        (
            "OPENROUTER_API_KEY",
            ProviderType.openrouter,
            "OpenRouter",
            ["openai/gpt-4o", "anthropic/claude-3.5-sonnet"],
        ),
    ]

    async def detect_all(self) -> list[DiscoveredProvider]:
        """Scan for all available providers and return discovered list."""
        discovered: list[DiscoveredProvider] = []

        # Check Ollama (local)
        ollama_result = await self._check_ollama()
        if ollama_result:
            discovered.append(ollama_result)

        # Check env-var-based providers
        for env_var, ptype, name, models in self._ENV_PROVIDERS:
            result = self._check_env_provider(env_var, ptype, name, models)
            if result:
                discovered.append(result)

        return discovered

    def detect_all_sync(self) -> list[DiscoveredProvider]:
        """Synchronous wrapper for ``detect_all``."""
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            return self._detect_env_only()
        return asyncio.run(self.detect_all())

    def _detect_env_only(self) -> list[DiscoveredProvider]:
        """Detect providers from environment variables only (no network)."""
        discovered: list[DiscoveredProvider] = []
        for env_var, ptype, name, models in self._ENV_PROVIDERS:
            result = self._check_env_provider(env_var, ptype, name, models)
            if result:
                discovered.append(result)
        return discovered

    async def _check_ollama(self) -> DiscoveredProvider | None:
        """Probe Ollama at localhost:11434."""
        from molabel.core.providers.base import check_endpoint_health

        url = "http://localhost:11434"
        health = await check_endpoint_health(url, timeout=3.0)

        if health.is_healthy:
            # Try to discover locally pulled models
            suggested: list[str] = []
            try:
                from molabel.core.providers.ollama_adapter import OllamaAdapter

                adapter = OllamaAdapter()
                models = await adapter._async_list_models()
                suggested = [m.model_id for m in models[:5]]
            except Exception:
                logger.debug("Could not list Ollama models", exc_info=True)

            return DiscoveredProvider(
                provider_type=ProviderType.ollama,
                name="Ollama (local)",
                health=health,
                base_url=url,
                suggested_models=suggested or ["llama3.1", "mistral"],
                detected_at=datetime.now(UTC),
            )

        return None

    def _check_env_provider(
        self,
        env_var: str,
        provider_type: str,
        name: str,
        suggested_models: list[str],
    ) -> DiscoveredProvider | None:
        """Check if an API key environment variable is set."""
        api_key = resolve_api_key(env_var)
        if not api_key:
            return None

        return DiscoveredProvider(
            provider_type=provider_type,
            name=name,
            health=HealthStatus(
                is_healthy=True,
                error=None,
            ),
            auth_ref=env_var,
            suggested_models=suggested_models,
            detected_at=datetime.now(UTC),
        )

    async def check_provider_health(
        self,
        provider_type: str,
        *,
        base_url: str | None = None,
        auth_ref: str | None = None,
    ) -> HealthStatus:
        """Check health of a specific provider.

        Args:
            provider_type: One of the ProviderType enum values.
            base_url: Override base URL (for Ollama, custom).
            auth_ref: Environment variable name for the API key.

        Returns:
            HealthStatus indicating online/offline/error status.
        """
        if provider_type == ProviderType.ollama:
            from molabel.core.providers.base import check_endpoint_health

            url = base_url or "http://localhost:11434"
            return await check_endpoint_health(url, timeout=5.0)

        if provider_type == ProviderType.openai_compatible:
            from molabel.core.providers.openai_adapter import OpenAIAdapter

            adapter = OpenAIAdapter(
                base_url=base_url or "https://api.openai.com/v1",
                auth_ref=auth_ref or "OPENAI_API_KEY",
            )
            return await adapter._async_health_check()

        if provider_type == ProviderType.anthropic:
            from molabel.core.providers.anthropic_adapter import AnthropicAdapter

            adapter = AnthropicAdapter(auth_ref=auth_ref or "ANTHROPIC_API_KEY")
            return await adapter._async_health_check()

        if provider_type == ProviderType.openrouter:
            from molabel.core.providers.openrouter_adapter import OpenRouterAdapter

            adapter = OpenRouterAdapter(auth_ref=auth_ref or "OPENROUTER_API_KEY")
            return await adapter._async_health_check()

        return HealthStatus(
            is_healthy=False,
            error=f"Unknown provider type: {provider_type}",
        )

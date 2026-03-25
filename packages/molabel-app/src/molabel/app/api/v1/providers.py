"""Provider management endpoints — /api/v1/providers.

Handles provider auto-detection, health checks, and model listing.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from molabel.core.providers.detection import DiscoveredProvider, ProviderDetector
from molabel.core.providers.hf_auth import HFAuthStatus, HuggingFaceAuth
from molabel.core.types import HealthStatus, ModelInfo

router = APIRouter(prefix="/providers", tags=["providers"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ProviderListResponse(BaseModel):
    """List of discovered providers."""

    providers: list[DiscoveredProvider]


class ProviderHealthResponse(BaseModel):
    """Health check response for a specific provider."""

    provider_type: str
    health: HealthStatus


class ProviderModelsResponse(BaseModel):
    """Available models for a provider type."""

    provider_type: str
    models: list[ModelInfo]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=ProviderListResponse)
async def list_providers() -> ProviderListResponse:
    """List discovered/configured providers.

    Returns the cached list of discovered providers.  If no scan has
    been performed yet, triggers an initial scan automatically.
    """
    detector = ProviderDetector()
    providers = await detector.detect_all()
    return ProviderListResponse(providers=providers)


@router.post("/scan", response_model=ProviderListResponse)
async def scan_providers() -> ProviderListResponse:
    """Trigger provider detection scan.

    Scans Ollama at localhost:11434, checks env vars for API keys,
    and returns discovered providers with health status.
    """
    detector = ProviderDetector()
    providers = await detector.detect_all()
    return ProviderListResponse(providers=providers)


@router.get("/health/{provider_type}", response_model=ProviderHealthResponse)
async def check_provider_health(
    provider_type: str,
    base_url: str | None = None,
    auth_ref: str | None = None,
) -> ProviderHealthResponse:
    """Check health of a specific provider.

    Args:
        provider_type: One of: openai_compatible, openrouter, ollama, anthropic.
        base_url: Override base URL (query parameter).
        auth_ref: Override auth env var name (query parameter).
    """
    detector = ProviderDetector()
    health = await detector.check_provider_health(
        provider_type,
        base_url=base_url,
        auth_ref=auth_ref,
    )
    return ProviderHealthResponse(
        provider_type=provider_type,
        health=health,
    )


@router.get("/models/{provider_type}", response_model=ProviderModelsResponse)
async def list_provider_models(
    provider_type: str,
) -> ProviderModelsResponse:
    """List available models for a provider type."""
    from molabel.core.types import ProviderType

    models: list[ModelInfo] = []

    if provider_type == ProviderType.openai_compatible:
        from molabel.core.providers.openai_adapter import OpenAIAdapter

        models = OpenAIAdapter().list_models()

    elif provider_type == ProviderType.openrouter:
        from molabel.core.providers.openrouter_adapter import OpenRouterAdapter

        models = OpenRouterAdapter().list_models()

    elif provider_type == ProviderType.ollama:
        from molabel.core.providers.ollama_adapter import OllamaAdapter

        models = OllamaAdapter().list_models()

    elif provider_type == ProviderType.anthropic:
        from molabel.core.providers.anthropic_adapter import AnthropicAdapter

        models = AnthropicAdapter().list_models()

    return ProviderModelsResponse(
        provider_type=provider_type,
        models=models,
    )


@router.get("/hf/auth", response_model=HFAuthStatus)
async def check_hf_auth() -> HFAuthStatus:
    """Check HuggingFace Hub authentication status.

    Validates HF_TOKEN env var and checks write permissions.
    """
    hf_auth = HuggingFaceAuth()
    return await hf_auth.check_auth()

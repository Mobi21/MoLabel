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
    resolved_base_url: str | None = None
    auth_ref: str | None = None
    model_id: str | None = None
    reachable: bool
    authenticated: bool
    model_valid: bool | None = None


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
    model_id: str | None = None,
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
    resolved_base_url = _default_base_url(provider_type, base_url)
    resolved_auth_ref = _default_auth_ref(provider_type, auth_ref)
    model_valid = _model_is_known(provider_type, model_id) if model_id else None
    authenticated = health.is_healthy or not _looks_auth_error(health.error)
    return ProviderHealthResponse(
        provider_type=provider_type,
        health=health,
        resolved_base_url=resolved_base_url,
        auth_ref=resolved_auth_ref,
        model_id=model_id,
        reachable=health.is_healthy or bool(health.error),
        authenticated=authenticated,
        model_valid=model_valid,
    )


def _default_base_url(provider_type: str, base_url: str | None) -> str | None:
    if base_url:
        return base_url
    from molabel.core.types import ProviderType

    if provider_type == ProviderType.ollama:
        return "http://localhost:11434"
    if provider_type == ProviderType.openai_compatible:
        return "https://api.openai.com/v1"
    if provider_type == ProviderType.anthropic:
        return "https://api.anthropic.com/v1"
    if provider_type == ProviderType.openrouter:
        return "https://openrouter.ai/api/v1"
    return None


def _default_auth_ref(provider_type: str, auth_ref: str | None) -> str | None:
    if auth_ref:
        return auth_ref
    from molabel.core.types import ProviderType

    if provider_type == ProviderType.openai_compatible:
        return "OPENAI_API_KEY"
    if provider_type == ProviderType.anthropic:
        return "ANTHROPIC_API_KEY"
    if provider_type == ProviderType.openrouter:
        return "OPENROUTER_API_KEY"
    return None


def _looks_auth_error(error: str | None) -> bool:
    if not error:
        return False
    lowered = error.lower()
    return any(token in lowered for token in ["auth", "api key", "unauthorized", "401"])


def _model_is_known(provider_type: str, model_id: str | None) -> bool:
    if not model_id:
        return False
    from molabel.core.types import ProviderType

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
    else:
        return False
    return any(model.model_id == model_id for model in models)


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

"""Tier 3 — API Coverage: Providers (T3-17).

Tests:
    T3-17: List, scan, health, models, HF auth
"""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SHARED_WORKSPACE

BASE = "/api/v1"

# All 5 provider types from ProviderType enum
PROVIDER_TYPES = ["openai_compatible", "openrouter", "ollama", "anthropic", "custom"]


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier3
async def test_providers_list_scan_health_models_hf(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T3-17: List providers, scan, health check, list models, HF auth."""

    # Providers endpoints don't require auth (no CurrentReviewer dependency)

    with checkpoint(ctx, "list_providers"):
        resp = await client.get(f"{BASE}/providers")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "providers" in body
        # May be empty if no providers are discovered in test environment
        assert isinstance(body["providers"], list)

    with checkpoint(ctx, "scan_providers"):
        resp = await client.post(f"{BASE}/providers/scan")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "providers" in body

    for provider_type in PROVIDER_TYPES:
        with checkpoint(ctx, f"health_{provider_type}"):
            resp = await client.get(
                f"{BASE}/providers/health/{provider_type}",
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["provider_type"] == provider_type
            assert "health" in body
            assert "is_healthy" in body["health"]
            assert "resolved_base_url" in body
            assert "auth_ref" in body
            assert "reachable" in body
            assert "authenticated" in body
            assert "model_valid" in body

    with checkpoint(ctx, "health_minimax_model_identity"):
        resp = await client.get(
            f"{BASE}/providers/health/anthropic",
            params={
                "base_url": "https://api.minimax.io/anthropic",
                "auth_ref": "ANTHROPIC_API_KEY",
                "model_id": "MiniMax-M2.7-highspeed",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["resolved_base_url"] == "https://api.minimax.io/anthropic"
        assert body["auth_ref"] == "ANTHROPIC_API_KEY"
        assert body["model_id"] == "MiniMax-M2.7-highspeed"
        assert body["model_valid"] is True

    for provider_type in PROVIDER_TYPES:
        with checkpoint(ctx, f"models_{provider_type}"):
            resp = await client.get(f"{BASE}/providers/models/{provider_type}")
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["provider_type"] == provider_type
            assert "models" in body
            assert isinstance(body["models"], list)

    with checkpoint(ctx, "hf_auth_check"):
        resp = await client.get(f"{BASE}/providers/hf/auth")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "is_authenticated" in body

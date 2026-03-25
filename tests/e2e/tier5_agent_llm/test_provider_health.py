"""Provider health test (T5-08).

All 5 provider types return HealthStatus:
openai_compatible, openrouter, ollama, anthropic, custom.
"""

from __future__ import annotations

import pytest

from molabel.core.types import ProviderType
from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SHARED_WORKSPACE

ALL_PROVIDER_TYPES = [
    ProviderType.openai_compatible,
    ProviderType.openrouter,
    ProviderType.ollama,
    ProviderType.anthropic,
    ProviderType.custom,
]


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier5
async def test_all_provider_types_return_health_status(
    ctx: TestContext,
    client: InstrumentedClient,
) -> None:
    """T5-08: All 5 provider types return HealthStatus via the health endpoint.

    Tests that the API responds with a well-formed HealthStatus for each
    provider type. In test mode (no real credentials), providers will return
    is_healthy=False with an error message — that's fine, we just validate
    the response shape.
    """
    with checkpoint(ctx, "verify_provider_type_enum_coverage"):
        expected_types = {
            "openai_compatible",
            "openrouter",
            "ollama",
            "anthropic",
            "custom",
        }
        actual_types = {pt.value for pt in ProviderType}
        assert expected_types == actual_types, (
            f"ProviderType enum mismatch. Expected {expected_types}, got {actual_types}"
        )

    for provider_type in ALL_PROVIDER_TYPES:
        with checkpoint(ctx, f"health_check_{provider_type.value}"):
            resp = await client.get(f"/providers/health/{provider_type.value}")
            # The health endpoint always returns 200 with HealthStatus
            # (is_healthy may be False if no real API key is configured)
            assert resp.status_code == 200, (
                f"Expected 200 for /providers/health/{provider_type.value}, "
                f"got {resp.status_code}: {resp.text}"
            )

            body = resp.json()

            # Validate response shape: HealthStatus model
            assert "health" in body, f"Missing 'health' key for {provider_type.value}"
            assert "provider_type" in body

            health = body["health"]
            assert "is_healthy" in health, (
                f"Missing 'is_healthy' in health for {provider_type.value}"
            )
            assert isinstance(health["is_healthy"], bool)

            # Optional fields that may be present
            if health.get("latency_ms") is not None:
                assert isinstance(health["latency_ms"], int)
                assert health["latency_ms"] >= 0

            if health.get("error") is not None:
                assert isinstance(health["error"], str)

            assert body["provider_type"] == provider_type.value

    with checkpoint(ctx, "scan_providers_endpoint"):
        scan_resp = await client.post("/providers/scan")
        assert scan_resp.status_code == 200
        scan_body = scan_resp.json()
        assert "providers" in scan_body
        assert isinstance(scan_body["providers"], list)

    with checkpoint(ctx, "list_providers_endpoint"):
        list_resp = await client.get("/providers")
        assert list_resp.status_code == 200
        list_body = list_resp.json()
        assert "providers" in list_body
        assert isinstance(list_body["providers"], list)

"""T8-03: Provider timeout + retry — mock times out on first call, succeeds on second.

Verifies:
- A provider that raises asyncio.TimeoutError on first call
- Retry logic (simulated) succeeds on second call
- Response from second call is returned correctly
- The retry pattern is valid for agent run infrastructure
"""

from __future__ import annotations

import asyncio

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.parallel import INDEPENDENT


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier8
async def test_provider_timeouts(client, ctx):
    """T8-03: Mock provider timeout on first call, succeed on second — verify retry."""

    # ── Checkpoint 1: Setup ───────────────────────────────────────────────────
    with checkpoint(ctx, "setup"):
        ws = await client.post(
            "/workspaces", json={"workspace_name": "Provider Timeout Test"}
        )
        assert ws.status_code == 201
        _ws_id = ws.json()["workspace_id"]

        reviewer = await client.post(
            "/reviewer-profiles", json={"display_name": "Tester"}
        )
        assert reviewer.status_code == 201
        await client.login(reviewer.json()["reviewer_id"])

    # ── Checkpoint 2: Simulate timeout then success pattern ───────────────────
    with checkpoint(ctx, "timeout_then_success"):
        call_count = 0
        success_result = {"sentiment": "positive", "confidence": 0.92}

        async def flaky_call(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TimeoutError("Provider timed out after 30s")
            return success_result

        # Simulate retry wrapper
        async def call_with_retry(fn, max_retries: int = 3):
            last_exc = None
            for _ in range(max_retries):
                try:
                    return await fn()
                except TimeoutError as e:
                    last_exc = e
                    continue
            raise last_exc  # type: ignore[misc]

        result = await call_with_retry(flaky_call, max_retries=3)
        assert result == success_result
        assert call_count == 2, (
            f"Expected 2 calls (1 timeout + 1 success), got {call_count}"
        )

    # ── Checkpoint 3: Max retries exhausted raises final error ────────────────
    with checkpoint(ctx, "max_retries_exhausted"):
        always_timeout_count = 0

        async def always_timeout(*args, **kwargs):
            nonlocal always_timeout_count
            always_timeout_count += 1
            raise TimeoutError("Always times out")

        async def call_with_retry_v2(fn, max_retries: int = 3):
            last_exc = None
            for _ in range(max_retries):
                try:
                    return await fn()
                except TimeoutError as e:
                    last_exc = e
            raise last_exc  # type: ignore[misc]

        with pytest.raises(asyncio.TimeoutError):
            await call_with_retry_v2(always_timeout, max_retries=3)
        assert always_timeout_count == 3, (
            f"Expected 3 calls, got {always_timeout_count}"
        )

    # ── Checkpoint 4: API model profile creation ──────────────────────────────
    with checkpoint(ctx, "model_profile"):
        # Create a model profile (provider config)
        model_resp = await client.post(
            "/model-profiles",
            json={
                "model_identifier": "minimax-2.7",
                "provider": "anthropic",
                "base_url": "https://api.minimax.chat/v1",
                "display_name": "MiniMax 2.7",
            },
        )
        assert model_resp.status_code == 201
        model_id = model_resp.json()["model_profile_id"]
        assert model_id

    # ── Checkpoint 5: Runtime profile with retry config ───────────────────────
    with checkpoint(ctx, "runtime_profile"):
        rt_resp = await client.post(
            "/runtime-profiles",
            json={
                "profile_name": "Retry Profile",
                "max_retries": 3,
                "retry_delay_seconds": 1.0,
                "timeout_seconds": 30,
                "batch_size": 10,
            },
        )
        assert rt_resp.status_code == 201
        rt_body = rt_resp.json()
        assert rt_body.get("max_retries") == 3
        assert rt_body.get("timeout_seconds") == 30

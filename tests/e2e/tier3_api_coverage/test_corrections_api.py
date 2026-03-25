"""Tier 3 — API Coverage: Corrections (T3-16).

Tests:
    T3-16: List batches, trigger analysis (202), get refinement (404)
"""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SHARED_WORKSPACE

BASE = "/api/v1"


async def _setup(client: InstrumentedClient) -> None:
    rp = await client.post(
        f"{BASE}/reviewer-profiles",
        json={
            "display_name": "Corr Reviewer",
            "workspace_id": "00000000-0000-0000-0000-000000000001",
        },
    )
    assert rp.status_code == 201
    reviewer_id = rp.json()["id"]
    login = await client.post(f"{BASE}/sessions", json={"reviewer_id": reviewer_id})
    assert login.status_code == 200
    client._session_cookie = login.cookies.get("molabel_session")


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier3
async def test_corrections_list_analyze_refinement(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T3-16: List correction batches, trigger analysis, get refinement."""

    await _setup(client)

    with checkpoint(ctx, "list_correction_batches"):
        resp = await client.get(f"{BASE}/corrections")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "items" in body
        # Empty initially
        assert body["items"] == []

    with checkpoint(ctx, "list_correction_batches_filtered"):
        resp = await client.get(
            f"{BASE}/corrections",
            params={
                "workspace_id": "00000000-0000-0000-0000-000000000001",
                "status": "accumulating",
            },
        )
        assert resp.status_code == 200, resp.text

    fake_batch_id = "00000000-0000-0000-0000-ba7ch0000001"
    with checkpoint(ctx, "trigger_correction_analysis"):
        resp = await client.post(
            f"{BASE}/corrections/analyze",
            json={"batch_id": fake_batch_id},
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["batch_id"] == fake_batch_id
        assert body["status"] == "pending"
        assert "job_id" in body

    with checkpoint(ctx, "trigger_correction_analysis_with_model"):
        resp = await client.post(
            f"{BASE}/corrections/analyze",
            json={
                "batch_id": fake_batch_id,
                "model_profile_id": "00000000-0000-0000-0000-000000000001",
            },
        )
        assert resp.status_code == 202, resp.text

    with checkpoint(ctx, "get_refinement_suggestion_404"):
        resp = await client.get(f"{BASE}/corrections/{fake_batch_id}/refinement")
        assert resp.status_code == 404, resp.text
        body = resp.json()
        assert "error" in body

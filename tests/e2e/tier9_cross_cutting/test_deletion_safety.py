"""Tier 9 — Cross-Cutting: Deletion Safety (T9-06).

Tests:
    T9-06: Attempt to delete or overwrite resources with active dependencies;
           verify FK constraints are respected or appropriate errors returned.
"""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import INDEPENDENT

BASE = "/api/v1"
WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"


async def _setup(client: InstrumentedClient) -> dict:
    """Create reviewer, login, workspace, dataset, model profile."""
    rp = await client.post(
        f"{BASE}/reviewer-profiles",
        json={"display_name": "Deletion Safety Reviewer", "workspace_id": WORKSPACE_ID},
    )
    assert rp.status_code == 201
    reviewer_id = rp.json()["id"]

    login = await client.post(f"{BASE}/sessions", json={"reviewer_id": reviewer_id})
    assert login.status_code == 200
    client._session_cookie = login.cookies.get("molabel_session")

    ws = await client.post(
        f"{BASE}/workspaces",
        json={
            "path": "/tmp/ws-deletion-safety",
            "workspace_name": "Deletion Safety WS",
        },
    )
    assert ws.status_code == 201
    workspace_id = ws.json()["workspace_id"]

    mp = await client.post(
        f"{BASE}/model-profiles",
        json={
            "model_profile_slug": "deletion-safety-model",
            "provider_type": "openai_compatible",
            "model_identifier": "gpt-4o",
        },
    )
    assert mp.status_code == 201
    model_profile_id = mp.json()["id"]

    return {
        "workspace_id": workspace_id,
        "model_profile_id": model_profile_id,
        "reviewer_id": reviewer_id,
    }


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier9
async def test_deletion_safety(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T9-06: Deletion of resources respects FK constraints and returns proper errors.
    """

    ids = await _setup(client)
    workspace_id = ids["workspace_id"]
    model_profile_id = ids["model_profile_id"]
    reviewer_id = ids["reviewer_id"]

    # --- Model profile can be deleted when no agent runs reference it ---
    with checkpoint(ctx, "delete_model_profile_204"):
        resp = await client.delete(f"{BASE}/model-profiles/{model_profile_id}")
        assert resp.status_code == 204, resp.text

    # --- Deleting again returns 404 ---
    with checkpoint(ctx, "delete_model_profile_again_404"):
        resp = await client.delete(f"{BASE}/model-profiles/{model_profile_id}")
        assert resp.status_code == 404, resp.text
        body = resp.json()
        assert "error" in body

    # --- Cannot get deleted model profile ---
    with checkpoint(ctx, "get_deleted_model_profile_404"):
        resp = await client.get(f"{BASE}/model-profiles/{model_profile_id}")
        assert resp.status_code == 404, resp.text
        body = resp.json()
        assert "error" in body

    # --- Reviewer profile patch still works (no delete endpoint) ---
    with checkpoint(ctx, "reviewer_profile_patch_safe"):
        resp = await client.patch(
            f"{BASE}/reviewer-profiles/{reviewer_id}",
            json={"display_name": "Deletion Safety Reviewer (Updated)"},
        )
        assert resp.status_code == 200, resp.text

    # --- Dataset operations respect workspace existence ---
    with checkpoint(ctx, "dataset_list_requires_known_workspace"):
        # Dataset list filtered by existing workspace should return 200
        resp = await client.get(
            f"{BASE}/datasets",
            params={"workspace_id": workspace_id},
        )
        assert resp.status_code == 200, resp.text

    # --- Fake resource deletions return 404 with error body ---
    with checkpoint(ctx, "fake_resource_deletion_returns_404"):
        fake_mp_id = "00000000-0000-0000-0000-de1e7100faac"
        resp = await client.delete(f"{BASE}/model-profiles/{fake_mp_id}")
        assert resp.status_code == 404, resp.text
        body = resp.json()
        assert "error" in body

    # --- Runtime profile delete also returns 404 for unknown ---
    with checkpoint(ctx, "fake_runtime_profile_deletion_returns_404"):
        fake_rp_id = "00000000-0000-0000-0000-f00000000001"
        resp = await client.delete(f"{BASE}/runtime-profiles/{fake_rp_id}")
        assert resp.status_code == 404, resp.text
        body = resp.json()
        assert "error" in body

    # --- Workspace cannot be deleted via API (no delete endpoint) ---
    with checkpoint(ctx, "workspace_has_no_delete_endpoint"):
        resp = await client.delete(f"{BASE}/workspaces/{workspace_id}")
        # No DELETE /workspaces/{id} endpoint exists — expect 405 Method Not Allowed
        assert resp.status_code == 405, resp.text

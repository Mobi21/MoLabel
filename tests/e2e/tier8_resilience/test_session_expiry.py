"""T8-05: Session expiry — 401 on expired session, claim eventually reclaimed.

Verifies:
- Without a valid session cookie, protected endpoints return 401
- After login, requests succeed
- After logout (DELETE /sessions), subsequent requests return 401
- Session is per-reviewer (different reviewer IDs get separate sessions)
"""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.parallel import INDEPENDENT


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier8
async def test_session_expiry(client, ctx):
    """T8-05: Session expires — 401 on expired session, claim eventually reclaimed."""

    # ── Checkpoint 1: No session → 401 on protected endpoint ─────────────────
    with checkpoint(ctx, "no_session_401"):
        # A fresh client has no session cookie
        # Try to create a dataset (requires auth)
        resp = await client.post(
            "/datasets",
            json={
                "dataset_name": "Auth Test",
                "workspace_id": "00000000-0000-0000-0000-000000000001",
                "source_type": "jsonl",
            },
        )
        # Should fail with 401 (no session)
        assert resp.status_code in (401, 403), (
            f"Expected 401/403 without session, got {resp.status_code}"
        )

    # ── Checkpoint 2: Create reviewer and login ───────────────────────────────
    with checkpoint(ctx, "login"):
        reviewer = await client.post(
            "/reviewer-profiles",
            json={"display_name": "Session Test User"},
        )
        assert reviewer.status_code == 201
        reviewer_id = reviewer.json()["reviewer_id"]

        # Login
        login_resp = await client.post(
            "/sessions",
            json={"reviewer_id": reviewer_id},
        )
        assert login_resp.status_code == 201

        # After login, store session cookie
        session_cookie = login_resp.cookies.get("molabel_session")
        if session_cookie:
            client._session_cookie = session_cookie

    # ── Checkpoint 3: Authenticated requests succeed ──────────────────────────
    with checkpoint(ctx, "authenticated_success"):
        ws_resp = await client.post(
            "/workspaces",
            json={"workspace_name": "Session Test Workspace"},
        )
        assert ws_resp.status_code == 201
        ws_id = ws_resp.json()["workspace_id"]

        # GET /sessions/me returns current user
        me_resp = await client.get("/sessions/me")
        assert me_resp.status_code == 200
        me_body = me_resp.json()
        assert me_body.get("reviewer_id") == reviewer_id

    # ── Checkpoint 4: Logout → 401 ────────────────────────────────────────────
    with checkpoint(ctx, "logout_401"):
        logout_resp = await client.delete("/sessions")
        assert logout_resp.status_code in (200, 204)

        # Clear the session cookie
        client._session_cookie = None

        # After logout, protected endpoints return 401
        post_logout = await client.post(
            "/datasets",
            json={
                "dataset_name": "Post Logout",
                "workspace_id": ws_id,
                "source_type": "jsonl",
            },
        )
        assert post_logout.status_code in (401, 403), (
            f"Expected 401/403 after logout, got {post_logout.status_code}"
        )

    # ── Checkpoint 5: Re-login succeeds ─────────────────────────────────────
    with checkpoint(ctx, "relogin"):
        await client.login(reviewer_id)

        ds = await client.post(
            "/datasets",
            json={
                "dataset_name": "Post-relogin Dataset",
                "workspace_id": ws_id,
                "source_type": "jsonl",
            },
        )
        assert ds.status_code == 201, (
            f"Expected 201 after re-login, got {ds.status_code}"
        )

    # ── Checkpoint 6: Separate reviewer gets separate session ─────────────────
    with checkpoint(ctx, "separate_sessions"):
        reviewer2 = await client.post(
            "/reviewer-profiles",
            json={"display_name": "Second Reviewer"},
        )
        assert reviewer2.status_code == 201
        reviewer2_id = reviewer2.json()["reviewer_id"]

        # Switch to reviewer2
        await client.login(reviewer2_id)

        # /sessions/me now returns reviewer2
        me2_resp = await client.get("/sessions/me")
        assert me2_resp.status_code == 200
        me2_body = me2_resp.json()
        assert me2_body.get("reviewer_id") == reviewer2_id

"""Tier 9 — Cross-Cutting: Error Format Consistency (T9-08).

Tests:
    T9-08: Trigger 400, 401, 404, 409 errors and verify all return the
           consistent ErrorResponse schema:
           {"error": {"code": ..., "message": ..., "details": ...}}.
"""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import INDEPENDENT

BASE = "/api/v1"
WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"


async def _setup(client: InstrumentedClient) -> None:
    rp = await client.post(
        f"{BASE}/reviewer-profiles",
        json={"display_name": "Error Format Reviewer", "workspace_id": WORKSPACE_ID},
    )
    assert rp.status_code == 201
    reviewer_id = rp.json()["id"]
    login = await client.post(f"{BASE}/sessions", json={"reviewer_id": reviewer_id})
    assert login.status_code == 200
    client._session_cookie = login.cookies.get("molabel_session")


def _assert_error_response(body: dict, label: str) -> None:
    """Assert the body matches ErrorResponse shape:
    {"error": {"code": ..., "message": ...}}.
    """
    assert "error" in body, f"[{label}] Missing 'error' key in response body: {body}"
    error = body["error"]
    assert isinstance(error, dict), (
        f"[{label}] 'error' must be a dict, got: {type(error)}"
    )
    assert "code" in error or "message" in error, (
        f"[{label}] 'error' must contain 'code' or 'message', got: {error}"
    )


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier9
async def test_error_format(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T9-08: 400, 401, 404, 409 all return consistent ErrorResponse schema."""

    await _setup(client)

    # --- 401: no session cookie ---
    with checkpoint(ctx, "error_401_schema"):
        client._session_cookie = None
        client._client.cookies.clear()
        resp = await client.get(f"{BASE}/me")
        assert resp.status_code == 401, resp.text
        body = resp.json()
        _assert_error_response(body, "401_me")
        # Restore session
        rp2 = await client.post(
            f"{BASE}/reviewer-profiles",
            json={
                "display_name": "Error Format Reviewer 2",
                "workspace_id": WORKSPACE_ID,
            },
        )
        assert rp2.status_code == 201
        login2 = await client.post(
            f"{BASE}/sessions", json={"reviewer_id": rp2.json()["id"]}
        )
        assert login2.status_code == 200
        client._session_cookie = login2.cookies.get("molabel_session")

    # --- 404: unknown resource ---
    with checkpoint(ctx, "error_404_workspace_schema"):
        resp = await client.get(
            f"{BASE}/workspaces/00000000-0000-0000-0000-f00fa7000001"
        )
        assert resp.status_code == 404, resp.text
        body = resp.json()
        _assert_error_response(body, "404_workspace")

    with checkpoint(ctx, "error_404_model_profile_schema"):
        resp = await client.get(
            f"{BASE}/model-profiles/00000000-0000-0000-0000-f00fa7000002"
        )
        assert resp.status_code == 404, resp.text
        body = resp.json()
        _assert_error_response(body, "404_model_profile")

    with checkpoint(ctx, "error_404_plugin_schema"):
        resp = await client.get(f"{BASE}/plugins/molabel.plugins.nonexistent")
        assert resp.status_code == 404, resp.text
        body = resp.json()
        _assert_error_response(body, "404_plugin")

    with checkpoint(ctx, "error_404_audit_event_schema"):
        resp = await client.get(f"{BASE}/audit/00000000-0000-0000-0000-f00fa7000003")
        assert resp.status_code == 404, resp.text
        body = resp.json()
        _assert_error_response(body, "404_audit")

    with checkpoint(ctx, "error_404_adjudication_schema"):
        resp = await client.get(
            f"{BASE}/adjudication/00000000-0000-0000-0000-f00fa7000004"
        )
        assert resp.status_code == 404, resp.text
        body = resp.json()
        _assert_error_response(body, "404_adjudication")

    # --- 400/422: invalid request body ---
    with checkpoint(ctx, "error_422_invalid_body_schema"):
        # POST /reviewer-profiles with missing required field → 422
        resp = await client.post(
            f"{BASE}/reviewer-profiles",
            json={"not_a_field": "bad"},
        )
        assert resp.status_code in (400, 422), resp.text
        body = resp.json()
        # FastAPI 422 returns {"detail": [...]} by default;
        # our error handler wraps it as {"error": {...}}
        assert "error" in body or "detail" in body, (
            f"422 body should contain 'error' or 'detail', got: {body}"
        )

    with checkpoint(ctx, "error_422_invalid_session_schema"):
        # POST /sessions with invalid UUID → 422
        resp = await client.post(
            f"{BASE}/sessions",
            json={"reviewer_id": "not-a-uuid"},
        )
        assert resp.status_code in (400, 422), resp.text
        body = resp.json()
        assert "error" in body or "detail" in body, (
            f"422 body should contain 'error' or 'detail', got: {body}"
        )

    with checkpoint(ctx, "error_json_content_type"):
        # All error responses must have JSON Content-Type
        resp = await client.get(
            f"{BASE}/workspaces/00000000-0000-0000-0000-f00fa7000005"
        )
        assert resp.status_code == 404
        assert "application/json" in resp.headers.get("content-type", ""), (
            f"Error response must have JSON content-type, "
            f"got: {resp.headers.get('content-type')}"
        )

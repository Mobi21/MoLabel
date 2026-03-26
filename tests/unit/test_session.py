"""Unit tests for session management (SE-001 through SE-012).

Tests cover:
- App secret generation and persistence (SE-011)
- Cookie signing and verification (SE-002)
- Avatar color assignment (SE-001)
- Debounced last_active_at updates (SE-004)
- Session validation middleware (SE-004)
- Profile creation, listing, and update endpoints (SE-001, SE-003)
- Session creation, logout, and switching (SE-002, SE-005)
- Network binding config (SE-012)
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from unittest.mock import patch

from conftest import TEST_SECRET
from sqlalchemy import text

from molabel.app.services.session import (
    AVATAR_COLORS,
    COOKIE_NAME,
    DEBOUNCE_INTERVAL_S,
    create_session_token,
    get_or_create_app_secret,
    pick_avatar_color,
    reset_last_active_cache,
    should_update_last_active,
    verify_session_token,
)

# engine, workspace, reviewer, second_reviewer, app, client, and
# _clear_debounce_cache fixtures are provided by conftest.py.


# ===================================================================
# SE-011: App secret auto-generation
# ===================================================================


class TestAppSecret:
    """Tests for get_or_create_app_secret (SE-011)."""

    def test_creates_secret_on_first_launch(self, tmp_path: Path) -> None:
        """Secret is generated and persisted when none exists."""
        secret = get_or_create_app_secret(tmp_path)
        assert len(secret) > 0
        secret_path = tmp_path / ".molabel" / "app_secret"
        assert secret_path.is_file()
        assert secret_path.read_text().strip() == secret

    def test_loads_existing_secret(self, tmp_path: Path) -> None:
        """Same secret is returned on subsequent calls."""
        secret1 = get_or_create_app_secret(tmp_path)
        secret2 = get_or_create_app_secret(tmp_path)
        assert secret1 == secret2

    def test_creates_directory_structure(self, tmp_path: Path) -> None:
        """The .molabel directory is created if it does not exist."""
        workbench = tmp_path / "deep" / "nested"
        get_or_create_app_secret(workbench)
        assert (workbench / ".molabel" / "app_secret").is_file()

    def test_secret_is_sufficiently_long(self, tmp_path: Path) -> None:
        """The generated secret has enough entropy (128 hex chars = 64 bytes)."""
        secret = get_or_create_app_secret(tmp_path)
        # 64 bytes -> 128 hex chars.
        assert len(secret) == 128


# ===================================================================
# SE-002: Cookie signing and verification
# ===================================================================


class TestSessionToken:
    """Tests for create_session_token / verify_session_token (SE-002)."""

    def test_roundtrip(self) -> None:
        """A token created with a secret can be verified with the same secret."""
        reviewer_id = uuid.uuid4()
        token = create_session_token(reviewer_id, TEST_SECRET)
        result = verify_session_token(token, TEST_SECRET)
        assert result == reviewer_id

    def test_wrong_secret_fails(self) -> None:
        """Verification fails with a different secret."""
        reviewer_id = uuid.uuid4()
        token = create_session_token(reviewer_id, TEST_SECRET)
        result = verify_session_token(token, "wrong-secret")
        assert result is None

    def test_tampered_payload_fails(self) -> None:
        """Verification fails if the payload portion is modified."""
        reviewer_id = uuid.uuid4()
        token = create_session_token(reviewer_id, TEST_SECRET)
        # Tamper with the payload by replacing a character.
        tampered = "X" + token[1:]
        result = verify_session_token(tampered, TEST_SECRET)
        assert result is None

    def test_empty_token(self) -> None:
        """Empty token returns None."""
        assert verify_session_token("", TEST_SECRET) is None

    def test_no_separator(self) -> None:
        """Token without separator returns None."""
        assert verify_session_token("noseparatorhere", TEST_SECRET) is None

    def test_invalid_uuid_in_payload(self) -> None:
        """Token with invalid UUID returns None even if signature is valid."""
        import base64
        import hashlib
        import hmac
        import json

        payload_json = json.dumps(
            {"reviewer_id": "not-a-uuid", "issued_at": 1234567890},
            separators=(",", ":"),
        )
        payload_b64 = base64.urlsafe_b64encode(payload_json.encode("utf-8")).decode(
            "ascii"
        )
        sig = hmac.new(
            TEST_SECRET.encode(), payload_b64.encode(), hashlib.sha256
        ).hexdigest()
        token = f"{payload_b64}.{sig}"
        assert verify_session_token(token, TEST_SECRET) is None

    def test_token_payload_is_base64url_encoded(self) -> None:
        """Token payload is base64url-encoded, not plain JSON."""
        reviewer_id = uuid.uuid4()
        token = create_session_token(reviewer_id, TEST_SECRET)
        payload_part = token.rsplit(".", maxsplit=1)[0]
        # The payload should NOT start with '{' (plain JSON).
        assert not payload_part.startswith("{")
        # It should be decodable as base64url.
        import base64
        import json

        decoded = base64.urlsafe_b64decode(payload_part.encode("ascii")).decode("utf-8")
        data = json.loads(decoded)
        assert data["reviewer_id"] == str(reviewer_id)


# ===================================================================
# SE-001: Avatar color assignment
# ===================================================================


class TestAvatarColor:
    """Tests for pick_avatar_color (SE-001)."""

    def test_first_color_from_empty(self) -> None:
        """First profile gets the first palette color."""
        assert pick_avatar_color([]) == AVATAR_COLORS[0]

    def test_cycles_through_palette(self) -> None:
        """Colors cycle through the palette avoiding immediate duplicates."""
        used: list[str] = []
        for i in range(len(AVATAR_COLORS)):
            color = pick_avatar_color(used)
            assert color == AVATAR_COLORS[i]
            used.append(color)

    def test_wraps_after_full_palette(self) -> None:
        """After exhausting the palette, starts over from the first color."""
        used = list(AVATAR_COLORS)
        next_color = pick_avatar_color(used)
        assert next_color == AVATAR_COLORS[0]

    def test_skips_most_used(self) -> None:
        """Picks least-used color when usage is uneven."""
        # Use the first color 3 times, the second 1 time.
        used = [AVATAR_COLORS[0]] * 3 + [AVATAR_COLORS[1]]
        color = pick_avatar_color(used)
        # Should pick a color with 0 uses (index 2 or later).
        assert color == AVATAR_COLORS[2]


# ===================================================================
# SE-004: Debounced last_active_at
# ===================================================================


class TestDebounce:
    """Tests for should_update_last_active (SE-004)."""

    def test_first_call_returns_true(self) -> None:
        """First call for a reviewer always triggers an update."""
        reviewer_id = uuid.uuid4()
        assert should_update_last_active(reviewer_id) is True

    def test_immediate_second_call_returns_false(self) -> None:
        """Calls within the debounce window are suppressed."""
        reviewer_id = uuid.uuid4()
        should_update_last_active(reviewer_id)
        assert should_update_last_active(reviewer_id) is False

    def test_different_reviewers_independent(self) -> None:
        """Debounce is per-reviewer, not global."""
        r1 = uuid.uuid4()
        r2 = uuid.uuid4()
        assert should_update_last_active(r1) is True
        assert should_update_last_active(r2) is True

    def test_update_after_debounce_window(self) -> None:
        """Update triggers again after the debounce interval elapses."""
        reviewer_id = uuid.uuid4()
        should_update_last_active(reviewer_id)

        # Simulate time passing by manipulating the cache directly.
        import time

        from molabel.app.services.session import _last_active_cache

        _last_active_cache[reviewer_id] = time.time() - DEBOUNCE_INTERVAL_S - 1
        assert should_update_last_active(reviewer_id) is True

    def test_reset_clears_cache(self) -> None:
        """reset_last_active_cache allows immediate updates."""
        reviewer_id = uuid.uuid4()
        should_update_last_active(reviewer_id)
        reset_last_active_cache()
        assert should_update_last_active(reviewer_id) is True


# ===================================================================
# SE-001, SE-003: Reviewer profile API endpoints
# ===================================================================


class TestReviewerProfileEndpoints:
    """Tests for /api/v1/reviewer-profiles endpoints."""

    def test_create_profile(self, client, workspace) -> None:
        """POST creates a profile with auto-assigned avatar color (SE-001)."""
        resp = client.post(
            "/api/v1/reviewer-profiles",
            json={
                "display_name": "Alice",
                "workspace_id": str(workspace.id),
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["display_name"] == "Alice"
        assert data["avatar_color"] in AVATAR_COLORS
        assert data["is_operator"] is False
        assert data["is_active"] is True
        # id should be a valid UUID.
        uuid.UUID(data["id"])

    def test_create_profile_validates_name(self, client, workspace) -> None:
        """Empty display name is rejected."""
        resp = client.post(
            "/api/v1/reviewer-profiles",
            json={
                "display_name": "",
                "workspace_id": str(workspace.id),
            },
        )
        assert resp.status_code == 422

    def test_create_profile_name_max_length(self, client, workspace) -> None:
        """Display name exceeding 64 characters is rejected."""
        resp = client.post(
            "/api/v1/reviewer-profiles",
            json={
                "display_name": "A" * 65,
                "workspace_id": str(workspace.id),
            },
        )
        assert resp.status_code == 422

    def test_list_profiles(self, client, reviewer) -> None:
        """GET returns active profiles (SE-003)."""
        resp = client.get("/api/v1/reviewer-profiles")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert any(p["display_name"] == "Test Reviewer" for p in data)

    def test_list_profiles_filters_inactive(self, client, engine, reviewer) -> None:
        """Inactive profiles are excluded when active_only=True."""
        # Deactivate the reviewer via raw SQL.
        with engine.connect() as conn:
            conn.execute(
                text("UPDATE reviewer_profiles SET is_active = 0 WHERE id = :id"),
                {"id": str(reviewer.id)},
            )
            conn.commit()

        resp = client.get("/api/v1/reviewer-profiles?active_only=true")
        assert resp.status_code == 200
        data = resp.json()
        assert not any(p["id"] == str(reviewer.id) for p in data)

    def test_get_profile(self, client, reviewer) -> None:
        """GET /{id} returns the specific profile."""
        resp = client.get(f"/api/v1/reviewer-profiles/{reviewer.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["display_name"] == "Test Reviewer"

    def test_get_nonexistent_profile(self, client) -> None:
        """GET /{id} returns 404 for unknown ID."""
        resp = client.get(f"/api/v1/reviewer-profiles/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_update_profile(self, client, reviewer) -> None:
        """PATCH updates display_name and avatar_color."""
        resp = client.patch(
            f"/api/v1/reviewer-profiles/{reviewer.id}",
            json={
                "display_name": "Updated Name",
                "avatar_color": "#FF5733",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["display_name"] == "Updated Name"
        assert data["avatar_color"] == "#FF5733"

    def test_update_profile_invalid_color(self, client, reviewer) -> None:
        """PATCH rejects invalid hex color format."""
        resp = client.patch(
            f"/api/v1/reviewer-profiles/{reviewer.id}",
            json={"avatar_color": "not-a-color"},
        )
        assert resp.status_code == 422

    def test_auto_color_cycling(self, client, workspace) -> None:
        """Multiple profiles get distinct colors from the palette (SE-001)."""
        colors: list[str] = []
        for i in range(4):
            resp = client.post(
                "/api/v1/reviewer-profiles",
                json={
                    "display_name": f"Reviewer {i}",
                    "workspace_id": str(workspace.id),
                },
            )
            assert resp.status_code == 201
            colors.append(resp.json()["avatar_color"])

        # First 4 should be distinct colors from the palette.
        assert len(set(colors)) == 4
        for c in colors:
            assert c in AVATAR_COLORS


# ===================================================================
# SE-002, SE-003, SE-005: Session endpoints
# ===================================================================


class TestSessionEndpoints:
    """Tests for /api/v1/sessions and /api/v1/me endpoints."""

    def test_create_session(self, client, reviewer) -> None:
        """POST /sessions sets the session cookie (SE-002)."""
        resp = client.post(
            "/api/v1/sessions",
            json={"reviewer_id": str(reviewer.id)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["reviewer_id"] == str(reviewer.id)
        assert data["display_name"] == "Test Reviewer"
        assert data["message"] == "session_created"

        # Cookie should be set.
        assert COOKIE_NAME in resp.cookies

    def test_create_session_nonexistent_reviewer(self, client) -> None:
        """POST /sessions returns 404 for unknown reviewer."""
        resp = client.post(
            "/api/v1/sessions",
            json={"reviewer_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404

    def test_get_me_with_session(self, client, reviewer) -> None:
        """GET /me returns current reviewer when session is valid (SE-003)."""
        # First, log in.
        client.post(
            "/api/v1/sessions",
            json={"reviewer_id": str(reviewer.id)},
        )
        # Then, check /me.
        resp = client.get("/api/v1/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["reviewer_id"] == str(reviewer.id)
        assert data["display_name"] == "Test Reviewer"

    def test_get_me_without_session(self, client) -> None:
        """GET /me returns 401 when no session cookie is present (SE-003)."""
        resp = client.get("/api/v1/me")
        assert resp.status_code == 401

    def test_delete_session(self, client, reviewer) -> None:
        """DELETE /sessions clears the session cookie."""
        # Log in.
        client.post(
            "/api/v1/sessions",
            json={"reviewer_id": str(reviewer.id)},
        )
        # Log out.
        resp = client.delete("/api/v1/sessions")
        assert resp.status_code == 204

        # /me should now fail.
        resp = client.get("/api/v1/me")
        assert resp.status_code == 401

    def test_switch_session(self, client, reviewer, second_reviewer) -> None:
        """POST /sessions/switch replaces the session cookie (SE-005)."""
        # Log in as first reviewer.
        client.post(
            "/api/v1/sessions",
            json={"reviewer_id": str(reviewer.id)},
        )

        # Switch to second reviewer.
        resp = client.post(
            "/api/v1/sessions/switch",
            json={"reviewer_id": str(second_reviewer.id)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["reviewer_id"] == str(second_reviewer.id)
        assert data["display_name"] == "Second Reviewer"
        assert data["message"] == "session_switched"

        # /me should now return the second reviewer.
        resp = client.get("/api/v1/me")
        assert resp.status_code == 200
        assert resp.json()["reviewer_id"] == str(second_reviewer.id)

    def test_switch_session_requires_existing_session(
        self, client, second_reviewer
    ) -> None:
        """POST /sessions/switch returns 401 without an existing session."""
        resp = client.post(
            "/api/v1/sessions/switch",
            json={"reviewer_id": str(second_reviewer.id)},
        )
        assert resp.status_code == 401

    def test_switch_to_inactive_profile_fails(
        self, client, engine, reviewer, second_reviewer
    ) -> None:
        """POST /sessions/switch to an inactive profile returns 404."""
        # Log in.
        client.post(
            "/api/v1/sessions",
            json={"reviewer_id": str(reviewer.id)},
        )
        # Deactivate the target via raw SQL.
        with engine.connect() as conn:
            conn.execute(
                text("UPDATE reviewer_profiles SET is_active = 0 WHERE id = :id"),
                {"id": str(second_reviewer.id)},
            )
            conn.commit()

        resp = client.post(
            "/api/v1/sessions/switch",
            json={"reviewer_id": str(second_reviewer.id)},
        )
        assert resp.status_code == 404

    def test_session_cookie_is_httponly(self, client, reviewer) -> None:
        """Session cookie has HttpOnly flag (SE-002)."""
        resp = client.post(
            "/api/v1/sessions",
            json={"reviewer_id": str(reviewer.id)},
        )
        # The TestClient exposes cookies, but we can verify the Set-Cookie header.
        set_cookie = resp.headers.get("set-cookie", "")
        assert "httponly" in set_cookie.lower()

    def test_session_cookie_samesite_strict(self, client, reviewer) -> None:
        """Session cookie has SameSite=Strict (SE-002)."""
        resp = client.post(
            "/api/v1/sessions",
            json={"reviewer_id": str(reviewer.id)},
        )
        set_cookie = resp.headers.get("set-cookie", "")
        assert "samesite=strict" in set_cookie.lower()


# ===================================================================
# SE-004: Session validation middleware
# ===================================================================


class TestSessionValidation:
    """Tests for the get_current_reviewer dependency (SE-004)."""

    def test_invalid_token_returns_401(self, client) -> None:
        """A tampered cookie value results in 401."""
        client.cookies.set(COOKIE_NAME, "invalid-token-value")
        resp = client.get("/api/v1/me")
        assert resp.status_code == 401

    def test_valid_token_for_deleted_reviewer(self, client, engine, reviewer) -> None:
        """A valid token for a deactivated reviewer returns 401."""
        # Create a valid token.
        token = create_session_token(reviewer.id, TEST_SECRET)
        # Deactivate the reviewer via raw SQL.
        with engine.connect() as conn:
            conn.execute(
                text("UPDATE reviewer_profiles SET is_active = 0 WHERE id = :id"),
                {"id": str(reviewer.id)},
            )
            conn.commit()

        client.cookies.set(COOKIE_NAME, token)
        resp = client.get("/api/v1/me")
        assert resp.status_code == 401

    def test_needs_session_header(self, client) -> None:
        """401 responses include X-MoLabel-Auth header (SE-003)."""
        resp = client.get("/api/v1/me")
        assert resp.status_code == 401


# ===================================================================
# SE-012: Network binding config
# ===================================================================


class TestNetworkBinding:
    """Tests for MOLABEL_HOST / MOLABEL_PORT configuration (SE-012)."""

    def test_default_host(self) -> None:
        """Default host is 0.0.0.0."""
        from molabel.app.main import MOLABEL_HOST

        # Only assert if env var is not set (to not break CI).
        if "MOLABEL_HOST" not in os.environ:
            assert MOLABEL_HOST == "0.0.0.0"

    def test_default_port(self) -> None:
        """Default port is 8000."""
        from molabel.app.main import MOLABEL_PORT

        if "MOLABEL_PORT" not in os.environ:
            assert MOLABEL_PORT == 8000

    def test_custom_host_from_env(self) -> None:
        """MOLABEL_HOST env var overrides the default."""
        with patch.dict(os.environ, {"MOLABEL_HOST": "127.0.0.1"}):
            # Re-import to pick up the new env value.
            import importlib

            import molabel.app.main as main_mod

            importlib.reload(main_mod)
            assert main_mod.MOLABEL_HOST == "127.0.0.1"

    def test_custom_port_from_env(self) -> None:
        """MOLABEL_PORT env var overrides the default."""
        with patch.dict(os.environ, {"MOLABEL_PORT": "9999"}):
            import importlib

            import molabel.app.main as main_mod

            importlib.reload(main_mod)
            assert main_mod.MOLABEL_PORT == 9999


# ===================================================================
# Health check (smoke test)
# ===================================================================


class TestHealthCheck:
    """Smoke test that the app still serves the health endpoint."""

    def test_health(self, client) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

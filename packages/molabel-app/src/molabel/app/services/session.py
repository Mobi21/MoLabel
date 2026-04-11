"""Session service: app secret, cookie signing/verification.

Covers SE-002, SE-004, SE-011.

Handles the application secret lifecycle and HMAC-based session token
creation and validation for the ``molabel_session`` cookie.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import json
import secrets
import time
import uuid
from pathlib import Path

# ---------------------------------------------------------------------------
# App Secret Management (SE-011)
# ---------------------------------------------------------------------------

_SECRET_FILENAME = "app_secret"
_SECRET_LENGTH = 64  # bytes of randomness


def _ensure_secret_dir(base_dir: Path) -> Path:
    """Create the secret directory if it does not exist."""
    secret_dir = base_dir / ".molabel"
    secret_dir.mkdir(parents=True, exist_ok=True)
    return secret_dir


def get_or_create_app_secret(workbench_dir: Path | None = None) -> str:
    """Load the application secret from disk, generating one on first launch.

    The secret is stored at ``<workbench_dir>/.molabel/app_secret``.  If the
    file does not exist, a cryptographically random secret is generated and
    persisted.

    Parameters
    ----------
    workbench_dir:
        Root directory for the workbench.  Defaults to ``workbench/`` in
        the current working directory.
    """
    if workbench_dir is None:
        workbench_dir = Path("workbench")

    secret_dir = _ensure_secret_dir(workbench_dir)
    secret_path = secret_dir / _SECRET_FILENAME

    if secret_path.is_file():
        return secret_path.read_text().strip()

    secret = secrets.token_hex(_SECRET_LENGTH)
    secret_path.write_text(secret)
    # Restrict permissions on Unix-like systems (best effort).
    with contextlib.suppress(OSError):
        secret_path.chmod(0o600)
    return secret


# ---------------------------------------------------------------------------
# Session Token Signing / Verification (SE-002, SE-004)
# ---------------------------------------------------------------------------

_SEPARATOR = "."


def _sign_payload(payload: str, secret: str) -> str:
    """Create an HMAC-SHA256 signature of *payload* using *secret*."""
    return hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def create_session_token(reviewer_id: uuid.UUID, secret: str) -> str:
    """Create a signed session token containing the reviewer ID.

    Token format: ``<base64url-json-payload>.<hmac-sha256-hex>``

    The payload is a JSON object with ``reviewer_id`` (str) and
    ``issued_at`` (float, Unix timestamp), base64url-encoded to reduce
    information exposure in the cookie value.
    """
    payload_json = json.dumps(
        {
            "reviewer_id": str(reviewer_id),
            "issued_at": time.time(),
        },
        separators=(",", ":"),
    )
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode("utf-8")).decode("ascii")
    signature = _sign_payload(payload_b64, secret)
    return f"{payload_b64}{_SEPARATOR}{signature}"


def verify_session_token(token: str, secret: str) -> uuid.UUID | None:
    """Verify a session token and return the reviewer UUID, or ``None``.

    Returns ``None`` if the token is malformed, the signature is invalid,
    or the reviewer_id is not a valid UUID.
    """
    parts = token.rsplit(_SEPARATOR, maxsplit=1)
    if len(parts) != 2:
        return None

    payload_b64, provided_sig = parts
    expected_sig = _sign_payload(payload_b64, secret)

    if not hmac.compare_digest(provided_sig, expected_sig):
        return None

    try:
        payload_json = base64.urlsafe_b64decode(payload_b64.encode("ascii")).decode(
            "utf-8"
        )
        data = json.loads(payload_json)
    except (json.JSONDecodeError, ValueError, Exception):
        return None

    reviewer_id_str = data.get("reviewer_id")
    if not reviewer_id_str:
        return None

    try:
        return uuid.UUID(reviewer_id_str)
    except (ValueError, AttributeError):
        return None


# ---------------------------------------------------------------------------
# Cookie Constants (SE-002)
# ---------------------------------------------------------------------------

COOKIE_NAME = "molabel_session"
COOKIE_PATH = "/"
COOKIE_SAMESITE = "strict"
COOKIE_HTTPONLY = True
# Secure=False because MoLabel runs over plain HTTP on localhost.
COOKIE_SECURE = False


# ---------------------------------------------------------------------------
# Avatar Color Palette (SE-001)
# ---------------------------------------------------------------------------

# 12 distinct, accessible colors for reviewer avatars.  The palette avoids
# adjacent hue collisions and has been chosen for sufficient contrast on
# both light and dark backgrounds.
AVATAR_COLORS: list[str] = [
    "#4A90D9",  # blue
    "#E67E22",  # orange
    "#27AE60",  # green
    "#9B59B6",  # purple
    "#E74C3C",  # red
    "#1ABC9C",  # teal
    "#F1C40F",  # yellow
    "#E84393",  # pink
    "#2C3E50",  # dark blue-grey
    "#8E44AD",  # deep purple
    "#D35400",  # burnt orange
    "#16A085",  # dark teal
]


def pick_avatar_color(existing_colors: list[str]) -> str:
    """Choose the next avatar color, cycling through the palette.

    Picks the color from :data:`AVATAR_COLORS` that has been used the
    fewest times among *existing_colors*, breaking ties by palette order.
    This avoids adjacent duplicates when possible.
    """
    if not existing_colors:
        return AVATAR_COLORS[0]

    counts: dict[str, int] = {c: 0 for c in AVATAR_COLORS}
    for c in existing_colors:
        if c in counts:
            counts[c] += 1

    min_count = min(counts.values())
    for color in AVATAR_COLORS:
        if counts[color] == min_count:
            return color

    # Fallback (should not be reached).
    return AVATAR_COLORS[0]


# ---------------------------------------------------------------------------
# Debounced last_active_at tracking (SE-004)
# ---------------------------------------------------------------------------

# In-memory cache mapping reviewer_id -> last update timestamp (epoch).
# Used to debounce last_active_at writes to once per DEBOUNCE_INTERVAL_S.
_last_active_cache: dict[uuid.UUID, float] = {}
DEBOUNCE_INTERVAL_S: float = 60.0


def should_update_last_active(reviewer_id: uuid.UUID) -> bool:
    """Return True if enough time has elapsed since the last update."""
    now = time.time()
    last = _last_active_cache.get(reviewer_id, 0.0)
    if now - last >= DEBOUNCE_INTERVAL_S:
        _last_active_cache[reviewer_id] = now
        return True
    return False


def reset_last_active_cache() -> None:
    """Clear the debounce cache (useful for testing)."""
    _last_active_cache.clear()

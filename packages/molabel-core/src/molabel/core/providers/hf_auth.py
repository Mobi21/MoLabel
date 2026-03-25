"""HuggingFace Hub authentication (PV-015).

Handles HF token validation, permission checking (read/write),
and token resolution from environment variables.
"""

from __future__ import annotations

import logging
import os

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_HF_API_URL = "https://huggingface.co/api"
_HF_TOKEN_ENV = "HF_TOKEN"
_HF_TOKEN_ALT_ENV = "HUGGING_FACE_HUB_TOKEN"


class HFAuthStatus(BaseModel):
    """Result of HuggingFace Hub authentication check."""

    is_authenticated: bool
    username: str | None = None
    has_write_permission: bool = False
    token_source: str | None = None
    """Which env var the token was found in."""
    error: str | None = None


class HuggingFaceAuth:
    """Manages HuggingFace Hub authentication for export operations.

    Token is resolved from environment variables in this order:
    1. ``HF_TOKEN``
    2. ``HUGGING_FACE_HUB_TOKEN``
    """

    def __init__(self, *, token: str | None = None) -> None:
        self._token = token

    def resolve_token(self) -> tuple[str | None, str | None]:
        """Resolve the HF token from explicit value or environment.

        Returns:
            Tuple of (token, source_env_var). Both are None if not found.
        """
        if self._token:
            return self._token, "explicit"

        for env_var in (_HF_TOKEN_ENV, _HF_TOKEN_ALT_ENV):
            token = os.environ.get(env_var)
            if token:
                return token, env_var

        return None, None

    async def check_auth(self) -> HFAuthStatus:
        """Validate the HF token and check permissions.

        Makes a call to the HuggingFace API ``/whoami`` endpoint
        to verify the token and determine permissions.
        """
        token, source = self.resolve_token()
        if not token:
            return HFAuthStatus(
                is_authenticated=False,
                token_source=None,
                error="No HuggingFace token found. Set HF_TOKEN environment variable.",
            )

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{_HF_API_URL}/whoami-v2",
                    headers={"Authorization": f"Bearer {token}"},
                )
                if resp.status_code == 401:
                    return HFAuthStatus(
                        is_authenticated=False,
                        token_source=source,
                        error="Invalid HuggingFace token.",
                    )
                if resp.status_code >= 400:
                    return HFAuthStatus(
                        is_authenticated=False,
                        token_source=source,
                        error=f"HuggingFace API error: HTTP {resp.status_code}",
                    )

                data = resp.json()
                username = data.get("name", "")

                # Check write permission from token fine-grained scopes
                auth_info = data.get("auth", {})
                access_token = auth_info.get("accessToken", {})
                role = access_token.get("role", "")
                has_write = role in {"write", "admin"}

                # Also check via fine-grained permissions if available
                if not has_write:
                    fine_grained = data.get("auth", {}).get("accessToken", {})
                    fined_grained_info = fine_grained.get("fineGrained", {})
                    scoped = fined_grained_info.get("scoped", [])
                    for scope in scoped:
                        perms = scope.get("permissions", [])
                        if any("write" in p for p in perms):
                            has_write = True
                            break

                return HFAuthStatus(
                    is_authenticated=True,
                    username=username,
                    has_write_permission=has_write,
                    token_source=source,
                )

        except httpx.ConnectError:
            return HFAuthStatus(
                is_authenticated=False,
                token_source=source,
                error=(
                    "Could not connect to HuggingFace. Check your internet connection."
                ),
            )
        except Exception as exc:
            return HFAuthStatus(
                is_authenticated=False,
                token_source=source,
                error=f"Error checking HuggingFace auth: {exc}",
            )

    def check_auth_sync(self) -> HFAuthStatus:
        """Synchronous wrapper for ``check_auth``."""
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            token, source = self.resolve_token()
            return HFAuthStatus(
                is_authenticated=token is not None,
                token_source=source,
                has_write_permission=False,
                error=None if token else "No HuggingFace token found.",
            )
        return asyncio.run(self.check_auth())

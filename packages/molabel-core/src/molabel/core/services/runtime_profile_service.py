"""Runtime profile management service (PV-009).

Handles routing modes, fallback model configuration, and concurrency
limits for agent runs.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlalchemy import text

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class RoutingMode(StrEnum):
    """Routing mode for model selection during agent runs.

    Values match the API spec: offline_preferred, cloud_preferred,
    hybrid, local_only.
    """

    offline_preferred = "offline_preferred"
    """Prefer local/offline models; fall back to cloud when unavailable."""

    cloud_preferred = "cloud_preferred"
    """Prefer cloud models; fall back to local when unavailable."""

    hybrid = "hybrid"
    """Use a mix of local and cloud providers based on availability."""

    local_only = "local_only"
    """Only use local models; never make cloud API calls."""


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class RuntimeProfileCreate(BaseModel):
    """Request schema for creating a runtime profile."""

    runtime_profile_slug: str
    mode: str = RoutingMode.cloud_preferred
    fallback_model_profile_id: UUID | None = None
    provider_priority: list[UUID] | None = None
    max_concurrent_requests: int | None = None
    timeout_seconds: int | None = None
    retry_config: dict[str, Any] | None = None


class RuntimeProfileUpdate(BaseModel):
    """Request schema for updating a runtime profile."""

    runtime_profile_slug: str | None = None
    mode: str | None = None
    fallback_model_profile_id: UUID | None = None
    provider_priority: list[UUID] | None = None
    max_concurrent_requests: int | None = None
    timeout_seconds: int | None = None
    retry_config: dict[str, Any] | None = None


class RuntimeProfileResponse(BaseModel):
    """Response schema for a runtime profile."""

    id: UUID
    runtime_profile_slug: str
    mode: str
    fallback_model_profile_id: UUID | None = None
    provider_priority: list[UUID] | None = None
    max_concurrent_requests: int | None = None
    timeout_seconds: int | None = None
    retry_config: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RetryConfig(BaseModel):
    """Configuration for retry behaviour on provider errors."""

    max_retries: int = 3
    initial_delay_seconds: float = 1.0
    backoff_multiplier: float = 2.0
    max_delay_seconds: float = 30.0
    retry_on_status_codes: list[int] = [429, 500, 502, 503]


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class RuntimeProfileService:
    """Manages runtime profile CRUD and routing logic.

    When *engine* is provided, data is persisted in SQLite via raw SQL.
    Without an engine the service falls back to in-memory dicts for
    unit-test convenience.
    """

    def __init__(self, engine: Any | None = None) -> None:
        self._engine = engine
        self._profiles: dict[UUID, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Internal: DB helpers
    # ------------------------------------------------------------------

    def _use_db(self) -> bool:
        return self._engine is not None

    def _db_insert(self, record: dict[str, Any]) -> None:
        with self._engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO runtime_profiles "
                    "(id, workspace_id, runtime_profile_slug, mode, "
                    "fallback_model_profile_id, provider_priority, "
                    "max_concurrent_requests, timeout_seconds, "
                    "retry_config, created_at, updated_at) "
                    "VALUES (:id, :workspace_id, :runtime_profile_slug, :mode, "
                    ":fallback_model_profile_id, :provider_priority, "
                    ":max_concurrent_requests, :timeout_seconds, "
                    ":retry_config, :created_at, :updated_at)"
                ),
                {
                    "id": str(record["id"]),
                    "workspace_id": str(record["workspace_id"]),
                    "runtime_profile_slug": record["runtime_profile_slug"],
                    "mode": record["mode"],
                    "fallback_model_profile_id": (
                        str(record["fallback_model_profile_id"])
                        if record.get("fallback_model_profile_id")
                        else None
                    ),
                    "provider_priority": json.dumps(record.get("provider_priority")),
                    "max_concurrent_requests": record.get("max_concurrent_requests"),
                    "timeout_seconds": record.get("timeout_seconds"),
                    "retry_config": json.dumps(record.get("retry_config")),
                    "created_at": record["created_at"].isoformat(),
                    "updated_at": record["updated_at"].isoformat(),
                },
            )
            conn.commit()

    def _db_get(self, profile_id: UUID) -> dict[str, Any] | None:
        with self._engine.connect() as conn:
            row = (
                conn.execute(
                    text("SELECT * FROM runtime_profiles WHERE id = :id"),
                    {"id": str(profile_id)},
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        return self._row_to_record(row)

    def _db_list(self, workspace_id: UUID) -> list[dict[str, Any]]:
        with self._engine.connect() as conn:
            rows = (
                conn.execute(
                    text("SELECT * FROM runtime_profiles WHERE workspace_id = :wid"),
                    {"wid": str(workspace_id)},
                )
                .mappings()
                .all()
            )
        return [self._row_to_record(r) for r in rows]

    def _db_update(self, profile_id: UUID, updates: dict[str, Any]) -> None:
        sets = []
        params: dict[str, Any] = {"id": str(profile_id)}
        for key, value in updates.items():
            if key in ("provider_priority", "retry_config"):
                sets.append(f"{key} = :{key}")
                params[key] = json.dumps(value)
            elif key in ("created_at", "updated_at"):
                sets.append(f"{key} = :{key}")
                params[key] = value.isoformat() if value else None
            elif key == "fallback_model_profile_id":
                sets.append(f"{key} = :{key}")
                params[key] = str(value) if value else None
            else:
                sets.append(f"{key} = :{key}")
                params[key] = str(value) if isinstance(value, UUID) else value
        if not sets:
            return
        sql = f"UPDATE runtime_profiles SET {', '.join(sets)} WHERE id = :id"
        with self._engine.connect() as conn:
            conn.execute(text(sql), params)
            conn.commit()

    def _db_delete(self, profile_id: UUID) -> bool:
        with self._engine.connect() as conn:
            result = conn.execute(
                text("DELETE FROM runtime_profiles WHERE id = :id"),
                {"id": str(profile_id)},
            )
            conn.commit()
            return result.rowcount > 0

    @staticmethod
    def _row_to_record(row: Any) -> dict[str, Any]:
        pp = row["provider_priority"]
        if isinstance(pp, str):
            pp = json.loads(pp)
        rc = row["retry_config"]
        if isinstance(rc, str):
            rc = json.loads(rc)
        created = row["created_at"]
        if isinstance(created, str):
            created = datetime.fromisoformat(created)
        updated = row["updated_at"]
        if isinstance(updated, str):
            updated = datetime.fromisoformat(updated)
        fallback = row.get("fallback_model_profile_id")
        return {
            "id": UUID(row["id"]) if isinstance(row["id"], str) else row["id"],
            "workspace_id": (
                UUID(row["workspace_id"])
                if isinstance(row["workspace_id"], str)
                else row["workspace_id"]
            ),
            "runtime_profile_slug": row["runtime_profile_slug"],
            "mode": row["mode"],
            "fallback_model_profile_id": (
                UUID(fallback) if isinstance(fallback, str) else fallback
            ),
            "provider_priority": pp,
            "max_concurrent_requests": row.get("max_concurrent_requests"),
            "timeout_seconds": row.get("timeout_seconds"),
            "retry_config": rc,
            "created_at": created,
            "updated_at": updated,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create(
        self,
        data: RuntimeProfileCreate,
        workspace_id: UUID,
    ) -> RuntimeProfileResponse:
        """Create a new runtime profile."""
        profile_id = uuid4()
        now = datetime.now(UTC)

        # Validate mode
        valid_modes = {m.value for m in RoutingMode}
        if data.mode not in valid_modes:
            raise ValueError(
                f"Invalid routing mode '{data.mode}'. "
                f"Must be one of: {', '.join(sorted(valid_modes))}"
            )

        record = {
            "id": profile_id,
            "workspace_id": workspace_id,
            "runtime_profile_slug": data.runtime_profile_slug,
            "mode": data.mode,
            "fallback_model_profile_id": data.fallback_model_profile_id,
            "provider_priority": (
                [str(p) for p in data.provider_priority]
                if data.provider_priority
                else None
            ),
            "max_concurrent_requests": data.max_concurrent_requests,
            "timeout_seconds": data.timeout_seconds,
            "retry_config": data.retry_config,
            "created_at": now,
            "updated_at": now,
        }

        if self._use_db():
            self._db_insert(record)
        else:
            self._profiles[profile_id] = record

        return self._to_response(record)

    def get(self, profile_id: UUID) -> RuntimeProfileResponse | None:
        """Get a runtime profile by ID."""
        if self._use_db():
            record = self._db_get(profile_id)
        else:
            record = self._profiles.get(profile_id)
        if record is None:
            return None
        return self._to_response(record)

    def list_profiles(
        self,
        workspace_id: UUID,
    ) -> list[RuntimeProfileResponse]:
        """List runtime profiles for a workspace."""
        if self._use_db():
            records = self._db_list(workspace_id)
            return [self._to_response(r) for r in records]

        results: list[RuntimeProfileResponse] = []
        for record in self._profiles.values():
            if record["workspace_id"] != workspace_id:
                continue
            results.append(self._to_response(record))
        return results

    def update(
        self,
        profile_id: UUID,
        data: RuntimeProfileUpdate,
    ) -> RuntimeProfileResponse | None:
        """Update an existing runtime profile."""
        if self._use_db():
            record = self._db_get(profile_id)
        else:
            record = self._profiles.get(profile_id)
        if record is None:
            return None

        update_data = data.model_dump(exclude_unset=True)

        if "mode" in update_data:
            valid_modes = {m.value for m in RoutingMode}
            if update_data["mode"] not in valid_modes:
                raise ValueError(
                    f"Invalid routing mode '{update_data['mode']}'. "
                    f"Must be one of: {', '.join(sorted(valid_modes))}"
                )

        if "provider_priority" in update_data and update_data["provider_priority"]:
            update_data["provider_priority"] = [
                str(p) for p in update_data["provider_priority"]
            ]

        for key, value in update_data.items():
            if key in record:
                record[key] = value
        record["updated_at"] = datetime.now(UTC)

        if self._use_db():
            self._db_update(profile_id, record)

        return self._to_response(record)

    def delete(self, profile_id: UUID) -> bool:
        """Delete a runtime profile. Returns True if it existed."""
        if self._use_db():
            return self._db_delete(profile_id)
        return self._profiles.pop(profile_id, None) is not None

    def get_effective_retry_config(
        self,
        profile_id: UUID,
    ) -> RetryConfig:
        """Get the effective retry configuration for a profile.

        Returns the profile's retry_config merged with defaults.
        """
        if self._use_db():
            record = self._db_get(profile_id)
        else:
            record = self._profiles.get(profile_id)
        if record is None or record.get("retry_config") is None:
            return RetryConfig()

        return RetryConfig(**record["retry_config"])

    def select_model_profile(
        self,
        profile_id: UUID,
        *,
        available_profiles: dict[UUID, bool] | None = None,
    ) -> UUID | None:
        """Select the next model profile based on routing mode.

        Args:
            profile_id: The runtime profile to use for selection.
            available_profiles: Map of model_profile_id -> is_available
                                for filtering. If None, all are considered available.

        Returns:
            The selected model_profile_id, or None if none available.
        """
        if self._use_db():
            record = self._db_get(profile_id)
        else:
            record = self._profiles.get(profile_id)
        if record is None:
            return None

        mode = record.get("mode", RoutingMode.cloud_preferred)
        priority = record.get("provider_priority") or []
        fallback_raw = record.get("fallback_model_profile_id")
        fallback_uuid = (
            fallback_raw
            if isinstance(fallback_raw, UUID)
            else UUID(fallback_raw)
            if fallback_raw
            else None
        )

        if not priority:
            # No priority list; return fallback if set
            return fallback_uuid

        priority_uuids = [p if isinstance(p, UUID) else UUID(p) for p in priority]

        if mode == RoutingMode.local_only:
            # Only use the first local provider (filtering is the caller's
            # responsibility); return first available or None.
            for pid in priority_uuids:
                if available_profiles is None or available_profiles.get(pid, True):
                    return pid
            return None

        if mode in (
            RoutingMode.cloud_preferred,
            RoutingMode.offline_preferred,
            RoutingMode.hybrid,
        ):
            for pid in priority_uuids:
                if available_profiles is None or available_profiles.get(pid, True):
                    return pid
            # All primary profiles unavailable; try fallback
            if fallback_uuid is not None and (
                available_profiles is None
                or available_profiles.get(fallback_uuid, True)
            ):
                return fallback_uuid
            return None

        # Unrecognised mode: return first available
        return priority_uuids[0] if priority_uuids else None

    def _to_response(self, record: dict[str, Any]) -> RuntimeProfileResponse:
        """Convert an internal record to a response model."""
        provider_priority = record.get("provider_priority")
        priority_uuids = None
        if provider_priority:
            priority_uuids = [UUID(p) for p in provider_priority]

        fallback = record.get("fallback_model_profile_id")
        fallback_uuid = UUID(fallback) if isinstance(fallback, str) else fallback

        return RuntimeProfileResponse(
            id=record["id"],
            runtime_profile_slug=record["runtime_profile_slug"],
            mode=record["mode"],
            fallback_model_profile_id=fallback_uuid,
            provider_priority=priority_uuids,
            max_concurrent_requests=record.get("max_concurrent_requests"),
            timeout_seconds=record.get("timeout_seconds"),
            retry_config=record.get("retry_config"),
            created_at=record.get("created_at"),
            updated_at=record.get("updated_at"),
        )

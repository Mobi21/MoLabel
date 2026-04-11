"""Model profile management service (PV-008).

Handles CRUD operations, connectivity testing, and one-click switching
for model profiles.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlalchemy import text

from molabel.core.providers.base import ProviderError
from molabel.core.types import HealthStatus, ModelInfo, ProviderType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class ModelProfileCreate(BaseModel):
    """Request schema for creating a model profile."""

    model_profile_slug: str
    provider_type: ProviderType
    provider_name: str | None = None
    model_identifier: str
    transport: str = "https"
    auth_ref: str | None = None
    base_url: str | None = None
    supports_structured_output: bool | None = None
    supports_tool_use: bool | None = None
    context_window: int | None = None
    cost_per_input_token: float | None = None
    cost_per_output_token: float | None = None
    capability_tags: list[str] | None = None
    routing_metadata: dict[str, Any] | None = None


class ModelProfileUpdate(BaseModel):
    """Request schema for updating a model profile."""

    model_profile_slug: str | None = None
    provider_name: str | None = None
    model_identifier: str | None = None
    transport: str | None = None
    auth_ref: str | None = None
    base_url: str | None = None
    supports_structured_output: bool | None = None
    supports_tool_use: bool | None = None
    context_window: int | None = None
    cost_per_input_token: float | None = None
    cost_per_output_token: float | None = None
    capability_tags: list[str] | None = None
    routing_metadata: dict[str, Any] | None = None


class ModelProfileResponse(BaseModel):
    """Response schema for a model profile."""

    id: UUID
    model_profile_slug: str
    provider_type: str
    provider_name: str | None = None
    model_identifier: str
    transport: str
    auth_ref: str | None = None
    supports_structured_output: bool | None = None
    supports_tool_use: bool | None = None
    context_window: int | None = None
    cost_per_input_token: float | None = None
    cost_per_output_token: float | None = None
    is_available: bool | None = None
    capability_tags: list[str] | None = None
    routing_metadata: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ConnectivityTestResult(BaseModel):
    """Result of testing connectivity to a model profile's provider."""

    profile_id: UUID
    health: HealthStatus
    available_models: list[ModelInfo] = []
    error: str | None = None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ModelProfileService:
    """Manages model profile CRUD and connectivity testing.

    When *engine* is provided, data is persisted in SQLite via raw SQL
    (matching the app-layer pattern). Without an engine the service falls
    back to in-memory dicts for unit-test convenience.
    """

    def __init__(self, engine: Any | None = None) -> None:
        self._engine = engine
        # Fallback in-memory store when no DB engine is provided.
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
                    "INSERT INTO model_profiles "
                    "(id, workspace_id, model_profile_slug, provider_type, "
                    "provider_name, model_identifier, transport, auth_ref, "
                    "supports_structured_output, supports_tool_use, "
                    "context_window, cost_per_input_token, cost_per_output_token, "
                    "is_available, capability_tags, routing_metadata, "
                    "created_at, updated_at) "
                    "VALUES (:id, :workspace_id, :model_profile_slug, :provider_type, "
                    ":provider_name, :model_identifier, :transport, :auth_ref, "
                    ":supports_structured_output, :supports_tool_use, "
                    ":context_window, :cost_per_input_token, :cost_per_output_token, "
                    ":is_available, :capability_tags, :routing_metadata, "
                    ":created_at, :updated_at)"
                ),
                {
                    "id": str(record["id"]),
                    "workspace_id": str(record["workspace_id"]),
                    "model_profile_slug": record["model_profile_slug"],
                    "provider_type": str(record["provider_type"]),
                    "provider_name": record.get("provider_name"),
                    "model_identifier": record["model_identifier"],
                    "transport": record["transport"],
                    "auth_ref": record.get("auth_ref"),
                    "supports_structured_output": record.get(
                        "supports_structured_output"
                    ),
                    "supports_tool_use": record.get("supports_tool_use"),
                    "context_window": record.get("context_window"),
                    "cost_per_input_token": record.get("cost_per_input_token"),
                    "cost_per_output_token": record.get("cost_per_output_token"),
                    "is_available": record.get("is_available"),
                    "capability_tags": json.dumps(record.get("capability_tags")),
                    "routing_metadata": json.dumps(record.get("routing_metadata")),
                    "created_at": record["created_at"].isoformat(),
                    "updated_at": record["updated_at"].isoformat(),
                },
            )
            conn.commit()

    def _db_get(self, profile_id: UUID) -> dict[str, Any] | None:
        with self._engine.connect() as conn:
            row = (
                conn.execute(
                    text("SELECT * FROM model_profiles WHERE id = :id"),
                    {"id": str(profile_id)},
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        return self._row_to_record(row)

    def _db_list(
        self, workspace_id: UUID, provider_type: str | None = None
    ) -> list[dict[str, Any]]:
        with self._engine.connect() as conn:
            if provider_type:
                rows = (
                    conn.execute(
                        text(
                            "SELECT * FROM model_profiles "
                            "WHERE workspace_id = :wid AND provider_type = :pt"
                        ),
                        {"wid": str(workspace_id), "pt": provider_type},
                    )
                    .mappings()
                    .all()
                )
            else:
                rows = (
                    conn.execute(
                        text("SELECT * FROM model_profiles WHERE workspace_id = :wid"),
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
            if key in ("capability_tags", "routing_metadata"):
                sets.append(f"{key} = :{key}")
                params[key] = json.dumps(value)
            elif key in ("created_at", "updated_at"):
                sets.append(f"{key} = :{key}")
                params[key] = value.isoformat() if value else None
            else:
                sets.append(f"{key} = :{key}")
                params[key] = str(value) if isinstance(value, UUID) else value
        if not sets:
            return
        sql = f"UPDATE model_profiles SET {', '.join(sets)} WHERE id = :id"
        with self._engine.connect() as conn:
            conn.execute(text(sql), params)
            conn.commit()

    def _db_delete(self, profile_id: UUID) -> bool:
        with self._engine.connect() as conn:
            result = conn.execute(
                text("DELETE FROM model_profiles WHERE id = :id"),
                {"id": str(profile_id)},
            )
            conn.commit()
            return result.rowcount > 0

    @staticmethod
    def _row_to_record(row: Any) -> dict[str, Any]:
        cap_tags = row["capability_tags"]
        if isinstance(cap_tags, str):
            cap_tags = json.loads(cap_tags)
        routing_meta = row["routing_metadata"]
        if isinstance(routing_meta, str):
            routing_meta = json.loads(routing_meta)
        created = row["created_at"]
        if isinstance(created, str):
            created = datetime.fromisoformat(created)
        updated = row["updated_at"]
        if isinstance(updated, str):
            updated = datetime.fromisoformat(updated)
        return {
            "id": UUID(row["id"]) if isinstance(row["id"], str) else row["id"],
            "workspace_id": (
                UUID(row["workspace_id"])
                if isinstance(row["workspace_id"], str)
                else row["workspace_id"]
            ),
            "model_profile_slug": row["model_profile_slug"],
            "provider_type": row["provider_type"],
            "provider_name": row.get("provider_name"),
            "model_identifier": row["model_identifier"],
            "transport": row["transport"],
            "auth_ref": row.get("auth_ref"),
            "supports_structured_output": row.get("supports_structured_output"),
            "supports_tool_use": row.get("supports_tool_use"),
            "context_window": row.get("context_window"),
            "cost_per_input_token": row.get("cost_per_input_token"),
            "cost_per_output_token": row.get("cost_per_output_token"),
            "is_available": row.get("is_available"),
            "capability_tags": cap_tags,
            "routing_metadata": routing_meta,
            "created_at": created,
            "updated_at": updated,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create(
        self,
        data: ModelProfileCreate,
        workspace_id: UUID,
    ) -> ModelProfileResponse:
        """Create a new model profile."""
        profile_id = uuid4()
        now = datetime.now(UTC)

        # Persist base_url in routing_metadata so it survives DB round-trips
        routing_metadata = dict(data.routing_metadata) if data.routing_metadata else {}
        if data.base_url:
            routing_metadata["base_url"] = data.base_url

        record = {
            "id": profile_id,
            "workspace_id": workspace_id,
            "model_profile_slug": data.model_profile_slug,
            "provider_type": data.provider_type,
            "provider_name": data.provider_name,
            "model_identifier": data.model_identifier,
            "transport": data.transport,
            "auth_ref": data.auth_ref,
            "base_url": data.base_url,
            "supports_structured_output": data.supports_structured_output,
            "supports_tool_use": data.supports_tool_use,
            "context_window": data.context_window,
            "cost_per_input_token": data.cost_per_input_token,
            "cost_per_output_token": data.cost_per_output_token,
            "is_available": None,
            "capability_tags": data.capability_tags,
            "routing_metadata": routing_metadata,
            "created_at": now,
            "updated_at": now,
        }

        if self._use_db():
            self._db_insert(record)
        else:
            self._profiles[profile_id] = record

        return self._to_response(record)

    def get(self, profile_id: UUID) -> ModelProfileResponse | None:
        """Get a model profile by ID."""
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
        *,
        provider_type: str | None = None,
    ) -> list[ModelProfileResponse]:
        """List model profiles for a workspace."""
        if self._use_db():
            records = self._db_list(workspace_id, provider_type)
            return [self._to_response(r) for r in records]

        results: list[ModelProfileResponse] = []
        for record in self._profiles.values():
            if record["workspace_id"] != workspace_id:
                continue
            if provider_type and record["provider_type"] != provider_type:
                continue
            results.append(self._to_response(record))
        return results

    def update(
        self,
        profile_id: UUID,
        data: ModelProfileUpdate,
    ) -> ModelProfileResponse | None:
        """Update an existing model profile."""
        if self._use_db():
            record = self._db_get(profile_id)
        else:
            record = self._profiles.get(profile_id)
        if record is None:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if key in record:
                record[key] = value
        record["updated_at"] = datetime.now(UTC)

        if self._use_db():
            self._db_update(profile_id, record)
        return self._to_response(record)

    def delete(self, profile_id: UUID) -> bool:
        """Delete a model profile. Returns True if it existed."""
        if self._use_db():
            return self._db_delete(profile_id)
        return self._profiles.pop(profile_id, None) is not None

    def test_connectivity(self, profile_id: UUID) -> ConnectivityTestResult:
        """Test connectivity to the provider configured in a profile.

        Creates the appropriate adapter and runs health check + model list.
        """
        if self._use_db():
            record = self._db_get(profile_id)
        else:
            record = self._profiles.get(profile_id)
        if record is None:
            return ConnectivityTestResult(
                profile_id=profile_id,
                health=HealthStatus(is_healthy=False, error="Profile not found"),
            )

        try:
            adapter = self._create_adapter(record)
            health = adapter.check_health()
            models: list[ModelInfo] = []
            if health.is_healthy:
                import contextlib

                with contextlib.suppress(Exception):
                    models = adapter.list_models()

            # Update availability
            record["is_available"] = health.is_healthy
            record["updated_at"] = datetime.now(UTC)
            if self._use_db():
                self._db_update(
                    profile_id,
                    {
                        "is_available": health.is_healthy,
                        "updated_at": record["updated_at"],
                    },
                )

            return ConnectivityTestResult(
                profile_id=profile_id,
                health=health,
                available_models=models,
            )
        except Exception as exc:
            record["is_available"] = False
            record["updated_at"] = datetime.now(UTC)
            if self._use_db():
                self._db_update(
                    profile_id,
                    {
                        "is_available": False,
                        "updated_at": record["updated_at"],
                    },
                )
            return ConnectivityTestResult(
                profile_id=profile_id,
                health=HealthStatus(is_healthy=False, error=str(exc)),
                error=str(exc),
            )

    def _create_adapter(self, record: dict[str, Any]) -> Any:
        """Create a provider adapter from a profile record."""
        provider_type = record["provider_type"]
        auth_ref = record.get("auth_ref")
        base_url = record.get("base_url")
        # Fall back to routing_metadata for DB round-tripped records
        if not base_url:
            rm = record.get("routing_metadata")
            if isinstance(rm, dict):
                base_url = rm.get("base_url")

        if provider_type == ProviderType.openai_compatible:
            from molabel.core.providers.openai_adapter import OpenAIAdapter

            kwargs: dict[str, Any] = {"auth_ref": auth_ref}
            if base_url:
                kwargs["base_url"] = base_url
            return OpenAIAdapter(**kwargs)

        if provider_type == ProviderType.openrouter:
            from molabel.core.providers.openrouter_adapter import OpenRouterAdapter

            return OpenRouterAdapter(auth_ref=auth_ref)

        if provider_type == ProviderType.ollama:
            from molabel.core.providers.ollama_adapter import OllamaAdapter

            kwargs = {}
            if base_url:
                kwargs["base_url"] = base_url
            return OllamaAdapter(**kwargs)

        if provider_type == ProviderType.anthropic:
            from molabel.core.providers.anthropic_adapter import AnthropicAdapter

            kwargs: dict[str, Any] = {"auth_ref": auth_ref}
            if base_url:
                kwargs["base_url"] = base_url
            return AnthropicAdapter(**kwargs)

        if provider_type == ProviderType.custom:
            from molabel.core.providers.custom_adapter import CustomAdapter

            return CustomAdapter()

        raise ProviderError(
            f"Unknown provider type: {provider_type}",
            provider=str(provider_type),
        )

    def _to_response(self, record: dict[str, Any]) -> ModelProfileResponse:
        """Convert an internal record to a response model."""
        return ModelProfileResponse(
            id=record["id"],
            model_profile_slug=record["model_profile_slug"],
            provider_type=record["provider_type"],
            provider_name=record.get("provider_name"),
            model_identifier=record["model_identifier"],
            transport=record["transport"],
            auth_ref=record.get("auth_ref"),
            supports_structured_output=record.get("supports_structured_output"),
            supports_tool_use=record.get("supports_tool_use"),
            context_window=record.get("context_window"),
            cost_per_input_token=record.get("cost_per_input_token"),
            cost_per_output_token=record.get("cost_per_output_token"),
            is_available=record.get("is_available"),
            capability_tags=record.get("capability_tags"),
            routing_metadata=record.get("routing_metadata"),
            created_at=record.get("created_at"),
            updated_at=record.get("updated_at"),
        )

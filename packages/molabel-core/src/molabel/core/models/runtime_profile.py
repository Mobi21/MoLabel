"""RuntimeProfile domain model (DM-010)."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Index
from sqlmodel import JSON, Column, Field, Relationship, SQLModel

if TYPE_CHECKING:
    from molabel.core.models.model_profile import ModelProfile
    from molabel.core.models.workspace import Workspace


class RuntimeProfile(SQLModel, table=True):
    """Runtime routing and concurrency configuration."""

    __tablename__ = "runtime_profiles"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    runtime_profile_slug: str
    mode: str
    fallback_model_profile_id: uuid.UUID | None = Field(
        default=None, foreign_key="model_profiles.id"
    )
    provider_priority: list | None = Field(default=None, sa_column=Column(JSON))
    max_concurrent_requests: int | None = None
    timeout_seconds: int | None = None
    retry_config: dict | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # -- foreign keys --
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id")

    # -- relationships --
    workspace: "Workspace" = Relationship(back_populates="runtime_profiles")
    fallback_model_profile: Optional["ModelProfile"] = Relationship(
        back_populates="fallback_runtime_profiles"
    )

    __table_args__ = (
        Index("idx_runtime_profiles_slug", "runtime_profile_slug"),
        Index("idx_runtime_profiles_workspace_id", "workspace_id"),
    )

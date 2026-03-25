"""ModelProfile domain model (DM-009)."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Index
from sqlmodel import JSON, Column, Field, Relationship, SQLModel

from molabel.core.types import ProviderType

if TYPE_CHECKING:
    from molabel.core.models.cost_record import CostRecord
    from molabel.core.models.runtime_profile import RuntimeProfile
    from molabel.core.models.workspace import Workspace


class ModelProfile(SQLModel, table=True):
    """Configuration for an LLM provider and model."""

    __tablename__ = "model_profiles"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    model_profile_slug: str
    provider_type: ProviderType
    provider_name: str | None = None
    model_identifier: str
    transport: str
    auth_ref: str | None = None
    supports_structured_output: bool | None = None
    supports_tool_use: bool | None = None
    context_window: int | None = None
    capability_tags: list | None = Field(default=None, sa_column=Column(JSON))
    routing_metadata: dict | None = Field(default=None, sa_column=Column(JSON))
    cost_per_input_token: float | None = None
    cost_per_output_token: float | None = None
    is_available: bool | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # -- foreign keys --
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id")

    # -- relationships --
    workspace: "Workspace" = Relationship(back_populates="model_profiles")
    fallback_runtime_profiles: list["RuntimeProfile"] = Relationship(
        back_populates="fallback_model_profile"
    )
    cost_records: list["CostRecord"] = Relationship(back_populates="model_profile")

    __table_args__ = (
        Index("idx_model_profiles_slug", "model_profile_slug"),
        Index("idx_model_profiles_workspace_id", "workspace_id"),
    )

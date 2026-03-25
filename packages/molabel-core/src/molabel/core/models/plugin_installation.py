"""PluginInstallation domain model (DM-027)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Index
from sqlmodel import JSON, Column, Field, SQLModel


class PluginInstallation(SQLModel, table=True):
    """Tracks an installed plugin and its workspace-level configuration."""

    __tablename__ = "plugin_installations"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    plugin_id: str
    plugin_version: str
    plugin_type: str
    compatible_core_version: str
    entrypoint: str
    is_enabled: bool = Field(default=True)
    is_compatible: bool = Field(default=True)
    capabilities: dict | None = Field(default=None, sa_column=Column(JSON))
    config: dict | None = Field(default=None, sa_column=Column(JSON))
    installed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # -- foreign keys --
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id")

    __table_args__ = (
        Index("idx_plugin_installations_plugin_id", "plugin_id"),
        Index("idx_plugin_installations_workspace_id", "workspace_id"),
    )

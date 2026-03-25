"""LabelMapping domain model (DM-023)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Index
from sqlmodel import JSON, Column, Field, SQLModel

from molabel.core.types import TrustLevel


class LabelMapping(SQLModel, table=True):
    """Maps external label formats to MoLabel's internal schema."""

    __tablename__ = "label_mappings"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    mapping_slug: str
    name: str
    source_system: str
    source_format: str | None = None
    task_schema_id: uuid.UUID = Field(foreign_key="task_schemas.id")
    field_mappings: dict = Field(sa_column=Column(JSON, nullable=False))
    value_mappings: dict | None = Field(default=None, sa_column=Column(JSON))
    type_conversions: dict | None = Field(default=None, sa_column=Column(JSON))
    unmapped_field_policy: str = Field(default="preserve_reference")
    default_trust_level: TrustLevel
    file_path: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # -- foreign keys --
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id")

    __table_args__ = (
        Index("idx_label_mappings_slug", "mapping_slug"),
        Index("idx_label_mappings_workspace_id", "workspace_id"),
    )

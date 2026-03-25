"""TaskSchema domain model (DM-008)."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Index
from sqlmodel import JSON, Column, Field, Relationship, SQLModel

from molabel.core.types import BlindReviewPolicy

if TYPE_CHECKING:
    from molabel.core.models.workspace import Workspace


class TaskSchema(SQLModel, table=True):
    """Defines a labelling task: fields, instructions, review policies."""

    __tablename__ = "task_schemas"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    task_schema_slug: str
    version: int
    task_type: str
    title: str
    instructions: str | None = None
    record_selector: dict | None = Field(default=None, sa_column=Column(JSON))
    label_fields: dict = Field(sa_column=Column(JSON, nullable=False))
    required_fields: list | None = Field(default=None, sa_column=Column(JSON))
    optional_fields: list | None = Field(default=None, sa_column=Column(JSON))
    blind_review_policy: BlindReviewPolicy
    overlap_policy: dict | None = Field(default=None, sa_column=Column(JSON))
    adjudication_policy: dict | None = Field(default=None, sa_column=Column(JSON))
    supported_agent_roles: list | None = Field(default=None, sa_column=Column(JSON))
    default_model_profile_id: uuid.UUID | None = Field(
        default=None, foreign_key="model_profiles.id"
    )
    export_mapping: dict | None = Field(default=None, sa_column=Column(JSON))
    is_active: bool = True
    is_frozen: bool = False
    file_path: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # -- foreign keys --
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id")

    # -- relationships --
    workspace: "Workspace" = Relationship(back_populates="task_schemas")

    __table_args__ = (
        Index("idx_task_schemas_slug", "task_schema_slug"),
        Index("idx_task_schemas_workspace_id", "workspace_id"),
    )

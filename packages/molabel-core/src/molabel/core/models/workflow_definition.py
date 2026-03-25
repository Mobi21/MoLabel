"""WorkflowDefinition domain model (DM-017)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Index
from sqlmodel import JSON, Column, Field, SQLModel


class WorkflowDefinition(SQLModel, table=True):
    """A versioned workflow definition with composable steps."""

    __tablename__ = "workflow_definitions"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workflow_slug: str
    version: int
    name: str
    description: str | None = None
    steps: list = Field(sa_column=Column(JSON, nullable=False))
    is_template: bool = Field(default=False)
    template_source: str | None = None
    file_path: str
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # -- foreign keys --
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id")

    __table_args__ = (
        Index("idx_workflow_definitions_slug", "workflow_slug"),
        Index("idx_workflow_definitions_workspace_id", "workspace_id"),
    )

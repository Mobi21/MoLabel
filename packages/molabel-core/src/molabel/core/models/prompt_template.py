"""PromptTemplate domain model (DM-020)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Index
from sqlmodel import JSON, Column, Field, SQLModel


class PromptTemplate(SQLModel, table=True):
    """A versioned prompt template for agent-driven labelling."""

    __tablename__ = "prompt_templates"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    prompt_slug: str
    version: str
    name: str
    description: str | None = None
    system_instructions: str
    task_rubric: str | None = None
    few_shot_examples: list | None = Field(default=None, sa_column=Column(JSON))
    instruction_patches: list | None = Field(default=None, sa_column=Column(JSON))
    output_schema: dict | None = Field(default=None, sa_column=Column(JSON))
    parent_version_id: uuid.UUID | None = Field(
        default=None, foreign_key="prompt_templates.id"
    )
    refinement_source_batch_id: uuid.UUID | None = None
    is_frozen: bool = Field(default=False)
    file_path: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # -- foreign keys --
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id")

    __table_args__ = (
        Index("idx_prompt_templates_slug", "prompt_slug"),
        Index("idx_prompt_templates_workspace_id", "workspace_id"),
    )

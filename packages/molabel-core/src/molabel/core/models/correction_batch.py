"""CorrectionBatch domain model (DM-021)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Index
from sqlmodel import JSON, Column, Field, SQLModel

from molabel.core.types import CorrectionBatchStatus


class CorrectionBatch(SQLModel, table=True):
    """Accumulated human corrections used to refine a prompt template."""

    __tablename__ = "correction_batches"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    prompt_template_id: uuid.UUID = Field(foreign_key="prompt_templates.id")
    batch_sequence: int
    status: CorrectionBatchStatus
    correction_count: int = Field(default=0)
    batch_threshold: int = Field(default=25)
    corrections: list | None = Field(default=None, sa_column=Column(JSON))
    analysis_results: dict | None = Field(default=None, sa_column=Column(JSON))
    proposed_refinements: dict | None = Field(default=None, sa_column=Column(JSON))
    applied_prompt_version_id: uuid.UUID | None = Field(
        default=None, foreign_key="prompt_templates.id"
    )
    file_path: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    analyzed_at: datetime | None = None
    applied_at: datetime | None = None

    # -- foreign keys --
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id")

    __table_args__ = (
        Index("idx_correction_batches_template_id", "prompt_template_id"),
        Index("idx_correction_batches_workspace_id", "workspace_id"),
    )

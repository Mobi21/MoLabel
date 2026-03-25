"""Adjudication domain model (DM-016)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Index
from sqlmodel import JSON, Column, Field, SQLModel

from molabel.core.types import AdjudicationResolution


class Adjudication(SQLModel, table=True):
    """Resolution record for conflicting review events on a record."""

    __tablename__ = "adjudications"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    record_id: uuid.UUID = Field(foreign_key="records.id")
    dataset_id: uuid.UUID = Field(foreign_key="datasets.id")
    task_schema_id: uuid.UUID = Field(foreign_key="task_schemas.id")
    adjudicator_id: uuid.UUID = Field(foreign_key="reviewer_profiles.id")
    workflow_step_execution_id: uuid.UUID | None = Field(
        default=None, foreign_key="workflow_step_executions.id"
    )
    conflicting_event_ids: list = Field(sa_column=Column(JSON, nullable=False))
    resolution: AdjudicationResolution
    resolved_labels: dict | None = Field(default=None, sa_column=Column(JSON))
    rationale: str | None = None
    policy_reference: str | None = None
    metadata_: dict | None = Field(default=None, sa_column=Column("metadata", JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # -- foreign keys --
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id")

    __table_args__ = (
        Index("idx_adjudications_record_id", "record_id"),
        Index("idx_adjudications_workspace_id", "workspace_id"),
    )

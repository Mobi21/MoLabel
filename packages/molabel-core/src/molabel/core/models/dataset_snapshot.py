"""DatasetSnapshot domain model (DM-022)."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Index
from sqlmodel import JSON, Column, Field, Relationship, SQLModel

if TYPE_CHECKING:
    from molabel.core.models.dataset import Dataset


class DatasetSnapshot(SQLModel, table=True):
    """A point-in-time snapshot of dataset state and quality metrics."""

    __tablename__ = "dataset_snapshots"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    dataset_id: uuid.UUID = Field(foreign_key="datasets.id")
    workflow_step_execution_id: uuid.UUID | None = Field(
        default=None, foreign_key="workflow_step_executions.id"
    )
    name: str
    description: str | None = None
    snapshot_type: str  # "full" or "delta"
    parent_snapshot_id: uuid.UUID | None = Field(
        default=None, foreign_key="dataset_snapshots.id"
    )
    record_count: int
    labeled_count: int
    quality_metrics: dict | None = Field(default=None, sa_column=Column(JSON))
    label_summary: dict | None = Field(default=None, sa_column=Column(JSON))
    dataset_membership: dict | None = Field(default=None, sa_column=Column(JSON))
    workflow_state: dict | None = Field(default=None, sa_column=Column(JSON))
    prompt_versions: dict | None = Field(default=None, sa_column=Column(JSON))
    project_config: dict | None = Field(default=None, sa_column=Column(JSON))
    delta_data: dict | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # -- foreign keys --
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id")

    # -- relationships --
    dataset: "Dataset" = Relationship(back_populates="dataset_snapshots")

    __table_args__ = (
        Index("idx_dataset_snapshots_dataset_id", "dataset_id"),
        Index("idx_dataset_snapshots_workspace_id", "workspace_id"),
    )

"""Dataset domain model (DM-006)."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Index
from sqlmodel import JSON, Column, Field, Relationship, SQLModel

from molabel.core.types import DatasetHealthStatus

if TYPE_CHECKING:
    from molabel.core.models.artifact import Artifact
    from molabel.core.models.dataset_snapshot import DatasetSnapshot
    from molabel.core.models.record import Record
    from molabel.core.models.workspace import Workspace


class Dataset(SQLModel, table=True):
    """A named collection of records within a workspace."""

    __tablename__ = "datasets"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    dataset_name: str
    dataset_slug: str
    description: str | None = None
    source_type: str
    source_config: dict | None = Field(default=None, sa_column=Column(JSON))
    loader_plugin: str | None = None
    record_kind: str | None = None
    canonical_id_strategy: str
    indexing_mode: str
    record_count: int | None = None
    labeled_count: int | None = None
    health_status: DatasetHealthStatus | None = None
    tags: list | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_indexed_at: datetime | None = None

    # -- foreign keys --
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id")

    # -- relationships --
    workspace: "Workspace" = Relationship(back_populates="datasets")
    records: list["Record"] = Relationship(back_populates="dataset")
    artifacts: list["Artifact"] = Relationship(back_populates="dataset")
    dataset_snapshots: list["DatasetSnapshot"] = Relationship(back_populates="dataset")

    __table_args__ = (
        Index("idx_datasets_slug", "dataset_slug"),
        Index("idx_datasets_workspace_id", "workspace_id"),
    )

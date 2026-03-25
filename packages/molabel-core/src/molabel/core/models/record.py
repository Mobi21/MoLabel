"""Record domain model (DM-007)."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Index
from sqlmodel import JSON, Column, Field, Relationship, SQLModel

if TYPE_CHECKING:
    from molabel.core.models.dataset import Dataset


class Record(SQLModel, table=True):
    """An individual data record within a dataset."""

    __tablename__ = "records"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    external_id: str | None = None
    sequence_index: int | None = None
    content_hash: str | None = None
    stable_fields: dict = Field(sa_column=Column(JSON, nullable=False))
    payload: dict | None = Field(default=None, sa_column=Column(JSON))
    record_kind: str | None = None
    source_metadata: dict | None = Field(default=None, sa_column=Column(JSON))
    label_count: int | None = Field(default=0)
    latest_label: dict | None = Field(default=None, sa_column=Column(JSON))
    composite_confidence: float | None = None
    export_eligible: bool = Field(default=False)
    flags: list | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # -- foreign keys --
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id")
    dataset_id: uuid.UUID = Field(foreign_key="datasets.id")
    artifact_id: uuid.UUID | None = Field(default=None, foreign_key="artifacts.id")

    # -- relationships --
    dataset: "Dataset" = Relationship(back_populates="records")

    __table_args__ = (
        Index("idx_records_dataset_id", "dataset_id"),
        Index("idx_records_dataset_export", "dataset_id", "export_eligible"),
        Index("idx_records_content_hash", "content_hash"),
        Index("idx_records_composite_confidence", "dataset_id", "composite_confidence"),
        Index("idx_records_external_id", "external_id"),
        Index("idx_records_workspace_id", "workspace_id"),
    )

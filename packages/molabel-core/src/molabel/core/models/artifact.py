"""Artifact domain model (DM-005)."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Optional

from sqlmodel import JSON, Column, Field, Relationship, SQLModel

if TYPE_CHECKING:
    from molabel.core.models.dataset import Dataset
    from molabel.core.models.workspace import Workspace


class Artifact(SQLModel, table=True):
    """An indexed source file belonging to a workspace."""

    __tablename__ = "artifacts"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    file_path: str
    file_hash: str
    file_size_bytes: int
    file_format: str
    record_count: int | None = None
    loader_plugin: str | None = None
    metadata_: dict | None = Field(default=None, sa_column=Column("metadata", JSON))
    stale: bool = False
    indexed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # -- foreign keys --
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id")
    dataset_id: uuid.UUID | None = Field(default=None, foreign_key="datasets.id")

    # -- relationships --
    workspace: "Workspace" = Relationship(back_populates="artifacts")
    dataset: Optional["Dataset"] = Relationship(back_populates="artifacts")

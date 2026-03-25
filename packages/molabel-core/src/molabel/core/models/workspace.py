"""Workspace domain model (DM-004)."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlmodel import JSON, Column, Field, Relationship, SQLModel

if TYPE_CHECKING:
    from molabel.core.models.artifact import Artifact
    from molabel.core.models.cost_record import CostRecord
    from molabel.core.models.dataset import Dataset
    from molabel.core.models.model_profile import ModelProfile
    from molabel.core.models.reviewer_profile import ReviewerProfile
    from molabel.core.models.runtime_profile import RuntimeProfile
    from molabel.core.models.task_schema import TaskSchema


class Workspace(SQLModel, table=True):
    """A MoLabel workspace -- the top-level organisational unit."""

    __tablename__ = "workspaces"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_name: str
    workspace_slug: str = Field(index=True, unique=True)
    core_version: str
    root_path: str
    manifest_path: str
    reference_app: str | None = None
    settings: dict | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # -- relationships --
    datasets: list["Dataset"] = Relationship(back_populates="workspace")
    artifacts: list["Artifact"] = Relationship(back_populates="workspace")
    task_schemas: list["TaskSchema"] = Relationship(back_populates="workspace")
    model_profiles: list["ModelProfile"] = Relationship(back_populates="workspace")
    runtime_profiles: list["RuntimeProfile"] = Relationship(back_populates="workspace")
    reviewer_profiles: list["ReviewerProfile"] = Relationship(
        back_populates="workspace"
    )
    cost_records: list["CostRecord"] = Relationship(back_populates="workspace")

    __table_args__: tuple = ()  # slug index created by Field(index=True, unique=True)

"""ExportBundle domain model (DM-025)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Index
from sqlmodel import JSON, Column, Field, SQLModel

from molabel.core.types import ExportBundleStatus, ExportFormat


class ExportBundle(SQLModel, table=True):
    """A packaged dataset export in a specific format."""

    __tablename__ = "export_bundles"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    dataset_id: uuid.UUID = Field(foreign_key="datasets.id")
    task_schema_id: uuid.UUID = Field(foreign_key="task_schemas.id")
    workflow_step_execution_id: uuid.UUID | None = Field(
        default=None, foreign_key="workflow_step_executions.id"
    )
    export_slug: str
    status: ExportBundleStatus
    export_format: ExportFormat
    output_path: str
    output_namespace: str | None = None
    record_count: int
    include_config: dict | None = Field(default=None, sa_column=Column(JSON))
    filter_config: dict | None = Field(default=None, sa_column=Column(JSON))
    file_hash: str | None = None
    file_size_bytes: int | None = None
    source_snapshot_id: uuid.UUID | None = Field(
        default=None, foreign_key="dataset_snapshots.id"
    )
    validation_run_id: uuid.UUID | None = None
    packager_plugin: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # -- foreign keys --
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id")

    __table_args__ = (
        Index("idx_export_bundles_dataset_id", "dataset_id"),
        Index("idx_export_bundles_workspace_id", "workspace_id"),
    )

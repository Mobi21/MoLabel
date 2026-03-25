"""ValidationRun domain model (DM-024)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Index
from sqlmodel import JSON, Column, Field, SQLModel

from molabel.core.types import ValidationStatus


class ValidationRun(SQLModel, table=True):
    """Tracks execution of validation gates against a dataset or export."""

    __tablename__ = "validation_runs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    target_type: str
    target_id: uuid.UUID
    workflow_step_execution_id: uuid.UUID | None = Field(
        default=None, foreign_key="workflow_step_executions.id"
    )
    validation_plugin: str | None = None
    status: ValidationStatus
    gates: dict | None = Field(default=None, sa_column=Column(JSON))
    passed_gate_count: int | None = None
    total_gate_count: int | None = None
    summary: str | None = None
    report_path: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # -- foreign keys --
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id")

    __table_args__ = (
        Index("idx_validation_runs_target", "target_type", "target_id"),
        Index("idx_validation_runs_workspace_id", "workspace_id"),
    )

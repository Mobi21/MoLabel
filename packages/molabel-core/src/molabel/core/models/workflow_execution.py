"""WorkflowExecution domain model (DM-018)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Index
from sqlmodel import JSON, Column, Field, SQLModel

from molabel.core.types import WorkflowExecutionStatus


class WorkflowExecution(SQLModel, table=True):
    """A running or completed instance of a workflow definition."""

    __tablename__ = "workflow_executions"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workflow_definition_id: uuid.UUID = Field(foreign_key="workflow_definitions.id")
    workflow_version: int
    status: WorkflowExecutionStatus
    current_step_id: str | None = None
    step_execution_count: int | None = None
    context: dict | None = Field(default=None, sa_column=Column(JSON))
    error_summary: str | None = None
    started_at: datetime | None = None
    paused_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # -- foreign keys --
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id")

    __table_args__ = (
        Index("idx_workflow_executions_def_id", "workflow_definition_id"),
        Index("idx_workflow_executions_status", "status"),
        Index("idx_workflow_executions_workspace_id", "workspace_id"),
    )

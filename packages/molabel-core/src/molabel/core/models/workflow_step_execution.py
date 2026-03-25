"""WorkflowStepExecution domain model (DM-019)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Index
from sqlmodel import JSON, Column, Field, SQLModel

from molabel.core.types import WorkflowStepExecutionStatus, WorkflowStepType


class WorkflowStepExecution(SQLModel, table=True):
    """Execution state for an individual step within a workflow run."""

    __tablename__ = "workflow_step_executions"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workflow_execution_id: uuid.UUID = Field(foreign_key="workflow_executions.id")
    step_id: str
    step_type: WorkflowStepType
    step_config: dict = Field(sa_column=Column(JSON, nullable=False))
    status: WorkflowStepExecutionStatus
    iteration: int = Field(default=0)
    parent_step_execution_id: uuid.UUID | None = Field(
        default=None, foreign_key="workflow_step_executions.id"
    )
    result: dict | None = Field(default=None, sa_column=Column(JSON))
    error_summary: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # -- foreign keys --
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id")

    __table_args__ = (
        Index("idx_wf_step_exec_execution_id", "workflow_execution_id"),
        Index("idx_wf_step_exec_status", "status"),
        Index("idx_wf_step_exec_workspace_id", "workspace_id"),
    )

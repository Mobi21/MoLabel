"""AgentRun domain model (DM-013)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Index
from sqlmodel import JSON, Column, Field, SQLModel

from molabel.core.types import AgentRole, AgentRunStatus


class AgentRun(SQLModel, table=True):
    """Tracks a single batch execution of an AI agent."""

    __tablename__ = "agent_runs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    dataset_id: uuid.UUID = Field(foreign_key="datasets.id")
    task_schema_id: uuid.UUID = Field(foreign_key="task_schemas.id")
    model_profile_id: uuid.UUID = Field(foreign_key="model_profiles.id")
    runtime_profile_id: uuid.UUID | None = Field(
        default=None, foreign_key="runtime_profiles.id"
    )
    prompt_template_id: uuid.UUID | None = None
    prompt_version: str | None = None
    agent_role: AgentRole
    adapter_plugin: str | None = None
    status: AgentRunStatus
    config: dict | None = Field(default=None, sa_column=Column(JSON))
    record_filter: dict | None = Field(default=None, sa_column=Column(JSON))
    total_records: int | None = None
    completed_records: int | None = None
    failed_records: int | None = None
    retry_count: int = Field(default=0)
    error_summary: str | None = None
    cost_estimate: dict | None = Field(default=None, sa_column=Column(JSON))
    cost_actual: dict | None = Field(default=None, sa_column=Column(JSON))
    comparison_id: uuid.UUID | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # -- foreign keys --
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id")
    workflow_step_execution_id: uuid.UUID | None = Field(
        default=None, foreign_key="workflow_step_executions.id"
    )

    __table_args__ = (
        Index("idx_agent_runs_dataset_id", "dataset_id"),
        Index("idx_agent_runs_status", "status"),
        Index("idx_agent_runs_workspace_id", "workspace_id"),
    )

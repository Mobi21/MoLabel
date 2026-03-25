"""AgentOutput domain model (DM-015)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Index
from sqlmodel import JSON, Column, Field, SQLModel


class AgentOutput(SQLModel, table=True):
    """Per-record output produced by an agent run."""

    __tablename__ = "agent_outputs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    agent_run_id: uuid.UUID = Field(foreign_key="agent_runs.id")
    record_id: uuid.UUID = Field(foreign_key="records.id")
    task_schema_id: uuid.UUID = Field(foreign_key="task_schemas.id")
    output_type: str
    labels: dict = Field(sa_column=Column(JSON, nullable=False))
    raw_response: dict | None = Field(default=None, sa_column=Column(JSON))
    confidence_self_reported: float | None = None
    confidence_self_consistency: float | None = None
    confidence_logprobs: float | None = None
    composite_confidence: float | None = None
    tokens_input: int | None = None
    tokens_output: int | None = None
    latency_ms: int | None = None
    validation_passed: bool
    validation_errors: list | None = Field(default=None, sa_column=Column(JSON))
    retry_attempt: int = Field(default=0)
    is_visible_for_review: bool = Field(default=False)
    normalization_status: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # -- foreign keys --
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id")

    __table_args__ = (
        Index("idx_agent_outputs_run_id", "agent_run_id"),
        Index("idx_agent_outputs_record_id", "record_id"),
        Index("idx_agent_outputs_workspace_id", "workspace_id"),
    )

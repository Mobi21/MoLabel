"""AgentEvent domain model (DM-014)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Index
from sqlmodel import JSON, Column, Field, SQLModel

from molabel.core.types import AgentEventType


class AgentEvent(SQLModel, table=True):
    """An ordered event within an agent run for progress tracking."""

    __tablename__ = "agent_events"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    agent_run_id: uuid.UUID = Field(foreign_key="agent_runs.id")
    event_type: AgentEventType
    record_id: uuid.UUID | None = Field(default=None, foreign_key="records.id")
    sequence_number: int
    payload: dict | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    __table_args__ = (
        Index("idx_agent_events_run_id", "agent_run_id"),
        Index("idx_agent_events_run_seq", "agent_run_id", "sequence_number"),
    )

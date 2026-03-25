"""ReviewEvent domain model (DM-012).

Append-only ledger of every label decision (human, agent, or import).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Index
from sqlmodel import JSON, Column, Field, SQLModel

from molabel.core.types import ReviewDecision, ReviewEventSource, TrustLevel


class ReviewEvent(SQLModel, table=True):
    """An immutable record of a single review decision."""

    __tablename__ = "review_events"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    review_task_id: uuid.UUID | None = Field(
        default=None, foreign_key="review_tasks.id"
    )
    record_id: uuid.UUID = Field(foreign_key="records.id")
    task_schema_id: uuid.UUID = Field(foreign_key="task_schemas.id")
    task_schema_version: int
    reviewer_id: uuid.UUID | None = Field(
        default=None, foreign_key="reviewer_profiles.id"
    )
    source: ReviewEventSource
    source_system: str | None = None
    source_file: str | None = None
    trust_level: TrustLevel | None = None
    decision: ReviewDecision | None = None
    labels: dict = Field(sa_column=Column(JSON, nullable=False))
    previous_labels: dict | None = Field(default=None, sa_column=Column(JSON))
    rationale: str | None = None
    confidence: float | None = None
    ai_was_revealed: bool | None = Field(default=None)
    review_duration_ms: int | None = None
    agent_run_id: uuid.UUID | None = Field(default=None, foreign_key="agent_runs.id")
    agent_output_id: uuid.UUID | None = Field(
        default=None, foreign_key="agent_outputs.id"
    )
    unmapped_fields: dict | None = Field(default=None, sa_column=Column(JSON))
    supersedes_event_id: uuid.UUID | None = Field(
        default=None, foreign_key="review_events.id"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # -- foreign keys --
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id")

    __table_args__ = (
        Index("idx_review_events_task_id", "review_task_id"),
        Index("idx_review_events_record_id", "record_id"),
        Index("idx_review_events_reviewer_id", "reviewer_id"),
        Index("idx_review_events_workspace_id", "workspace_id"),
    )

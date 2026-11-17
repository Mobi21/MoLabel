"""ReviewEvent domain model (DM-012).

Append-only ledger of every label decision (human, agent, or import).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Index
from sqlmodel import JSON, Column, Field, SQLModel

from molabel.core.database import HyphenatedUuid
from molabel.core.types import ReviewEventSource, TrustLevel


class ReviewEvent(SQLModel, table=True):
    """An immutable record of a single review decision."""

    __tablename__ = "review_events"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4, primary_key=True, sa_type=HyphenatedUuid
    )
    review_task_id: uuid.UUID | None = Field(
        default=None, foreign_key="review_tasks.id", sa_type=HyphenatedUuid
    )
    record_id: uuid.UUID = Field(foreign_key="records.id", sa_type=HyphenatedUuid)
    task_schema_id: uuid.UUID = Field(
        foreign_key="task_schemas.id", sa_type=HyphenatedUuid
    )
    task_schema_version: int
    reviewer_id: uuid.UUID | None = Field(
        default=None, foreign_key="reviewer_profiles.id", sa_type=HyphenatedUuid
    )
    source: ReviewEventSource
    source_system: str | None = None
    source_file: str | None = None
    trust_level: TrustLevel | None = None
    # A ReviewDecision value, or a pre-rename name such as accept_ai on old rows.
    decision: str | None = None
    labels: dict = Field(sa_column=Column(JSON, nullable=False))
    previous_labels: dict | None = Field(default=None, sa_column=Column(JSON))
    rationale: str | None = None
    confidence: float | None = None
    ai_was_revealed: bool | None = Field(default=None)
    review_duration_ms: int | None = None
    agent_run_id: uuid.UUID | None = Field(
        default=None, foreign_key="agent_runs.id", sa_type=HyphenatedUuid
    )
    agent_output_id: uuid.UUID | None = Field(
        default=None, foreign_key="agent_outputs.id", sa_type=HyphenatedUuid
    )
    unmapped_fields: dict | None = Field(default=None, sa_column=Column(JSON))
    supersedes_event_id: uuid.UUID | None = Field(
        default=None, foreign_key="review_events.id", sa_type=HyphenatedUuid
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # -- foreign keys --
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id", sa_type=HyphenatedUuid)

    __table_args__ = (
        Index("idx_review_events_task_id", "review_task_id"),
        Index("idx_review_events_record_id", "record_id"),
        Index("idx_review_events_reviewer_id", "reviewer_id"),
        Index("idx_review_events_supersedes_event_id", "supersedes_event_id"),
        Index("idx_review_events_workspace_id", "workspace_id"),
    )

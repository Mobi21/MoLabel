"""ReviewTask domain model (DM-011)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Index
from sqlmodel import JSON, Column, Field, SQLModel

from molabel.core.types import ReviewTaskStatus


class ReviewTask(SQLModel, table=True):
    """A single review item in a human-review queue."""

    __tablename__ = "review_tasks"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    queue_id: str
    record_id: uuid.UUID = Field(foreign_key="records.id")
    task_schema_id: uuid.UUID = Field(foreign_key="task_schemas.id")
    status: ReviewTaskStatus
    priority: int
    priority_reason: str | None = None
    claimed_by: uuid.UUID | None = Field(
        default=None, foreign_key="reviewer_profiles.id"
    )
    claimed_at: datetime | None = None
    claim_expired_count: int = Field(default=0)
    is_overlap: bool = Field(default=False)
    is_calibration: bool = Field(default=False)
    draft_labels: dict | None = Field(default=None, sa_column=Column(JSON))
    agent_output_ids: str | None = Field(default=None)
    ai_revealed: bool = Field(default=False)
    ai_revealed_at: datetime | None = None
    submitted_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # -- foreign keys --
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id")
    dataset_id: uuid.UUID = Field(foreign_key="datasets.id")

    __table_args__ = (
        Index("idx_review_tasks_queue_status", "queue_id", "status"),
        Index("idx_review_tasks_record_id", "record_id"),
        Index("idx_review_tasks_claimed_by", "claimed_by"),
        Index("idx_review_tasks_workspace_id", "workspace_id"),
    )

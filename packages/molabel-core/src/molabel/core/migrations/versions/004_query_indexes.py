"""Index the correction chain and each dataset's records by creation time.

``review_events.supersedes_event_id`` is what every "counted event" query
tests with NOT EXISTS, once per event, and without an index that is a scan
of the whole table per event. ``records(dataset_id, created_at)`` serves the
record listing's filter and its newest-first order without sorting the
dataset. ``review_tasks(claimed_by, queue_id, record_id)`` lets the queue
listing probe for the reviewer's own copy of a record instead of walking
the queue per task, and replaces the index on ``claimed_by`` alone, which it
covers as a prefix. docs/performance.md has the measurements.

Revision ID: 004
Revises: 003
Create Date: 2026-11-16
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "idx_review_events_supersedes_event_id",
        "review_events",
        ["supersedes_event_id"],
        unique=False,
    )
    op.create_index(
        "idx_records_dataset_created_at",
        "records",
        ["dataset_id", "created_at"],
        unique=False,
    )
    op.drop_index("idx_review_tasks_claimed_by", table_name="review_tasks")
    op.create_index(
        "idx_review_tasks_claimed_by_queue_record",
        "review_tasks",
        ["claimed_by", "queue_id", "record_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_review_tasks_claimed_by_queue_record", table_name="review_tasks")
    op.create_index(
        "idx_review_tasks_claimed_by", "review_tasks", ["claimed_by"], unique=False
    )
    op.drop_index("idx_records_dataset_created_at", table_name="records")
    op.drop_index("idx_review_events_supersedes_event_id", table_name="review_events")

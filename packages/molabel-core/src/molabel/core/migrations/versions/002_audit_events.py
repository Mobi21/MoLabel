"""Add audit_events, which routes used to create on first write.

Revision ID: 002
Revises: 001
Create Date: 2026-11-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A pre-Alembic database already has this table if any route wrote an
    # audit event. Its columns match, but its id was a nullable TEXT key, and
    # the artifact route created it without the workspace index. Rebuild it
    # with the rows kept.
    if sa.inspect(op.get_bind()).has_table("audit_events"):
        with op.batch_alter_table("audit_events", recreate="always") as batch:
            batch.alter_column("id", existing_type=sa.Text(), nullable=False)
    else:
        op.create_table(
            "audit_events",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("workspace_id", sa.Text(), nullable=True),
            sa.Column("event_type", sa.Text(), nullable=True),
            sa.Column("actor", sa.Text(), nullable=True),
            sa.Column("actor_name", sa.Text(), nullable=True),
            sa.Column("object_type", sa.Text(), nullable=True),
            sa.Column("object_id", sa.Text(), nullable=True),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("details", sa.Text(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    op.create_index(
        "idx_audit_events_workspace_id",
        "audit_events",
        ["workspace_id"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("idx_audit_events_workspace_id", table_name="audit_events")
    op.drop_table("audit_events")

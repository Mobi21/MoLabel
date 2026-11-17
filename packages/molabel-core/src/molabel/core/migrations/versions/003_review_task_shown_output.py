"""Record on each review task the agent output its claimant was shown.

Revision ID: 003
Revises: 002
Create Date: 2026-11-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("review_tasks") as batch:
        batch.add_column(sa.Column("shown_agent_output_id", sa.Uuid(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("review_tasks") as batch:
        batch.drop_column("shown_agent_output_id")

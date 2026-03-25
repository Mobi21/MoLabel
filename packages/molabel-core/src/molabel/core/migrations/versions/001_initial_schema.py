"""Initial schema — creates all tables from SQLModel metadata.

Revision ID: 001
Revises: None
Create Date: 2026-03-23
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlmodel import SQLModel

# Import all models so their tables are registered on SQLModel.metadata.
import molabel.core.models  # noqa: F401

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create all tables defined in the SQLModel metadata."""
    bind = op.get_bind()
    SQLModel.metadata.create_all(bind)


def downgrade() -> None:
    """Drop all tables defined in the SQLModel metadata."""
    bind = op.get_bind()
    SQLModel.metadata.drop_all(bind)

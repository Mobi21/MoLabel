"""SavedView domain model (DM-029)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Index
from sqlmodel import JSON, Column, Field, SQLModel

from molabel.core.database import HyphenatedUuid


class SavedView(SQLModel, table=True):
    """A user-saved filter/sort/column configuration for a list view."""

    __tablename__ = "saved_views"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4, primary_key=True, sa_type=HyphenatedUuid
    )
    owner_id: uuid.UUID | None = Field(
        default=None, foreign_key="reviewer_profiles.id", sa_type=HyphenatedUuid
    )
    view_name: str
    description: str | None = None
    view_type: str
    target_dataset_id: uuid.UUID | None = Field(
        default=None, foreign_key="datasets.id", sa_type=HyphenatedUuid
    )
    filters: dict = Field(sa_column=Column(JSON, nullable=False))
    sort_config: dict | None = Field(default=None, sa_column=Column(JSON))
    column_config: dict | None = Field(default=None, sa_column=Column(JSON))
    grouping: dict | None = Field(default=None, sa_column=Column(JSON))
    is_default: bool = Field(default=False)
    is_shared: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # -- foreign keys --
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id", sa_type=HyphenatedUuid)

    __table_args__ = (
        Index("idx_saved_views_view_type", "view_type"),
        Index("idx_saved_views_workspace_id", "workspace_id"),
    )

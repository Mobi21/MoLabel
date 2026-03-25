"""ReviewerProfile domain model (DM-030)."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlmodel import JSON, Column, Field, Relationship, SQLModel

if TYPE_CHECKING:
    from molabel.core.models.workspace import Workspace


class ReviewerProfile(SQLModel, table=True):
    """A human reviewer identity for queue assignment and provenance tracking.

    Note: the data model spec defines reviewer_profiles as global (not
    workspace-scoped).  For Phase-1 we keep a workspace FK so that the
    single-workspace constraint is easy to enforce; this can be relaxed in
    a future migration.
    """

    __tablename__ = "reviewer_profiles"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    display_name: str
    avatar_color: str | None = None
    is_operator: bool = Field(default=False)
    is_active: bool = Field(default=True)
    preferences: dict | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_active_at: datetime | None = None

    # -- foreign keys --
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id")

    # -- relationships --
    workspace: "Workspace" = Relationship(back_populates="reviewer_profiles")

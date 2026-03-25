"""Release domain model (DM-026)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Index
from sqlmodel import JSON, Column, Field, SQLModel

from molabel.core.types import ReleaseStatus


class Release(SQLModel, table=True):
    """A versioned dataset release with validation and approval tracking."""

    __tablename__ = "releases"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    release_slug: str
    version: str
    name: str
    description: str | None = None
    status: ReleaseStatus
    export_bundle_ids: list = Field(sa_column=Column(JSON, nullable=False))
    validation_run_ids: list | None = Field(default=None, sa_column=Column(JSON))
    dataset_snapshot_id: uuid.UUID | None = Field(
        default=None, foreign_key="dataset_snapshots.id"
    )
    quality_summary: dict | None = Field(default=None, sa_column=Column(JSON))
    signed_off_by: uuid.UUID | None = Field(
        default=None, foreign_key="reviewer_profiles.id"
    )
    signed_off_at: datetime | None = None
    release_metadata: dict | None = Field(default=None, sa_column=Column(JSON))
    manifest_path: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    released_at: datetime | None = None
    revoked_at: datetime | None = None

    # -- foreign keys --
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id")

    __table_args__ = (
        Index("idx_releases_release_slug", "release_slug"),
        Index("idx_releases_workspace_id", "workspace_id"),
    )

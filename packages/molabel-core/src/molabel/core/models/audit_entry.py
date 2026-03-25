"""AuditEntry domain model (DM-028)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Index
from sqlmodel import JSON, Column, Field, SQLModel

from molabel.core.types import AuditAction


class AuditEntry(SQLModel, table=True):
    """Immutable audit log entry for workspace-level events."""

    __tablename__ = "audit_entries"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    action: AuditAction
    actor_type: str
    actor_id: str | None = None
    target_type: str
    target_id: uuid.UUID
    detail: dict | None = Field(default=None, sa_column=Column(JSON))
    file_path: str | None = None
    file_hash_before: str | None = None
    file_hash_after: str | None = None
    session_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # -- foreign keys --
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id")

    __table_args__ = (
        Index("idx_audit_entries_action", "action"),
        Index("idx_audit_entries_target", "target_type", "target_id"),
        Index("idx_audit_entries_workspace_id", "workspace_id"),
    )

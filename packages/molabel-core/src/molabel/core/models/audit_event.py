"""AuditEvent: the audit trail written by the audit, release and artifact routes."""

from sqlalchemy import Index, Text
from sqlmodel import Column, Field, SQLModel


class AuditEvent(SQLModel, table=True):
    """One audit trail row. Columns are TEXT to match rows written before Alembic."""

    __tablename__ = "audit_events"

    id: str = Field(sa_column=Column(Text, primary_key=True))
    workspace_id: str | None = Field(default=None, sa_column=Column(Text))
    event_type: str | None = Field(default=None, sa_column=Column(Text))
    actor: str | None = Field(default=None, sa_column=Column(Text))
    actor_name: str | None = Field(default=None, sa_column=Column(Text))
    object_type: str | None = Field(default=None, sa_column=Column(Text))
    object_id: str | None = Field(default=None, sa_column=Column(Text))
    summary: str | None = Field(default=None, sa_column=Column(Text))
    details: str | None = Field(default=None, sa_column=Column(Text))
    created_at: str | None = Field(default=None, sa_column=Column(Text))

    __table_args__ = (Index("idx_audit_events_workspace_id", "workspace_id"),)

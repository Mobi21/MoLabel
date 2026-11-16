-- The audit_events table that the audit, release and artifact routes created
-- with CREATE TABLE IF NOT EXISTS before Alembic owned the schema.

CREATE TABLE IF NOT EXISTS audit_events (id TEXT PRIMARY KEY, workspace_id TEXT, event_type TEXT, actor TEXT, actor_name TEXT, object_type TEXT, object_id TEXT, summary TEXT, details TEXT, created_at TEXT);

CREATE INDEX IF NOT EXISTS idx_audit_events_workspace_id ON audit_events(workspace_id);

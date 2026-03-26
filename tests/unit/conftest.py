"""Shared fixtures for unit tests.

Provides common database setup, workspace/reviewer creation, and
FastAPI test client fixtures used across test_session.py and
test_queue_claims.py.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine

from molabel.app.main import create_app
from molabel.app.services.session import reset_last_active_cache

# ---------------------------------------------------------------------------
# Lightweight data holders (avoid triggering SQLAlchemy mapper config)
# ---------------------------------------------------------------------------

TEST_SECRET = "test-secret-for-unit-tests-only"


@dataclass
class WorkspaceData:
    """Holds workspace fields for test reference without ORM."""

    id: uuid.UUID
    workspace_name: str
    workspace_slug: str


@dataclass
class ReviewerData:
    """Holds reviewer profile fields for test reference without ORM."""

    id: uuid.UUID
    display_name: str
    avatar_color: str
    workspace_id: uuid.UUID


@dataclass
class TaskData:
    """Holds review task fields for test reference without ORM."""

    id: uuid.UUID
    queue_id: str
    record_id: uuid.UUID
    task_schema_id: uuid.UUID
    workspace_id: uuid.UUID
    dataset_id: uuid.UUID
    priority: int


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def engine():
    """Create an in-memory SQLite engine with all tables needed for tests.

    Tables are created via raw DDL to avoid foreign-key issues with tables
    not needed by session/claim tests.
    """
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with eng.connect() as conn:
        conn.execute(
            text("""
            CREATE TABLE workspaces (
                id TEXT PRIMARY KEY,
                workspace_name TEXT NOT NULL,
                workspace_slug TEXT NOT NULL UNIQUE,
                core_version TEXT NOT NULL,
                root_path TEXT NOT NULL,
                manifest_path TEXT NOT NULL,
                reference_app TEXT,
                settings TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        )
        conn.execute(
            text("""
            CREATE TABLE reviewer_profiles (
                id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                avatar_color TEXT,
                is_operator INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                preferences TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                last_active_at TEXT,
                workspace_id TEXT NOT NULL REFERENCES workspaces(id)
            )
        """)
        )
        conn.execute(
            text("""
            CREATE TABLE review_tasks (
                id TEXT PRIMARY KEY,
                queue_id TEXT NOT NULL,
                record_id TEXT NOT NULL,
                task_schema_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'available'
                    CHECK(status IN ('available','claimed','submitted','skipped')),
                priority INTEGER NOT NULL DEFAULT 0,
                priority_reason TEXT,
                claimed_by TEXT REFERENCES reviewer_profiles(id),
                claimed_at TEXT,
                claim_expired_count INTEGER NOT NULL DEFAULT 0,
                is_overlap INTEGER NOT NULL DEFAULT 0,
                is_calibration INTEGER NOT NULL DEFAULT 0,
                draft_labels TEXT,
                ai_revealed INTEGER NOT NULL DEFAULT 0,
                ai_revealed_at TEXT,
                submitted_at TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                workspace_id TEXT NOT NULL,
                dataset_id TEXT NOT NULL
            )
        """)
        )
        conn.execute(
            text("""
            CREATE TABLE review_events (
                id TEXT PRIMARY KEY,
                review_task_id TEXT,
                record_id TEXT NOT NULL,
                task_schema_id TEXT NOT NULL,
                task_schema_version INTEGER NOT NULL,
                reviewer_id TEXT,
                source TEXT NOT NULL,
                source_system TEXT,
                source_file TEXT,
                trust_level TEXT,
                decision TEXT,
                labels TEXT NOT NULL,
                previous_labels TEXT,
                rationale TEXT,
                confidence REAL,
                ai_was_revealed INTEGER,
                review_duration_ms INTEGER,
                agent_run_id TEXT,
                agent_output_id TEXT,
                unmapped_fields TEXT,
                supersedes_event_id TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                workspace_id TEXT NOT NULL
            )
        """)
        )
        conn.execute(
            text("""
            CREATE TABLE task_schemas (
                id TEXT PRIMARY KEY,
                task_schema_slug TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                task_type TEXT NOT NULL,
                title TEXT NOT NULL,
                instructions TEXT,
                record_selector TEXT,
                label_fields TEXT NOT NULL,
                required_fields TEXT,
                optional_fields TEXT,
                blind_review_policy TEXT NOT NULL
                    DEFAULT 'hide_agent_outputs_by_default',
                overlap_policy TEXT,
                adjudication_policy TEXT,
                supported_agent_roles TEXT,
                default_model_profile_id TEXT,
                export_mapping TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                is_frozen INTEGER NOT NULL DEFAULT 0,
                file_path TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                workspace_id TEXT NOT NULL REFERENCES workspaces(id)
            )
        """)
        )
        conn.execute(
            text("""
            CREATE TABLE agent_outputs (
                id TEXT PRIMARY KEY,
                agent_run_id TEXT NOT NULL,
                record_id TEXT NOT NULL,
                task_schema_id TEXT NOT NULL,
                output_type TEXT NOT NULL,
                labels TEXT NOT NULL,
                raw_response TEXT,
                confidence_self_reported REAL,
                confidence_self_consistency REAL,
                confidence_logprobs REAL,
                composite_confidence REAL,
                tokens_input INTEGER,
                tokens_output INTEGER,
                latency_ms INTEGER,
                validation_passed INTEGER NOT NULL DEFAULT 1,
                validation_errors TEXT,
                retry_attempt INTEGER NOT NULL DEFAULT 0,
                is_visible_for_review INTEGER NOT NULL DEFAULT 0,
                normalization_status TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                workspace_id TEXT NOT NULL
            )
        """)
        )
        conn.execute(
            text("""
            CREATE INDEX idx_review_tasks_queue_status
                ON review_tasks(queue_id, status, priority DESC, created_at ASC)
        """)
        )
        conn.execute(
            text("""
            CREATE INDEX idx_review_tasks_claimed_by
                ON review_tasks(claimed_by)
        """)
        )
        conn.execute(
            text("""
            CREATE INDEX idx_review_events_task_id
                ON review_events(review_task_id)
        """)
        )
        conn.commit()
    return eng


# ---------------------------------------------------------------------------
# Workspace / reviewer fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def workspace(engine) -> WorkspaceData:
    """Insert a test workspace via raw SQL."""
    ws_id = uuid.uuid4()
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO workspaces (id, workspace_name, workspace_slug, "
                "core_version, root_path, manifest_path) "
                "VALUES (:id, :name, :slug, :ver, :path, :manifest)"
            ),
            {
                "id": str(ws_id),
                "name": "Test Workspace",
                "slug": "test-workspace",
                "ver": "0.1.0",
                "path": "/tmp/test",
                "manifest": "/tmp/test/workbench.project.yaml",
            },
        )
        conn.commit()
    return WorkspaceData(
        id=ws_id,
        workspace_name="Test Workspace",
        workspace_slug="test-workspace",
    )


def insert_reviewer(
    engine,
    workspace: WorkspaceData,
    *,
    display_name: str = "Test Reviewer",
    avatar_color: str = "#4A90D9",
    last_active_at_expr: str | None = None,
) -> ReviewerData:
    """Helper to insert a reviewer profile via raw SQL.

    Parameters
    ----------
    last_active_at_expr:
        A SQLite expression for ``last_active_at``.  ``None`` uses the
        current timestamp; pass a string like ``"datetime('now', '-15 minutes')"``
        for idle/offline reviewers.
    """
    r_id = uuid.uuid4()
    now = datetime.now(UTC).isoformat()

    lat_sql = ":now" if last_active_at_expr is None else last_active_at_expr

    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO reviewer_profiles "
                "(id, display_name, avatar_color, is_operator, is_active, "
                f"workspace_id, created_at, last_active_at) "
                f"VALUES (:id, :name, :color, 0, 1, :ws, :now, {lat_sql})"
            ),
            {
                "id": str(r_id),
                "name": display_name,
                "color": avatar_color,
                "ws": str(workspace.id),
                "now": now,
            },
        )
        conn.commit()
    return ReviewerData(
        id=r_id,
        display_name=display_name,
        avatar_color=avatar_color,
        workspace_id=workspace.id,
    )


@pytest.fixture()
def reviewer(engine, workspace) -> ReviewerData:
    """Insert a test reviewer profile via raw SQL."""
    return insert_reviewer(engine, workspace)


@pytest.fixture()
def second_reviewer(engine, workspace) -> ReviewerData:
    """Insert a second test reviewer profile via raw SQL."""
    return insert_reviewer(
        engine, workspace, display_name="Second Reviewer", avatar_color="#E67E22"
    )


# ---------------------------------------------------------------------------
# App / client fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def app(engine):
    """Create a test FastAPI application with an in-memory database."""
    application = create_app()
    application.state.engine = engine
    application.state.app_secret = TEST_SECRET
    return application


@pytest.fixture()
def client(app):
    """Create a test HTTP client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_debounce_cache():
    """Reset the debounce cache between tests."""
    reset_last_active_cache()
    yield
    reset_last_active_cache()

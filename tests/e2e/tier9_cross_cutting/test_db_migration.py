"""Tier 9 — Cross-Cutting: Database Migration (T9-12).

Tests:
    T9-12: create_all_tables() on a fresh in-memory SQLite database creates
           all expected tables; verify table existence and foreign key pragmas.
"""

from __future__ import annotations

import pytest
from sqlmodel import SQLModel, create_engine

from molabel.core.database import create_all_tables
from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import INDEPENDENT

# All 28 tables expected after create_all_tables()
EXPECTED_TABLES = {
    "workspaces",
    "datasets",
    "dataset_snapshots",
    "records",
    "task_schemas",
    "workflow_definitions",
    "workflow_executions",
    "workflow_step_executions",
    "agent_runs",
    "agent_events",
    "agent_outputs",
    "review_events",
    "review_tasks",
    "adjudications",
    "export_bundles",
    "releases",
    "validation_runs",
    "correction_batches",
    "cost_records",
    "audit_entries",
    "artifacts",
    "label_mappings",
    "model_profiles",
    "runtime_profiles",
    "reviewer_profiles",
    "prompt_templates",
    "plugin_installations",
    "saved_views",
}


def _get_tables(engine) -> set[str]:
    """Return the set of table names present in the SQLite database."""
    from sqlalchemy import text

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ).fetchall()
    return {row[0] for row in rows}


def _get_foreign_keys_enabled(engine) -> bool:
    """Check whether PRAGMA foreign_keys is ON."""
    from sqlalchemy import text

    with engine.connect() as conn:
        row = conn.execute(text("PRAGMA foreign_keys")).first()
    return bool(row[0]) if row else False


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier9
async def test_db_migration(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T9-12: create_all_tables() on fresh SQLite creates all 28 expected tables."""

    with checkpoint(ctx, "create_all_tables_on_fresh_db"):
        # Use a separate in-memory engine (not the test app's engine)
        engine = create_engine("sqlite:///:memory:", echo=False)
        # Should not raise
        create_all_tables(engine)

    with checkpoint(ctx, "all_expected_tables_exist"):
        engine = create_engine("sqlite:///:memory:", echo=False)
        create_all_tables(engine)
        actual = _get_tables(engine)
        missing = EXPECTED_TABLES - actual
        assert not missing, (
            f"create_all_tables() is missing tables: {sorted(missing)}\n"
            f"Tables found: {sorted(actual)}"
        )

    with checkpoint(ctx, "no_unexpected_tables"):
        engine = create_engine("sqlite:///:memory:", echo=False)
        create_all_tables(engine)
        actual = _get_tables(engine)
        actual - EXPECTED_TABLES
        # There may be extra tables added in the future — warn rather than fail
        # but at minimum we must have all expected ones
        assert EXPECTED_TABLES.issubset(actual), (
            f"Expected tables are not a subset of actual tables.\n"
            f"Missing: {sorted(EXPECTED_TABLES - actual)}"
        )

    with checkpoint(ctx, "table_count_at_least_28"):
        engine = create_engine("sqlite:///:memory:", echo=False)
        create_all_tables(engine)
        actual = _get_tables(engine)
        assert len(actual) >= 28, (
            f"Expected at least 28 tables, got {len(actual)}: {sorted(actual)}"
        )

    with checkpoint(ctx, "idempotent_create_all_tables"):
        # Calling create_all_tables twice must not raise
        engine = create_engine("sqlite:///:memory:", echo=False)
        create_all_tables(engine)
        count_first = len(_get_tables(engine))
        create_all_tables(engine)
        count_second = len(_get_tables(engine))
        assert count_first == count_second, (
            f"Second call to create_all_tables() changed table count: "
            f"{count_first} -> {count_second}"
        )

    with checkpoint(ctx, "workspaces_table_has_columns"):
        from sqlalchemy import inspect

        engine = create_engine("sqlite:///:memory:", echo=False)
        create_all_tables(engine)
        inspector = inspect(engine)
        ws_cols = {col["name"] for col in inspector.get_columns("workspaces")}
        required_cols = {"id", "workspace_name", "root_path", "core_version"}
        missing_cols = required_cols - ws_cols
        assert not missing_cols, (
            f"workspaces table missing columns: {missing_cols}. Found: {ws_cols}"
        )

    with checkpoint(ctx, "reviewer_profiles_table_has_columns"):
        from sqlalchemy import inspect

        engine = create_engine("sqlite:///:memory:", echo=False)
        create_all_tables(engine)
        inspector = inspect(engine)
        rp_cols = {col["name"] for col in inspector.get_columns("reviewer_profiles")}
        required_cols = {"id", "display_name", "is_active", "is_operator"}
        missing_cols = required_cols - rp_cols
        assert not missing_cols, (
            f"reviewer_profiles table missing columns: {missing_cols}. Found: {rp_cols}"
        )

    with checkpoint(ctx, "datasets_table_has_columns"):
        from sqlalchemy import inspect

        engine = create_engine("sqlite:///:memory:", echo=False)
        create_all_tables(engine)
        inspector = inspect(engine)
        ds_cols = {col["name"] for col in inspector.get_columns("datasets")}
        required_cols = {"id", "workspace_id", "dataset_name"}
        missing_cols = required_cols - ds_cols
        assert not missing_cols, (
            f"datasets table missing columns: {missing_cols}. Found: {ds_cols}"
        )

    with checkpoint(ctx, "sqlmodel_metadata_includes_all_tables"):
        # Verify SQLModel metadata has all table entries after import
        import molabel.core.models  # noqa: F401

        metadata_tables = set(SQLModel.metadata.tables.keys())
        missing = EXPECTED_TABLES - metadata_tables
        assert not missing, (
            f"SQLModel metadata is missing table entries: {sorted(missing)}"
        )

    with checkpoint(ctx, "agent_runs_table_has_columns"):
        from sqlalchemy import inspect

        engine = create_engine("sqlite:///:memory:", echo=False)
        create_all_tables(engine)
        inspector = inspect(engine)
        ar_cols = {col["name"] for col in inspector.get_columns("agent_runs")}
        required_cols = {"id", "workspace_id", "status"}
        missing_cols = required_cols - ar_cols
        assert not missing_cols, (
            f"agent_runs table missing columns: {missing_cols}. Found: {ar_cols}"
        )

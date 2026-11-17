"""Store every UUID in its hyphenated form (#29).

The SQLModel ORM stored UUIDs as 32-character hex while every route stored
them hyphenated through raw SQL, so once foreign keys were enforced a row
from one path could not reference a row from the other, and ``session.get``
never found a route's row. Every UUID column now uses
``molabel.core.database.HyphenatedUuid``, and this revision rewrites the hex
values already stored, in every UUID column of every table at this
revision, to the hyphenated form. A value that is not 32 hex characters is
left alone, so the rewrite is a no-op on hyphenated data and on a second
run. ``upgrade_database`` runs it with foreign keys off, which rewriting a
referenced primary key needs; the rows that reference it are rewritten in
the same transaction.

The revision is one-way. Downgrade changes nothing and logs a warning that
points to the backup ``upgrade_database`` wrote before the upgrade.
``sa.Uuid`` reads the hyphenated form, and the routes always wrote it, so an
older release runs on these rows unchanged. It writes new ORM rows as hex
again, the mix this revision removes.

Revision ID: 005
Revises: 004
Create Date: 2026-11-17
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID_COLUMNS: dict[str, tuple[str, ...]] = {
    "adjudications": (
        "id",
        "record_id",
        "dataset_id",
        "task_schema_id",
        "adjudicator_id",
        "workflow_step_execution_id",
        "workspace_id",
    ),
    "agent_events": ("id", "agent_run_id", "record_id"),
    "agent_outputs": (
        "id",
        "agent_run_id",
        "record_id",
        "task_schema_id",
        "workspace_id",
    ),
    "agent_runs": (
        "id",
        "dataset_id",
        "task_schema_id",
        "model_profile_id",
        "runtime_profile_id",
        "prompt_template_id",
        "comparison_id",
        "workspace_id",
        "workflow_step_execution_id",
    ),
    "artifacts": ("id", "workspace_id", "dataset_id"),
    "audit_entries": ("id", "target_id", "workspace_id"),
    "correction_batches": (
        "id",
        "prompt_template_id",
        "applied_prompt_version_id",
        "workspace_id",
    ),
    "cost_records": (
        "id",
        "agent_run_id",
        "agent_output_id",
        "model_profile_id",
        "workspace_id",
    ),
    "dataset_snapshots": (
        "id",
        "dataset_id",
        "workflow_step_execution_id",
        "parent_snapshot_id",
        "workspace_id",
    ),
    "datasets": ("id", "workspace_id"),
    "export_bundles": (
        "id",
        "dataset_id",
        "task_schema_id",
        "workflow_step_execution_id",
        "source_snapshot_id",
        "validation_run_id",
        "workspace_id",
    ),
    "label_mappings": ("id", "task_schema_id", "workspace_id"),
    "model_profiles": ("id", "workspace_id"),
    "plugin_installations": ("id", "workspace_id"),
    "prompt_templates": (
        "id",
        "parent_version_id",
        "refinement_source_batch_id",
        "workspace_id",
    ),
    "records": ("id", "workspace_id", "dataset_id", "artifact_id"),
    "releases": ("id", "dataset_snapshot_id", "signed_off_by", "workspace_id"),
    "review_events": (
        "id",
        "review_task_id",
        "record_id",
        "task_schema_id",
        "reviewer_id",
        "agent_run_id",
        "agent_output_id",
        "supersedes_event_id",
        "workspace_id",
    ),
    "review_tasks": (
        "id",
        "record_id",
        "task_schema_id",
        "claimed_by",
        "shown_agent_output_id",
        "workspace_id",
        "dataset_id",
    ),
    "reviewer_profiles": ("id", "workspace_id"),
    "runtime_profiles": ("id", "fallback_model_profile_id", "workspace_id"),
    "saved_views": ("id", "owner_id", "target_dataset_id", "workspace_id"),
    "task_schemas": ("id", "default_model_profile_id", "workspace_id"),
    "validation_runs": (
        "id",
        "target_id",
        "workflow_step_execution_id",
        "workspace_id",
    ),
    "workflow_definitions": ("id", "workspace_id"),
    "workflow_executions": ("id", "workflow_definition_id", "workspace_id"),
    "workflow_step_executions": (
        "id",
        "workflow_execution_id",
        "parent_step_execution_id",
        "workspace_id",
    ),
    "workspaces": ("id",),
}
"""Every UUID column of every table at revision 004."""

_GROUPS = ((1, 8), (9, 4), (13, 4), (17, 4), (21, 12))
"""The (start, length) of each hyphen-separated group of the 32 hex digits."""


def _hyphenated(column: str) -> str:
    groups = " || '-' || ".join(
        f"substr({column}, {start}, {length})" for start, length in _GROUPS
    )
    return f"lower({groups})"


def upgrade() -> None:
    for table, columns in UUID_COLUMNS.items():
        for column in columns:
            op.execute(
                sa.text(
                    f"UPDATE {table} SET {column} = {_hyphenated(column)} "
                    f"WHERE length({column}) = 32 "
                    f"AND {column} NOT GLOB '*[^0-9a-fA-F]*'"
                )
            )


def downgrade() -> None:
    logging.getLogger("molabel.core.migrations").warning(
        "Revision 005 is one-way. Downgrading it leaves every UUID hyphenated. "
        "To return to the data from before the upgrade, restore the "
        "molabel.backup.<timestamp>.sqlite file that the upgrade wrote beside "
        "the database."
    )

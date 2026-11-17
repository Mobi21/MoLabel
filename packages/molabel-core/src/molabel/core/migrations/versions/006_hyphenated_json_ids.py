"""Store the ids that JSON and text columns hold hyphenated too (#29).

Revision 005 rewrote every UUID column, but a row's id is also copied into
JSON and text columns, in the spelling the writer read from the database. A
workflow copied its records' hex ids into ``workflow_executions.context``;
once 005 rewrote ``records.id``, resuming that workflow into an export
queried the hex ids and exported nothing.

This revision rewrites a value only where ``ID_POSITIONS`` or
``TEXT_ID_COLUMNS`` says an id sits, and only when it is 32 hex characters.
A value anywhere else is never read, so a hash such as
``records.content_hash`` or a sha256 inside a payload stays as it is. A row
with no run of 32 hex digits is skipped in SQL, and a second run finds
nothing to rewrite. ``docs/architecture/database-migrations.md`` lists every
column that holds ids, and why the ones missing here are left alone.

The revision is one-way, as 005 is. Downgrade changes nothing and logs a
warning that points to the backup. Every reader parses the hyphenated form.

Revision ID: 006
Revises: 005
Create Date: 2026-11-17
"""

from __future__ import annotations

import json
import logging
import string
import uuid
from collections.abc import Callable, Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EACH = "*"
"""A path step: each item of a list, or each value of an object."""

KEYS = "<keys>"
"""The last step of a path: each key of an object."""

Path = tuple[str, ...]

_STEP_SUMMARY_IDS: tuple[Path, ...] = (
    ("dataset_id",),
    ("snapshot_id",),
    ("bundle_id",),
    ("agent_run_id",),
    ("agent_run_ids", EACH),
    ("per_model_results", EACH, "agent_run_id"),
)
"""Where a workflow step's summary names a row.

``task_schema_id`` is left out: a step summary copies the configured
selector, which may be a slug, and no lookup reads it back.
"""

ID_POSITIONS: dict[tuple[str, str], tuple[Path, ...]] = {
    ("workflow_executions", "context"): (
        ("workspace_id",),
        ("workflow_execution_id",),
        ("datasets", KEYS),
        ("datasets", EACH, "dataset_id"),
        ("record_sets", EACH, "record_ids", EACH),
        ("agent_run_ids", EACH),
        ("agent_outputs", KEYS),
        ("agent_outputs", EACH, "agent_run_id"),
        ("export_bundle_ids", EACH),
        ("snapshot_ids", EACH),
        *(("step_outputs", EACH, "summary", *path) for path in _STEP_SUMMARY_IDS),
    ),
    ("workflow_step_executions", "result"): tuple(
        ("summary", *path) for path in _STEP_SUMMARY_IDS
    ),
    ("review_tasks", "agent_output_ids"): ((EACH,),),
    ("adjudications", "conflicting_event_ids"): ((EACH,),),
    ("adjudications", "metadata"): (("review_event_id",),),
    ("dataset_snapshots", "dataset_membership"): (("record_states", KEYS),),
    ("saved_views", "filters"): (
        ("dataset_id",),
        ("parent_subset_id",),
        ("selection_criteria", "include_record_ids", EACH),
        ("selection_criteria", "exclude_record_ids", EACH),
    ),
    ("datasets", "source_config"): (("source_dataset_id",), ("source_subset_id",)),
    ("agent_events", "payload"): (
        ("workspace_id",),
        ("dataset_id",),
        ("task_schema_id",),
        ("model_profile_id",),
        ("record_ids", EACH),
    ),
}
"""Where an id sits in each JSON column that holds one, by (table, column)."""

TEXT_ID_COLUMNS: dict[str, tuple[str, ...]] = {
    "audit_events": ("workspace_id", "actor", "object_id"),
}
"""Text columns, not typed as UUIDs, whose whole value is an id."""

_HEX_RUN = "*" + "[0-9a-fA-F]" * 32 + "*"
"""A GLOB for text with 32 hex digits in a row, the only text a hex id is in."""


def _hyphenated(value: Any) -> Any:
    if (
        isinstance(value, str)
        and len(value) == 32
        and all(c in string.hexdigits for c in value)
    ):
        return str(uuid.UUID(value))
    return value


def _rewrite(node: Any, path: Path) -> Any:
    """``node`` with the 32-hex ids at ``path`` hyphenated, and nothing else changed."""
    if not path:
        return _hyphenated(node)
    step, rest = path[0], path[1:]
    if step == KEYS and isinstance(node, dict):
        return {_hyphenated(key): value for key, value in node.items()}
    if step == EACH and isinstance(node, list):
        return [_rewrite(item, rest) for item in node]
    if step == EACH and isinstance(node, dict):
        return {key: _rewrite(value, rest) for key, value in node.items()}
    if isinstance(node, dict) and step in node:
        return {**node, step: _rewrite(node[step], rest)}
    return node


def _json_ids(paths: tuple[Path, ...]) -> Callable[[str], str]:
    def rewrite_document(raw: str) -> str:
        try:
            document = json.loads(raw)
        except json.JSONDecodeError:
            return raw
        rewritten = document
        for path in paths:
            rewritten = _rewrite(rewritten, path)
        return raw if rewritten == document else json.dumps(rewritten)

    return rewrite_document


def _rewrite_column(
    table: str, column: str, rewrite_value: Callable[[str], str]
) -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(f"SELECT id, {column} FROM {table} WHERE {column} GLOB :hex_run"),
        {"hex_run": _HEX_RUN},
    ).fetchall()
    update = sa.text(f"UPDATE {table} SET {column} = :value WHERE id = :id")
    for row_id, raw in rows:
        value = rewrite_value(raw)
        if value != raw:
            bind.execute(update, {"value": value, "id": row_id})


def upgrade() -> None:
    for (table, column), paths in ID_POSITIONS.items():
        _rewrite_column(table, column, _json_ids(paths))
    for table, columns in TEXT_ID_COLUMNS.items():
        for column in columns:
            _rewrite_column(table, column, _hyphenated)


def downgrade() -> None:
    logging.getLogger("molabel.core.migrations").warning(
        "Revision 006 is one-way. Downgrading it leaves the ids in JSON and "
        "text columns hyphenated. "
        "To return to the data from before the upgrade, restore the "
        "molabel.backup.<timestamp>.sqlite file that the upgrade wrote beside "
        "the database."
    )

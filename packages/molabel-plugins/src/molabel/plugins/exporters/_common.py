"""Shared helpers for export packager plugins.

Centralises ``_select_labels`` and ``_build_row`` logic used by all
built-in exporters.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from molabel.core.types import Record, ReviewEvent


def select_labels(
    events: list[ReviewEvent],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Pick the labels to export from a list of review events.

    Strategy (from ``config["label_strategy"]``):
    - ``"latest"`` (default): use the most recent event's labels.
    - ``"first"``: use the earliest event's labels.
    """
    if not events:
        return {}
    strategy = config.get("label_strategy", "latest")
    sorted_events = sorted(
        events,
        key=lambda e: (e.created_at or datetime.min, str(e.id)),
        reverse=(strategy == "latest"),
    )
    return dict(sorted_events[0].labels)


def build_row(
    record: Record,
    labels: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Build the export row dict for a single record."""
    include_metadata = config.get("include_metadata", False)
    columns = config.get("columns")  # optional column filter

    row: dict[str, Any] = {}
    row.update(record.stable_fields)
    row.update(labels)

    if include_metadata:
        row["_record_id"] = str(record.id)
        row["_external_id"] = record.external_id

    if columns:
        row = {k: v for k, v in row.items() if k in columns}

    return row

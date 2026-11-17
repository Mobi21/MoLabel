"""Agent proposals are read once each, however many ids or outputs there are."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import Connection, text

import molabel.app.services.review_events as review_events
from molabel.app.services.review_events import (
    queue_agent_proposals,
    run_agent_proposals,
)
from molabel.core.database import engine_from_url
from molabel.core.migration_runner import upgrade_database

MORE_THAN_SQLITE_BINDS = 33_000
"""SQLite binds at most 32,766 variables in one statement."""


def _seed_review_scope(conn: Connection) -> dict[str, str]:
    """A workspace with one dataset, schema, model profile and record."""
    ids = {
        name: str(uuid.uuid4())
        for name in ("workspace", "dataset", "schema", "profile", "record")
    }
    now = datetime.now(UTC).isoformat()
    conn.execute(
        text(
            "INSERT INTO workspaces (id, workspace_name, workspace_slug, "
            "core_version, root_path, manifest_path, created_at, updated_at) "
            "VALUES (:id, 'w', 'w', '0.1.0', '/w', '/w/m.yaml', :now, :now)"
        ),
        {"id": ids["workspace"], "now": now},
    )
    conn.execute(
        text(
            "INSERT INTO datasets (id, dataset_name, dataset_slug, source_type, "
            "canonical_id_strategy, indexing_mode, created_at, updated_at, "
            "workspace_id) VALUES (:id, 'd', 'd', 'jsonl', 'external_id', "
            "'full', :now, :now, :wid)"
        ),
        {"id": ids["dataset"], "now": now, "wid": ids["workspace"]},
    )
    conn.execute(
        text(
            "INSERT INTO task_schemas (id, task_schema_slug, version, task_type, "
            "title, label_fields, blind_review_policy, is_active, is_frozen, "
            "created_at, updated_at, workspace_id) VALUES (:id, 's', 1, "
            "'classification', 'S', '[]', 'show_agent_outputs', 1, 0, :now, "
            ":now, :wid)"
        ),
        {"id": ids["schema"], "now": now, "wid": ids["workspace"]},
    )
    conn.execute(
        text(
            "INSERT INTO model_profiles (id, model_profile_slug, provider_type, "
            "model_identifier, transport, created_at, updated_at, workspace_id) "
            "VALUES (:id, 'offline', 'offline', 'offline-heuristic', 'builtin', "
            ":now, :now, :wid)"
        ),
        {"id": ids["profile"], "now": now, "wid": ids["workspace"]},
    )
    conn.execute(
        text(
            "INSERT INTO records (id, stable_fields, export_eligible, created_at, "
            "updated_at, workspace_id, dataset_id) VALUES (:id, '{}', 0, :now, "
            ":now, :wid, :did)"
        ),
        {
            "id": ids["record"],
            "now": now,
            "wid": ids["workspace"],
            "did": ids["dataset"],
        },
    )
    return ids


def _seed_agent_run(conn: Connection, ids: dict[str, str], output_count: int) -> str:
    """A completed agent run with ``output_count`` outputs on the one record."""
    run_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    conn.execute(
        text(
            "INSERT INTO agent_runs (id, dataset_id, task_schema_id, "
            "model_profile_id, agent_role, status, retry_count, created_at, "
            "updated_at, workspace_id) VALUES (:id, :did, :sid, :pid, "
            "'proposer', 'completed', 0, :now, :now, :wid)"
        ),
        {
            "id": run_id,
            "did": ids["dataset"],
            "sid": ids["schema"],
            "pid": ids["profile"],
            "now": now,
            "wid": ids["workspace"],
        },
    )
    conn.execute(
        text(
            "INSERT INTO agent_outputs (id, agent_run_id, record_id, "
            "task_schema_id, output_type, labels, validation_passed, "
            "retry_attempt, is_visible_for_review, created_at, workspace_id) "
            "VALUES (:id, :run, :record, :schema, 'label', :labels, 1, 0, 1, "
            ":now, :wid)"
        ),
        [
            {
                "id": str(uuid.uuid4()),
                "run": run_id,
                "record": ids["record"],
                "schema": ids["schema"],
                "labels": json.dumps({"run": run_id, "index": index}),
                "now": now,
                "wid": ids["workspace"],
            }
            for index in range(output_count)
        ],
    )
    return run_id


def _output_ids(conn: Connection, run_id: str) -> list[str]:
    rows = conn.execute(
        text("SELECT id FROM agent_outputs WHERE agent_run_id = :run"), {"run": run_id}
    ).fetchall()
    return [str(row[0]) for row in rows]


def _bind_outputs_to_queue(
    conn: Connection, ids: dict[str, str], queue_id: str, output_ids: list[str]
) -> None:
    now = datetime.now(UTC).isoformat()
    conn.execute(
        text(
            "INSERT INTO review_tasks (id, queue_id, record_id, task_schema_id, "
            "status, priority, claim_expired_count, is_overlap, is_calibration, "
            "agent_output_ids, ai_revealed, created_at, updated_at, "
            "workspace_id, dataset_id) VALUES (:id, :queue, :record, :schema, "
            "'available', :priority, 0, 0, 0, :outputs, 0, :now, :now, :wid, "
            ":did)"
        ),
        [
            {
                "id": str(uuid.uuid4()),
                "queue": queue_id,
                "record": ids["record"],
                "schema": ids["schema"],
                "priority": index,
                "outputs": json.dumps([output_id]),
                "now": now,
                "wid": ids["workspace"],
                "did": ids["dataset"],
            }
            for index, output_id in enumerate(output_ids)
        ],
    )


def _engine() -> Any:
    engine = engine_from_url("sqlite://")
    upgrade_database(engine)
    return engine


def test_a_queue_with_more_outputs_than_sqlite_binds_at_once_is_read_whole():
    engine = _engine()
    queue_id = f"queue-{uuid.uuid4()}"
    with engine.begin() as conn:
        ids = _seed_review_scope(conn)
        run_id = _seed_agent_run(conn, ids, MORE_THAN_SQLITE_BINDS)
        _bind_outputs_to_queue(conn, ids, queue_id, _output_ids(conn, run_id))

    with engine.connect() as conn:
        proposals = queue_agent_proposals(conn, [queue_id])

    assert len(proposals) == MORE_THAN_SQLITE_BINDS
    assert {proposal.agent_run_id for proposal in proposals} == {run_id}
    assert sorted(proposal.labels["index"] for proposal in proposals) == list(
        range(MORE_THAN_SQLITE_BINDS)
    )


def test_a_run_id_repeated_across_chunks_yields_its_outputs_once(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(review_events, "IN_LIST_CHUNK", 2)
    engine = _engine()
    with engine.begin() as conn:
        ids = _seed_review_scope(conn)
        repeated = _seed_agent_run(conn, ids, 2)
        other = _seed_agent_run(conn, ids, 1)

    with engine.connect() as conn:
        proposals = run_agent_proposals(conn, [repeated, other, repeated])

    assert sorted((p.agent_run_id, p.labels["index"]) for p in proposals) == sorted(
        [(other, 0), (repeated, 0), (repeated, 1)]
    )

"""Read the human review events and agent proposals of review queues.

Agreement and adjudication rate the same values, so both read them here.
``molabel.core.quality.review_agreement`` decides which event counts and
which labels each decision rates.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import bindparam, text

from molabel.core.agents.queue_binding import deserialize_agent_output_ids
from molabel.core.quality.review_agreement import AgentProposal, ReviewEventLabels


def json_object(value: Any) -> dict[str, Any]:
    """Parse a JSON column into a dict, or an empty dict when it holds none."""
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    try:
        parsed = json.loads(str(value))
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _utc(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def queue_review_events(conn: Any, queue_ids: Sequence[str]) -> list[ReviewEventLabels]:
    """Human review events submitted or corrected on the tasks of these queues."""
    rows = conn.execute(
        text(
            "SELECT e.id, e.record_id, e.reviewer_id, e.decision, e.labels, "
            "e.supersedes_event_id, e.created_at "
            "FROM review_events e "
            "JOIN review_tasks t ON t.id = e.review_task_id "
            "WHERE e.source = 'human' AND e.reviewer_id IS NOT NULL "
            "AND t.queue_id IN :queue_ids"
        ).bindparams(bindparam("queue_ids", expanding=True)),
        {"queue_ids": list(queue_ids)},
    ).fetchall()
    return [
        ReviewEventLabels(
            event_id=str(row[0]),
            record_id=str(row[1]),
            reviewer_id=str(row[2]),
            decision=row[3],
            labels=json_object(row[4]),
            supersedes_event_id=str(row[5]) if row[5] else None,
            created_at=_utc(row[6]),
        )
        for row in rows
    ]


def _proposals(conn: Any, where: str, values: list[str]) -> list[AgentProposal]:
    rows = conn.execute(
        text(
            f"SELECT record_id, agent_run_id, labels FROM agent_outputs WHERE {where}"
        ).bindparams(bindparam("values", expanding=True)),
        {"values": values},
    ).fetchall()
    return [
        AgentProposal(
            record_id=str(row[0]),
            agent_run_id=str(row[1]),
            labels=json_object(row[2]),
        )
        for row in rows
    ]


def run_agent_proposals(conn: Any, agent_run_ids: Sequence[str]) -> list[AgentProposal]:
    """Every output of these agent runs."""
    return _proposals(conn, "agent_run_id IN :values", list(agent_run_ids))


def queue_agent_proposals(conn: Any, queue_ids: Sequence[str]) -> list[AgentProposal]:
    """The agent outputs the tasks of these queues are bound to."""
    rows = conn.execute(
        text(
            "SELECT agent_output_ids FROM review_tasks WHERE queue_id IN :queue_ids"
        ).bindparams(bindparam("queue_ids", expanding=True)),
        {"queue_ids": list(queue_ids)},
    ).fetchall()
    output_ids = {
        str(output_id)
        for (raw,) in rows
        for output_id in deserialize_agent_output_ids(raw)
    }
    return _proposals(conn, "id IN :values", sorted(output_ids))

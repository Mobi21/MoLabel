"""Review events written before the accept/edit/reject rename stay readable."""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlmodel import Session, select

from molabel.core.database import create_all_tables, get_engine
from molabel.core.models.review_event import ReviewEvent


def test_orm_loads_review_event_with_pre_rename_decision(tmp_path) -> None:
    engine = get_engine(tmp_path / "events.db")
    create_all_tables(engine)
    with engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys=OFF"))
        conn.execute(
            text(
                "INSERT INTO review_events (id, record_id, task_schema_id, "
                "task_schema_version, source, decision, labels, created_at, "
                "workspace_id) VALUES (:id, :record_id, :task_schema_id, 1, "
                "'human', 'accept_ai', '{}', '2026-01-01T00:00:00', :workspace_id)"
            ),
            {
                "id": uuid.uuid4().hex,
                "record_id": uuid.uuid4().hex,
                "task_schema_id": uuid.uuid4().hex,
                "workspace_id": uuid.uuid4().hex,
            },
        )
        conn.commit()

    with Session(engine) as session:
        events = session.exec(select(ReviewEvent)).all()

    assert [event.decision for event in events] == ["accept_ai"]

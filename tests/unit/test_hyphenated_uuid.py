"""Every UUID column stores the hyphenated form, the one the routes write."""

from __future__ import annotations

import uuid

from sqlalchemy import Uuid, text
from sqlmodel import Session, SQLModel, select

import molabel.core.models  # noqa: F401
from molabel.core.database import HyphenatedUuid, engine_from_url
from molabel.core.migration_runner import upgrade_database
from molabel.core.models import Dataset, Workspace

INSERT_WORKSPACE = text(
    "INSERT INTO workspaces (id, workspace_name, workspace_slug, core_version, "
    "root_path, manifest_path, created_at, updated_at) VALUES (:id, 'w', 'w', "
    "'0.1.0', '/w', '/w/m.yaml', '2026-01-01T00:00:00', '2026-01-01T00:00:00')"
)


def _engine():
    engine = engine_from_url("sqlite://")
    upgrade_database(engine)
    return engine


def _workspace(workspace_id: uuid.UUID) -> Workspace:
    return Workspace(
        id=workspace_id,
        workspace_name="w",
        workspace_slug="w",
        core_version="0.1.0",
        root_path="/w",
        manifest_path="/w/m.yaml",
    )


def _dataset(workspace_id: uuid.UUID) -> Dataset:
    return Dataset(
        dataset_name="d",
        dataset_slug="d",
        source_type="jsonl",
        canonical_id_strategy="external_id",
        indexing_mode="full",
        workspace_id=workspace_id,
    )


def test_every_uuid_column_stores_the_hyphenated_form() -> None:
    uuid_columns = [
        column
        for table in SQLModel.metadata.tables.values()
        for column in table.columns
        if isinstance(column.type, Uuid)
    ]

    assert len(uuid_columns) == 114
    assert [
        (column.table.name, column.name)
        for column in uuid_columns
        if not isinstance(column.type, HyphenatedUuid)
    ] == []


def test_an_orm_row_is_stored_as_the_routes_spell_it() -> None:
    engine = _engine()
    workspace_id = uuid.uuid4()
    with Session(engine) as session:
        session.add(_workspace(workspace_id))
        session.commit()

    with engine.connect() as conn:
        stored = conn.execute(text("SELECT id FROM workspaces")).scalar()
        by_route_spelling = conn.execute(
            text("SELECT count(*) FROM workspaces WHERE id = :id"),
            {"id": str(workspace_id)},
        ).scalar()

    assert stored == str(workspace_id)
    assert by_route_spelling == 1


def test_a_route_row_is_found_by_the_orm_and_can_be_referenced_by_it() -> None:
    engine = _engine()
    workspace_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(INSERT_WORKSPACE, {"id": str(workspace_id)})

    with Session(engine) as session:
        assert session.get(Workspace, workspace_id) is not None
        assert session.get(Workspace, str(workspace_id)) is not None
        session.add(_dataset(workspace_id))
        session.commit()
        found = session.exec(
            select(Dataset).where(Dataset.workspace_id == str(workspace_id))
        ).all()

    assert [dataset.workspace_id for dataset in found] == [workspace_id]
    with engine.connect() as conn:
        assert conn.execute(text("SELECT workspace_id FROM datasets")).scalar() == str(
            workspace_id
        )


def test_a_row_stored_as_hex_still_reads_back() -> None:
    engine = _engine()
    workspace_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(INSERT_WORKSPACE, {"id": workspace_id.hex})

    with Session(engine) as session:
        assert session.exec(select(Workspace)).one().id == workspace_id

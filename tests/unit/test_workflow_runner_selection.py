from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy import text

from molabel.app.api.v1.workflows import (
    _ensure_model_profile,
    _HeuristicAgentRunner,
    _LlmAgentRunner,
    _select_agent_runner,
    _WorkflowDataLoader,
)
from molabel.core.database import create_all_tables, get_engine
from molabel.core.providers.model_defaults import MINIMAX_M27_HIGHSPEED


def _insert_model_profile(
    engine,
    workspace_id: str,
    *,
    profile_id: str,
    slug: str,
    model_identifier: str,
    provider_type: str = "anthropic",
) -> None:
    now = datetime.now(UTC).isoformat()
    with engine.connect() as conn:
        conn.execute(
            text(
                """
                INSERT INTO model_profiles (
                    id, model_profile_slug, provider_type, provider_name,
                    model_identifier, transport, auth_ref,
                    supports_structured_output, supports_tool_use,
                    is_available, created_at, updated_at, workspace_id
                )
                VALUES (
                    :id, :slug, :provider_type, :provider_name,
                    :model_identifier, 'responses', 'ANTHROPIC_API_KEY',
                    1, 0, 1, :now, :now, :workspace_id
                )
                """
            ),
            {
                "id": profile_id,
                "slug": slug,
                "provider_type": provider_type,
                "provider_name": "MiniMax",
                "model_identifier": model_identifier,
                "now": now,
                "workspace_id": workspace_id,
            },
        )
        conn.commit()


def _build_engine(tmp_path):
    engine = get_engine(tmp_path / "workflow-runner-selection.db")
    create_all_tables(engine)
    return engine


def _insert_workspace(engine, root_path) -> str:
    workspace_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    with engine.connect() as conn:
        conn.execute(
            text(
                """
                INSERT INTO workspaces (
                    id, workspace_name, workspace_slug, core_version,
                    root_path, manifest_path, created_at, updated_at
                )
                VALUES (
                    :id, 'Runner Selection', 'runner-selection', '0.1.0',
                    :root_path, :manifest_path, :now, :now
                )
                """
            ),
            {
                "id": workspace_id,
                "root_path": str(root_path),
                "manifest_path": str(root_path / "workbench.project.yaml"),
                "now": now,
            },
        )
        conn.commit()
    return workspace_id


def test_select_agent_runner_uses_model_profile_id(tmp_path) -> None:
    engine = _build_engine(tmp_path)
    workspace_id = _insert_workspace(engine, tmp_path)
    profile_id = str(uuid.uuid4())
    _insert_model_profile(
        engine,
        workspace_id,
        profile_id=profile_id,
        slug="minimax-2-7",
        model_identifier="MiniMax-M2.7-highspeed",
    )
    definition = SimpleNamespace(
        steps=[
            SimpleNamespace(
                id="label",
                type="agent_run",
                config={"model_profile_id": profile_id},
            )
        ]
    )

    runner = _select_agent_runner(
        engine.connect(),
        definition=definition,
        workspace_id=workspace_id,
    )

    assert isinstance(runner, _LlmAgentRunner)


def test_select_agent_runner_uses_model_profile_slug(tmp_path) -> None:
    engine = _build_engine(tmp_path)
    workspace_id = _insert_workspace(engine, tmp_path)
    profile_id = str(uuid.uuid4())
    _insert_model_profile(
        engine,
        workspace_id,
        profile_id=profile_id,
        slug="minimax-2-7",
        model_identifier="MiniMax-M2.7-highspeed",
    )
    definition = SimpleNamespace(
        steps=[
            SimpleNamespace(
                id="label",
                type="agent_run",
                config={"model": "minimax-2-7"},
            )
        ]
    )

    runner = _select_agent_runner(
        engine.connect(),
        definition=definition,
        workspace_id=workspace_id,
    )

    assert isinstance(runner, _LlmAgentRunner)


def test_select_agent_runner_keeps_heuristic_for_custom_profile(tmp_path) -> None:
    engine = _build_engine(tmp_path)
    workspace_id = _insert_workspace(engine, tmp_path)
    profile_id = str(uuid.uuid4())
    _insert_model_profile(
        engine,
        workspace_id,
        profile_id=profile_id,
        slug="demo-heuristic",
        model_identifier="heuristic-agent",
        provider_type="custom",
    )
    definition = SimpleNamespace(
        steps=[
            SimpleNamespace(
                id="label",
                type="agent_run",
                config={"model_profile_id": profile_id},
            )
        ]
    )

    runner = _select_agent_runner(
        engine.connect(),
        definition=definition,
        workspace_id=workspace_id,
    )

    assert isinstance(runner, _HeuristicAgentRunner)


def test_ensure_model_profile_resolves_existing_profile_id(tmp_path) -> None:
    engine = _build_engine(tmp_path)
    workspace_id = _insert_workspace(engine, tmp_path)
    profile_id = str(uuid.uuid4())
    _insert_model_profile(
        engine,
        workspace_id,
        profile_id=profile_id,
        slug="minimax-2-7",
        model_identifier="MiniMax-M2.7-highspeed",
    )

    with engine.connect() as conn:
        resolved = _ensure_model_profile(
            conn,
            workspace_id=workspace_id,
            model_identifier=profile_id,
        )

    assert resolved == profile_id


def test_ensure_model_profile_resolves_existing_profile_slug(tmp_path) -> None:
    engine = _build_engine(tmp_path)
    workspace_id = _insert_workspace(engine, tmp_path)
    profile_id = str(uuid.uuid4())
    _insert_model_profile(
        engine,
        workspace_id,
        profile_id=profile_id,
        slug="minimax-2-7",
        model_identifier="MiniMax-M2.7-highspeed",
    )

    with engine.connect() as conn:
        resolved = _ensure_model_profile(
            conn,
            workspace_id=workspace_id,
            model_identifier="minimax-2-7",
        )

    assert resolved == profile_id


def test_ensure_model_profile_infers_minimax_profile(tmp_path, monkeypatch) -> None:
    engine = _build_engine(tmp_path)
    workspace_id = _insert_workspace(engine, tmp_path)
    monkeypatch.setenv("MINIMAX_BASE_URL", MINIMAX_M27_HIGHSPEED.base_url)
    monkeypatch.setenv("MINIMAX_API_KEY", "test-key")

    with engine.connect() as conn:
        profile_id = _ensure_model_profile(
            conn,
            workspace_id=workspace_id,
            model_identifier=MINIMAX_M27_HIGHSPEED.model_identifier,
        )
        row = conn.execute(
            text(
                "SELECT provider_type, provider_name, auth_ref, routing_metadata "
                "FROM model_profiles WHERE id = :id"
            ),
            {"id": profile_id},
        ).first()

    assert row is not None
    assert row[0] == "anthropic"
    assert row[1] == "MiniMax"
    assert row[2] == "MINIMAX_API_KEY"
    assert MINIMAX_M27_HIGHSPEED.base_url in str(row[3])


def test_select_agent_runner_uses_step_provider_hint_without_profile(tmp_path) -> None:
    engine = _build_engine(tmp_path)
    workspace_id = _insert_workspace(engine, tmp_path)
    definition = SimpleNamespace(
        steps=[
            SimpleNamespace(
                id="label",
                type="agent_run",
                config={
                    "model": "MiniMax-M2.7-highspeed",
                    "provider_type": "anthropic",
                    "base_url": "https://api.minimax.io/anthropic",
                },
            )
        ]
    )

    runner = _select_agent_runner(
        engine.connect(),
        definition=definition,
        workspace_id=workspace_id,
    )

    assert isinstance(runner, _LlmAgentRunner)


def test_workflow_data_loader_uses_record_id_field_from_dataset_config(
    tmp_path,
) -> None:
    engine = _build_engine(tmp_path)
    workspace_id = _insert_workspace(engine, tmp_path)
    source_path = tmp_path / "records.jsonl"
    source_path.write_text(
        "\n".join(
            [
                '{"post_id":"alpha","text":"first"}',
                '{"post_id":"beta","text":"second"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    dataset_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    with engine.connect() as conn:
        conn.execute(
            text(
                """
                INSERT INTO datasets (
                    id, dataset_name, dataset_slug, source_type, source_config,
                    loader_plugin, record_kind, canonical_id_strategy, indexing_mode,
                    record_count, labeled_count, health_status, created_at, updated_at,
                    last_indexed_at, workspace_id
                )
                VALUES (
                    :id, 'records', 'records', 'local_file', :source_config,
                    'molabel.loaders.jsonl', 'document', 'source_record_id',
                    'projection', 0, 0, 'stale', :now, :now, :now, :workspace_id
                )
                """
            ),
            {
                "id": dataset_id,
                "source_config": (
                    '{"paths":["records.jsonl"],"record_id_field":"post_id"}'
                ),
                "now": now,
                "workspace_id": workspace_id,
            },
        )
        conn.commit()

        loader = _WorkflowDataLoader(
            conn,
            workspace_id=workspace_id,
            workspace_root=tmp_path,
        )
        loader.load_records("records.jsonl", {})

        rows = conn.execute(
            text(
                "SELECT external_id FROM records WHERE dataset_id = :dataset_id "
                "ORDER BY sequence_index ASC"
            ),
            {"dataset_id": dataset_id},
        ).fetchall()

    assert [str(row[0]) for row in rows] == ["alpha", "beta"]

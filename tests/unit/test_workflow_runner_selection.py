from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy import text

from molabel.app.api.v1.workflows import (
    _HeuristicAgentRunner,
    _LlmAgentRunner,
    _ensure_model_profile,
    _select_agent_runner,
)
from molabel.core.database import create_all_tables, get_engine


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
        model_identifier="minimax-2.7",
    )
    definition = SimpleNamespace(
        steps=[
            SimpleNamespace(
                id="label",
                type="agent_labeling",
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
        model_identifier="minimax-2.7",
    )
    definition = SimpleNamespace(
        steps=[
            SimpleNamespace(
                id="label",
                type="agent_labeling",
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
                type="agent_labeling",
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
        model_identifier="minimax-2.7",
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
        model_identifier="minimax-2.7",
    )

    with engine.connect() as conn:
        resolved = _ensure_model_profile(
            conn,
            workspace_id=workspace_id,
            model_identifier="minimax-2-7",
        )

    assert resolved == profile_id

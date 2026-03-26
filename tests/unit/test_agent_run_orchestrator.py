"""Tests for persisted agent-run orchestration."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine, select

from molabel.core.agents.agent_run_orchestrator import AgentRunOrchestrator
from molabel.core.database import create_all_tables, get_session
from molabel.core.models.agent_event import AgentEvent
from molabel.core.models.agent_run import AgentRun
from molabel.core.models.dataset import Dataset
from molabel.core.models.model_profile import ModelProfile
from molabel.core.models.record import Record
from molabel.core.models.task_schema import TaskSchema
from molabel.core.models.workspace import Workspace
from molabel.core.types import (
    AgentEventType,
    AgentRunStatus,
    BlindReviewPolicy,
    ProviderType,
)
from molabel.core.workflow.context import RecordSet, WorkflowContext
from molabel.core.workflow.steps.agent_steps import AgentRunExecutor


@pytest.fixture()
def db_engine():
    """In-memory SQLite engine with all MoLabel tables."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    create_all_tables(engine)
    return engine


@pytest.fixture()
def agent_run_seed(db_engine) -> dict[str, Any]:
    """Seed the tables needed for persisted agent-run orchestration."""
    workspace_id = uuid.uuid4()
    dataset_id = uuid.uuid4()
    task_schema_id = uuid.uuid4()
    model_profile_id = uuid.uuid4()
    record_ids: list[uuid.UUID] = []

    with get_session(db_engine) as session:
        session.add(
            Workspace(
                id=workspace_id,
                workspace_name="Agent Test Workspace",
                workspace_slug="agent-test-workspace",
                core_version="0.1.0",
                root_path="/tmp/agent-tests",
                manifest_path="workbench.project.yaml",
            )
        )
        session.add(
            Dataset(
                id=dataset_id,
                workspace_id=workspace_id,
                dataset_name="Agent Dataset",
                dataset_slug="agent-dataset",
                source_type="local_file",
                canonical_id_strategy="source_record_id",
                indexing_mode="projection",
            )
        )
        session.add(
            ModelProfile(
                id=model_profile_id,
                workspace_id=workspace_id,
                model_profile_slug="agent-model",
                provider_type=ProviderType.openai_compatible,
                model_identifier="test-model",
                transport="https",
            )
        )
        session.add(
            TaskSchema(
                id=task_schema_id,
                workspace_id=workspace_id,
                task_schema_slug="agent-schema",
                version=1,
                task_type="ordinal_text_review",
                title="Agent Schema",
                label_fields=[{"name": "sentiment", "field_type": "categorical"}],
                blind_review_policy=BlindReviewPolicy.hide_agent_outputs_by_default,
            )
        )
        session.commit()

        for index in range(3):
            record = Record(
                workspace_id=workspace_id,
                dataset_id=dataset_id,
                external_id=f"record-{index}",
                stable_fields={"text": f"Record {index}"},
                payload={"text": f"Record {index}"},
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            record_ids.append(record.id)

    return {
        "workspace_id": workspace_id,
        "dataset_id": dataset_id,
        "task_schema_id": task_schema_id,
        "model_profile_id": model_profile_id,
        "record_ids": record_ids,
    }


def _make_context(
    record_ids: list[uuid.UUID],
    workspace_id: uuid.UUID,
) -> WorkflowContext:
    ctx = WorkflowContext(
        workspace_id=str(workspace_id),
        workflow_execution_id=str(uuid.uuid4()),
        workflow_version=1,
    )
    ctx.record_sets["_init"] = RecordSet(
        record_ids=[str(record_id) for record_id in record_ids],
        record_count=len(record_ids),
        description="Seed records",
    )
    ctx.active_record_set_id = "_init"
    return ctx


def test_orchestrator_emits_batched_events_and_completes(db_engine, agent_run_seed):
    """A clean run should persist the full lifecycle and batch events."""

    orchestrator = AgentRunOrchestrator(db_engine, default_batch_size=2)
    record_ids = agent_run_seed["record_ids"]

    result = orchestrator.run(
        record_ids=[str(record_id) for record_id in record_ids],
        config={"batch_size": 2},
        workspace_id=agent_run_seed["workspace_id"],
        dataset_id=agent_run_seed["dataset_id"],
        task_schema_id=agent_run_seed["task_schema_id"],
        model_profile_id=agent_run_seed["model_profile_id"],
        agent_role="proposer",
        services={},
    )

    assert result.status == AgentRunStatus.completed
    assert result.completed_records == 3
    assert result.failed_records == 0
    assert result.batch_count == 2
    assert result.event_count == 9

    with get_session(db_engine) as session:
        run = session.get(AgentRun, result.agent_run_id)
        assert run is not None
        assert run.status == AgentRunStatus.completed
        assert run.completed_records == 3
        assert run.failed_records == 0
        assert run.started_at is not None
        assert run.completed_at is not None

        events = session.exec(
            select(AgentEvent)
            .where(AgentEvent.agent_run_id == result.agent_run_id)
            .order_by(AgentEvent.sequence_number)
        ).all()
        assert [event.event_type for event in events] == [
            AgentEventType.run_started,
            AgentEventType.batch_started,
            AgentEventType.record_completed,
            AgentEventType.record_completed,
            AgentEventType.batch_completed,
            AgentEventType.batch_started,
            AgentEventType.record_completed,
            AgentEventType.batch_completed,
            AgentEventType.run_completed,
        ]
        assert [event.sequence_number for event in events] == list(range(1, 10))


def test_orchestrator_marks_partial_failure_when_a_record_fails(
    db_engine, agent_run_seed
):
    """A per-record failure should preserve successful rows and mark the run partial."""

    failing_record_id = agent_run_seed["record_ids"][1]

    def processor(**kwargs: Any) -> dict[str, Any]:
        if kwargs["record_id"] == failing_record_id:
            raise RuntimeError("model rejected record")
        return {"success": True, "record_id": str(kwargs["record_id"])}

    orchestrator = AgentRunOrchestrator(db_engine, default_batch_size=2)
    result = orchestrator.run(
        record_ids=[str(record_id) for record_id in agent_run_seed["record_ids"]],
        config={"batch_size": 2},
        workspace_id=agent_run_seed["workspace_id"],
        dataset_id=agent_run_seed["dataset_id"],
        task_schema_id=agent_run_seed["task_schema_id"],
        model_profile_id=agent_run_seed["model_profile_id"],
        agent_role="critic",
        services={"record_processor": processor},
    )

    assert result.status == AgentRunStatus.partially_completed
    assert result.completed_records == 2
    assert result.failed_records == 1
    assert result.batch_count == 2
    assert result.event_count == 9

    with get_session(db_engine) as session:
        run = session.get(AgentRun, result.agent_run_id)
        assert run is not None
        assert run.status == AgentRunStatus.partially_completed
        assert run.completed_records == 2
        assert run.failed_records == 1


def test_agent_step_uses_persisted_result_counts(db_engine, agent_run_seed):
    """The workflow step should reflect the persisted run counts in context."""

    failing_record_id = agent_run_seed["record_ids"][1]

    def processor(**kwargs: Any) -> dict[str, Any]:
        if kwargs["record_id"] == failing_record_id:
            raise RuntimeError("model rejected record")
        return {"success": True}

    orchestrator = AgentRunOrchestrator(db_engine, default_batch_size=2)
    executor = AgentRunExecutor()
    context = _make_context(
        agent_run_seed["record_ids"], agent_run_seed["workspace_id"]
    )

    result = executor.execute(
        "agent",
        {
            "prompt_ref": "prompt.yaml",
            "model_profile_id": str(agent_run_seed["model_profile_id"]),
            "dataset_id": str(agent_run_seed["dataset_id"]),
            "task_schema_id": str(agent_run_seed["task_schema_id"]),
            "batch_size": 2,
            "agent_role": "critic",
        },
        context,
        services={"agent_runner": orchestrator, "record_processor": processor},
    )

    assert result.success
    assert result.is_partial
    assert result.output is not None
    assert result.output.summary["agent_run_status"] == "partially_completed"
    assert result.output.summary["records_completed"] == 2
    assert result.output.summary["records_failed"] == 1
    assert len(context.agent_run_ids) == 1

    run_id = context.agent_run_ids[0]
    output_ref = context.agent_outputs[run_id]
    assert output_ref.success_count == 2
    assert output_ref.failure_count == 1
    assert context.metrics["agent.coverage"] == pytest.approx(2 / 3)

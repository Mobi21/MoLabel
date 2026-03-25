"""Agent run orchestration service with persisted lifecycle state."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlmodel import Session

from molabel.core.database import get_session
from molabel.core.models.agent_event import AgentEvent
from molabel.core.models.agent_run import AgentRun
from molabel.core.types import AgentEventType, AgentRole, AgentRunStatus

logger = logging.getLogger(__name__)


class AgentRunExecutionError(RuntimeError):
    """Raised when agent-run orchestration fails after partial progress."""

    def __init__(
        self,
        message: str,
        *,
        partial_results: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.partial_results = partial_results or {}


class AgentRunBatchResult(BaseModel):
    """Structured result for a persisted batched agent run."""

    agent_run_id: UUID
    status: AgentRunStatus
    total_records: int
    completed_records: int
    failed_records: int
    batch_size: int
    batch_count: int
    event_count: int
    error_summary: str | None = None
    partial_results: dict[str, Any] | None = None


class AgentRunOrchestrator:
    """Persist agent-run lifecycle state and batch progress events.

    The orchestrator writes ``AgentRun`` and ``AgentEvent`` rows directly
    through the core SQLite engine. It processes records in batches and
    emits progress events as each batch is started/completed and as each
    individual record succeeds or fails.

    The service is intentionally narrow: it assumes the caller has already
    resolved the workspace, dataset, task schema, and model profile IDs.
    """

    def __init__(
        self,
        engine: Any | None = None,
        *,
        default_batch_size: int = 25,
    ) -> None:
        self._engine = engine
        self._default_batch_size = max(1, int(default_batch_size))

    def run(
        self,
        *,
        record_ids: Sequence[str | UUID],
        config: Mapping[str, Any],
        agent_run_id: str | UUID | None = None,
        workspace_id: str | UUID,
        dataset_id: str | UUID,
        task_schema_id: str | UUID,
        model_profile_id: str | UUID,
        runtime_profile_id: str | UUID | None = None,
        agent_role: str | AgentRole = AgentRole.proposer,
        services: dict[str, Any] | None = None,
        step_id: str | None = None,
    ) -> AgentRunBatchResult:
        """Execute a batched agent run and persist lifecycle rows."""

        if self._engine is None:
            raise RuntimeError("AgentRunOrchestrator requires a database engine")

        services = services or {}
        processor = self._resolve_record_processor(services)
        batch_size = self._resolve_batch_size(config)
        run_uuid = _coerce_uuid(agent_run_id) if agent_run_id is not None else uuid4()
        workspace_uuid = _coerce_uuid(workspace_id)
        dataset_uuid = _coerce_uuid(dataset_id)
        task_schema_uuid = _coerce_uuid(task_schema_id)
        model_profile_uuid = _coerce_uuid(model_profile_id)
        runtime_profile_uuid = (
            _coerce_uuid(runtime_profile_id) if runtime_profile_id is not None else None
        )
        agent_role_enum = _coerce_agent_role(agent_role)
        record_uuids = [_coerce_uuid(record_id) for record_id in record_ids]

        total_records = len(record_uuids)
        completed_records = 0
        failed_records = 0
        event_count = 0
        next_sequence = 1
        batch_count = 0
        errors: list[str] = []
        started_at = datetime.now(UTC)

        self._create_planned_run(
            run_uuid=run_uuid,
            workspace_id=workspace_uuid,
            dataset_id=dataset_uuid,
            task_schema_id=task_schema_uuid,
            model_profile_id=model_profile_uuid,
            runtime_profile_id=runtime_profile_uuid,
            agent_role=agent_role_enum,
            config=dict(config),
            total_records=total_records,
        )

        with get_session(self._engine) as session:
            self._insert_event(
                session,
                agent_run_id=run_uuid,
                event_type=AgentEventType.run_started,
                sequence_number=next_sequence,
                payload={
                    "step_id": step_id,
                    "workspace_id": str(workspace_uuid),
                    "dataset_id": str(dataset_uuid),
                    "task_schema_id": str(task_schema_uuid),
                    "model_profile_id": str(model_profile_uuid),
                    "total_records": total_records,
                    "batch_size": batch_size,
                    "status": AgentRunStatus.running.value,
                },
            )
            event_count += 1
            next_sequence += 1
            self._update_run(
                session,
                run_uuid,
                status=AgentRunStatus.running,
                started_at=started_at,
                updated_at=started_at,
            )
            session.commit()

        try:
            for batch_index, batch in enumerate(
                _chunked(record_uuids, batch_size),
                start=1,
            ):
                batch_count += 1
                batch_started_at = datetime.now(UTC)

                with get_session(self._engine) as session:
                    self._insert_event(
                        session,
                        agent_run_id=run_uuid,
                        event_type=AgentEventType.batch_started,
                        sequence_number=next_sequence,
                        payload={
                            "batch_index": batch_index,
                            "batch_size": len(batch),
                            "record_ids": [str(record_id) for record_id in batch],
                        },
                    )
                    event_count += 1
                    next_sequence += 1
                    session.commit()

                batch_completed = 0
                batch_failed = 0

                for record_index, record_id in enumerate(batch, start=1):
                    try:
                        processor_result = self._run_record_processor(
                            processor=processor,
                            record_id=record_id,
                            record_index=record_index,
                            batch_index=batch_index,
                            agent_run_id=run_uuid,
                            workspace_id=workspace_uuid,
                            dataset_id=dataset_uuid,
                            task_schema_id=task_schema_uuid,
                            model_profile_id=model_profile_uuid,
                            agent_role=agent_role_enum,
                            config=dict(config),
                            services=services,
                            step_id=step_id,
                        )
                        batch_completed += 1
                        completed_records += 1
                        payload = {
                            "batch_index": batch_index,
                            "record_index": record_index,
                            "record_id": str(record_id),
                            "status": "completed",
                        }
                        if processor_result is not None:
                            payload["result"] = processor_result
                        event_type = AgentEventType.record_completed
                    except Exception as exc:  # pragma: no cover - defensive
                        batch_failed += 1
                        failed_records += 1
                        error_message = str(exc)
                        errors.append(error_message)
                        payload = {
                            "batch_index": batch_index,
                            "record_index": record_index,
                            "record_id": str(record_id),
                            "status": "failed",
                            "error": error_message,
                        }
                        event_type = AgentEventType.record_failed

                    with get_session(self._engine) as session:
                        self._insert_event(
                            session,
                            agent_run_id=run_uuid,
                            event_type=event_type,
                            sequence_number=next_sequence,
                            payload=payload,
                            record_id=record_id,
                        )
                        event_count += 1
                        next_sequence += 1
                        session.commit()

                with get_session(self._engine) as session:
                    self._insert_event(
                        session,
                        agent_run_id=run_uuid,
                        event_type=AgentEventType.batch_completed,
                        sequence_number=next_sequence,
                        payload={
                            "batch_index": batch_index,
                            "started_at": batch_started_at.isoformat(),
                            "completed_at": datetime.now(UTC).isoformat(),
                            "completed_records": batch_completed,
                            "failed_records": batch_failed,
                            "status": (
                                AgentRunStatus.partially_completed.value
                                if batch_failed and batch_completed
                                else AgentRunStatus.failed.value
                                if batch_failed and not batch_completed
                                else AgentRunStatus.completed.value
                            ),
                        },
                    )
                    event_count += 1
                    next_sequence += 1
                    self._update_run(
                        session,
                        run_uuid,
                        completed_records=completed_records,
                        failed_records=failed_records,
                        updated_at=datetime.now(UTC),
                    )
                    session.commit()

        except Exception as exc:
            partial_results = {
                "agent_run_id": str(run_uuid),
                "status": AgentRunStatus.partially_completed.value
                if completed_records
                else AgentRunStatus.failed.value,
                "completed_records": completed_records,
                "failed_records": failed_records,
                "event_count": event_count,
                "total_records": total_records,
                "error": str(exc),
            }
            self._mark_terminal_state(
                run_uuid=run_uuid,
                status=(
                    AgentRunStatus.partially_completed
                    if completed_records
                    else AgentRunStatus.failed
                ),
                completed_records=completed_records,
                failed_records=failed_records,
                error_summary=_summarize_errors(errors or [str(exc)]),
                event_type=(
                    AgentEventType.run_completed
                    if completed_records
                    else AgentEventType.run_failed
                ),
                sequence_number=next_sequence,
                payload=partial_results,
            )
            raise AgentRunExecutionError(
                f"Agent run {run_uuid} failed during orchestration",
                partial_results=partial_results,
            ) from exc

        final_status = (
            AgentRunStatus.completed
            if failed_records == 0
            else AgentRunStatus.partially_completed
            if completed_records > 0
            else AgentRunStatus.failed
        )
        terminal_event_type = (
            AgentEventType.run_completed
            if final_status != AgentRunStatus.failed
            else AgentEventType.run_failed
        )
        self._mark_terminal_state(
            run_uuid=run_uuid,
            status=final_status,
            completed_records=completed_records,
            failed_records=failed_records,
            error_summary=_summarize_errors(errors),
            event_type=terminal_event_type,
            sequence_number=next_sequence,
            payload={
                "status": final_status.value,
                "completed_records": completed_records,
                "failed_records": failed_records,
                "event_count": event_count + 1,
                "batch_count": batch_count,
            },
        )
        event_count += 1

        return AgentRunBatchResult(
            agent_run_id=run_uuid,
            status=final_status,
            total_records=total_records,
            completed_records=completed_records,
            failed_records=failed_records,
            batch_size=batch_size,
            batch_count=batch_count,
            event_count=event_count,
            error_summary=_summarize_errors(errors),
        )

    def _resolve_batch_size(self, config: Mapping[str, Any]) -> int:
        batch_size = config.get("batch_size", self._default_batch_size)
        try:
            return max(1, int(batch_size))
        except (TypeError, ValueError):
            return self._default_batch_size

    def _resolve_record_processor(self, services: dict[str, Any]) -> Any | None:
        for key in (
            "record_processor",
            "agent_record_processor",
            "agent_batch_processor",
        ):
            if key in services:
                return services[key]
        return None

    def _create_planned_run(
        self,
        *,
        run_uuid: UUID,
        workspace_id: UUID,
        dataset_id: UUID,
        task_schema_id: UUID,
        model_profile_id: UUID,
        runtime_profile_id: UUID | None,
        agent_role: AgentRole,
        config: dict[str, Any],
        total_records: int,
    ) -> None:
        with get_session(self._engine) as session:
            session.add(
                AgentRun(
                    id=run_uuid,
                    workspace_id=workspace_id,
                    dataset_id=dataset_id,
                    task_schema_id=task_schema_id,
                    model_profile_id=model_profile_id,
                    runtime_profile_id=runtime_profile_id,
                    agent_role=agent_role,
                    status=AgentRunStatus.planned,
                    config=config,
                    total_records=total_records,
                    completed_records=0,
                    failed_records=0,
                    retry_count=0,
                )
            )
            session.commit()

    def _update_run(self, session: Session, run_uuid: UUID, **updates: Any) -> None:
        run = session.get(AgentRun, run_uuid)
        if run is None:
            raise RuntimeError(f"AgentRun {run_uuid} not found")
        for key, value in updates.items():
            setattr(run, key, value)
        session.add(run)

    def _insert_event(
        self,
        session: Session,
        *,
        agent_run_id: UUID,
        event_type: AgentEventType,
        sequence_number: int,
        payload: dict[str, Any] | None = None,
        record_id: UUID | None = None,
    ) -> None:
        session.add(
            AgentEvent(
                agent_run_id=agent_run_id,
                event_type=event_type,
                record_id=record_id,
                sequence_number=sequence_number,
                payload=payload,
            )
        )

    def _run_record_processor(
        self,
        *,
        processor: Any | None,
        record_id: UUID,
        record_index: int,
        batch_index: int,
        agent_run_id: UUID,
        workspace_id: UUID,
        dataset_id: UUID,
        task_schema_id: UUID,
        model_profile_id: UUID,
        agent_role: AgentRole,
        config: dict[str, Any],
        services: dict[str, Any],
        step_id: str | None,
    ) -> Any | None:
        if processor is None:
            return None
        return processor(
            record_id=record_id,
            record_index=record_index,
            batch_index=batch_index,
            agent_run_id=agent_run_id,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            task_schema_id=task_schema_id,
            model_profile_id=model_profile_id,
            agent_role=agent_role.value,
            config=config,
            services=services,
            step_id=step_id,
        )

    def _mark_terminal_state(
        self,
        *,
        run_uuid: UUID,
        status: AgentRunStatus,
        completed_records: int,
        failed_records: int,
        error_summary: str | None,
        event_type: AgentEventType,
        sequence_number: int,
        payload: dict[str, Any],
    ) -> None:
        completed_at = datetime.now(UTC)
        with get_session(self._engine) as session:
            self._insert_event(
                session,
                agent_run_id=run_uuid,
                event_type=event_type,
                sequence_number=sequence_number,
                payload=payload,
            )
            self._update_run(
                session,
                run_uuid,
                status=status,
                completed_records=completed_records,
                failed_records=failed_records,
                error_summary=error_summary,
                completed_at=completed_at,
                updated_at=completed_at,
            )
            session.commit()


def _coerce_uuid(value: str | UUID) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _coerce_agent_role(value: str | AgentRole) -> AgentRole:
    if isinstance(value, AgentRole):
        return value
    return AgentRole(str(value))


def _chunked(values: Sequence[UUID], batch_size: int) -> list[list[UUID]]:
    return [list(values[i : i + batch_size]) for i in range(0, len(values), batch_size)]


def _summarize_errors(errors: Sequence[str]) -> str | None:
    if not errors:
        return None
    summary = "; ".join(errors[:3])
    if len(summary) > 500:
        return summary[:497] + "..."
    return summary

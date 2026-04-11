"""Workflow endpoints — /api/v1/workflows.

CRUD for workflow definitions plus execution management
(API-019 through API-028).
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text

from molabel.app.middleware.session import CurrentReviewer
from molabel.app.schemas import PaginatedResponse, QueryParams
from molabel.app.utils import get_engine
from molabel.core.agents.queue_binding import serialize_agent_output_ids
from molabel.core.types import (
    BlindReviewPolicy,
    ProviderType,
    WorkflowExecutionStatus,
    WorkflowStepExecutionStatus,
)
from molabel.core.types import ReviewTaskStatus as ReviewTaskStatusEnum
from molabel.core.workflow.context import WorkflowContext
from molabel.core.workflow.engine import WorkflowEngine, create_default_registry
from molabel.core.workflow.parser import StepDefinition, WorkflowDefinitionParsed

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflows", tags=["workflows"])

# ---------------------------------------------------------------------------
# Response / request models
# ---------------------------------------------------------------------------


class StepPosition(BaseModel):
    """Visual position of a step in the workflow canvas."""

    x: float = 0
    y: float = 0


class WorkflowStep(BaseModel):
    """A single step within a workflow definition."""

    step_id: str
    step_type: str
    label: str | None = None
    config: dict[str, Any] = {}
    position: StepPosition | None = None


class WorkflowEdge(BaseModel):
    """A directed edge between two workflow steps."""

    source_step_id: str
    target_step_id: str
    condition: str | None = None


class WorkflowSummary(BaseModel):
    """Workflow definition list item."""

    workflow_id: str
    workflow_slug: str
    version: int
    name: str
    description: str | None = None
    step_count: int = 0
    is_template: bool = False
    is_active: bool = True
    workspace_id: str
    created_at: datetime
    updated_at: datetime


class WorkflowDetail(BaseModel):
    """Full workflow definition detail."""

    workflow_id: str
    workflow_slug: str
    version: int
    name: str
    description: str | None = None
    steps: list[WorkflowStep] = []
    edges: list[WorkflowEdge] = []
    is_template: bool = False
    template_source: str | None = None
    file_path: str
    is_active: bool = True
    workspace_id: str
    created_at: datetime
    updated_at: datetime


class WorkflowCreate(BaseModel):
    """Request body for creating a workflow."""

    workspace_id: str
    name: str
    workflow_slug: str | None = None
    description: str | None = None
    steps: list[WorkflowStep] = []
    edges: list[WorkflowEdge] = []
    is_template: bool = False
    template_source: str | None = None
    file_path: str | None = None


class WorkflowUpdate(BaseModel):
    """Request body for updating a workflow."""

    name: str | None = None
    description: str | None = None
    steps: list[WorkflowStep] | None = None
    edges: list[WorkflowEdge] | None = None
    is_active: bool | None = None


class WorkflowExecuteRequest(BaseModel):
    """Request body for executing a workflow."""

    context: dict[str, Any] | None = None
    dataset_id: str | None = None


class StepState(BaseModel):
    """Execution state for a single workflow step."""

    step_execution_id: str
    step_id: str
    step_type: str
    status: str
    iteration: int = 0
    result: dict[str, Any] | None = None
    error_summary: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class WorkflowExecution(BaseModel):
    """A running or completed instance of a workflow."""

    execution_id: str
    workflow_definition_id: str
    workflow_version: int
    status: str
    current_step_id: str | None = None
    step_execution_count: int | None = None
    error_summary: str | None = None
    started_at: datetime | None = None
    paused_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class WorkflowExecutionDetail(BaseModel):
    """Full execution detail with step states."""

    execution_id: str
    workflow_definition_id: str
    workflow_version: int
    status: str
    current_step_id: str | None = None
    step_execution_count: int | None = None
    context: dict[str, Any] | None = None
    error_summary: str | None = None
    step_states: list[StepState] = []
    started_at: datetime | None = None
    paused_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class StepAdvanceRequest(BaseModel):
    """Request body for advancing a workflow step."""

    result: dict[str, Any] | None = None
    decision: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_summary(row: Any) -> WorkflowSummary:
    """Convert a database row to a WorkflowSummary."""
    import json

    steps_raw = row[4]
    if isinstance(steps_raw, str):
        try:
            steps = json.loads(steps_raw)
        except (json.JSONDecodeError, TypeError):
            steps = []
    elif isinstance(steps_raw, list):
        steps = steps_raw
    else:
        steps = []

    return WorkflowSummary(
        workflow_id=str(row[0]),
        workflow_slug=str(row[1]),
        version=int(row[2]),
        name=str(row[3]),
        description=str(row[5]) if row[5] else None,
        step_count=len(steps),
        is_template=bool(row[6]) if row[6] is not None else False,
        is_active=bool(row[7]) if row[7] is not None else True,
        workspace_id=str(row[8]),
        created_at=(
            datetime.fromisoformat(str(row[9])) if row[9] else datetime.now(UTC)
        ),
        updated_at=(
            datetime.fromisoformat(str(row[10])) if row[10] else datetime.now(UTC)
        ),
    )


def _row_to_detail(row: Any) -> WorkflowDetail:
    """Convert a database row to a WorkflowDetail."""
    import json

    steps_raw = row[4]
    if isinstance(steps_raw, str):
        try:
            steps_data = json.loads(steps_raw)
        except (json.JSONDecodeError, TypeError):
            steps_data = []
    elif isinstance(steps_data := steps_raw, list):
        pass
    else:
        steps_data = []

    steps = [
        WorkflowStep(
            step_id=s.get("step_id", s.get("id", "")),
            step_type=s.get("step_type", s.get("type", "")),
            label=s.get("label"),
            config=s.get("config", {}),
        )
        if isinstance(s, dict)
        else WorkflowStep(step_id=str(s), step_type="unknown")
        for s in steps_data
    ]

    return WorkflowDetail(
        workflow_id=str(row[0]),
        workflow_slug=str(row[1]),
        version=int(row[2]),
        name=str(row[3]),
        description=str(row[5]) if row[5] else None,
        steps=steps,
        edges=[],
        is_template=bool(row[6]) if row[6] is not None else False,
        template_source=str(row[7]) if row[7] else None,
        file_path=str(row[8]),
        is_active=bool(row[9]) if row[9] is not None else True,
        workspace_id=str(row[10]),
        created_at=(
            datetime.fromisoformat(str(row[11])) if row[11] else datetime.now(UTC)
        ),
        updated_at=(
            datetime.fromisoformat(str(row[12])) if row[12] else datetime.now(UTC)
        ),
    )


def _execution_row_to_model(row: Any) -> WorkflowExecution:
    """Convert a database row to a WorkflowExecution."""
    return WorkflowExecution(
        execution_id=str(row[0]),
        workflow_definition_id=str(row[1]),
        workflow_version=int(row[2]),
        status=str(row[3]),
        current_step_id=str(row[4]) if row[4] else None,
        step_execution_count=int(row[5]) if row[5] is not None else None,
        error_summary=str(row[6]) if row[6] else None,
        started_at=(datetime.fromisoformat(str(row[7])) if row[7] else None),
        paused_at=(datetime.fromisoformat(str(row[8])) if row[8] else None),
        completed_at=(datetime.fromisoformat(str(row[9])) if row[9] else None),
        created_at=(
            datetime.fromisoformat(str(row[10])) if row[10] else datetime.now(UTC)
        ),
        updated_at=(
            datetime.fromisoformat(str(row[11])) if row[11] else datetime.now(UTC)
        ),
    )


def _json_loads(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (json.JSONDecodeError, TypeError):
        return None


def _json_dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value)


def _build_workflow_definition(row: Any) -> WorkflowDefinitionParsed:
    steps_raw = _json_loads(row[4])
    steps_data = steps_raw if isinstance(steps_raw, list) else []
    steps: list[StepDefinition] = []
    predecessors: dict[str, list[str]] = {}
    successors: dict[str, list[str]] = {}
    step_index: dict[str, StepDefinition] = {}

    for index, item in enumerate(steps_data):
        if not isinstance(item, dict):
            continue
        step = StepDefinition(
            id=str(item.get("step_id", item.get("id", f"step-{index + 1}"))),
            type=str(item.get("step_type", item.get("type", ""))),
            config=dict(item.get("config", {})),
        )
        steps.append(step)
        step_index[step.id] = step
        predecessors[step.id] = [steps[index - 1].id] if index > 0 else []
        successors.setdefault(step.id, [])
        if index > 0:
            prev = steps[index - 1].id
            successors.setdefault(prev, []).append(step.id)

    return WorkflowDefinitionParsed(
        name=str(row[3]),
        version=int(row[2]),
        description=str(row[5]) if row[5] else "",
        steps=steps,
        step_index=step_index,
        predecessors=predecessors,
        successors=successors,
    )


def _load_workflow_context(
    raw_context: Any,
    *,
    workspace_id: str,
    execution_id: str,
    workflow_version: int,
) -> WorkflowContext:
    context_dict = _json_loads(raw_context)
    if isinstance(context_dict, dict):
        context_dict.setdefault("workspace_id", workspace_id)
        context_dict.setdefault("workflow_execution_id", execution_id)
        context_dict.setdefault("workflow_version", workflow_version)
        return WorkflowContext.from_dict(context_dict)
    return WorkflowContext(
        workspace_id=workspace_id,
        workflow_execution_id=execution_id,
        workflow_version=workflow_version,
    )


def _sync_step_execution_rows(
    conn: Any,
    *,
    execution_id: str,
    workspace_id: str,
    definition: WorkflowDefinitionParsed,
    workflow_context: WorkflowContext,
    engine: WorkflowEngine,
    step_errors: dict[str, str | None],
) -> None:
    now = datetime.now(UTC).isoformat()
    for step in definition.steps:
        row = conn.execute(
            text(
                "SELECT id FROM workflow_step_executions "
                "WHERE workflow_execution_id = :eid AND step_id = :step_id "
                "LIMIT 1"
            ),
            {"eid": execution_id, "step_id": step.id},
        ).first()
        step_output = workflow_context.step_outputs.get(step.id)
        timing = workflow_context.step_timings.get(step.id)
        result_payload = None
        if step_output is not None:
            result_payload = {
                "status": step_output.status,
                "summary": step_output.summary,
                "warnings": step_output.warnings,
            }

        params = {
            "id": str(uuid.uuid4()),
            "eid": execution_id,
            "step_id": step.id,
            "step_type": step.type,
            "step_config": _json_dumps(step.config) or "{}",
            "status": engine.step_states.get(
                step.id, WorkflowStepExecutionStatus.pending
            ).value,
            "iteration": 0,
            "result": _json_dumps(result_payload),
            "error_summary": step_errors.get(step.id),
            "started_at": timing.started_at if timing else None,
            "completed_at": timing.completed_at if timing else None,
            "workspace_id": workspace_id,
            "updated_at": now,
            "created_at": now,
        }
        if row is None:
            conn.execute(
                text(
                    "INSERT INTO workflow_step_executions "
                    "(id, workflow_execution_id, step_id, step_type, step_config, "
                    "status, iteration, result, error_summary, started_at, "
                    "completed_at, created_at, updated_at, workspace_id) "
                    "VALUES (:id, :eid, :step_id, :step_type, :step_config, "
                    ":status, :iteration, :result, :error_summary, :started_at, "
                    ":completed_at, :created_at, :updated_at, :workspace_id)"
                ),
                params,
            )
            continue
        conn.execute(
            text(
                "UPDATE workflow_step_executions SET "
                "step_type = :step_type, "
                "step_config = :step_config, "
                "status = :status, "
                "iteration = :iteration, "
                "result = :result, "
                "error_summary = :error_summary, "
                "started_at = :started_at, "
                "completed_at = :completed_at, "
                "updated_at = :updated_at "
                "WHERE workflow_execution_id = :eid AND step_id = :step_id"
            ),
            params,
        )


def _resolve_execution_status(
    engine: WorkflowEngine,
    step_errors: dict[str, str | None],
) -> tuple[str, str | None, str | None]:
    waiting_steps = engine.get_waiting_steps()
    if waiting_steps:
        waiting_step = waiting_steps[0]
        return "paused", waiting_step, step_errors.get(waiting_step)

    for step_id, state in engine.step_states.items():
        if state in {
            WorkflowStepExecutionStatus.failed,
            WorkflowStepExecutionStatus.partially_failed,
            WorkflowStepExecutionStatus.interrupted,
        }:
            return "paused", step_id, step_errors.get(step_id)

    if engine.execution_status == WorkflowExecutionStatus.completed:
        return "completed", None, None

    ready_steps = engine.get_ready_steps()
    if ready_steps:
        return "running", ready_steps[0], None

    return engine.execution_status.value, None, None


def _update_execution_row(
    conn: Any,
    *,
    execution_id: str,
    workflow_context: WorkflowContext,
    engine: WorkflowEngine,
    definition: WorkflowDefinitionParsed,
    step_errors: dict[str, str | None],
) -> None:
    now = datetime.now(UTC).isoformat()
    status, current_step_id, error_summary = _resolve_execution_status(
        engine, step_errors
    )
    conn.execute(
        text(
            "UPDATE workflow_executions SET "
            "status = :status, "
            "current_step_id = :current_step_id, "
            "step_execution_count = :step_execution_count, "
            "context = :context, "
            "error_summary = :error_summary, "
            "paused_at = :paused_at, "
            "completed_at = :completed_at, "
            "updated_at = :updated_at "
            "WHERE id = :id"
        ),
        {
            "id": execution_id,
            "status": status,
            "current_step_id": current_step_id,
            "step_execution_count": len(definition.steps),
            "context": workflow_context.to_json(),
            "error_summary": error_summary,
            "paused_at": now if status == "paused" else None,
            "completed_at": now if status == "completed" else None,
            "updated_at": now,
        },
    )


def _resolve_workspace_root(conn: Any, workspace_id: str) -> Path:
    row = conn.execute(
        text("SELECT root_path FROM workspaces WHERE id = :wid"),
        {"wid": workspace_id},
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return Path(str(row[0])).expanduser().resolve()


def _resolve_dataset(
    conn: Any,
    *,
    workspace_id: str,
    source: str,
) -> tuple[str, str | None]:
    rows = conn.execute(
        text(
            "SELECT id, record_kind, source_config FROM datasets "
            "WHERE workspace_id = :wid"
        ),
        {"wid": workspace_id},
    ).fetchall()
    source_norm = str(Path(source).as_posix())
    for row in rows:
        source_config = _json_loads(row[2])
        paths = []
        if isinstance(source_config, dict):
            raw_paths = source_config.get("paths", [])
            if isinstance(raw_paths, list):
                paths = [str(Path(str(path)).as_posix()) for path in raw_paths]
        if source_norm in paths:
            return str(row[0]), str(row[1]) if row[1] else None

    dataset_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    conn.execute(
        text(
            "INSERT INTO datasets "
            "(id, dataset_name, dataset_slug, source_type, source_config, "
            "loader_plugin, record_kind, canonical_id_strategy, indexing_mode, "
            "record_count, labeled_count, health_status, created_at, updated_at, "
            "last_indexed_at, workspace_id) "
            "VALUES (:id, :name, :slug, 'local_file', :source_config, NULL, NULL, "
            "'source_record_id', 'projection', 0, 0, 'stale', :now, :now, :now, "
            ":wid)"
        ),
        {
            "id": dataset_id,
            "name": Path(source_norm).stem,
            "slug": Path(source_norm).stem,
            "source_config": _json_dumps({"paths": [source_norm]}),
            "now": now,
            "wid": workspace_id,
        },
    )
    return dataset_id, None


def _extract_record_text(payload: dict[str, Any] | None) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ("text", "content", "message", "review", "body", "input"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return json.dumps(payload, sort_keys=True)


def _infer_sentiment_labels(text_value: str) -> dict[str, str]:
    lowered = text_value.lower()
    positive_hits = sum(
        token in lowered
        for token in ("love", "great", "excellent", "good", "amazing", "helpful")
    )
    negative_hits = sum(
        token in lowered
        for token in ("bad", "awful", "terrible", "hate", "broken", "slow")
    )
    if positive_hits > negative_hits:
        sentiment = "positive"
    elif negative_hits > positive_hits:
        sentiment = "negative"
    else:
        sentiment = "neutral"
    return {"sentiment": sentiment}


def _resolve_task_schema(
    conn: Any,
    *,
    workspace_id: str,
    selector: str | None,
) -> tuple[str, str]:
    if selector:
        row = conn.execute(
            text(
                """
                SELECT id, blind_review_policy
                FROM task_schemas
                WHERE workspace_id = :wid
                  AND (id = :selector OR task_schema_slug = :selector)
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"wid": workspace_id, "selector": selector},
        ).first()
        if row is not None:
            return str(row[0]), str(row[1])

    rows = conn.execute(
        text(
            "SELECT id, blind_review_policy FROM task_schemas "
            "WHERE workspace_id = :wid AND is_active = 1 "
            "ORDER BY created_at DESC"
        ),
        {"wid": workspace_id},
    ).fetchall()
    if len(rows) == 1:
        return str(rows[0][0]), str(rows[0][1])
    if not rows:
        raise HTTPException(status_code=400, detail="No active task schema available")
    raise HTTPException(
        status_code=400,
        detail="Workflow step requires task_schema_id when multiple schemas exist",
    )


def _ensure_model_profile(
    conn: Any,
    *,
    workspace_id: str,
    model_identifier: str,
) -> str:
    row = conn.execute(
        text(
            "SELECT id FROM model_profiles "
            "WHERE workspace_id = :wid AND id = :model "
            "ORDER BY created_at DESC LIMIT 1"
        ),
        {"wid": workspace_id, "model": model_identifier},
    ).first()
    if row is not None:
        return str(row[0])
    row = conn.execute(
        text(
            "SELECT id FROM model_profiles "
            "WHERE id = :model "
            "ORDER BY created_at DESC LIMIT 1"
        ),
        {"model": model_identifier},
    ).first()
    if row is not None:
        return str(row[0])
    row = conn.execute(
        text(
            "SELECT id FROM model_profiles "
            "WHERE workspace_id = :wid "
            "AND (model_identifier = :model OR model_profile_slug = :model) "
            "ORDER BY created_at DESC LIMIT 1"
        ),
        {"wid": workspace_id, "model": model_identifier},
    ).first()
    if row is not None:
        return str(row[0])
    # Fall back to any workspace (the model-profile endpoint may use a
    # default workspace_id that differs from the workflow's workspace).
    row = conn.execute(
        text(
            "SELECT id FROM model_profiles "
            "WHERE model_identifier = :model OR model_profile_slug = :model "
            "ORDER BY created_at DESC LIMIT 1"
        ),
        {"model": model_identifier},
    ).first()
    if row is not None:
        return str(row[0])

    profile_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    slug = model_identifier.lower().replace(" ", "-")
    conn.execute(
        text(
            """
            INSERT INTO model_profiles (
                id, model_profile_slug, provider_type, provider_name,
                model_identifier, transport, auth_ref, supports_structured_output,
                supports_tool_use, context_window, capability_tags, routing_metadata,
                cost_per_input_token, cost_per_output_token, is_available,
                created_at, updated_at, workspace_id
            )
            VALUES (
                :id, :slug, :provider_type, :provider_name, :model_identifier,
                'builtin', NULL, 1, 0, NULL, :capability_tags, NULL, NULL, NULL, 1,
                :now, :now, :wid
            )
            """
        ),
        {
            "id": profile_id,
            "slug": slug,
            "provider_type": ProviderType.custom.value,
            "provider_name": "builtin-heuristic",
            "model_identifier": model_identifier,
            "capability_tags": _json_dumps(["heuristic", "workflow-demo"]),
            "now": now,
            "wid": workspace_id,
        },
    )
    return profile_id


class _LoadedRecord:
    def __init__(self, record_id: str) -> None:
        self.id = record_id


class _WorkflowDataLoader:
    def __init__(self, conn: Any, *, workspace_id: str, workspace_root: Path) -> None:
        self._conn = conn
        self._workspace_id = workspace_id
        self._workspace_root = workspace_root

    def load_records(
        self,
        source: str,
        _config: dict[str, Any],
    ) -> list[_LoadedRecord]:
        source_path = (self._workspace_root / source).resolve()
        if not source_path.is_file():
            raise FileNotFoundError(f"Data source not found: {source}")

        dataset_id, default_record_kind = _resolve_dataset(
            self._conn,
            workspace_id=self._workspace_id,
            source=source,
        )
        existing_rows = self._conn.execute(
            text("SELECT id, external_id FROM records WHERE dataset_id = :dataset_id"),
            {"dataset_id": dataset_id},
        ).fetchall()
        existing_by_external = {
            str(row[1]): str(row[0]) for row in existing_rows if row[1] is not None
        }

        records: list[_LoadedRecord] = []
        now = datetime.now(UTC).isoformat()
        lines = source_path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            if not line.strip():
                continue
            payload = json.loads(line)
            external_id = str(
                payload.get("id")
                or payload.get("record_id")
                or payload.get("external_id")
                or f"{source_path.stem}-{index + 1}"
            )
            record_id = existing_by_external.get(external_id)
            content_hash = hashlib.sha256(
                json.dumps(payload, sort_keys=True).encode("utf-8")
            ).hexdigest()
            if record_id is None:
                record_id = str(uuid.uuid4())
                stable_fields = {
                    "text": _extract_record_text(payload),
                }
                self._conn.execute(
                    text(
                        """
                        INSERT INTO records (
                            id, external_id, sequence_index, content_hash,
                            stable_fields, payload, record_kind, source_metadata,
                            label_count, latest_label, composite_confidence,
                            export_eligible, flags, created_at, updated_at,
                            workspace_id, dataset_id, artifact_id
                        )
                        VALUES (
                            :id, :external_id, :sequence_index, :content_hash,
                            :stable_fields, :payload, :record_kind,
                            :source_metadata, 0, NULL, NULL, 0, NULL,
                            :created_at, :updated_at, :workspace_id,
                            :dataset_id, NULL
                        )
                        """
                    ),
                    {
                        "id": record_id,
                        "external_id": external_id,
                        "sequence_index": index,
                        "content_hash": content_hash,
                        "stable_fields": _json_dumps(stable_fields) or "{}",
                        "payload": _json_dumps(payload) or "{}",
                        "record_kind": default_record_kind or "text",
                        "source_metadata": _json_dumps(
                            {"source": source, "line_number": index + 1}
                        ),
                        "created_at": now,
                        "updated_at": now,
                        "workspace_id": self._workspace_id,
                        "dataset_id": dataset_id,
                    },
                )
            records.append(_LoadedRecord(record_id))

        self._conn.execute(
            text(
                """
                UPDATE datasets
                SET record_count = :record_count,
                    health_status = 'healthy',
                    last_indexed_at = :now,
                    updated_at = :now
                WHERE id = :dataset_id
                """
            ),
            {
                "record_count": len(records),
                "now": now,
                "dataset_id": dataset_id,
            },
        )
        return records


class _HeuristicAgentRunner:
    def __init__(self, conn: Any, *, workspace_id: str) -> None:
        self._conn = conn
        self._workspace_id = workspace_id

    def run(self, **kwargs: Any) -> dict[str, Any]:
        record_ids = [str(record_id) for record_id in kwargs.get("record_ids", [])]
        agent_run_id = str(kwargs.get("agent_run_id") or uuid.uuid4())
        config = dict(kwargs.get("config", {}))
        model_identifier = str(config.get("model") or "heuristic-agent")
        task_schema_selector = config.get("task_schema_id")
        now = datetime.now(UTC).isoformat()

        if not record_ids:
            return {
                "agent_run_id": agent_run_id,
                "status": "completed",
                "total_records": 0,
                "completed_records": 0,
                "failed_records": 0,
                "batch_size": 1,
                "batch_count": 0,
                "event_count": 0,
            }

        first_record = self._conn.execute(
            text("SELECT dataset_id FROM records WHERE id = :record_id LIMIT 1"),
            {"record_id": record_ids[0]},
        ).first()
        if first_record is None:
            raise HTTPException(status_code=404, detail="Record not found")

        dataset_id = str(first_record[0])
        task_schema_id, blind_policy = _resolve_task_schema(
            self._conn,
            workspace_id=self._workspace_id,
            selector=str(task_schema_selector)
            if task_schema_selector is not None
            else None,
        )
        model_profile_id = _ensure_model_profile(
            self._conn,
            workspace_id=self._workspace_id,
            model_identifier=model_identifier,
        )
        self._conn.execute(
            text(
                """
                INSERT INTO agent_runs (
                    id, dataset_id, task_schema_id, model_profile_id,
                    runtime_profile_id, prompt_template_id, prompt_version,
                    agent_role, adapter_plugin, status, config, record_filter,
                    total_records, completed_records, failed_records, retry_count,
                    error_summary, cost_estimate, cost_actual, comparison_id,
                    started_at, completed_at, created_at, updated_at,
                    workspace_id, workflow_step_execution_id
                )
                VALUES (
                    :id, :dataset_id, :task_schema_id, :model_profile_id,
                    NULL, NULL, NULL, :agent_role, 'builtin.heuristic',
                    'completed', :config, NULL, :total_records,
                    :completed_records, 0, 0, NULL, NULL, NULL, NULL,
                    :started_at, :completed_at, :created_at, :updated_at,
                    :workspace_id, NULL
                )
                """
            ),
            {
                "id": agent_run_id,
                "dataset_id": dataset_id,
                "task_schema_id": task_schema_id,
                "model_profile_id": model_profile_id,
                "agent_role": str(kwargs.get("agent_role") or "proposer"),
                "config": _json_dumps(config),
                "total_records": len(record_ids),
                "completed_records": len(record_ids),
                "started_at": now,
                "completed_at": now,
                "created_at": now,
                "updated_at": now,
                "workspace_id": self._workspace_id,
            },
        )

        show_outputs = blind_policy == BlindReviewPolicy.show_agent_outputs.value
        for record_id in record_ids:
            record_row = self._conn.execute(
                text("SELECT payload FROM records WHERE id = :record_id LIMIT 1"),
                {"record_id": record_id},
            ).first()
            payload = _json_loads(record_row[0]) if record_row else {}
            labels = _infer_sentiment_labels(_extract_record_text(payload))
            self._conn.execute(
                text(
                    """
                    INSERT INTO agent_outputs (
                        id, agent_run_id, record_id, task_schema_id, output_type,
                        labels, raw_response, confidence_self_reported,
                        confidence_self_consistency, confidence_logprobs,
                        composite_confidence, tokens_input, tokens_output,
                        latency_ms, validation_passed, validation_errors,
                        retry_attempt, is_visible_for_review,
                        normalization_status, created_at, workspace_id
                    )
                    VALUES (
                        :id, :agent_run_id, :record_id, :task_schema_id,
                        'labels', :labels, :raw_response, NULL, NULL, NULL,
                        :confidence, NULL, NULL, NULL, 1, NULL, 0,
                        :is_visible_for_review, 'ready', :created_at,
                        :workspace_id
                    )
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "agent_run_id": agent_run_id,
                    "record_id": record_id,
                    "task_schema_id": task_schema_id,
                    "labels": _json_dumps(labels) or "{}",
                    "raw_response": _json_dumps(
                        {
                            "strategy": "builtin-heuristic",
                            "model": model_identifier,
                        }
                    ),
                    "confidence": 0.6,
                    "is_visible_for_review": 1 if show_outputs else 0,
                    "created_at": now,
                    "workspace_id": self._workspace_id,
                },
            )

        return {
            "agent_run_id": agent_run_id,
            "status": "completed",
            "total_records": len(record_ids),
            "completed_records": len(record_ids),
            "failed_records": 0,
            "batch_size": max(1, len(record_ids)),
            "batch_count": 1 if record_ids else 0,
            "event_count": len(record_ids),
        }


class _LlmAgentRunner:
    """Agent runner that calls a real LLM provider for label proposals.

    Loads the model profile, prompt template, and task schema from the DB,
    then calls the provider via StructuredOutputEnforcer for each record.
    Results are normalized and persisted to agent_outputs.
    """

    def __init__(self, conn: Any, *, workspace_id: str) -> None:
        self._conn = conn
        self._workspace_id = workspace_id

    def run(self, **kwargs: Any) -> dict[str, Any]:
        try:
            return self._run_inner(**kwargs)
        except Exception:
            logger.exception("_LlmAgentRunner.run() crashed")
            raise

    def _run_inner(self, **kwargs: Any) -> dict[str, Any]:
        record_ids = [str(record_id) for record_id in kwargs.get("record_ids", [])]
        agent_run_id = str(kwargs.get("agent_run_id") or uuid.uuid4())
        config = dict(kwargs.get("config", {}))
        model_identifier = str(config.get("model") or "")
        task_schema_selector = config.get("task_schema_id")
        prompt_ref = config.get("prompt_ref")
        agent_role = str(kwargs.get("agent_role") or "proposer")
        now = datetime.now(UTC).isoformat()

        if not record_ids:
            return {
                "agent_run_id": agent_run_id,
                "status": "completed",
                "total_records": 0,
                "completed_records": 0,
                "failed_records": 0,
                "batch_size": 1,
                "batch_count": 0,
                "event_count": 0,
            }

        # --- resolve DB references ---
        first_record = self._conn.execute(
            text("SELECT dataset_id FROM records WHERE id = :record_id LIMIT 1"),
            {"record_id": record_ids[0]},
        ).first()
        if first_record is None:
            raise HTTPException(status_code=404, detail="Record not found")

        dataset_id = str(first_record[0])
        task_schema_id, blind_policy = _resolve_task_schema(
            self._conn,
            workspace_id=self._workspace_id,
            selector=str(task_schema_selector)
            if task_schema_selector is not None
            else None,
        )
        model_profile_id = _ensure_model_profile(
            self._conn,
            workspace_id=self._workspace_id,
            model_identifier=model_identifier,
        )

        # Load full model profile for provider instantiation
        profile_row = self._conn.execute(
            text(
                "SELECT provider_type, auth_ref, model_identifier, "
                "routing_metadata "
                "FROM model_profiles WHERE id = :pid LIMIT 1"
            ),
            {"pid": model_profile_id},
        ).first()
        if profile_row is None:
            raise HTTPException(
                status_code=500,
                detail=f"Model profile '{model_profile_id}' not found after ensure",
            )
        provider_type = str(profile_row[0])
        auth_ref = profile_row[1]
        db_model_id = str(profile_row[2])
        routing_metadata = _json_loads(profile_row[3]) or {}
        base_url = (
            routing_metadata.get("base_url")
            if isinstance(routing_metadata, dict)
            else None
        )
        logger.info(
            "LLM runner: profile_id=%s provider=%s model=%s "
            "auth_ref=%s base_url=%s routing_metadata=%s",
            model_profile_id,
            provider_type,
            db_model_id,
            auth_ref,
            base_url,
            routing_metadata,
        )

        # Load prompt template
        system_instructions, task_rubric = self._load_prompt(prompt_ref)

        # Load task schema label fields for structured output
        label_fields = self._load_label_fields(task_schema_id)
        output_schema = self._build_output_schema(label_fields)

        # Instantiate provider adapter
        adapter = self._create_adapter(
            provider_type, auth_ref=auth_ref, base_url=base_url
        )
        enforcer = _get_structured_output_enforcer()

        # Create agent_runs row
        self._conn.execute(
            text(
                """
                INSERT INTO agent_runs (
                    id, dataset_id, task_schema_id, model_profile_id,
                    runtime_profile_id, prompt_template_id, prompt_version,
                    agent_role, adapter_plugin, status, config, record_filter,
                    total_records, completed_records, failed_records, retry_count,
                    error_summary, cost_estimate, cost_actual, comparison_id,
                    started_at, completed_at, created_at, updated_at,
                    workspace_id, workflow_step_execution_id
                )
                VALUES (
                    :id, :dataset_id, :task_schema_id, :model_profile_id,
                    NULL, NULL, NULL, :agent_role, :adapter_plugin,
                    'running', :config, NULL, :total_records,
                    0, 0, 0, NULL, NULL, NULL, NULL,
                    :started_at, NULL, :created_at, :updated_at,
                    :workspace_id, NULL
                )
                """
            ),
            {
                "id": agent_run_id,
                "dataset_id": dataset_id,
                "task_schema_id": task_schema_id,
                "model_profile_id": model_profile_id,
                "agent_role": agent_role,
                "adapter_plugin": f"builtin.{provider_type}",
                "config": _json_dumps(config),
                "total_records": len(record_ids),
                "started_at": now,
                "created_at": now,
                "updated_at": now,
                "workspace_id": self._workspace_id,
            },
        )

        show_outputs = blind_policy == BlindReviewPolicy.show_agent_outputs.value
        completed = 0
        failed = 0
        error_summary_parts: list[str] = []

        for record_id in record_ids:
            try:
                labels, raw_response, confidence, tokens_in, tokens_out, latency = (
                    self._label_record(
                        record_id=record_id,
                        adapter=adapter,
                        enforcer=enforcer,
                        db_model_id=db_model_id,
                        system_instructions=system_instructions,
                        task_rubric=task_rubric,
                        output_schema=output_schema,
                        label_fields=label_fields,
                    )
                )
                self._conn.execute(
                    text(
                        """
                        INSERT INTO agent_outputs (
                            id, agent_run_id, record_id, task_schema_id, output_type,
                            labels, raw_response, confidence_self_reported,
                            confidence_self_consistency, confidence_logprobs,
                            composite_confidence, tokens_input, tokens_output,
                            latency_ms, validation_passed, validation_errors,
                            retry_attempt, is_visible_for_review,
                            normalization_status, created_at, workspace_id
                        )
                        VALUES (
                            :id, :agent_run_id, :record_id, :task_schema_id,
                            'labels', :labels, :raw_response, NULL, NULL, NULL,
                            :confidence, :tokens_input, :tokens_output,
                            :latency_ms, 1, NULL, 0,
                            :is_visible_for_review, 'normalized', :created_at,
                            :workspace_id
                        )
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "agent_run_id": agent_run_id,
                        "record_id": record_id,
                        "task_schema_id": task_schema_id,
                        "labels": _json_dumps(labels) or "{}",
                        "raw_response": _json_dumps(raw_response),
                        "confidence": confidence,
                        "tokens_input": tokens_in,
                        "tokens_output": tokens_out,
                        "latency_ms": latency,
                        "is_visible_for_review": 1 if show_outputs else 0,
                        "created_at": datetime.now(UTC).isoformat(),
                        "workspace_id": self._workspace_id,
                    },
                )
                completed += 1
            except Exception as exc:
                failed += 1
                error_summary_parts.append(
                    f"record {record_id}: {type(exc).__name__}: {exc}"
                )
                logger.warning(
                    "LLM labeling failed for record %s: %s",
                    record_id,
                    exc,
                    exc_info=True,
                )

        # Update agent_runs row with final status
        final_status = (
            "completed"
            if failed == 0
            else ("partially_completed" if completed > 0 else "failed")
        )
        finished_at = datetime.now(UTC).isoformat()
        self._conn.execute(
            text(
                """
                UPDATE agent_runs
                SET status = :status,
                    completed_records = :completed,
                    failed_records = :failed,
                    error_summary = :error_summary,
                    completed_at = :completed_at,
                    updated_at = :updated_at
                WHERE id = :id
                """
            ),
            {
                "id": agent_run_id,
                "status": final_status,
                "completed": completed,
                "failed": failed,
                "error_summary": "; ".join(error_summary_parts[:5])
                if error_summary_parts
                else None,
                "completed_at": finished_at,
                "updated_at": finished_at,
            },
        )

        logger.info(
            "LLM agent run %s: %d/%d completed, %d failed (model=%s)",
            agent_run_id,
            completed,
            len(record_ids),
            failed,
            db_model_id,
        )

        return {
            "agent_run_id": agent_run_id,
            "status": final_status,
            "total_records": len(record_ids),
            "completed_records": completed,
            "failed_records": failed,
            "batch_size": max(1, len(record_ids)),
            "batch_count": 1 if record_ids else 0,
            "event_count": completed,
        }

    def _label_record(
        self,
        *,
        record_id: str,
        adapter: Any,
        enforcer: Any,
        db_model_id: str,
        system_instructions: str,
        task_rubric: str | None,
        output_schema: dict[str, Any],
        label_fields: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], dict[str, Any], float, int, int, int]:
        """Call the LLM for a single record and return normalized labels.

        Returns (labels, raw_response, confidence, tokens_in, tokens_out, latency_ms).
        """
        from molabel.core.agents.output_validator import _normalize_labels
        from molabel.core.types import LabelFieldDefinition, Message

        record_row = self._conn.execute(
            text("SELECT payload FROM records WHERE id = :record_id LIMIT 1"),
            {"record_id": record_id},
        ).first()
        payload = _json_loads(record_row[0]) if record_row else {}
        record_text = _extract_record_text(payload)

        # Build messages with task schema context
        system_parts = [system_instructions]
        if task_rubric:
            system_parts.append(f"\n\nTask rubric:\n{task_rubric}")

        # Include label field definitions so the model knows what to produce
        field_descriptions: list[str] = []
        for f in label_fields:
            desc = f"- `{f['name']}` ({f.get('field_type', 'string')})"
            if f.get("required", True):
                desc += ", required"
            if f.get("description"):
                desc += f": {f['description']}"
            if f.get("options"):
                desc += f"\n  Valid values: {f['options']}"
            field_descriptions.append(desc)
        if field_descriptions:
            system_parts.append(
                "\n\nYou must return a JSON object with these fields:\n"
                + "\n".join(field_descriptions)
                + "\n\nSelect labels ONLY from the valid values listed above."
            )

        system_msg = Message(role="system", content="".join(system_parts))
        user_msg = Message(
            role="user",
            content=f"Classify the following text:\n\n{record_text}",
        )

        # Run in a thread to avoid "asyncio.run() cannot be called from
        # a running event loop" — the adapter's complete() uses asyncio.run()
        # internally, but FastAPI's endpoint handler is already async.
        import concurrent.futures

        def _enforce() -> Any:
            return enforcer.enforce(
                adapter,
                [system_msg, user_msg],
                db_model_id,
                output_schema,
                temperature=0.0,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(_enforce).result(timeout=120)

        if not result.is_valid or result.parsed is None:
            raise ValueError(
                f"Structured output enforcement failed: {result.validation_errors}"
            )

        # Normalize labels against task schema field definitions
        field_defs = [
            LabelFieldDefinition(
                name=f["name"],
                field_type=f["field_type"],
                required=f.get("required", True),
                options=f.get("options"),
                description=f.get("description", ""),
            )
            for f in label_fields
        ]
        normalized, _norm_errors = _normalize_labels(result.parsed, field_defs)

        confidence = result.parsed.get("confidence", 0.8)
        if not isinstance(confidence, (int, float)):
            confidence = 0.8

        raw_response = {
            "strategy": "llm-structured-output",
            "model": db_model_id,
            "attempts": result.attempts,
            "used_native": result.used_native,
            "raw_content": result.raw_content[:500],
        }

        return (
            normalized,
            raw_response,
            float(confidence),
            0,  # tokens_in — not tracked by enforcer
            0,  # tokens_out — not tracked by enforcer
            0,  # latency_ms — not tracked by enforcer
        )

    def _load_prompt(self, prompt_ref: str | None) -> tuple[str, str | None]:
        """Load system_instructions and task_rubric from the prompt_templates table."""
        if prompt_ref:
            row = self._conn.execute(
                text(
                    "SELECT system_instructions, task_rubric "
                    "FROM prompt_templates "
                    "WHERE workspace_id = :wid "
                    "  AND (id = :ref OR prompt_slug = :ref) "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"wid": self._workspace_id, "ref": prompt_ref},
            ).first()
            if row is not None:
                return str(row[0]), row[1] if row[1] else None

        # Fallback: generic classification prompt
        logger.warning(
            "Prompt '%s' not found; using generic classification prompt",
            prompt_ref,
        )
        return (
            "You are a precise text classification assistant. "
            "Classify the input text according to the provided schema. "
            "Return ONLY the structured output matching the required fields.",
            None,
        )

    def _load_label_fields(self, task_schema_id: str) -> list[dict[str, Any]]:
        """Load label field definitions from the task_schemas table."""
        row = self._conn.execute(
            text("SELECT label_fields FROM task_schemas WHERE id = :id LIMIT 1"),
            {"id": task_schema_id},
        ).first()
        if row is None:
            return []
        fields = _json_loads(row[0])
        return fields if isinstance(fields, list) else []

    def _build_output_schema(
        self, label_fields: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Build a JSON Schema from task schema label fields."""
        properties: dict[str, Any] = {}
        required: list[str] = []

        type_map = {
            "categorical": "string",
            "ordinal": "string",
            "text": "string",
            "bool": "boolean",
            "numeric": "number",
        }

        for field in label_fields:
            name = field["name"]
            ftype = field.get("field_type", "string")

            if ftype == "multi_select":
                # multi_select fields are JSON arrays whose items are
                # constrained to the declared options vocabulary.
                items_schema: dict[str, Any] = {"type": "string"}
                if field.get("options"):
                    items_schema["enum"] = field["options"]
                prop: dict[str, Any] = {
                    "type": "array",
                    "items": items_schema,
                }
            else:
                prop = {
                    "type": type_map.get(ftype, "string"),
                }
                if field.get("options"):
                    prop["enum"] = field["options"]

            if field.get("description"):
                prop["description"] = field["description"]
            properties[name] = prop
            if field.get("required", True):
                required.append(name)

        return {
            "title": "structured_output",
            "type": "object",
            "properties": properties,
            "required": required,
        }

    def _create_adapter(
        self,
        provider_type: str,
        *,
        auth_ref: str | None,
        base_url: str | None,
    ) -> Any:
        """Instantiate the correct provider adapter from profile data."""
        if provider_type == ProviderType.anthropic:
            import os

            from molabel.core.providers.anthropic_adapter import AnthropicAdapter

            kwargs: dict[str, Any] = {}
            if auth_ref:
                kwargs["auth_ref"] = auth_ref
            # Use base_url from profile, fall back to ANTHROPIC_BASE_URL env
            effective_base_url = base_url or os.environ.get("ANTHROPIC_BASE_URL")
            if effective_base_url:
                kwargs["base_url"] = effective_base_url
            return AnthropicAdapter(**kwargs)

        if provider_type == ProviderType.openai_compatible:
            from molabel.core.providers.openai_adapter import OpenAIAdapter

            kwargs = {}
            if auth_ref:
                kwargs["auth_ref"] = auth_ref
            if base_url:
                kwargs["base_url"] = base_url
            return OpenAIAdapter(**kwargs)

        if provider_type == ProviderType.openrouter:
            from molabel.core.providers.openrouter_adapter import OpenRouterAdapter

            return OpenRouterAdapter(auth_ref=auth_ref)

        if provider_type == ProviderType.ollama:
            from molabel.core.providers.ollama_adapter import OllamaAdapter

            kwargs = {}
            if base_url:
                kwargs["base_url"] = base_url
            return OllamaAdapter(**kwargs)

        raise HTTPException(
            status_code=500,
            detail=f"Unsupported provider type for LLM runner: {provider_type}",
        )


def _get_structured_output_enforcer() -> Any:
    """Lazy import to avoid circular dependency at module level."""
    from molabel.core.providers.structured_output import StructuredOutputEnforcer

    return StructuredOutputEnforcer()


class _WorkflowExporter:
    def __init__(self, conn: Any, *, workspace_root: Path) -> None:
        self._conn = conn
        self._workspace_root = workspace_root

    def export(
        self,
        *,
        record_ids: list[str],
        format: str,
        destination: str,
        config: dict[str, Any],
        bundle_id: str,
    ) -> dict[str, Any]:
        del config
        if format != "jsonl":
            return {"record_count": len(record_ids)}

        destination_dir = (self._workspace_root / destination).resolve()
        destination_dir.mkdir(parents=True, exist_ok=True)
        output_path = destination_dir / f"{bundle_id}.jsonl"

        rows: list[str] = []
        for record_id in record_ids:
            row = self._conn.execute(
                text(
                    "SELECT external_id, payload, latest_label "
                    "FROM records WHERE id = :record_id LIMIT 1"
                ),
                {"record_id": record_id},
            ).first()
            if row is None:
                continue
            payload = _json_loads(row[1])
            latest_label = _json_loads(row[2])
            payload_dict = payload if isinstance(payload, dict) else {"value": payload}
            rows.append(
                json.dumps(
                    {
                        "record_id": record_id,
                        "external_id": str(row[0]) if row[0] else None,
                        **payload_dict,
                        "labels": latest_label,
                    }
                )
            )

        output_path.write_text(
            "\n".join(rows) + ("\n" if rows else ""),
            encoding="utf-8",
        )
        return {
            "record_count": len(rows),
            "file_path": str(output_path),
        }


def _materialize_review_queue(
    conn: Any,
    *,
    workspace_id: str,
    queue_id: str,
    record_ids: list[str],
    config: dict[str, Any],
    workflow_context: WorkflowContext,
) -> None:
    existing = conn.execute(
        text("SELECT count(*) FROM review_tasks WHERE queue_id = :queue_id"),
        {"queue_id": queue_id},
    ).first()
    if existing is not None and int(existing[0]) > 0:
        return

    task_schema_id, _blind_policy = _resolve_task_schema(
        conn,
        workspace_id=workspace_id,
        selector=str(config.get("task_schema_id"))
        if config.get("task_schema_id") is not None
        else None,
    )
    latest_agent_run_id = (
        workflow_context.agent_run_ids[-1] if workflow_context.agent_run_ids else None
    )
    output_rows = []
    if latest_agent_run_id:
        output_rows = conn.execute(
            text(
                "SELECT id, record_id FROM agent_outputs "
                "WHERE agent_run_id = :agent_run_id"
            ),
            {"agent_run_id": latest_agent_run_id},
        ).fetchall()
    output_by_record = {str(row[1]): uuid.UUID(str(row[0])) for row in output_rows}

    now = datetime.now(UTC).isoformat()
    for priority, record_id in enumerate(record_ids, start=1):
        record_row = conn.execute(
            text("SELECT dataset_id FROM records WHERE id = :record_id LIMIT 1"),
            {"record_id": record_id},
        ).first()
        if record_row is None:
            continue
        agent_output_ids = None
        output_id = output_by_record.get(record_id)
        if output_id is not None:
            agent_output_ids = serialize_agent_output_ids([output_id])
        conn.execute(
            text(
                "INSERT INTO review_tasks "
                "(id, queue_id, record_id, task_schema_id, status, priority, "
                "priority_reason, claimed_by, claimed_at, claim_expired_count, "
                "is_overlap, is_calibration, draft_labels, agent_output_ids, "
                "ai_revealed, ai_revealed_at, submitted_at, created_at, updated_at, "
                "workspace_id, dataset_id) "
                "VALUES (:id, :queue_id, :record_id, :task_schema_id, :status, "
                ":priority, 'workflow_queue', NULL, NULL, 0, 0, 0, NULL, "
                ":agent_output_ids, 0, NULL, NULL, :created_at, :updated_at, "
                ":workspace_id, :dataset_id)"
            ),
            {
                "id": str(uuid.uuid4()),
                "queue_id": queue_id,
                "record_id": record_id,
                "task_schema_id": task_schema_id,
                "status": ReviewTaskStatusEnum.available.value,
                "priority": priority,
                "agent_output_ids": agent_output_ids,
                "created_at": now,
                "updated_at": now,
                "workspace_id": workspace_id,
                "dataset_id": str(record_row[0]),
            },
        )


def _assert_human_queue_complete(
    conn: Any,
    *,
    workflow_context: WorkflowContext,
    step_id: str,
) -> None:
    step_output = workflow_context.step_outputs.get(step_id)
    queue_id = ""
    if step_output is not None:
        queue_id = str(step_output.summary.get("queue_id", ""))
    if not queue_id:
        return

    remaining = conn.execute(
        text(
            "SELECT count(*) FROM review_tasks "
            "WHERE queue_id = :queue_id AND status != 'submitted'"
        ),
        {"queue_id": queue_id},
    ).scalar_one()
    if int(remaining) > 0:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Review queue '{queue_id}' is not complete; "
                f"{int(remaining)} task(s) still need submission"
            ),
        )


def _restore_engine_state(
    conn: Any,
    *,
    execution_id: str,
    engine: WorkflowEngine,
) -> None:
    rows = conn.execute(
        text(
            "SELECT step_id, status FROM workflow_step_executions "
            "WHERE workflow_execution_id = :eid"
        ),
        {"eid": execution_id},
    ).fetchall()
    for row in rows:
        step_id = str(row[0])
        status = str(row[1])
        if step_id in engine._step_states:
            engine._step_states[step_id] = WorkflowStepExecutionStatus(status)


def _select_agent_runner(
    conn: Any,
    *,
    definition: WorkflowDefinitionParsed,
    workspace_id: str,
) -> _LlmAgentRunner | _HeuristicAgentRunner:
    """Pick the right agent runner based on the workflow's step configs.

    If any agent_run / agent_labeling step references a real model
    (i.e. not 'heuristic-agent') that has a model profile with a known
    provider_type, use _LlmAgentRunner.  Otherwise fall back to
    _HeuristicAgentRunner.
    """
    agent_step_types = {"agent_run", "agent_labeling"}

    def _lookup_provider_type(
        *,
        model_identifier: str | None = None,
        model_profile_id: str | None = None,
    ) -> str | None:
        if model_profile_id:
            row = conn.execute(
                text(
                    "SELECT provider_type FROM model_profiles "
                    "WHERE workspace_id = :wid AND id = :pid "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"wid": workspace_id, "pid": model_profile_id},
            ).first()
            if row is None:
                row = conn.execute(
                    text(
                        "SELECT provider_type FROM model_profiles "
                        "WHERE id = :pid ORDER BY created_at DESC LIMIT 1"
                    ),
                    {"pid": model_profile_id},
                ).first()
            if row is not None:
                return str(row[0])

        if model_identifier:
            row = conn.execute(
                text(
                    "SELECT provider_type FROM model_profiles "
                    "WHERE workspace_id = :wid AND id = :model "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"wid": workspace_id, "model": model_identifier},
            ).first()
            if row is None:
                row = conn.execute(
                    text(
                        "SELECT provider_type FROM model_profiles "
                        "WHERE id = :model ORDER BY created_at DESC LIMIT 1"
                    ),
                    {"model": model_identifier},
                ).first()
            if row is not None:
                return str(row[0])

            row = conn.execute(
                text(
                    "SELECT provider_type FROM model_profiles "
                    "WHERE workspace_id = :wid "
                    "AND (model_identifier = :model OR model_profile_slug = :model) "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"wid": workspace_id, "model": model_identifier},
            ).first()
            if row is None:
                row = conn.execute(
                    text(
                        "SELECT provider_type FROM model_profiles "
                        "WHERE model_identifier = :model OR model_profile_slug = :model "
                        "ORDER BY created_at DESC LIMIT 1"
                    ),
                    {"model": model_identifier},
                ).first()
            if row is not None:
                return str(row[0])

        return None

    for step in definition.steps:
        logger.debug("Runner selection: step '%s' type='%s'", step.id, step.type)
        if step.type not in agent_step_types:
            continue
        model_identifier = (
            str(step.config.get("model")) if step.config.get("model") else None
        )
        model_profile_id = (
            str(step.config.get("model_profile_id"))
            if step.config.get("model_profile_id")
            else None
        )
        logger.info(
            "Runner selection: agent step '%s' model='%s' model_profile_id='%s' "
            "config=%s",
            step.id,
            model_identifier,
            model_profile_id,
            step.config,
        )
        if model_identifier == "heuristic-agent":
            continue
        if model_identifier is None and model_profile_id is None:
            continue
        # Debug: list all model profiles in the DB
        all_profiles = conn.execute(
            text(
                "SELECT id, model_profile_slug, model_identifier, provider_type, "
                "workspace_id "
                "FROM model_profiles ORDER BY created_at DESC"
            )
        ).fetchall()
        logger.info(
            "Runner selection: searching for model_identifier='%s', "
            "model_profile_id='%s', workspace='%s'. All profiles in DB: %s",
            model_identifier,
            model_profile_id,
            workspace_id,
            [
                (str(r[0]), str(r[1]), str(r[2]), str(r[3]), str(r[4]))
                for r in all_profiles
            ],
        )
        provider_type = _lookup_provider_type(
            model_identifier=model_identifier,
            model_profile_id=model_profile_id,
        )
        if provider_type is not None:
            logger.info(
                "Runner selection: found profile for model='%s' profile_id='%s', "
                "provider_type='%s' (custom=%s)",
                model_identifier,
                model_profile_id,
                provider_type,
                provider_type == ProviderType.custom,
            )
            if provider_type != ProviderType.custom:
                logger.info(
                    "Using LLM agent runner for model '%s' profile_id='%s' "
                    "(provider=%s)",
                    model_identifier,
                    model_profile_id,
                    provider_type,
                )
                return _LlmAgentRunner(conn, workspace_id=workspace_id)
        else:
            logger.warning(
                "Runner selection: no model profile found for model='%s' "
                "profile_id='%s' in workspace '%s' or globally",
                model_identifier,
                model_profile_id,
                workspace_id,
            )

    logger.info("Runner selection: falling back to HeuristicAgentRunner")
    return _HeuristicAgentRunner(conn, workspace_id=workspace_id)


def _run_engine_until_blocked(
    conn: Any,
    *,
    execution_id: str,
    workflow_row: Any,
    workflow_context: WorkflowContext,
    resume_step_id: str | None = None,
) -> tuple[WorkflowDefinitionParsed, WorkflowEngine, dict[str, str | None]]:
    definition = _build_workflow_definition(workflow_row)
    workspace_id = str(workflow_row[10])
    workspace_root = _resolve_workspace_root(conn, workspace_id)
    agent_runner = _select_agent_runner(
        conn, definition=definition, workspace_id=workspace_id
    )
    engine = WorkflowEngine(
        create_default_registry(),
        services={
            "data_loader": _WorkflowDataLoader(
                conn,
                workspace_id=workspace_id,
                workspace_root=workspace_root,
            ),
            "agent_runner": agent_runner,
            "exporter": _WorkflowExporter(
                conn,
                workspace_root=workspace_root,
            ),
        },
    )
    engine.initialize(definition, workflow_context)
    step_errors: dict[str, str | None] = {}

    if resume_step_id is not None:
        _restore_engine_state(conn, execution_id=execution_id, engine=engine)
        current_state = engine.step_states.get(resume_step_id)
        if current_state == WorkflowStepExecutionStatus.waiting_for_human:
            _assert_human_queue_complete(
                conn,
                workflow_context=workflow_context,
                step_id=resume_step_id,
            )
            engine.resume_human_step(resume_step_id)
        elif current_state == WorkflowStepExecutionStatus.waiting_for_breakpoint:
            engine.continue_breakpoint(resume_step_id)
        elif current_state == WorkflowStepExecutionStatus.waiting_for_gate:
            engine.approve_gate(resume_step_id, approved=True)

    _sync_step_execution_rows(
        conn,
        execution_id=execution_id,
        workspace_id=workspace_id,
        definition=definition,
        workflow_context=workflow_context,
        engine=engine,
        step_errors=step_errors,
    )

    while True:
        ready_steps = engine.get_ready_steps()
        if not ready_steps:
            break
        current_step_id = ready_steps[0]
        result = engine.execute_step(current_step_id)
        if result.error:
            step_errors[current_step_id] = result.error
        _sync_step_execution_rows(
            conn,
            execution_id=execution_id,
            workspace_id=workspace_id,
            definition=definition,
            workflow_context=workflow_context,
            engine=engine,
            step_errors=step_errors,
        )
        if result.waiting_for_human:
            step_output = workflow_context.step_outputs.get(current_step_id)
            if step_output is not None:
                queue_id = str(step_output.summary.get("queue_id", ""))
                if queue_id:
                    record_set = workflow_context.record_sets.get(current_step_id)
                    _materialize_review_queue(
                        conn,
                        workspace_id=workspace_id,
                        queue_id=queue_id,
                        record_ids=list(record_set.record_ids if record_set else []),
                        config=definition.get_step(current_step_id).config,
                        workflow_context=workflow_context,
                    )
            break
        if not result.success:
            break

    _update_execution_row(
        conn,
        execution_id=execution_id,
        workflow_context=workflow_context,
        engine=engine,
        definition=definition,
        step_errors=step_errors,
    )
    return definition, engine, step_errors


# ---------------------------------------------------------------------------
# Endpoints — workflow definitions
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedResponse[WorkflowSummary])
async def list_workflows(
    request: Request,
    params: Annotated[QueryParams, Depends()],
) -> PaginatedResponse[WorkflowSummary]:
    """List workflow definitions (API-019)."""
    engine = get_engine(request)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, workflow_slug, version, name, steps, "
                "description, is_template, is_active, workspace_id, "
                "created_at, updated_at "
                "FROM workflow_definitions "
                "ORDER BY created_at DESC "
                "LIMIT :limit"
            ),
            {"limit": params.limit},
        ).fetchall()

    items = [_row_to_summary(r) for r in rows]
    return PaginatedResponse(items=items, cursor=None, has_more=False)


@router.get("/{workflow_id}", response_model=WorkflowDetail)
async def get_workflow(
    request: Request,
    workflow_id: uuid.UUID,
) -> WorkflowDetail:
    """Get workflow definition detail (API-020)."""
    engine = get_engine(request)
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, workflow_slug, version, name, steps, "
                "description, is_template, template_source, file_path, "
                "is_active, workspace_id, created_at, updated_at "
                "FROM workflow_definitions WHERE id = :id"
            ),
            {"id": str(workflow_id)},
        ).first()

    if row is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    return _row_to_detail(row)


@router.post("", response_model=WorkflowDetail, status_code=201)
async def create_workflow(
    request: Request,
    body: WorkflowCreate,
    _reviewer: CurrentReviewer,
) -> WorkflowDetail:
    """Create a new workflow definition (API-021)."""
    import json

    engine = get_engine(request)
    workflow_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    slug = body.workflow_slug or body.name.lower().replace(" ", "-")
    file_path = body.file_path or f"workflows/{slug}.yaml"

    steps_json = json.dumps([s.model_dump(mode="json") for s in body.steps])

    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO workflow_definitions "
                "(id, workflow_slug, version, name, steps, description, "
                "is_template, template_source, file_path, is_active, "
                "workspace_id, created_at, updated_at) "
                "VALUES (:id, :slug, 1, :name, :steps, :desc, "
                ":is_template, :template_source, :fp, 1, :wid, :now, :now)"
            ),
            {
                "id": workflow_id,
                "slug": slug,
                "name": body.name,
                "steps": steps_json,
                "desc": body.description,
                "is_template": 1 if body.is_template else 0,
                "template_source": body.template_source,
                "fp": file_path,
                "wid": body.workspace_id,
                "now": now,
            },
        )
        conn.commit()

        row = conn.execute(
            text(
                "SELECT id, workflow_slug, version, name, steps, "
                "description, is_template, template_source, file_path, "
                "is_active, workspace_id, created_at, updated_at "
                "FROM workflow_definitions WHERE id = :id"
            ),
            {"id": workflow_id},
        ).first()

    return _row_to_detail(row)


@router.put("/{workflow_id}", response_model=WorkflowDetail)
async def update_workflow(
    request: Request,
    workflow_id: uuid.UUID,
    body: WorkflowUpdate,
    _reviewer: CurrentReviewer,
) -> WorkflowDetail:
    """Update a workflow definition (API-022)."""
    import json

    engine = get_engine(request)
    now = datetime.now(UTC).isoformat()

    with engine.connect() as conn:
        existing = conn.execute(
            text("SELECT id FROM workflow_definitions WHERE id = :id"),
            {"id": str(workflow_id)},
        ).first()
        if existing is None:
            raise HTTPException(status_code=404, detail="Workflow not found")

        updates: list[str] = ["updated_at = :now"]
        params: dict[str, Any] = {"id": str(workflow_id), "now": now}

        if body.name is not None:
            updates.append("name = :name")
            params["name"] = body.name
        if body.description is not None:
            updates.append("description = :desc")
            params["desc"] = body.description
        if body.steps is not None:
            updates.append("steps = :steps")
            params["steps"] = json.dumps(
                [s.model_dump(mode="json") for s in body.steps]
            )
        if body.is_active is not None:
            updates.append("is_active = :is_active")
            params["is_active"] = 1 if body.is_active else 0

        set_clause = ", ".join(updates)
        conn.execute(
            text(
                f"UPDATE workflow_definitions SET {set_clause} WHERE id = :id"  # noqa: S608
            ),
            params,
        )
        conn.commit()

        row = conn.execute(
            text(
                "SELECT id, workflow_slug, version, name, steps, "
                "description, is_template, template_source, file_path, "
                "is_active, workspace_id, created_at, updated_at "
                "FROM workflow_definitions WHERE id = :id"
            ),
            {"id": str(workflow_id)},
        ).first()

    return _row_to_detail(row)


# ---------------------------------------------------------------------------
# Endpoints — workflow executions
# ---------------------------------------------------------------------------


@router.post(
    "/{workflow_id}/execute",
    response_model=WorkflowExecution,
    status_code=202,
)
async def execute_workflow(
    request: Request,
    workflow_id: uuid.UUID,
    _reviewer: CurrentReviewer,
    body: WorkflowExecuteRequest | None = None,
) -> WorkflowExecution:
    """Execute a workflow (API-023)."""
    engine = get_engine(request)
    now = datetime.now(UTC).isoformat()

    with engine.connect() as conn:
        wf_row = conn.execute(
            text(
                "SELECT id, workflow_slug, version, name, steps, description, "
                "is_template, template_source, file_path, is_active, workspace_id, "
                "created_at, updated_at "
                "FROM workflow_definitions WHERE id = :id"
            ),
            {"id": str(workflow_id)},
        ).first()
        if wf_row is None:
            raise HTTPException(status_code=404, detail="Workflow not found")

        exec_id = str(uuid.uuid4())
        initial_context = dict(body.context or {}) if body and body.context else {}
        if body and body.dataset_id:
            initial_context.setdefault("dataset_id", body.dataset_id)

        conn.execute(
            text(
                "INSERT INTO workflow_executions "
                "(id, workflow_definition_id, workflow_version, status, "
                "context, workspace_id, started_at, created_at, updated_at) "
                "VALUES (:id, :wfid, :ver, 'running', :ctx, :wid, :now, :now, :now)"
            ),
            {
                "id": exec_id,
                "wfid": str(workflow_id),
                "ver": int(wf_row[2]),
                "ctx": _json_dumps(initial_context),
                "wid": str(wf_row[10]),
                "now": now,
            },
        )
        workflow_context = _load_workflow_context(
            initial_context,
            workspace_id=str(wf_row[10]),
            execution_id=exec_id,
            workflow_version=int(wf_row[2]),
        )
        _run_engine_until_blocked(
            conn,
            execution_id=exec_id,
            workflow_row=wf_row,
            workflow_context=workflow_context,
        )
        conn.commit()
        exec_row = conn.execute(
            text(
                "SELECT id, workflow_definition_id, workflow_version, status, "
                "current_step_id, step_execution_count, error_summary, "
                "started_at, paused_at, completed_at, created_at, updated_at "
                "FROM workflow_executions WHERE id = :id"
            ),
            {"id": exec_id},
        ).first()

    if exec_row is None:
        raise HTTPException(status_code=500, detail="Execution was not persisted")
    execution = _execution_row_to_model(exec_row)
    if execution.status == "paused" and execution.error_summary:
        execution.status = "running"
    return execution


@router.get(
    "/{workflow_id}/executions",
    response_model=PaginatedResponse[WorkflowExecution],
)
async def list_executions(
    request: Request,
    workflow_id: uuid.UUID,
    params: Annotated[QueryParams, Depends()],
) -> PaginatedResponse[WorkflowExecution]:
    """List executions for a workflow (API-024)."""
    engine = get_engine(request)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, workflow_definition_id, workflow_version, status, "
                "current_step_id, step_execution_count, error_summary, "
                "started_at, paused_at, completed_at, created_at, updated_at "
                "FROM workflow_executions "
                "WHERE workflow_definition_id = :wfid "
                "ORDER BY created_at DESC "
                "LIMIT :limit"
            ),
            {"wfid": str(workflow_id), "limit": params.limit},
        ).fetchall()

    items = [_execution_row_to_model(r) for r in rows]
    return PaginatedResponse(items=items, cursor=None, has_more=False)


@router.get(
    "/{workflow_id}/executions/{execution_id}",
    response_model=WorkflowExecutionDetail,
)
async def get_execution(
    request: Request,
    workflow_id: uuid.UUID,
    execution_id: uuid.UUID,
) -> WorkflowExecutionDetail:
    """Get execution detail with step states (API-025)."""
    import json

    engine = get_engine(request)
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, workflow_definition_id, workflow_version, status, "
                "current_step_id, step_execution_count, error_summary, "
                "context, started_at, paused_at, completed_at, "
                "created_at, updated_at "
                "FROM workflow_executions "
                "WHERE id = :eid AND workflow_definition_id = :wfid"
            ),
            {"eid": str(execution_id), "wfid": str(workflow_id)},
        ).first()

        if row is None:
            raise HTTPException(status_code=404, detail="Execution not found")

        step_rows = conn.execute(
            text(
                "SELECT id, step_id, step_type, status, iteration, "
                "result, error_summary, started_at, completed_at "
                "FROM workflow_step_executions "
                "WHERE workflow_execution_id = :eid "
                "ORDER BY created_at"
            ),
            {"eid": str(execution_id)},
        ).fetchall()

    def _parse_json(val: Any) -> Any:
        if val is None:
            return None
        if isinstance(val, (dict, list)):
            return val
        try:
            return json.loads(str(val))
        except (json.JSONDecodeError, TypeError):
            return None

    step_states = [
        StepState(
            step_execution_id=str(sr[0]),
            step_id=str(sr[1]),
            step_type=str(sr[2]),
            status=str(sr[3]),
            iteration=int(sr[4]) if sr[4] is not None else 0,
            result=_parse_json(sr[5]),
            error_summary=str(sr[6]) if sr[6] else None,
            started_at=(datetime.fromisoformat(str(sr[7])) if sr[7] else None),
            completed_at=(datetime.fromisoformat(str(sr[8])) if sr[8] else None),
        )
        for sr in step_rows
    ]

    return WorkflowExecutionDetail(
        execution_id=str(row[0]),
        workflow_definition_id=str(row[1]),
        workflow_version=int(row[2]),
        status=str(row[3]),
        current_step_id=str(row[4]) if row[4] else None,
        step_execution_count=int(row[5]) if row[5] is not None else None,
        error_summary=str(row[6]) if row[6] else None,
        context=_parse_json(row[7]),
        step_states=step_states,
        started_at=(datetime.fromisoformat(str(row[8])) if row[8] else None),
        paused_at=(datetime.fromisoformat(str(row[9])) if row[9] else None),
        completed_at=(datetime.fromisoformat(str(row[10])) if row[10] else None),
        created_at=(
            datetime.fromisoformat(str(row[11])) if row[11] else datetime.now(UTC)
        ),
        updated_at=(
            datetime.fromisoformat(str(row[12])) if row[12] else datetime.now(UTC)
        ),
    )


@router.post(
    "/{workflow_id}/executions/{execution_id}/steps/{step_id}/advance",
    response_model=WorkflowExecutionDetail,
)
async def advance_step(
    request: Request,
    workflow_id: uuid.UUID,
    execution_id: uuid.UUID,
    step_id: str,
    _reviewer: CurrentReviewer,
    body: StepAdvanceRequest | None = None,
) -> WorkflowExecutionDetail:
    """Advance a workflow step (API-026)."""
    engine = get_engine(request)
    with engine.connect() as conn:
        exec_row = conn.execute(
            text(
                """
                SELECT id, workflow_definition_id, workflow_version,
                       context, workspace_id
                FROM workflow_executions
                WHERE id = :eid AND workflow_definition_id = :wfid
                """
            ),
            {"eid": str(execution_id), "wfid": str(workflow_id)},
        ).first()
        if exec_row is None:
            raise HTTPException(status_code=404, detail="Execution not found")

        wf_row = conn.execute(
            text(
                "SELECT id, workflow_slug, version, name, steps, description, "
                "is_template, template_source, file_path, is_active, workspace_id, "
                "created_at, updated_at "
                "FROM workflow_definitions WHERE id = :id"
            ),
            {"id": str(workflow_id)},
        ).first()
        if wf_row is None:
            raise HTTPException(status_code=404, detail="Workflow not found")

        workflow_context = _load_workflow_context(
            exec_row[3],
            workspace_id=str(exec_row[4]),
            execution_id=str(execution_id),
            workflow_version=int(exec_row[2]),
        )
        _run_engine_until_blocked(
            conn,
            execution_id=str(execution_id),
            workflow_row=wf_row,
            workflow_context=workflow_context,
            resume_step_id=step_id,
        )
        conn.commit()

    return await get_execution(request, workflow_id, execution_id)


@router.post(
    "/{workflow_id}/executions/{execution_id}/pause",
    response_model=WorkflowExecutionDetail,
)
async def pause_execution(
    request: Request,
    workflow_id: uuid.UUID,
    execution_id: uuid.UUID,
    _reviewer: CurrentReviewer,
) -> WorkflowExecutionDetail:
    """Pause a running workflow execution (API-027)."""
    engine = get_engine(request)
    now = datetime.now(UTC).isoformat()

    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, status FROM workflow_executions "
                "WHERE id = :eid AND workflow_definition_id = :wfid"
            ),
            {"eid": str(execution_id), "wfid": str(workflow_id)},
        ).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Execution not found")

        conn.execute(
            text(
                "UPDATE workflow_executions "
                "SET status = 'paused', paused_at = :now, updated_at = :now "
                "WHERE id = :eid"
            ),
            {"now": now, "eid": str(execution_id)},
        )
        conn.commit()

    return await get_execution(request, workflow_id, execution_id)


@router.post(
    "/{workflow_id}/executions/{execution_id}/cancel",
    response_model=WorkflowExecutionDetail,
)
async def cancel_execution(
    request: Request,
    workflow_id: uuid.UUID,
    execution_id: uuid.UUID,
    _reviewer: CurrentReviewer,
) -> WorkflowExecutionDetail:
    """Cancel a running or paused workflow execution (API-028)."""
    engine = get_engine(request)
    now = datetime.now(UTC).isoformat()

    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, status FROM workflow_executions "
                "WHERE id = :eid AND workflow_definition_id = :wfid"
            ),
            {"eid": str(execution_id), "wfid": str(workflow_id)},
        ).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Execution not found")

        conn.execute(
            text(
                "UPDATE workflow_executions "
                "SET status = 'cancelled', completed_at = :now, updated_at = :now "
                "WHERE id = :eid"
            ),
            {"now": now, "eid": str(execution_id)},
        )
        conn.commit()

    return await get_execution(request, workflow_id, execution_id)

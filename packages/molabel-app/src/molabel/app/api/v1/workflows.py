"""Workflow endpoints — /api/v1/workflows.

CRUD for workflow definitions plus execution management
(API-019 through API-028).
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import bindparam, text

from molabel.app.api.v1.model_profiles import SHARED_PROFILE_WORKSPACE
from molabel.app.middleware.session import CurrentReviewer
from molabel.app.schemas import (
    ErrorDetail,
    ErrorResponse,
    PaginatedResponse,
    QueryParams,
)
from molabel.app.utils import get_engine
from molabel.app.workspace_config import WORKFLOW, workspace_files, workspace_folder
from molabel.app.workspace_paths import resolve_in_workspace
from molabel.core.agents.queue_binding import serialize_agent_output_ids
from molabel.core.providers.base import ProviderError, resolve_api_key
from molabel.core.providers.detection import ProviderDetector
from molabel.core.providers.model_defaults import (
    MINIMAX_M27_HIGHSPEED,
    is_minimax_model,
)
from molabel.core.providers.offline_adapter import (
    OFFLINE_CONFIDENCE,
    OFFLINE_MODEL_ID,
)
from molabel.core.quality.agreement_metrics import AgreementRecord
from molabel.core.quality.review_agreement import (
    AgentProposal,
    ReviewEventLabels,
    agreement_records_from_reviews,
)
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


def _option_description_lines(field: dict[str, Any]) -> list[str]:
    descriptions = field.get("option_descriptions")
    options = field.get("options")
    if not isinstance(descriptions, dict) or not isinstance(options, list):
        return []

    lines: list[str] = []
    for option in options:
        text = descriptions.get(str(option))
        if text:
            lines.append(f"  - `{option}`: {text}")
    return lines


def _format_label_field_for_prompt(field: dict[str, Any]) -> str:
    desc = f"- `{field['name']}` ({field.get('field_type', 'string')})"
    if field.get("required", True):
        desc += ", required"
    if field.get("description"):
        desc += f": {field['description']}"
    if field.get("options"):
        desc += f"\n  Valid values: {field['options']}"
    option_lines = _option_description_lines(field)
    if option_lines:
        desc += "\n  Option rubric:\n" + "\n".join(option_lines)
    return desc


def _json_schema_field_description(field: dict[str, Any]) -> str:
    description = str(field.get("description") or "")
    option_lines = _option_description_lines(field)
    if option_lines:
        rubric = "Option rubric:\n" + "\n".join(option_lines)
        return f"{description}\n\n{rubric}" if description else rubric
    return description


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


def _with_offline_model(config: dict[str, Any]) -> dict[str, Any]:
    """Select the offline provider's one model for ``provider_type: offline``.

    ``model`` and ``model_profile_id`` each become that model, or ``model``
    does when the step sets neither. A model profile the step pins by id
    stays, so that its provider is checked against the step's.
    """
    if _normalize_provider_type(config.get("provider_type")) != ProviderType.offline:
        return config
    selected = {
        key: str(config.get(key) or "").strip() for key in ("model", "model_profile_id")
    }
    if not any(selected.values()):
        return {**config, "model": OFFLINE_MODEL_ID}
    return {
        **config,
        **{
            key: OFFLINE_MODEL_ID
            for key, value in selected.items()
            if value and _profile_id(value) is None
        },
    }


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
            config=_with_offline_model(dict(item.get("config", {}))),
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
    config: dict[str, Any] | None = None,
) -> tuple[str, str | None, dict[str, Any]]:
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
            return (
                str(row[0]),
                str(row[1]) if row[1] else None,
                source_config if isinstance(source_config, dict) else {},
            )

    dataset_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    source_config: dict[str, Any] = {"paths": [source_norm]}
    if isinstance(config, dict):
        record_id_field = config.get("record_id_field")
        if isinstance(record_id_field, str) and record_id_field.strip():
            source_config["record_id_field"] = record_id_field.strip()
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
            "source_config": _json_dumps(source_config),
            "now": now,
            "wid": workspace_id,
        },
    )
    return dataset_id, None, source_config


def _extract_record_text(payload: dict[str, Any] | None) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ("text", "content", "message", "review", "body", "input"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return json.dumps(payload, sort_keys=True)


_PROMPT_LEAK_FIELDS = frozenset(
    {
        "label",
        "source_label",
        "gold_label",
        "gold_labels",
        "ground_truth",
        "ground_truth_label",
        "ground_truth_labels",
    }
)


def _sanitize_record_payload_for_prompt(
    payload: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Drop obvious truth-bearing fields from proposer-visible record payloads."""
    if not isinstance(payload, dict):
        return None
    return {
        key: value
        for key, value in payload.items()
        if key.lower() not in _PROMPT_LEAK_FIELDS
    }


def _build_record_prompt_content(
    *,
    record_identifier: str,
    payload: dict[str, Any] | None,
) -> str:
    """Build a stable user prompt that preserves structured record context."""
    sanitized_payload = _sanitize_record_payload_for_prompt(payload)
    parts = [f"Record ID: {record_identifier}"]
    record_text = _extract_record_text(sanitized_payload)
    if record_text:
        parts.append(f"Reviewer-facing text:\n{record_text}")
    if sanitized_payload:
        rendered_payload = json.dumps(
            sanitized_payload,
            indent=2,
            ensure_ascii=True,
            sort_keys=True,
        )
        parts.append(f"Raw record JSON:\n{rendered_payload}")
    return "\n\n".join(parts)


def _extract_external_record_id(
    payload: dict[str, Any],
    *,
    record_id_field: str | None,
    default_id: str,
) -> str:
    candidate_fields: list[str] = []
    if record_id_field:
        candidate_fields.append(record_id_field)
    candidate_fields.extend(["id", "record_id", "external_id"])

    seen: set[str] = set()
    for field_name in candidate_fields:
        normalized_name = str(field_name).strip()
        if not normalized_name or normalized_name in seen:
            continue
        seen.add(normalized_name)
        value = payload.get(normalized_name)
        if value is None:
            continue
        value_str = str(value).strip()
        if value_str:
            return value_str

    return default_id


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


def _normalize_provider_type(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _profile_id(value: str) -> str | None:
    """``value`` as a profile id in canonical UUID form, or None if not a UUID."""
    try:
        return str(uuid.UUID(value))
    except ValueError:
        return None


def _infer_profile_defaults(
    *,
    model_identifier: str,
    provider_type: str | None,
    provider_name: str | None,
    auth_ref: str | None,
    base_url: str | None,
) -> tuple[str, str | None, str | None, str | None]:
    import os

    normalized_model = model_identifier.strip().lower()
    inferred_provider_type = _normalize_provider_type(provider_type)
    inferred_provider_name = provider_name
    inferred_auth_ref = auth_ref
    inferred_base_url = base_url

    if inferred_provider_type is None:
        if normalized_model == OFFLINE_MODEL_ID:
            inferred_provider_type = ProviderType.offline.value
        elif normalized_model.startswith("claude-") or is_minimax_model(
            model_identifier
        ):
            inferred_provider_type = ProviderType.anthropic.value
        elif normalized_model.startswith(("gpt-", "o1", "o3", "o4")):
            inferred_provider_type = ProviderType.openai_compatible.value

    if inferred_provider_type == ProviderType.offline.value:
        inferred_provider_name = inferred_provider_name or "Offline heuristic"
        inferred_auth_ref = None
        inferred_base_url = None
    elif inferred_provider_type == ProviderType.anthropic.value:
        if not inferred_provider_name:
            inferred_provider_name = (
                MINIMAX_M27_HIGHSPEED.provider_name
                if is_minimax_model(model_identifier)
                else "Anthropic"
            )
        if not inferred_auth_ref:
            if is_minimax_model(model_identifier):
                inferred_auth_ref = (
                    MINIMAX_M27_HIGHSPEED.fallback_auth_ref
                    if MINIMAX_M27_HIGHSPEED.fallback_auth_ref
                    and os.environ.get(MINIMAX_M27_HIGHSPEED.fallback_auth_ref)
                    else MINIMAX_M27_HIGHSPEED.primary_auth_ref
                )
            else:
                inferred_auth_ref = "ANTHROPIC_API_KEY"
        if not inferred_base_url and is_minimax_model(model_identifier):
            inferred_base_url = os.environ.get(
                "MINIMAX_BASE_URL",
                MINIMAX_M27_HIGHSPEED.base_url,
            )
    elif inferred_provider_type == ProviderType.openai_compatible.value:
        if not inferred_provider_name:
            inferred_provider_name = "OpenAI Compatible"
        if not inferred_auth_ref:
            inferred_auth_ref = "OPENAI_API_KEY"

    return (
        inferred_provider_type or ProviderType.custom.value,
        inferred_provider_name,
        inferred_auth_ref,
        inferred_base_url,
    )


_DEFAULT_PROFILE_TRAITS: tuple[str, list[str], float | None] = (
    "https",
    ["workflow-auto-profile"],
    None,
)
_BUILTIN_PROFILE_TRAITS: dict[str, tuple[str, list[str], float | None]] = {
    ProviderType.offline.value: ("builtin", ["offline", "heuristic"], 0.0),
}
_RUNNABLE_PROVIDERS = frozenset(ProviderType) - {ProviderType.custom}
_AGENT_STEP_TYPES = frozenset({"agent_run", "agent_labeling"})


class UnresolvedModelError(Exception):
    """An agent step names a model or provider that MoLabel cannot run."""

    def __init__(
        self,
        message: str,
        *,
        model: str,
        provider_type: str | None,
        step_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.model = model
        self.provider_type = provider_type
        self.step_id = step_id


async def unresolved_model_error_handler(
    _request: Request, exc: UnresolvedModelError
) -> JSONResponse:
    providers = await ProviderDetector().detect_all()
    return JSONResponse(
        status_code=400,
        content=ErrorResponse(
            error=ErrorDetail(
                code="MODEL_UNRESOLVED",
                message=str(exc),
                details={
                    "step_id": exc.step_id,
                    "model": exc.model,
                    "provider_type": exc.provider_type,
                    "usable_providers": [
                        {
                            "provider_type": provider.provider_type,
                            "name": provider.name,
                            "models": provider.suggested_models,
                        }
                        for provider in providers
                    ],
                },
            )
        ).model_dump(mode="json"),
    )


def _resolve_step_model(
    conn: Any, *, workspace_id: str, config: dict[str, Any]
) -> str | None:
    """The model profile an agent step runs on, or None if it names no model.

    ``model`` and ``model_profile_id`` each select a profile through
    ``_ensure_model_profile``, and the step runs on the one ``model`` selects.
    When the step sets both, their profiles must have one provider, or
    ``UnresolvedModelError`` is raised.
    """
    config = _with_offline_model(config)

    def value(key: str) -> str | None:
        raw = config.get(key)
        return (str(raw).strip() or None) if raw is not None else None

    settings = {
        key: value(key)
        for key in ("provider_type", "provider_name", "auth_ref", "base_url")
    }
    resolved = [
        (
            selector,
            _ensure_model_profile(
                conn, workspace_id=workspace_id, model_identifier=selector, **settings
            ),
        )
        for selector in (value("model"), value("model_profile_id"))
        if selector is not None
    ]
    if len(resolved) == 2:
        (model, model_profile), (pinned, pinned_profile) = resolved
        providers = dict(
            conn.execute(
                text(
                    "SELECT id, provider_type FROM model_profiles "
                    "WHERE id IN (:model_profile, :pinned_profile)"
                ),
                {"model_profile": model_profile, "pinned_profile": pinned_profile},
            ).fetchall()
        )
        if providers[model_profile] != providers[pinned_profile]:
            raise UnresolvedModelError(
                f"Model profile {pinned} uses provider "
                f"{providers[pinned_profile]}, but the step's model {model} uses "
                f"provider {providers[model_profile]}",
                model=pinned,
                provider_type=settings["provider_type"],
            )
    return resolved[0][1] if resolved else None


def _resolve_agent_models(
    conn: Any, *, definition: WorkflowDefinitionParsed, workspace_id: str
) -> None:
    """Fail before any step runs when an agent step's model cannot run."""
    for step in definition.steps:
        if step.type in _AGENT_STEP_TYPES:
            configs = [step.config]
        elif step.type == "agent_compare":
            configs = [
                {**step.config, "model": model}
                for model in step.config.get("models") or []
            ]
        else:
            continue
        for config in configs:
            try:
                if _resolve_step_model(conn, workspace_id=workspace_id, config=config):
                    continue
                raise UnresolvedModelError(
                    "The step names no model. Set model, model_profile_id or "
                    "provider_type: offline",
                    model="",
                    provider_type=config.get("provider_type"),
                )
            except UnresolvedModelError as exc:
                raise UnresolvedModelError(
                    f"Step '{step.id}': {exc}",
                    model=exc.model,
                    provider_type=exc.provider_type,
                    step_id=step.id,
                ) from None


def _ensure_model_profile(
    conn: Any,
    *,
    workspace_id: str,
    model_identifier: str,
    provider_type: str | None = None,
    provider_name: str | None = None,
    auth_ref: str | None = None,
    base_url: str | None = None,
) -> str:
    """Return the model profile an agent step runs on, creating one if none fits.

    A ``model_identifier`` that is a profile's id pins that profile. MoLabel
    must be able to run its provider, and it must have ``provider_type`` when
    that is given, or ``UnresolvedModelError`` is raised. Otherwise a profile
    fits when its slug or model id is ``model_identifier``, MoLabel can run its
    provider, and, when ``provider_type`` is given, it has that provider.
    Profiles come from the step's workspace or the shared profile workspace,
    and the step's own workspace wins. Without a fitting profile, a
    ``model_identifier`` shaped like a profile id raises
    ``UnresolvedModelError``, so no provider receives it as a model. Any other
    gets a new profile whose provider comes from ``provider_type`` or else from
    the model id, and a model or provider MoLabel cannot run raises
    ``UnresolvedModelError``.
    """
    requested_provider = _normalize_provider_type(provider_type)
    pinned_id = _profile_id(model_identifier)
    rows = conn.execute(
        text(
            "SELECT id, provider_type FROM model_profiles "
            "WHERE workspace_id IN (:wid, :shared) "
            "AND (id = :pinned_id OR model_identifier = :model "
            "OR model_profile_slug = :model) "
            "ORDER BY workspace_id = :wid DESC, created_at DESC"
        ),
        {
            "wid": workspace_id,
            "shared": str(SHARED_PROFILE_WORKSPACE),
            "pinned_id": pinned_id,
            "model": model_identifier,
        },
    ).fetchall()
    pinned_provider = next(
        (provider for pid, provider in rows if pid == pinned_id), None
    )
    if pinned_provider is not None:
        if requested_provider not in (None, pinned_provider):
            message = (
                f"Model profile {model_identifier} uses provider "
                f"{pinned_provider}, but the step sets provider_type "
                f"{requested_provider}"
            )
        elif pinned_provider not in _RUNNABLE_PROVIDERS:
            message = (
                f"Model profile {model_identifier} uses provider "
                f"{pinned_provider}, which MoLabel cannot run"
            )
        else:
            return pinned_id
        raise UnresolvedModelError(
            message, model=model_identifier, provider_type=requested_provider
        )
    for existing_id, existing_provider in rows:
        if existing_provider not in _RUNNABLE_PROVIDERS:
            continue
        if requested_provider is None or existing_provider == requested_provider:
            return str(existing_id)
    if pinned_id is not None:
        raise UnresolvedModelError(
            f"No model profile has id {model_identifier}, and no profile "
            "MoLabel can run has it as its model",
            model=model_identifier,
            provider_type=requested_provider,
        )

    if requested_provider is not None and requested_provider not in (
        _RUNNABLE_PROVIDERS
    ):
        raise UnresolvedModelError(
            f"provider_type '{requested_provider}' is not a provider MoLabel can run",
            model=model_identifier,
            provider_type=requested_provider,
        )
    (
        resolved_provider_type,
        resolved_provider_name,
        resolved_auth_ref,
        resolved_base_url,
    ) = _infer_profile_defaults(
        model_identifier=model_identifier,
        provider_type=provider_type,
        provider_name=provider_name,
        auth_ref=auth_ref,
        base_url=base_url,
    )
    if resolved_provider_type not in _RUNNABLE_PROVIDERS:
        raise UnresolvedModelError(
            f"Model '{model_identifier}' matches no model profile and no known "
            "provider. Set provider_type on the step, or create a profile "
            "for it with `molabel model-profile create`",
            model=model_identifier,
            provider_type=None,
        )

    profile_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    slug = model_identifier.lower().replace(" ", "-")
    routing_metadata = {}
    if resolved_base_url:
        routing_metadata["base_url"] = resolved_base_url
    transport, capability_tags, token_cost = _BUILTIN_PROFILE_TRAITS.get(
        resolved_provider_type, _DEFAULT_PROFILE_TRAITS
    )
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
                :transport, :auth_ref, 1, 0, NULL, :capability_tags,
                :routing_metadata, :token_cost, :token_cost, 1,
                :now, :now, :wid
            )
            """
        ),
        {
            "id": profile_id,
            "slug": slug,
            "provider_type": resolved_provider_type,
            "provider_name": resolved_provider_name or resolved_provider_type,
            "model_identifier": model_identifier,
            "transport": transport,
            "auth_ref": resolved_auth_ref,
            "capability_tags": _json_dumps(capability_tags),
            "routing_metadata": (
                _json_dumps(routing_metadata) if routing_metadata else None
            ),
            "token_cost": token_cost,
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

    def load_dataset_records(self, dataset_id: str) -> list[_LoadedRecord]:
        dataset = self._conn.execute(
            text("SELECT id FROM datasets WHERE id = :id AND workspace_id = :wid"),
            {"id": dataset_id, "wid": self._workspace_id},
        ).first()
        if dataset is None:
            raise LookupError(f"Dataset not found in this workspace: {dataset_id}")
        rows = self._conn.execute(
            text(
                "SELECT id FROM records WHERE dataset_id = :dataset_id "
                "ORDER BY sequence_index, created_at"
            ),
            {"dataset_id": dataset_id},
        ).fetchall()
        if not rows:
            raise LookupError(
                f"Dataset {dataset_id} has no records. Import records first."
            )
        return [_LoadedRecord(str(row[0])) for row in rows]

    def load_records(
        self,
        source: str,
        _config: dict[str, Any],
    ) -> list[_LoadedRecord]:
        source_path = resolve_in_workspace(self._workspace_root, source)
        if not source_path.is_file():
            raise FileNotFoundError(f"Data source not found: {source}")

        dataset_id, default_record_kind, source_config = _resolve_dataset(
            self._conn,
            workspace_id=self._workspace_id,
            source=source,
            config=_config,
        )
        record_id_field = None
        if isinstance(source_config, dict):
            raw_record_id_field = source_config.get("record_id_field")
            if isinstance(raw_record_id_field, str) and raw_record_id_field.strip():
                record_id_field = raw_record_id_field.strip()
        if record_id_field is None:
            fallback_record_id_field = _config.get("record_id_field")
            if (
                isinstance(fallback_record_id_field, str)
                and fallback_record_id_field.strip()
            ):
                record_id_field = fallback_record_id_field.strip()
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
            external_id = _extract_external_record_id(
                payload,
                record_id_field=record_id_field,
                default_id=f"{source_path.stem}-{index + 1}",
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


def _requires_api_key(provider_type: str, base_url: str | None) -> bool:
    """Whether the provider is a hosted API that refuses calls without a key."""
    if provider_type == ProviderType.openai_compatible:
        return not base_url or urlparse(base_url).hostname == "api.openai.com"
    return provider_type in (ProviderType.anthropic, ProviderType.openrouter)


def _missing_key_hint(auth_ref: str) -> str:
    return (
        f"{auth_ref} is not set. To label without an API key, recreate the "
        "workflow with `molabel workflow create --template <template-id> "
        "--provider offline`, or set `provider_type: offline` in this "
        "agent_run step's config"
    )


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
        model_profile_id = _resolve_step_model(
            self._conn, workspace_id=self._workspace_id, config=config
        )
        if model_profile_id is None:
            raise UnresolvedModelError(
                "The step names no model",
                model="",
                provider_type=_normalize_provider_type(config.get("provider_type")),
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
        auth_rejected = False

        for record_id in record_ids:
            try:
                labels, raw_response, confidence, tokens_in, tokens_out, latency = (
                    self._label_record(
                        record_id=record_id,
                        provider_type=provider_type,
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
                if isinstance(exc, ProviderError) and exc.status_code in (401, 403):
                    auth_rejected = True
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
        if (
            completed == 0
            and auth_rejected
            and auth_ref
            and _requires_api_key(provider_type, base_url)
            and resolve_api_key(auth_ref) is None
        ):
            error_summary_parts.insert(0, _missing_key_hint(auth_ref))
        error_summary = (
            "; ".join(error_summary_parts[:5]) if error_summary_parts else None
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
                "error_summary": error_summary,
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
            "error_summary": error_summary,
            "provider_type": provider_type,
        }

    def _label_record(
        self,
        *,
        record_id: str,
        provider_type: str,
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
            text(
                "SELECT external_id, payload FROM records WHERE id = :record_id LIMIT 1"
            ),
            {"record_id": record_id},
        ).first()
        payload = _json_loads(record_row[1]) if record_row else {}
        record_identifier = (
            str(record_row[0]).strip()
            if record_row is not None and record_row[0]
            else record_id
        )

        # Build messages with task schema context
        system_parts = [system_instructions]
        if task_rubric:
            system_parts.append(f"\n\nTask rubric:\n{task_rubric}")

        # Include label field definitions so the model knows what to produce.
        field_descriptions: list[str] = []
        for f in label_fields:
            field_descriptions.append(_format_label_field_for_prompt(f))
        if field_descriptions:
            system_parts.append(
                "\n\nYou must return a JSON object with these fields:\n"
                + "\n".join(field_descriptions)
                + "\n\nSelect labels ONLY from the valid values listed above."
            )
        field_names = {str(field.get("name")) for field in label_fields}
        if "evidence_atoms" in field_names:
            system_parts.append(
                "\n\nEvidence field contract:\n"
                "- `evidence_atoms` must be a JSON array of stable evidence atom "
                "IDs copied exactly from the raw record JSON.\n"
                "- Never paraphrase evidence into natural-language summaries.\n"
                "- Use exact identifiers such as "
                "`doc_1001_sentence_2`, `Page_sentence_0`, or "
                "`Page_cell_0_1_1` when those appear in the raw record.\n"
                "- When a record carries grouped evidence candidates, flatten "
                "them into one array of exact atom IDs.\n"
                "- If the verdict is `nei`, return an empty evidence array "
                "unless the task rubric says otherwise."
            )
        if "rationale_token_mask" in field_names:
            system_parts.append(
                "\n\nRationale field contract:\n"
                "- `rationale_token_mask` must be a JSON array of 0/1 integers.\n"
                "- Its length must exactly match the token sequence in the raw "
                "record.\n"
                "- Do not return token strings, character spans, or prose "
                "explanations in place of the mask."
            )

        system_msg = Message(role="system", content="".join(system_parts))
        user_msg = Message(
            role="user",
            content=_build_record_prompt_content(
                record_identifier=record_identifier,
                payload=payload,
            ),
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
                option_descriptions=f.get("option_descriptions"),
                description=f.get("description", ""),
            )
            for f in label_fields
        ]
        normalized, _norm_errors = _normalize_labels(result.parsed, field_defs)

        if provider_type == ProviderType.offline:
            confidence = OFFLINE_CONFIDENCE
            strategy = "offline-heuristic"
        else:
            confidence = result.parsed.get("confidence", 0.8)
            if not isinstance(confidence, (int, float)):
                confidence = 0.8
            strategy = "llm-structured-output"

        raw_response = {
            "strategy": strategy,
            "provider_type": provider_type,
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
            elif ftype == "json" and name == "evidence_atoms":
                # Grounded evidence benchmarks rely on stable atom IDs surviving
                # the proposer -> workflow_autorun hop as a JSON array.
                prop = {
                    "type": "array",
                    "items": {"type": "string"},
                }
            elif ftype == "json" and name == "rationale_token_mask":
                prop = {
                    "type": "array",
                    "items": {"type": "integer", "enum": [0, 1]},
                }
            elif ftype == "json":
                prop = {
                    "type": "object",
                    "additionalProperties": True,
                }
            else:
                prop = {
                    "type": type_map.get(ftype, "string"),
                }
                if field.get("options"):
                    prop["enum"] = field["options"]

            field_description = _json_schema_field_description(field)
            if field_description:
                prop["description"] = field_description
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

        if provider_type == ProviderType.offline:
            from molabel.core.providers.offline_adapter import OfflineAdapter

            return OfflineAdapter()

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

        destination_dir = resolve_in_workspace(self._workspace_root, destination)
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


def _utc(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


class _ReviewAgreementSource:
    """Agreement records from a workflow's review events and agent proposals.

    ``molabel.core.quality.review_agreement`` decides which event counts and
    which labels each decision rates.
    """

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def load_agreement_records(
        self,
        *,
        record_ids: Sequence[str],
        review_queue_ids: Sequence[str],
        agent_run_ids: Sequence[str],
        analysis_type: str,
        config: dict[str, Any],
    ) -> list[AgreementRecord]:
        del analysis_type, config
        output_rows = self._conn.execute(
            text(
                "SELECT record_id, agent_run_id, labels FROM agent_outputs "
                "WHERE agent_run_id IN :run_ids"
            ).bindparams(bindparam("run_ids", expanding=True)),
            {"run_ids": list(agent_run_ids)},
        ).fetchall()
        event_rows = self._conn.execute(
            text(
                "SELECT e.id, e.record_id, e.reviewer_id, e.decision, e.labels, "
                "e.supersedes_event_id, e.created_at "
                "FROM review_events e "
                "JOIN review_tasks t ON t.id = e.review_task_id "
                "WHERE e.source = 'human' AND e.reviewer_id IS NOT NULL "
                "AND t.queue_id IN :queue_ids"
            ).bindparams(bindparam("queue_ids", expanding=True)),
            {"queue_ids": list(review_queue_ids)},
        ).fetchall()
        events = [
            ReviewEventLabels(
                event_id=str(row[0]),
                record_id=str(row[1]),
                reviewer_id=str(row[2]),
                decision=row[3],
                labels=_json_loads(row[4]) or {},
                supersedes_event_id=str(row[5]) if row[5] else None,
                created_at=_utc(row[6]),
            )
            for row in event_rows
        ]
        proposals = [
            AgentProposal(
                record_id=str(row[0]),
                agent_run_id=str(row[1]),
                labels=_json_loads(row[2]) or {},
            )
            for row in output_rows
        ]
        return agreement_records_from_reviews(events, proposals, record_ids=record_ids)


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
    overlap_count = int(config.get("overlap_count", 1))

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
        for _copy in range(overlap_count):
            conn.execute(
                text(
                    "INSERT INTO review_tasks "
                    "(id, queue_id, record_id, task_schema_id, status, priority, "
                    "priority_reason, claimed_by, claimed_at, claim_expired_count, "
                    "is_overlap, is_calibration, draft_labels, agent_output_ids, "
                    "ai_revealed, ai_revealed_at, submitted_at, created_at, "
                    "updated_at, workspace_id, dataset_id) "
                    "VALUES (:id, :queue_id, :record_id, :task_schema_id, :status, "
                    ":priority, 'workflow_queue', NULL, NULL, 0, :is_overlap, 0, "
                    "NULL, :agent_output_ids, 0, NULL, NULL, :created_at, "
                    ":updated_at, :workspace_id, :dataset_id)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "queue_id": queue_id,
                    "record_id": record_id,
                    "task_schema_id": task_schema_id,
                    "status": ReviewTaskStatusEnum.available.value,
                    "priority": priority,
                    "is_overlap": overlap_count > 1,
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

    remaining, copies, reviewers = conn.execute(
        text(
            "SELECT "
            "(SELECT count(*) FROM review_tasks "
            " WHERE queue_id = :queue_id AND status != 'submitted'), "
            "(SELECT coalesce(max(n), 0) FROM (SELECT count(*) AS n FROM review_tasks "
            " WHERE queue_id = :queue_id GROUP BY record_id)), "
            "(SELECT count(DISTINCT claimed_by) FROM review_tasks "
            " WHERE queue_id = :queue_id AND status = 'submitted')"
        ),
        {"queue_id": queue_id},
    ).one()
    if int(remaining) > 0:
        detail = (
            f"Review queue '{queue_id}' is not complete; "
            f"{int(remaining)} task(s) still need submission"
        )
        if int(copies) > max(int(reviewers), 1):
            detail += (
                f". {copies} copies need {copies} distinct reviewers; "
                f"{reviewers} have submitted"
            )
        raise HTTPException(status_code=409, detail=detail)


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
    _resolve_agent_models(conn, definition=definition, workspace_id=workspace_id)
    engine = WorkflowEngine(
        create_default_registry(),
        services={
            "data_loader": _WorkflowDataLoader(
                conn,
                workspace_id=workspace_id,
                workspace_root=workspace_root,
            ),
            "agent_runner": _LlmAgentRunner(conn, workspace_id=workspace_id),
            "exporter": _WorkflowExporter(
                conn,
                workspace_root=workspace_root,
            ),
            "agreement_data_source": _ReviewAgreementSource(conn),
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


_WORKFLOW_DOCUMENT_FIELDS = {
    "workflow_slug",
    "name",
    "description",
    "is_template",
    "template_source",
}

_WORKFLOW_DETAIL_SQL = text(
    "SELECT id, workflow_slug, version, name, steps, "
    "description, is_template, template_source, file_path, "
    "is_active, workspace_id, created_at, updated_at "
    "FROM workflow_definitions WHERE id = :id"
)


def _workflow_document(workflow: WorkflowCreate | WorkflowDetail) -> dict[str, Any]:
    """The workflow file: the core format that ``parse_workflow_yaml`` reads.

    The API names a step's fields ``step_id`` and ``step_type``; the file
    names them ``id`` and ``type``.
    """
    document = workflow.model_dump(
        mode="json", include=_WORKFLOW_DOCUMENT_FIELDS, exclude_none=True
    )
    document["steps"] = [
        {
            "id": step.step_id,
            "type": step.step_type,
            **step.model_dump(
                mode="json", include={"label", "config", "position"}, exclude_none=True
            ),
        }
        for step in workflow.steps
    ]
    return document


def _api_step(step: Any) -> dict[str, Any]:
    """A file's step in the API form.

    Reads the core ``id`` and ``type``, or the ``step_id`` and ``step_type``
    that the API wrote to workflow files before they used the core format.
    """
    if not isinstance(step, dict):
        raise ValueError("each workflow step must be a mapping")
    fields = {k: v for k, v in step.items() if k in {"label", "config", "position"}}
    return {
        "step_id": step.get("id", step.get("step_id")),
        "step_type": step.get("type", step.get("step_type")),
        **fields,
    }


def index_workflow(
    conn: Any, *, workspace_id: str, slug: str, document: dict[str, Any], file_path: str
) -> None:
    """Rewrite the index row for a workflow file from the file's contents."""
    steps = document.get("steps") or []
    if not isinstance(steps, list):
        raise ValueError("steps must be a list")
    body = WorkflowCreate(
        **{
            **document,
            "steps": [_api_step(step) for step in steps],
            "workspace_id": workspace_id,
        }
    )
    slug = body.workflow_slug or slug
    params = {
        "slug": slug,
        "name": body.name,
        "steps": json.dumps([s.model_dump(mode="json") for s in body.steps]),
        "desc": body.description,
        "is_template": 1 if body.is_template else 0,
        "template_source": body.template_source,
        "fp": file_path,
        "wid": workspace_id,
        "now": datetime.now(UTC).isoformat(),
    }
    existing = conn.execute(
        text(
            "SELECT id FROM workflow_definitions "
            "WHERE workspace_id = :wid AND workflow_slug = :slug"
        ),
        {"wid": workspace_id, "slug": slug},
    ).first()
    if existing is None:
        conn.execute(_WORKFLOW_INSERT_SQL, {**params, "id": str(uuid.uuid4())})
        return
    conn.execute(
        text(
            "UPDATE workflow_definitions SET name = :name, steps = :steps, "
            "description = :desc, is_template = :is_template, "
            "template_source = :template_source, file_path = :fp, "
            "updated_at = :now WHERE id = :id"
        ),
        {**params, "id": str(existing[0])},
    )


_WORKFLOW_INSERT_SQL = text(
    "INSERT INTO workflow_definitions "
    "(id, workflow_slug, version, name, steps, description, "
    "is_template, template_source, file_path, is_active, "
    "workspace_id, created_at, updated_at) "
    "VALUES (:id, :slug, 1, :name, :steps, :desc, "
    ":is_template, :template_source, :fp, 1, :wid, :now, :now)"
)


@router.post("", response_model=WorkflowDetail, status_code=201)
async def create_workflow(
    request: Request,
    body: WorkflowCreate,
    _reviewer: CurrentReviewer,
) -> WorkflowDetail:
    """Create a new workflow definition (API-021) and write its file."""
    engine = get_engine(request)
    folder = workspace_folder(engine, body.workspace_id)
    workflow_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    slug = body.workflow_slug or body.name.lower().replace(" ", "-")
    with workspace_files(folder) as files, engine.connect() as conn:
        file_path = files.write_config(
            WORKFLOW,
            slug=slug,
            document=_workflow_document(
                body.model_copy(update={"workflow_slug": slug})
            ),
            file_path=body.file_path,
            overwrite=False,
        )
        conn.execute(
            _WORKFLOW_INSERT_SQL,
            {
                "id": workflow_id,
                "slug": slug,
                "name": body.name,
                "steps": json.dumps([s.model_dump(mode="json") for s in body.steps]),
                "desc": body.description,
                "is_template": 1 if body.is_template else 0,
                "template_source": body.template_source,
                "fp": file_path,
                "wid": body.workspace_id,
                "now": now,
            },
        )
        conn.commit()

    with engine.connect() as conn:
        row = conn.execute(_WORKFLOW_DETAIL_SQL, {"id": workflow_id}).first()

    return _row_to_detail(row)


@router.put("/{workflow_id}", response_model=WorkflowDetail)
async def update_workflow(
    request: Request,
    workflow_id: uuid.UUID,
    body: WorkflowUpdate,
    _reviewer: CurrentReviewer,
) -> WorkflowDetail:
    """Update a workflow definition (API-022) and rewrite its file."""
    engine = get_engine(request)
    now = datetime.now(UTC).isoformat()

    with engine.connect() as conn:
        existing = conn.execute(
            text("SELECT id, workspace_id FROM workflow_definitions WHERE id = :id"),
            {"id": str(workflow_id)},
        ).first()
        if existing is None:
            raise HTTPException(status_code=404, detail="Workflow not found")
    folder = workspace_folder(engine, str(existing[1]))

    with workspace_files(folder) as files, engine.connect() as conn:
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
        detail = _row_to_detail(
            conn.execute(_WORKFLOW_DETAIL_SQL, {"id": str(workflow_id)}).first()
        )
        file_path = files.write_config(
            WORKFLOW,
            slug=detail.workflow_slug,
            document=_workflow_document(detail),
            file_path=detail.file_path,
            overwrite=True,
        )
        if file_path != detail.file_path:
            conn.execute(
                text("UPDATE workflow_definitions SET file_path = :fp WHERE id = :id"),
                {"fp": file_path, "id": str(workflow_id)},
            )
            detail = detail.model_copy(update={"file_path": file_path})
        conn.commit()

    return detail


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
    return _execution_row_to_model(exec_row)


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

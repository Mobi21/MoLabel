"""Workflow endpoints — /api/v1/workflows.

CRUD for workflow definitions plus execution management
(API-019 through API-028).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text

from molabel.app.middleware.session import CurrentReviewer
from molabel.app.schemas import PaginatedResponse, QueryParams
from molabel.app.utils import get_engine

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
            datetime.fromisoformat(str(row[9]))
            if row[9]
            else datetime.now(UTC)
        ),
        updated_at=(
            datetime.fromisoformat(str(row[10]))
            if row[10]
            else datetime.now(UTC)
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
            datetime.fromisoformat(str(row[11]))
            if row[11]
            else datetime.now(UTC)
        ),
        updated_at=(
            datetime.fromisoformat(str(row[12]))
            if row[12]
            else datetime.now(UTC)
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
        started_at=(
            datetime.fromisoformat(str(row[7])) if row[7] else None
        ),
        paused_at=(
            datetime.fromisoformat(str(row[8])) if row[8] else None
        ),
        completed_at=(
            datetime.fromisoformat(str(row[9])) if row[9] else None
        ),
        created_at=(
            datetime.fromisoformat(str(row[10]))
            if row[10]
            else datetime.now(UTC)
        ),
        updated_at=(
            datetime.fromisoformat(str(row[11]))
            if row[11]
            else datetime.now(UTC)
        ),
    )


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

    steps_json = json.dumps(
        [s.model_dump(mode="json") for s in body.steps]
    )

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
    """Execute a workflow (API-023).

    Creates a new execution and returns 202.
    """
    import json

    engine = get_engine(request)
    now = datetime.now(UTC).isoformat()

    with engine.connect() as conn:
        wf_row = conn.execute(
            text(
                "SELECT id, version, workspace_id "
                "FROM workflow_definitions WHERE id = :id"
            ),
            {"id": str(workflow_id)},
        ).first()
        if wf_row is None:
            raise HTTPException(status_code=404, detail="Workflow not found")

        exec_id = str(uuid.uuid4())
        ctx = json.dumps(body.context) if body and body.context else None

        conn.execute(
            text(
                "INSERT INTO workflow_executions "
                "(id, workflow_definition_id, workflow_version, status, "
                "context, workspace_id, started_at, created_at, updated_at) "
                "VALUES (:id, :wfid, :ver, 'pending', :ctx, :wid, :now, :now, :now)"
            ),
            {
                "id": exec_id,
                "wfid": str(workflow_id),
                "ver": int(wf_row[1]),
                "ctx": ctx,
                "wid": str(wf_row[2]),
                "now": now,
            },
        )
        conn.commit()

    return WorkflowExecution(
        execution_id=exec_id,
        workflow_definition_id=str(workflow_id),
        workflow_version=int(wf_row[1]),
        status="pending",
        current_step_id=None,
        step_execution_count=0,
        error_summary=None,
        started_at=datetime.fromisoformat(now),
        paused_at=None,
        completed_at=None,
        created_at=datetime.fromisoformat(now),
        updated_at=datetime.fromisoformat(now),
    )


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
            started_at=(
                datetime.fromisoformat(str(sr[7])) if sr[7] else None
            ),
            completed_at=(
                datetime.fromisoformat(str(sr[8])) if sr[8] else None
            ),
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
        started_at=(
            datetime.fromisoformat(str(row[8])) if row[8] else None
        ),
        paused_at=(
            datetime.fromisoformat(str(row[9])) if row[9] else None
        ),
        completed_at=(
            datetime.fromisoformat(str(row[10])) if row[10] else None
        ),
        created_at=(
            datetime.fromisoformat(str(row[11]))
            if row[11]
            else datetime.now(UTC)
        ),
        updated_at=(
            datetime.fromisoformat(str(row[12]))
            if row[12]
            else datetime.now(UTC)
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
    now = datetime.now(UTC).isoformat()

    with engine.connect() as conn:
        exec_row = conn.execute(
            text(
                "SELECT id FROM workflow_executions "
                "WHERE id = :eid AND workflow_definition_id = :wfid"
            ),
            {"eid": str(execution_id), "wfid": str(workflow_id)},
        ).first()
        if exec_row is None:
            raise HTTPException(status_code=404, detail="Execution not found")

        conn.execute(
            text(
                "UPDATE workflow_executions "
                "SET current_step_id = :sid, updated_at = :now "
                "WHERE id = :eid"
            ),
            {"sid": step_id, "now": now, "eid": str(execution_id)},
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

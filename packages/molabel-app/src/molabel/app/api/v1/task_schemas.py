"""Task schema endpoints — /api/v1/task-schemas.

CRUD for task schema definitions (API-029 through API-032).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text

from molabel.app.middleware.session import CurrentReviewer
from molabel.app.schemas import PaginatedResponse, QueryParams
from molabel.app.utils import get_engine

router = APIRouter(prefix="/task-schemas", tags=["task-schemas"])

# ---------------------------------------------------------------------------
# Response / request models
# ---------------------------------------------------------------------------


class RecordSelector(BaseModel):
    """Criteria for selecting which records a task schema applies to."""

    dataset_ids: list[str] | None = None
    record_kind: str | None = None
    filter_expression: str | None = None


class LabelFieldDef(BaseModel):
    """Definition of a single label field."""

    name: str
    field_type: str
    """ordinal | categorical | text | numeric | bool | multi_select | json."""
    required: bool = True
    options: list[str] | None = None
    option_descriptions: dict[str, str] | None = None
    scale_min: float | None = None
    scale_max: float | None = None
    description: str = ""
    default: Any = None


class OptionalFieldDef(BaseModel):
    """Definition of an optional metadata field."""

    name: str
    field_type: str
    description: str = ""
    default: Any = None


class OverlapPolicy(BaseModel):
    """Policy for overlap (multi-annotation) assignments."""

    overlap_count: int = 1
    overlap_strategy: str = "random"  # random | round_robin | stratified
    calibration_fraction: float = 0.0


class AdjudicationPolicy(BaseModel):
    """Policy for resolving disagreements."""

    strategy: str = "majority_vote"
    min_agreement: float = 0.5
    auto_resolve: bool = False
    escalation_threshold: float | None = None


class ExportMapping(BaseModel):
    """Mapping for exporting labeled data."""

    format: str = "jsonl"
    field_mapping: dict[str, str] = {}
    include_metadata: bool = False


class TaskSchemaSummary(BaseModel):
    """Task schema list item."""

    task_schema_id: str
    task_schema_slug: str
    version: int
    task_type: str
    title: str
    instructions: str | None = None
    label_field_count: int = 0
    blind_review_policy: str
    is_active: bool = True
    is_frozen: bool = False
    workspace_id: str
    created_at: datetime
    updated_at: datetime


class TaskSchemaDetail(BaseModel):
    """Full task schema detail."""

    task_schema_id: str
    task_schema_slug: str
    version: int
    task_type: str
    title: str
    instructions: str | None = None
    record_selector: RecordSelector | None = None
    label_fields: list[LabelFieldDef] = []
    required_fields: list[str] = []
    optional_fields: list[OptionalFieldDef] = []
    blind_review_policy: str
    overlap_policy: OverlapPolicy | None = None
    adjudication_policy: AdjudicationPolicy | None = None
    supported_agent_roles: list[str] = []
    default_model_profile_id: str | None = None
    export_mapping: ExportMapping | None = None
    is_active: bool = True
    is_frozen: bool = False
    file_path: str | None = None
    workspace_id: str
    created_at: datetime
    updated_at: datetime


class TaskSchemaCreate(BaseModel):
    """Request body for creating a task schema."""

    workspace_id: str
    task_schema_slug: str | None = None
    task_type: str
    title: str
    instructions: str | None = None
    record_selector: RecordSelector | None = None
    label_fields: list[LabelFieldDef] = []
    required_fields: list[str] = []
    optional_fields: list[OptionalFieldDef] = []
    blind_review_policy: str = "hide_agent_outputs_by_default"
    overlap_policy: OverlapPolicy | None = None
    adjudication_policy: AdjudicationPolicy | None = None
    supported_agent_roles: list[str] = []
    default_model_profile_id: str | None = None
    export_mapping: ExportMapping | None = None
    file_path: str | None = None


class TaskSchemaUpdate(BaseModel):
    """Request body for updating a task schema."""

    title: str | None = None
    instructions: str | None = None
    record_selector: RecordSelector | None = None
    label_fields: list[LabelFieldDef] | None = None
    required_fields: list[str] | None = None
    optional_fields: list[OptionalFieldDef] | None = None
    blind_review_policy: str | None = None
    overlap_policy: OverlapPolicy | None = None
    adjudication_policy: AdjudicationPolicy | None = None
    supported_agent_roles: list[str] | None = None
    default_model_profile_id: str | None = None
    export_mapping: ExportMapping | None = None
    is_active: bool | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_json_field(val: Any) -> Any:
    """Parse a JSON field from a database row."""
    if val is None:
        return None
    if isinstance(val, (dict, list)):
        return val
    try:
        return json.loads(str(val))
    except (json.JSONDecodeError, TypeError):
        return None


def _row_to_summary(row: Any) -> TaskSchemaSummary:
    """Convert a database row to a TaskSchemaSummary."""
    label_fields_raw = _parse_json_field(row[6])
    label_field_count = (
        len(label_fields_raw) if isinstance(label_fields_raw, (list, dict)) else 0
    )

    return TaskSchemaSummary(
        task_schema_id=str(row[0]),
        task_schema_slug=str(row[1]),
        version=int(row[2]),
        task_type=str(row[3]),
        title=str(row[4]),
        instructions=str(row[5]) if row[5] else None,
        label_field_count=label_field_count,
        blind_review_policy=str(row[7]),
        is_active=bool(row[8]) if row[8] is not None else True,
        is_frozen=bool(row[9]) if row[9] is not None else False,
        workspace_id=str(row[10]),
        created_at=(
            datetime.fromisoformat(str(row[11])) if row[11] else datetime.now(UTC)
        ),
        updated_at=(
            datetime.fromisoformat(str(row[12])) if row[12] else datetime.now(UTC)
        ),
    )


def _row_to_detail(row: Any) -> TaskSchemaDetail:
    """Convert a database row to a TaskSchemaDetail."""
    label_fields_raw = _parse_json_field(row[7])
    label_fields: list[LabelFieldDef] = []
    if isinstance(label_fields_raw, list):
        label_fields = [
            LabelFieldDef(**f)
            if isinstance(f, dict)
            else LabelFieldDef(name=str(f), field_type="text")
            for f in label_fields_raw
        ]
    elif isinstance(label_fields_raw, dict):
        label_fields = [
            LabelFieldDef(name=k, field_type=v if isinstance(v, str) else "text")
            for k, v in label_fields_raw.items()
        ]

    record_selector_raw = _parse_json_field(row[6])
    record_selector = (
        RecordSelector(**record_selector_raw)
        if isinstance(record_selector_raw, dict)
        else None
    )

    required_fields_raw = _parse_json_field(row[8])
    required_fields = (
        required_fields_raw if isinstance(required_fields_raw, list) else []
    )

    optional_fields_raw = _parse_json_field(row[9])
    optional_fields: list[OptionalFieldDef] = []
    if isinstance(optional_fields_raw, list):
        optional_fields = [
            OptionalFieldDef(**f)
            if isinstance(f, dict)
            else OptionalFieldDef(name=str(f), field_type="text")
            for f in optional_fields_raw
        ]

    overlap_policy_raw = _parse_json_field(row[11])
    overlap_policy = (
        OverlapPolicy(**overlap_policy_raw)
        if isinstance(overlap_policy_raw, dict)
        else None
    )

    adjudication_policy_raw = _parse_json_field(row[12])
    adjudication_policy = (
        AdjudicationPolicy(**adjudication_policy_raw)
        if isinstance(adjudication_policy_raw, dict)
        else None
    )

    supported_agent_roles_raw = _parse_json_field(row[13])
    supported_agent_roles = (
        supported_agent_roles_raw if isinstance(supported_agent_roles_raw, list) else []
    )

    export_mapping_raw = _parse_json_field(row[15])
    export_mapping = (
        ExportMapping(**export_mapping_raw)
        if isinstance(export_mapping_raw, dict)
        else None
    )

    return TaskSchemaDetail(
        task_schema_id=str(row[0]),
        task_schema_slug=str(row[1]),
        version=int(row[2]),
        task_type=str(row[3]),
        title=str(row[4]),
        instructions=str(row[5]) if row[5] else None,
        record_selector=record_selector,
        label_fields=label_fields,
        required_fields=required_fields,
        optional_fields=optional_fields,
        blind_review_policy=str(row[10]),
        overlap_policy=overlap_policy,
        adjudication_policy=adjudication_policy,
        supported_agent_roles=supported_agent_roles,
        default_model_profile_id=str(row[14]) if row[14] else None,
        export_mapping=export_mapping,
        is_active=bool(row[16]) if row[16] is not None else True,
        is_frozen=bool(row[17]) if row[17] is not None else False,
        file_path=str(row[18]) if row[18] else None,
        workspace_id=str(row[19]),
        created_at=(
            datetime.fromisoformat(str(row[20])) if row[20] else datetime.now(UTC)
        ),
        updated_at=(
            datetime.fromisoformat(str(row[21])) if row[21] else datetime.now(UTC)
        ),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


_DETAIL_COLUMNS = (
    "id, task_schema_slug, version, task_type, title, instructions, "
    "record_selector, label_fields, required_fields, optional_fields, "
    "blind_review_policy, overlap_policy, adjudication_policy, "
    "supported_agent_roles, default_model_profile_id, export_mapping, "
    "is_active, is_frozen, file_path, workspace_id, created_at, updated_at"
)

_SUMMARY_COLUMNS = (
    "id, task_schema_slug, version, task_type, title, instructions, "
    "label_fields, blind_review_policy, is_active, is_frozen, "
    "workspace_id, created_at, updated_at"
)


@router.get("", response_model=PaginatedResponse[TaskSchemaSummary])
async def list_task_schemas(
    request: Request,
    params: Annotated[QueryParams, Depends()],
) -> PaginatedResponse[TaskSchemaSummary]:
    """List task schemas (API-029)."""
    engine = get_engine(request)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"SELECT {_SUMMARY_COLUMNS} "  # noqa: S608
                "FROM task_schemas "
                "ORDER BY created_at DESC "
                "LIMIT :limit"
            ),
            {"limit": params.limit},
        ).fetchall()

    items = [_row_to_summary(r) for r in rows]
    return PaginatedResponse(items=items, cursor=None, has_more=False)


@router.get("/{task_schema_id}", response_model=TaskSchemaDetail)
async def get_task_schema(
    request: Request,
    task_schema_id: uuid.UUID,
) -> TaskSchemaDetail:
    """Get task schema detail (API-030)."""
    engine = get_engine(request)
    with engine.connect() as conn:
        row = conn.execute(
            text(
                f"SELECT {_DETAIL_COLUMNS} "  # noqa: S608
                "FROM task_schemas WHERE id = :id"
            ),
            {"id": str(task_schema_id)},
        ).first()

    if row is None:
        raise HTTPException(status_code=404, detail="Task schema not found")

    return _row_to_detail(row)


@router.post("", response_model=TaskSchemaDetail, status_code=201)
async def create_task_schema(
    request: Request,
    body: TaskSchemaCreate,
    _reviewer: CurrentReviewer,
) -> TaskSchemaDetail:
    """Create a new task schema (API-031)."""
    engine = get_engine(request)
    schema_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    slug = body.task_schema_slug or body.title.lower().replace(" ", "-")

    label_fields_json = json.dumps(
        [f.model_dump(mode="json") for f in body.label_fields]
    )
    required_fields_json = json.dumps(body.required_fields)
    optional_fields_json = json.dumps(
        [f.model_dump(mode="json") for f in body.optional_fields]
    )
    record_selector_json = (
        json.dumps(body.record_selector.model_dump(mode="json"))
        if body.record_selector
        else None
    )
    overlap_json = (
        json.dumps(body.overlap_policy.model_dump(mode="json"))
        if body.overlap_policy
        else None
    )
    adjudication_json = (
        json.dumps(body.adjudication_policy.model_dump(mode="json"))
        if body.adjudication_policy
        else None
    )
    agent_roles_json = json.dumps(body.supported_agent_roles)
    export_json = (
        json.dumps(body.export_mapping.model_dump(mode="json"))
        if body.export_mapping
        else None
    )

    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO task_schemas "
                "(id, task_schema_slug, version, task_type, title, instructions, "
                "record_selector, label_fields, required_fields, optional_fields, "
                "blind_review_policy, overlap_policy, adjudication_policy, "
                "supported_agent_roles, default_model_profile_id, export_mapping, "
                "is_active, is_frozen, file_path, "
                "workspace_id, created_at, updated_at) "
                "VALUES (:id, :slug, 1, :task_type, :title, :instructions, "
                ":record_selector, :label_fields, :required_fields, :optional_fields, "
                ":blind_review_policy, :overlap_policy, :adjudication_policy, "
                ":agent_roles, :model_profile_id, :export_mapping, "
                "1, 0, :file_path, :wid, :now, :now)"
            ),
            {
                "id": schema_id,
                "slug": slug,
                "task_type": body.task_type,
                "title": body.title,
                "instructions": body.instructions,
                "record_selector": record_selector_json,
                "label_fields": label_fields_json,
                "required_fields": required_fields_json,
                "optional_fields": optional_fields_json,
                "blind_review_policy": body.blind_review_policy,
                "overlap_policy": overlap_json,
                "adjudication_policy": adjudication_json,
                "agent_roles": agent_roles_json,
                "model_profile_id": body.default_model_profile_id,
                "export_mapping": export_json,
                "file_path": body.file_path,
                "wid": body.workspace_id,
                "now": now,
            },
        )
        conn.commit()

        row = conn.execute(
            text(
                f"SELECT {_DETAIL_COLUMNS} "  # noqa: S608
                "FROM task_schemas WHERE id = :id"
            ),
            {"id": schema_id},
        ).first()

    return _row_to_detail(row)


@router.put("/{task_schema_id}", response_model=TaskSchemaDetail)
async def update_task_schema(
    request: Request,
    task_schema_id: uuid.UUID,
    body: TaskSchemaUpdate,
    _reviewer: CurrentReviewer,
) -> TaskSchemaDetail:
    """Update a task schema (API-032)."""
    engine = get_engine(request)
    now = datetime.now(UTC).isoformat()

    with engine.connect() as conn:
        existing = conn.execute(
            text("SELECT id, is_frozen FROM task_schemas WHERE id = :id"),
            {"id": str(task_schema_id)},
        ).first()
        if existing is None:
            raise HTTPException(status_code=404, detail="Task schema not found")
        if existing[1] and bool(existing[1]):
            raise HTTPException(
                status_code=409,
                detail="Task schema is frozen and cannot be updated",
            )

        updates: list[str] = ["updated_at = :now"]
        params: dict[str, Any] = {"id": str(task_schema_id), "now": now}

        if body.title is not None:
            updates.append("title = :title")
            params["title"] = body.title
        if body.instructions is not None:
            updates.append("instructions = :instructions")
            params["instructions"] = body.instructions
        if body.record_selector is not None:
            updates.append("record_selector = :record_selector")
            params["record_selector"] = json.dumps(
                body.record_selector.model_dump(mode="json")
            )
        if body.label_fields is not None:
            updates.append("label_fields = :label_fields")
            params["label_fields"] = json.dumps(
                [f.model_dump(mode="json") for f in body.label_fields]
            )
        if body.required_fields is not None:
            updates.append("required_fields = :required_fields")
            params["required_fields"] = json.dumps(body.required_fields)
        if body.optional_fields is not None:
            updates.append("optional_fields = :optional_fields")
            params["optional_fields"] = json.dumps(
                [f.model_dump(mode="json") for f in body.optional_fields]
            )
        if body.blind_review_policy is not None:
            updates.append("blind_review_policy = :brp")
            params["brp"] = body.blind_review_policy
        if body.overlap_policy is not None:
            updates.append("overlap_policy = :overlap")
            params["overlap"] = json.dumps(body.overlap_policy.model_dump(mode="json"))
        if body.adjudication_policy is not None:
            updates.append("adjudication_policy = :adj")
            params["adj"] = json.dumps(body.adjudication_policy.model_dump(mode="json"))
        if body.supported_agent_roles is not None:
            updates.append("supported_agent_roles = :agent_roles")
            params["agent_roles"] = json.dumps(body.supported_agent_roles)
        if body.default_model_profile_id is not None:
            updates.append("default_model_profile_id = :model_profile")
            params["model_profile"] = body.default_model_profile_id
        if body.export_mapping is not None:
            updates.append("export_mapping = :export_mapping")
            params["export_mapping"] = json.dumps(
                body.export_mapping.model_dump(mode="json")
            )
        if body.is_active is not None:
            updates.append("is_active = :is_active")
            params["is_active"] = 1 if body.is_active else 0

        set_clause = ", ".join(updates)
        conn.execute(
            text(
                f"UPDATE task_schemas SET {set_clause} WHERE id = :id"  # noqa: S608
            ),
            params,
        )
        conn.commit()

        row = conn.execute(
            text(
                f"SELECT {_DETAIL_COLUMNS} "  # noqa: S608
                "FROM task_schemas WHERE id = :id"
            ),
            {"id": str(task_schema_id)},
        ).first()

    return _row_to_detail(row)

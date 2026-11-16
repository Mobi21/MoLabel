"""Prompt template endpoints — /api/v1/prompts.

CRUD and versioning for prompt templates (API-053 through API-057).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import text

from molabel.app.middleware.session import CurrentReviewer
from molabel.app.schemas import PaginatedResponse, QueryParams
from molabel.app.utils import get_engine
from molabel.app.workspace_config import PROMPT, workspace_folder, write_config

router = APIRouter(prefix="/prompts", tags=["prompts"])


# ---------------------------------------------------------------------------
# Pydantic response / request models
# ---------------------------------------------------------------------------


class FewShotExample(BaseModel):
    """A single few-shot example attached to a prompt version."""

    record_id: str | None = None
    input_text: str
    expected_output: dict[str, Any]
    source: str


class PromptSummary(BaseModel):
    """Summary model for prompt list responses."""

    prompt_id: str
    workspace_id: str
    name: str
    agent_role: str
    task_schema_id: str
    current_version: str
    version_count: int
    last_used_at: datetime | None = None
    file_path: str
    created_at: datetime
    updated_at: datetime


class PromptVersion(BaseModel):
    """A single version of a prompt template."""

    version: str
    system_instructions: str
    task_rubric: str | None = None
    few_shot_examples: list[FewShotExample]
    correction_batch_id: str | None = None
    content_hash: str
    is_locked: bool
    agent_run_ids: list[str]
    created_at: datetime


class PromptDetail(BaseModel):
    """Detailed model for a single prompt template with all versions."""

    prompt_id: str
    workspace_id: str
    name: str
    agent_role: str
    task_schema_id: str
    current_version: str
    versions: list[PromptVersion]
    file_path: str
    created_at: datetime
    updated_at: datetime


class PromptCreate(BaseModel):
    """Request body for creating a new prompt template."""

    workspace_id: str
    name: str
    agent_role: str
    task_schema_id: str
    system_instructions: str
    task_rubric: str | None = None
    few_shot_examples: list[FewShotExample] = []


class PromptUpdate(BaseModel):
    """Request body for creating a new version of a prompt template."""

    system_instructions: str | None = None
    task_rubric: str | None = None
    few_shot_examples: list[FewShotExample] | None = None


class PromptDiff(BaseModel):
    """Diff between two prompt versions."""

    prompt_id: str
    version_1: str
    version_2: str
    system_instructions_diff: str | None = None
    task_rubric_diff: str | None = None
    few_shot_added: list[FewShotExample]
    few_shot_removed: list[FewShotExample]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedResponse[PromptSummary])
async def list_prompts(
    params: Annotated[QueryParams, Depends()],
    workspace_id: str = Query(..., description="Workspace ID (required)"),
    agent_role: str | None = Query(None),
    task_schema_id: str | None = Query(None),
) -> PaginatedResponse[PromptSummary]:
    """List prompt templates with filtering (API-053)."""
    return PaginatedResponse(items=[], cursor=None, has_more=False)


@router.get("/{prompt_id}", response_model=PromptDetail)
async def get_prompt(
    prompt_id: str,
) -> PromptDetail:
    """Get prompt template detail with all versions (API-054)."""
    raise HTTPException(status_code=404, detail="Prompt not found")


_PROMPT_INSERT_SQL = text(
    """
    INSERT INTO prompt_templates (
        id, prompt_slug, version, name, description,
        system_instructions, task_rubric, few_shot_examples,
        instruction_patches, output_schema,
        parent_version_id, refinement_source_batch_id,
        is_frozen, file_path, created_at, workspace_id
    ) VALUES (
        :id, :prompt_slug, :version, :name, :description,
        :system_instructions, :task_rubric,
        :few_shot_examples, NULL, NULL,
        NULL, NULL, 0, :file_path, :created_at,
        :workspace_id
    )
    """
)


def _prompt_slug(name: str) -> str:
    return name.lower().replace(" ", "-")[:64]


def _prompt_params(body: PromptCreate, *, slug: str, file_path: str) -> dict[str, Any]:
    return {
        "prompt_slug": slug,
        "version": "v1",
        "name": body.name,
        "description": None,
        "system_instructions": body.system_instructions,
        "task_rubric": body.task_rubric,
        "few_shot_examples": json.dumps(
            [ex.model_dump() for ex in body.few_shot_examples]
        )
        if body.few_shot_examples
        else None,
        "file_path": file_path,
        "workspace_id": body.workspace_id,
    }


def index_prompt(
    conn: Any, *, workspace_id: str, slug: str, document: dict[str, Any], file_path: str
) -> None:
    """Rewrite the index row for a prompt file from the file's contents."""
    body = PromptCreate(**{**document, "workspace_id": workspace_id})
    params = _prompt_params(body, slug=slug, file_path=file_path)
    existing = conn.execute(
        text(
            "SELECT id FROM prompt_templates "
            "WHERE workspace_id = :workspace_id AND prompt_slug = :prompt_slug"
        ),
        params,
    ).first()
    if existing is None:
        conn.execute(
            _PROMPT_INSERT_SQL,
            {
                **params,
                "id": str(uuid.uuid4()),
                "created_at": datetime.now(UTC).isoformat(),
            },
        )
        return
    conn.execute(
        text(
            "UPDATE prompt_templates SET name = :name, "
            "system_instructions = :system_instructions, task_rubric = :task_rubric, "
            "few_shot_examples = :few_shot_examples, file_path = :file_path "
            "WHERE id = :id"
        ),
        {**params, "id": str(existing[0])},
    )


@router.post("", response_model=PromptDetail, status_code=201)
async def create_prompt(
    request: Request,
    body: PromptCreate,
    reviewer: CurrentReviewer,
) -> PromptDetail:
    """Create a new prompt template (API-055) and write its file."""
    engine = get_engine(request)
    folder = workspace_folder(engine, body.workspace_id)
    now = datetime.now(UTC)
    prompt_id = str(uuid.uuid4())
    prompt_slug = _prompt_slug(body.name)
    content_hash = hashlib.sha256(
        (body.system_instructions + (body.task_rubric or "")).encode("utf-8")
    ).hexdigest()[:12]
    file_path = write_config(
        folder,
        PROMPT,
        slug=prompt_slug,
        document=body.model_dump(
            mode="json", exclude={"workspace_id"}, exclude_none=True
        ),
        file_path=None,
        overwrite=False,
    )

    with engine.connect() as conn:
        conn.execute(
            _PROMPT_INSERT_SQL,
            {
                **_prompt_params(body, slug=prompt_slug, file_path=file_path),
                "id": prompt_id,
                "created_at": now.isoformat(),
            },
        )
        conn.commit()

    initial_version = PromptVersion(
        version="v1",
        system_instructions=body.system_instructions,
        task_rubric=body.task_rubric,
        few_shot_examples=body.few_shot_examples,
        correction_batch_id=None,
        content_hash=content_hash,
        is_locked=False,
        agent_run_ids=[],
        created_at=now,
    )
    return PromptDetail(
        prompt_id=prompt_id,
        workspace_id=body.workspace_id,
        name=body.name,
        agent_role=body.agent_role,
        task_schema_id=body.task_schema_id,
        current_version="v1",
        versions=[initial_version],
        file_path=file_path,
        created_at=now,
        updated_at=now,
    )


@router.put("/{prompt_id}", response_model=PromptDetail)
async def update_prompt(
    prompt_id: str,
    body: PromptUpdate,
    reviewer: CurrentReviewer,
) -> PromptDetail:
    """Create a new version of a prompt template (API-056)."""
    raise HTTPException(status_code=404, detail="Prompt not found")


@router.get("/{prompt_id}/diff", response_model=PromptDiff)
async def get_prompt_diff(
    prompt_id: str,
    v1: str = Query(..., description="First version to compare"),
    v2: str = Query(..., description="Second version to compare"),
) -> PromptDiff:
    """Get diff between two prompt versions (API-057)."""
    raise HTTPException(status_code=404, detail="Prompt not found")

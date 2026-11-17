"""Gold sets -- /api/v1/gold-sets.

A gold set is ``gold/<slug>/gold.yaml`` and ``gold.jsonl`` in the session's
workspace, listed in the manifest (``docs/architecture/gold-sets.md``). Every
endpoint reads only the session's workspace: a set, queue or workflow
execution of another workspace answers 404. The CLI's ``molabel gold``
commands and the GUI use these endpoints.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, Field, model_validator

from molabel.app.errors import ApiError
from molabel.app.middleware.session import CurrentReviewer
from molabel.app.services.gold_sets import (
    GOLD_SLUG_PATTERN,
    StoredGoldSet,
    create_gold_set,
    dedupe_gold_set,
    execution_queue_ids,
    export_gold_set,
    list_gold_sets,
    promote_to_gold,
    read_gold_set,
)
from molabel.app.utils import get_engine
from molabel.app.workspace_config import workspace_folder
from molabel.core.gold.model import (
    GoldConflict,
    GoldItem,
    GoldItemRef,
    GoldSetHeader,
    GoldSetSource,
    dedupe,
    file_hash,
    render_items,
)
from molabel.core.gold.promotion import Skipped

router = APIRouter(prefix="/gold-sets", tags=["gold-sets"])

RECENT_ADDITIONS = 10
CONTENT_HASH_MATCHES = (
    "False when gold.jsonl is not the file the header describes: it was edited "
    "outside MoLabel, or a write stopped between gold.jsonl and gold.yaml. The "
    "header's version, item_count and content_hash then describe the previous file"
)


class GoldSetSummary(BaseModel):
    """A gold set's header, and where it lives in the workspace."""

    gold_set_id: str
    name: str
    task_schema: str
    version: int
    item_count: int
    content_hash: str
    previous_hash: str | None = None
    updated_at: str
    path: str = Field(description="The header file, relative to the workspace")
    content_hash_matches: bool = Field(description=CONTENT_HASH_MATCHES)


def _summary(path: str, header: GoldSetHeader, items_hash: str) -> GoldSetSummary:
    return GoldSetSummary(
        **header.model_dump(include=set(GoldSetSummary.model_fields)),
        path=path,
        content_hash_matches=header.content_hash == items_hash,
    )


class GoldSetList(BaseModel):
    items: list[GoldSetSummary]


class GoldSetDetail(GoldSetSummary):
    """A gold set with its sources, latest items, and the repeats it holds."""

    sources: list[GoldSetSource]
    recent_additions: list[GoldItem] = Field(description="Newest first")
    duplicates: list[GoldItemRef] = Field(
        description="Exact repeats, which gold dedupe removes"
    )
    conflicts: list[GoldConflict] = Field(
        description="Items with one input and different labels, left for a person"
    )


def _detail(stored: StoredGoldSet) -> GoldSetDetail:
    gold = stored.gold
    found = dedupe(gold.items)
    return GoldSetDetail(
        **_summary(stored.definition_path, gold.header, gold.file_hash).model_dump(),
        sources=gold.header.sources,
        recent_additions=list(reversed(gold.items[-RECENT_ADDITIONS:])),
        duplicates=list(found.removed),
        conflicts=list(found.conflicts),
    )


class GoldSetCreate(BaseModel):
    gold_set_id: str = Field(pattern=GOLD_SLUG_PATTERN, description="The set's slug")
    name: str | None = None
    task_schema_id: str = Field(description="The task schema's id or slug")


class GoldPromoteRequest(BaseModel):
    """The reviewed records to promote: a queue's, or a workflow execution's."""

    queue_id: str | None = None
    workflow_execution_id: str | None = Field(
        default=None, description="Every review queue the execution made"
    )
    record_ids: list[str] | None = Field(
        default=None, description="Only these records of queue_id"
    )
    allow_single_reviewer: bool = Field(
        default=False,
        description="Also promote a record one reviewer labelled, marked as such",
    )

    @model_validator(mode="after")
    def _one_source(self) -> GoldPromoteRequest:
        if (self.queue_id is None) == (self.workflow_execution_id is None):
            raise ValueError("pass queue_id or workflow_execution_id")
        if self.record_ids is not None and self.queue_id is None:
            raise ValueError("record_ids needs queue_id")
        return self


class GoldWriteCounts(BaseModel):
    added: int
    duplicates: int
    conflicts: int
    skipped: int


class GoldWriteReport(BaseModel):
    """What a promotion or append added, and what it left out and why."""

    gold_set: GoldSetSummary
    written: bool = Field(description="False when the files did not change")
    counts: GoldWriteCounts
    added: list[GoldItem]
    duplicates: list[GoldItemRef]
    conflicts: list[GoldConflict]
    skipped: list[Skipped]


class GoldDedupeReport(BaseModel):
    gold_set: GoldSetSummary
    written: bool
    removed: list[GoldItemRef]
    conflicts: list[GoldConflict]


class GoldExportRequest(BaseModel):
    format: Literal["jsonl"] = "jsonl"
    path: str = Field(description="Where to write, relative to the workspace")
    overwrite: bool = False


class GoldExport(BaseModel):
    """The set's items as JSONL, inline or written to a workspace path."""

    gold_set_id: str
    version: int
    format: Literal["jsonl"]
    item_count: int
    content_hash: str
    content_hash_matches: bool = Field(description=CONTENT_HASH_MATCHES)
    path: str | None = None
    content: str | None = None


def _folder(request: Request, reviewer: CurrentReviewer):
    return workspace_folder(get_engine(request), str(reviewer.workspace_id))


@router.get("", response_model=GoldSetList)
async def list_gold_sets_endpoint(
    request: Request, reviewer: CurrentReviewer
) -> GoldSetList:
    """List the gold sets of the session's workspace, in manifest order."""
    return GoldSetList(
        items=[
            _summary(path, header, items_hash)
            for path, header, items_hash in list_gold_sets(_folder(request, reviewer))
        ]
    )


@router.post("", response_model=GoldSetDetail, status_code=status.HTTP_201_CREATED)
async def create_gold_set_endpoint(
    request: Request, body: GoldSetCreate, reviewer: CurrentReviewer
) -> GoldSetDetail:
    """Write version 1 of an empty gold set and list it in the manifest."""
    path, gold = create_gold_set(
        get_engine(request),
        reviewer.workspace_id,
        slug=body.gold_set_id,
        name=body.name,
        task_schema=body.task_schema_id,
    )
    return _detail(StoredGoldSet(gold=gold, definition_path=path))


@router.get("/{gold_set_id}", response_model=GoldSetDetail)
async def get_gold_set(
    request: Request, gold_set_id: str, reviewer: CurrentReviewer
) -> GoldSetDetail:
    """Show a gold set: its header, newest items, duplicates and conflicts."""
    return _detail(read_gold_set(_folder(request, reviewer), gold_set_id))


def _write_report(request, gold_set_id, body, reviewer, *, failures_only):
    engine = get_engine(request)
    if body.queue_id is not None:
        queue_ids = [body.queue_id]
    else:
        with engine.connect() as conn:
            queue_ids = execution_queue_ids(
                conn, body.workflow_execution_id, reviewer.workspace_id
            )
        if not queue_ids:
            raise ApiError(
                409,
                "NO_REVIEW_QUEUES",
                "The workflow execution made no review queue",
                {"workflow_execution_id": body.workflow_execution_id},
            )
    write = promote_to_gold(
        engine,
        reviewer.workspace_id,
        gold_set_id,
        promoted_by=reviewer.id,
        queue_ids=queue_ids,
        record_ids=body.record_ids,
        allow_single_reviewer=body.allow_single_reviewer,
        failures_only=failures_only,
    )
    return GoldWriteReport(
        gold_set=_summary(
            write.definition_path, write.gold.header, write.gold.file_hash
        ),
        written=write.written,
        counts=GoldWriteCounts(
            added=len(write.added),
            duplicates=len(write.duplicates),
            conflicts=len(write.conflicts),
            skipped=len(write.skipped),
        ),
        added=list(write.added),
        duplicates=list(write.duplicates),
        conflicts=list(write.conflicts),
        skipped=list(write.skipped),
    )


@router.post("/{gold_set_id}/promote", response_model=GoldWriteReport)
async def promote_to_gold_set(
    request: Request,
    gold_set_id: str,
    body: GoldPromoteRequest,
    reviewer: CurrentReviewer,
) -> GoldWriteReport:
    """Promote reviewed records into the set.

    A record qualifies when an adjudication resolved it with labels or every
    counted reviewer gave identical labels, or, with allow_single_reviewer,
    one reviewer labelled it. Promoting a record again is a duplicate and
    changes nothing; other labels for the same input are a conflict, which
    is reported and never overwrites the item.
    """
    return _write_report(request, gold_set_id, body, reviewer, failures_only=False)


@router.post("/{gold_set_id}/append", response_model=GoldWriteReport)
async def append_failures_to_gold_set(
    request: Request,
    gold_set_id: str,
    body: GoldPromoteRequest,
    reviewer: CurrentReviewer,
) -> GoldWriteReport:
    """Append the reviewed records the model got wrong.

    These are the records that qualify for promotion and whose human label
    contradicts an agent proposal bound to their review tasks. Each item
    records that proposal. Append dedupes as promotion does.
    """
    return _write_report(request, gold_set_id, body, reviewer, failures_only=True)


@router.post("/{gold_set_id}/dedupe", response_model=GoldDedupeReport)
async def dedupe_gold_set_endpoint(
    request: Request, gold_set_id: str, reviewer: CurrentReviewer
) -> GoldDedupeReport:
    """Remove exact repeats, keeping the first, and report the conflicts left."""
    result = dedupe_gold_set(get_engine(request), reviewer.workspace_id, gold_set_id)
    return GoldDedupeReport(
        gold_set=_summary(
            result.definition_path, result.gold.header, result.gold.file_hash
        ),
        written=result.written,
        removed=list(result.removed),
        conflicts=list(result.conflicts),
    )


@router.get("/{gold_set_id}/export", response_model=GoldExport)
async def export_gold_set_content(
    request: Request,
    gold_set_id: str,
    reviewer: CurrentReviewer,
    format: Literal["jsonl"] = "jsonl",
) -> GoldExport:
    """The set's items as JSONL, one item per line as gold.jsonl holds them."""
    gold = read_gold_set(_folder(request, reviewer), gold_set_id).gold
    data = render_items(gold.items)
    return GoldExport(
        gold_set_id=gold_set_id,
        version=gold.header.version,
        format=format,
        item_count=len(gold.items),
        content_hash=file_hash(data),
        content_hash_matches=gold.content_hash_matches,
        content=data.decode("utf-8"),
    )


@router.post("/{gold_set_id}/export", response_model=GoldExport)
async def export_gold_set_to_path(
    request: Request,
    gold_set_id: str,
    body: GoldExportRequest,
    reviewer: CurrentReviewer,
) -> GoldExport:
    """Write the set's items as JSONL to a path inside the workspace."""
    stored, path, data = export_gold_set(
        get_engine(request),
        reviewer.workspace_id,
        gold_set_id,
        path=body.path,
        overwrite=body.overwrite,
    )
    return GoldExport(
        gold_set_id=gold_set_id,
        version=stored.gold.header.version,
        format=body.format,
        item_count=len(stored.gold.items),
        content_hash=file_hash(data),
        content_hash_matches=stored.gold.content_hash_matches,
        path=path,
    )

"""Gold sets in the workspace: their files, and promotion from review queues.

A set's files are the record of it; no database row indexes them. Every write
reads the set, changes it and writes it back inside ``workspace_files``, which
holds the workspace lock and restores both files if the write fails. Which
record gives which item is ``molabel.core.gold.promotion``'s call, on the
evidence ``reviewed_records`` reads from the review database.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import yaml
from pydantic import ValidationError
from sqlalchemy import bindparam, text

from molabel.app.api.v1.adjudication import (
    ReviewQueue,
    queue_disagreements,
    workspace_review_queue,
)
from molabel.app.errors import ApiError
from molabel.app.services.claims import scrub_review_value
from molabel.app.services.review_events import json_object, queue_review_events
from molabel.app.workspace_config import (
    MANIFEST_FILENAME,
    WorkspaceFiles,
    WorkspaceFolder,
    workspace_files,
    workspace_folder,
)
from molabel.app.workspace_paths import require_portable, resolve_in_workspace
from molabel.core.agents.queue_binding import deserialize_agent_output_ids
from molabel.core.database import hyphenated_id
from molabel.core.gold.calibration import CalibrationItems
from molabel.core.gold.model import (
    GOLD_DIRECTORY,
    HEADER_FILENAME,
    ITEMS_FILENAME,
    GoldConflict,
    GoldFileError,
    GoldInputRef,
    GoldItem,
    GoldItemRef,
    GoldSet,
    GoldSetHeader,
    GoldSetSource,
    StaleLine,
    dedupe,
    file_hash,
    merge,
    render_items,
)
from molabel.core.gold.promotion import (
    CountedReview,
    Proposal,
    Resolution,
    ReviewedRecord,
    Skipped,
    gold_candidate,
)
from molabel.core.manifest import GoldSetManifestEntry, load_manifest
from molabel.core.quality.review_agreement import counted_review_events, rated_labels

GOLD_SLUG_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,63}$"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _expanding(sql: str, name: str) -> Any:
    return text(sql).bindparams(bindparam(name, expanding=True))


def _entries(folder: WorkspaceFolder) -> list[GoldSetManifestEntry]:
    path = resolve_in_workspace(folder.path, MANIFEST_FILENAME)
    return load_manifest(path).gold_sets if path.is_file() else []


def _invalid(entry: GoldSetManifestEntry, message: str, **details: Any) -> ApiError:
    return ApiError(
        409,
        "GOLD_SET_INVALID",
        f"Gold set '{entry.gold_set_id}' cannot be read: {message}",
        {"gold_set_id": entry.gold_set_id, "path": entry.definition_path, **details},
    )


def _read_header(folder: WorkspaceFolder, entry: GoldSetManifestEntry) -> GoldSetHeader:
    path = resolve_in_workspace(folder.path, entry.definition_path)
    try:
        return GoldSetHeader.model_validate(
            yaml.safe_load(path.read_text(encoding="utf-8"))
        )
    except FileNotFoundError as exc:
        raise _invalid(entry, "its header file is missing") from exc
    except (yaml.YAMLError, ValidationError) as exc:
        raise _invalid(entry, f"its header does not parse: {exc}") from exc


def _items_data(folder: WorkspaceFolder, entry: GoldSetManifestEntry) -> bytes:
    header_path = resolve_in_workspace(folder.path, entry.definition_path)
    items_path = resolve_in_workspace(
        folder.path, f"{header_path.parent.as_posix()}/{ITEMS_FILENAME}"
    )
    return items_path.read_bytes() if items_path.is_file() else b""


def list_gold_sets(
    folder: WorkspaceFolder,
) -> list[tuple[str, GoldSetHeader, str]]:
    """Each listed set's header path, header and items file hash, in order."""
    return [
        (
            entry.definition_path,
            _read_header(folder, entry),
            file_hash(_items_data(folder, entry)),
        )
        for entry in _entries(folder)
    ]


@dataclass(frozen=True)
class StoredGoldSet:
    """A set as its files hold it, and where its header lives."""

    gold: GoldSet
    definition_path: str


def read_gold_set(folder: WorkspaceFolder, slug: str) -> StoredGoldSet:
    """The set *slug* that the workspace manifest lists, read from its files."""
    entry = next((e for e in _entries(folder) if e.gold_set_id == slug), None)
    if entry is None:
        raise ApiError(
            404,
            "GOLD_SET_NOT_FOUND",
            f"No gold set '{slug}' in this workspace",
            {"gold_set_id": slug},
        )
    header = _read_header(folder, entry)
    try:
        gold = GoldSet.read(header, _items_data(folder, entry))
    except GoldFileError as exc:
        raise _invalid(entry, f"{ITEMS_FILENAME} {exc}", line=exc.line) from exc
    return StoredGoldSet(gold=gold, definition_path=entry.definition_path)


def _write(files: WorkspaceFiles, stored: StoredGoldSet, gold: GoldSet) -> str:
    return files.write_gold_set(
        gold.header.gold_set_id,
        header=gold.header.model_dump(mode="json"),
        items=gold.data,
        definition_path=stored.definition_path,
    )


def _task_schema_slug(conn: Any, workspace_id: str, selector: str) -> str:
    row = conn.execute(
        text(
            "SELECT task_schema_slug FROM task_schemas WHERE workspace_id = :w "
            "AND (id = :id OR task_schema_slug = :selector) "
            "ORDER BY created_at DESC LIMIT 1"
        ),
        {"w": workspace_id, "id": hyphenated_id(selector), "selector": selector},
    ).first()
    if row is None:
        raise ApiError(
            404,
            "TASK_SCHEMA_NOT_FOUND",
            f"No task schema '{selector}' in this workspace",
            {"task_schema_id": selector},
        )
    return str(row[0])


def create_gold_set(
    engine: Any,
    workspace_id: uuid.UUID,
    *,
    slug: str,
    name: str | None,
    task_schema: str,
) -> tuple[str, GoldSet]:
    """Write version 1 of a new, empty set and list it in the manifest."""
    folder = workspace_folder(engine, str(workspace_id))
    with workspace_files(folder) as files:
        if any(entry.gold_set_id == slug for entry in _entries(folder)):
            raise ApiError(
                409,
                "GOLD_SET_EXISTS",
                f"Gold set '{slug}' already exists",
                {"gold_set_id": slug},
            )
        with engine.connect() as conn:
            schema_slug = _task_schema_slug(conn, str(workspace_id), task_schema)
        gold = GoldSet.new(
            slug=slug, name=name or slug, task_schema=schema_slug, now=_now()
        )
        set_folder = f"{GOLD_DIRECTORY}/{slug}"
        set_path = resolve_in_workspace(folder.path, set_folder)
        held = sorted(
            f"{set_folder}/{entry.name}"
            for entry in (set_path.iterdir() if set_path.is_dir() else ())
        )
        if held:
            raise ApiError(
                409,
                "GOLD_SET_FILES_EXIST",
                f"{set_folder}/ holds files the manifest does not list as a gold "
                "set. Pick another slug, move the folder away, or list its "
                f"{HEADER_FILENAME} under gold_sets in workbench.project.yaml.",
                {"gold_set_id": slug, "path": set_folder, "files": held},
            )
        path = files.write_gold_set(
            slug,
            header=gold.header.model_dump(mode="json"),
            items=gold.data,
            definition_path=None,
        )
    return path, gold


# ---------------------------------------------------------------------------
# Reading a review queue's records for promotion
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QueueSource:
    """A review queue, and the workflow execution that made it, if any."""

    queue_id: str
    workspace_id: str
    task_schema_id: str
    workflow_execution_id: str | None
    workflow: str | None
    calibration: bool

    def gold_source(self) -> GoldSetSource:
        return GoldSetSource(
            queue_id=self.queue_id,
            workflow_execution_id=self.workflow_execution_id,
            workflow=self.workflow,
        )


def queue_source(conn: Any, queue_id: str, workspace_id: uuid.UUID) -> QueueSource:
    """The queue of this workspace, or 404."""
    queue = workspace_review_queue(conn, queue_id, workspace_id)
    made_by = conn.execute(
        text(
            "SELECT x.workflow_execution_id, d.workflow_slug, x.step_type "
            "FROM workflow_step_executions x "
            "JOIN workflow_executions e ON e.id = x.workflow_execution_id "
            "LEFT JOIN workflow_definitions d ON d.id = e.workflow_definition_id "
            "WHERE json_extract(x.result, '$.summary.queue_id') = :q LIMIT 1"
        ),
        {"q": queue_id},
    ).first()
    return QueueSource(
        queue_id=queue.queue_id,
        workspace_id=queue.workspace_id,
        task_schema_id=queue.task_schema_id,
        workflow_execution_id=str(made_by[0]) if made_by else None,
        workflow=str(made_by[1]) if made_by and made_by[1] else None,
        calibration=queue.calibration,
    )


def execution_queue_ids(
    conn: Any, execution_id: str, workspace_id: uuid.UUID
) -> list[str]:
    """The review queues a workflow execution of this workspace made, or 404."""
    row = conn.execute(
        text(
            "SELECT context FROM workflow_executions "
            "WHERE id = :id AND workspace_id = :w"
        ),
        {"id": hyphenated_id(execution_id), "w": str(workspace_id)},
    ).first()
    if row is None:
        raise ApiError(
            404,
            "NOT_FOUND",
            "Workflow execution not found",
            {"workflow_execution_id": execution_id},
        )
    context = json_object(row[0])
    queue_ids = context.get("review_queue_ids") or []
    return [str(queue_id) for queue_id in queue_ids]


def _gold_input(stable_fields: Any, payload: Any) -> dict[str, Any]:
    """The content a reviewer labels: the stable fields, or the payload if empty."""
    stable = scrub_review_value(json_object(stable_fields))
    if any(value not in (None, "", [], {}) for value in stable.values()):
        return stable
    return scrub_review_value(json_object(payload))


def reviewed_records(
    conn: Any, source: QueueSource, record_ids: Sequence[str] | None = None
) -> list[ReviewedRecord]:
    """The queue's records with their counted reviews, resolutions and proposals.

    With *record_ids*, only those records; one the queue does not hold
    answers 404. Records come back by external id, then record id.
    """
    tasks: dict[str, list[tuple[str, Any]]] = defaultdict(list)
    for record_id, status, output_ids in conn.execute(
        text(
            "SELECT record_id, status, agent_output_ids FROM review_tasks "
            "WHERE queue_id = :q"
        ),
        {"q": source.queue_id},
    ).fetchall():
        tasks[str(record_id)].append((str(status), output_ids))
    wanted = (
        list(tasks) if record_ids is None else [hyphenated_id(r) for r in record_ids]
    )
    missing = [record_id for record_id in wanted if record_id not in tasks]
    if missing:
        raise ApiError(
            404,
            "NOT_FOUND",
            "The queue holds no task for these records",
            {"record_ids": missing},
        )
    if not wanted:
        return []

    reviews: dict[str, list[CountedReview]] = defaultdict(list)
    for event in counted_review_events(queue_review_events(conn, [source.queue_id])):
        reviews[event.record_id].append(
            CountedReview(
                review_event_id=event.event_id,
                reviewer_id=event.reviewer_id,
                decision=event.decision,
                ai_revealed=event.ai_revealed,
                labels=rated_labels(event),
            )
        )

    queue = ReviewQueue(source.queue_id, source.workspace_id, source.task_schema_id)
    disagreements = {str(d.item.record_id): d for d in queue_disagreements(conn, queue)}
    outcome_events = [
        d.outcome.review_event_id
        for d in disagreements.values()
        if d.outcome is not None and d.outcome.review_event_id
    ]
    revealed = {
        str(row[0]): bool(row[1])
        for row in conn.execute(
            _expanding(
                "SELECT id, ai_was_revealed = 1 OR agent_output_id IS NOT NULL "
                "FROM review_events WHERE id IN :ids",
                "ids",
            ),
            {"ids": outcome_events},
        ).fetchall()
    }

    output_ids = sorted(
        {
            str(output_id)
            for record_id in wanted
            for _status, raw in tasks[record_id]
            for output_id in deserialize_agent_output_ids(raw)
        }
    )
    proposals: dict[str, list[Proposal]] = defaultdict(list)
    for output_id, run_id, record_id, labels in conn.execute(
        _expanding(
            "SELECT id, agent_run_id, record_id, labels FROM agent_outputs "
            "WHERE id IN :ids ORDER BY created_at, id",
            "ids",
        ),
        {"ids": output_ids},
    ).fetchall():
        proposals[str(record_id)].append(
            Proposal(
                agent_output_id=str(output_id),
                agent_run_id=str(run_id),
                labels=json_object(labels),
            )
        )

    rows = conn.execute(
        _expanding(
            "SELECT r.id, r.external_id, r.stable_fields, r.payload, d.dataset_slug "
            "FROM records r LEFT JOIN datasets d ON d.id = r.dataset_id "
            "WHERE r.id IN :ids",
            "ids",
        ),
        {"ids": wanted},
    ).fetchall()
    rows = sorted(rows, key=lambda row: (str(row[1] or ""), str(row[0])))

    records = []
    for record_id, external_id, stable_fields, payload, dataset in rows:
        record_id = str(record_id)
        disagreement = disagreements.get(record_id)
        outcome = disagreement.outcome if disagreement else None
        records.append(
            ReviewedRecord(
                input_ref=GoldInputRef(
                    dataset=str(dataset) if dataset else None,
                    external_id=str(external_id) if external_id else None,
                    record_id=record_id,
                ),
                input=_gold_input(stable_fields, payload),
                queue_id=source.queue_id,
                workflow_execution_id=source.workflow_execution_id,
                open_copies=sum(
                    status in ("available", "claimed")
                    for status, _raw in tasks[record_id]
                ),
                reviews=tuple(reviews.get(record_id, ())),
                disagreement=disagreement is not None,
                resolution=Resolution(
                    adjudication_id=outcome.adjudication_id,
                    adjudicator_id=outcome.adjudicator_id,
                    resolution=outcome.resolution,
                    labels=outcome.resolved_labels,
                    review_event_id=outcome.review_event_id,
                    ai_revealed=revealed.get(outcome.review_event_id or "", False),
                    agent_sources=dict(outcome.agent_sources),
                )
                if outcome is not None
                else None,
                proposals=tuple(proposals.get(record_id, ())),
            )
        )
    return records


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GoldWrite:
    """A set after a promotion, and what happened to each record."""

    definition_path: str
    gold: GoldSet
    written: bool
    corrected: tuple[StaleLine, ...]
    """The stale lines the write rendered afresh."""
    added: tuple[GoldItem, ...]
    duplicates: tuple[GoldItemRef, ...]
    conflicts: tuple[GoldConflict, ...]
    skipped: tuple[Skipped, ...]


def promote_to_gold(
    engine: Any,
    workspace_id: uuid.UUID,
    slug: str,
    *,
    promoted_by: uuid.UUID,
    queue_ids: Sequence[str],
    record_ids: Sequence[str] | None = None,
    allow_single_reviewer: bool = False,
    failures_only: bool = False,
) -> GoldWrite:
    """Add the eligible records of these queues to the set, deduped.

    With *failures_only*, only the records whose human label contradicts an
    agent proposal. A run that adds nothing writes nothing.
    """
    folder = workspace_folder(engine, str(workspace_id))
    with workspace_files(folder) as files:
        stored = read_gold_set(folder, slug)
        gold = stored.gold
        promoted_at = _now()
        candidates: list[GoldItem] = []
        skipped: list[Skipped] = []
        sources: dict[str, GoldSetSource] = {}
        with engine.connect() as conn:
            for queue_id in queue_ids:
                source = queue_source(conn, queue_id, workspace_id)
                _check_source(conn, source, gold)
                sources[source.queue_id] = source.gold_source()
                for record in reviewed_records(conn, source, record_ids):
                    result = gold_candidate(
                        record,
                        task_schema=gold.header.task_schema,
                        promoted_by=str(promoted_by),
                        promoted_at=promoted_at,
                        allow_single_reviewer=allow_single_reviewer,
                        failures_only=failures_only,
                    )
                    if isinstance(result, Skipped):
                        skipped.append(result)
                    else:
                        candidates.append(result)

        merged = merge(gold.items, candidates)
        contributing = {item.provenance.queue_id for item in merged.added}
        revised = gold.appended(
            merged.added,
            now=promoted_at,
            sources=[sources[q] for q in sources if q in contributing],
        )
        if revised is not None:
            _write(files, stored, revised)
    return GoldWrite(
        definition_path=stored.definition_path,
        gold=revised or gold,
        written=revised is not None,
        corrected=gold.stale if revised is not None else (),
        added=merged.added,
        duplicates=merged.duplicates,
        conflicts=merged.conflicts,
        skipped=tuple(skipped),
    )


def _check_source(conn: Any, source: QueueSource, gold: GoldSet) -> None:
    if source.calibration:
        raise ApiError(
            409,
            "GOLD_SOURCE_IS_CALIBRATION",
            f"Queue '{source.queue_id}' is a calibration queue, whose answers "
            "test reviewers against gold and never become gold",
            {"queue_id": source.queue_id},
        )
    queue_schema = conn.execute(
        text("SELECT task_schema_slug FROM task_schemas WHERE id = :id"),
        {"id": source.task_schema_id},
    ).scalar()
    if queue_schema != gold.header.task_schema:
        raise ApiError(
            422,
            "GOLD_TASK_SCHEMA_MISMATCH",
            f"Gold set '{gold.header.gold_set_id}' holds task schema "
            f"'{gold.header.task_schema}', and queue '{source.queue_id}' "
            f"reviews '{queue_schema}'",
            {
                "gold_set_id": gold.header.gold_set_id,
                "gold_task_schema": gold.header.task_schema,
                "queue_id": source.queue_id,
                "queue_task_schema": queue_schema,
            },
        )


@dataclass(frozen=True)
class GoldDedupe:
    definition_path: str
    gold: GoldSet
    written: bool
    removed: tuple[GoldItemRef, ...]
    conflicts: tuple[GoldConflict, ...]


def dedupe_gold_set(engine: Any, workspace_id: uuid.UUID, slug: str) -> GoldDedupe:
    """Remove the set's exact repeats, and report the conflicts left in it."""
    folder = workspace_folder(engine, str(workspace_id))
    with workspace_files(folder) as files:
        stored = read_gold_set(folder, slug)
        deduped = dedupe(stored.gold.items)
        revised = (
            stored.gold.revised(deduped.items, now=_now()) if deduped.removed else None
        )
        if revised is not None:
            _write(files, stored, revised)
    return GoldDedupe(
        definition_path=stored.definition_path,
        gold=revised or stored.gold,
        written=revised is not None,
        removed=deduped.removed,
        conflicts=deduped.conflicts,
    )


def export_gold_set(
    engine: Any,
    workspace_id: uuid.UUID,
    slug: str,
    *,
    path: str,
    overwrite: bool,
) -> tuple[StoredGoldSet, str, bytes]:
    """Write the set's items, as MoLabel renders them, to *path* in the workspace."""
    folder = workspace_folder(engine, str(workspace_id))
    with workspace_files(folder) as files:
        stored = read_gold_set(folder, slug)
        require_portable(folder.path, path)
        target = resolve_in_workspace(folder.path, path)
        if target.exists() and not overwrite:
            relative = target.relative_to(folder.path).as_posix()
            raise ApiError(
                409,
                "EXPORT_PATH_EXISTS",
                f"{relative} exists; pass overwrite to replace it",
                {"path": relative},
            )
        data = render_items(stored.gold.items)
        written = files.write_file(path, data)
    return stored, written, data


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------


def gold_records(
    conn: Any, workspace_id: str, gold: GoldSet
) -> tuple[dict[str, GoldItem], list[str]]:
    """Each item by the record of this workspace it points to, and the rest.

    An item points to its ``record_id`` when this workspace holds it, or else
    to the record with its dataset slug and external id, which a database
    that imported the data again gives a new id.
    """
    held = {
        str(record_id)
        for (record_id,) in conn.execute(
            _expanding(
                "SELECT id FROM records WHERE workspace_id = :w AND id IN :ids", "ids"
            ),
            {
                "w": workspace_id,
                "ids": [
                    i.input_ref.record_id for i in gold.items if i.input_ref.record_id
                ],
            },
        ).fetchall()
    }
    by_record: dict[str, GoldItem] = {}
    unresolved: list[str] = []
    for item in gold.items:
        ref = item.input_ref
        record_id = ref.record_id if ref.record_id in held else None
        if record_id is None and ref.dataset and ref.external_id:
            found = conn.execute(
                text(
                    "SELECT r.id FROM records r JOIN datasets d ON d.id = r.dataset_id "
                    "WHERE r.workspace_id = :w AND d.dataset_slug = :dataset "
                    "AND r.external_id = :external_id LIMIT 1"
                ),
                {
                    "w": workspace_id,
                    "dataset": ref.dataset,
                    "external_id": ref.external_id,
                },
            ).scalar()
            record_id = str(found) if found else None
        if record_id is None or record_id in by_record:
            unresolved.append(item.item_id)
        else:
            by_record[record_id] = item
    return by_record, unresolved


def calibration_items(
    conn: Any, folder: WorkspaceFolder, slug: str
) -> CalibrationItems:
    """The records a calibration queue on set *slug* holds."""
    gold = read_gold_set(folder, slug).gold
    by_record, unresolved = gold_records(conn, folder.workspace_id, gold)
    return CalibrationItems(
        gold_set=slug,
        version=gold.header.version,
        content_hash=gold.file_hash,
        task_schema=gold.header.task_schema,
        record_ids=list(by_record),
        unresolved=unresolved,
    )

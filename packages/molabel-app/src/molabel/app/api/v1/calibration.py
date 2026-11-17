"""Calibration against gold -- /api/v1/calibration.

A ``human_calibration`` step makes a queue of a gold set's items. This
endpoint scores each reviewer of that queue against the set's expected
labels (``molabel.core.gold.calibration``). It reads only a queue of the
session's workspace and answers 404 for any other.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from molabel.app.api.v1.adjudication import workspace_review_queue
from molabel.app.errors import ApiError
from molabel.app.middleware.session import CurrentReviewer
from molabel.app.services.gold_sets import gold_records, read_gold_set
from molabel.app.services.review_events import json_object, queue_review_events
from molabel.app.utils import get_engine
from molabel.app.workspace_config import workspace_folder
from molabel.core.gold.calibration import ReviewerGoldScore, score_against_gold

router = APIRouter(prefix="/calibration", tags=["calibration"])


class ReviewerCalibration(ReviewerGoldScore):
    reviewer_name: str


class CalibrationReport(BaseModel):
    """Each reviewer of a calibration queue scored against its gold set.

    ``accuracy`` is the share of compared values that match gold, and
    ``cohen_kappa`` treats gold as a second rater, so a reviewer who always
    gives the most common label scores near 0.
    """

    queue_id: str
    gold_set_id: str
    gold_version: int = Field(description="The version the set is at now")
    queue_gold_version: int | None = Field(
        default=None, description="The version the queue was made from"
    )
    items: int = Field(description="Gold items in the queue")
    fields: list[str]
    reviewers: list[ReviewerCalibration]
    warnings: list[str] = []


def _label_fields(conn: Any, task_schema_id: str) -> list[str]:
    raw = conn.execute(
        text("SELECT label_fields FROM task_schemas WHERE id = :id"),
        {"id": task_schema_id},
    ).scalar()
    fields = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(fields, list):
        return []
    return [field["name"] for field in fields if isinstance(field, dict)]


@router.get("/queues/{queue_id}", response_model=CalibrationReport)
async def get_calibration_report(
    request: Request, queue_id: str, reviewer: CurrentReviewer
) -> CalibrationReport:
    """Score each reviewer of a calibration queue against its gold set."""
    engine = get_engine(request)
    folder = workspace_folder(engine, str(reviewer.workspace_id))
    with engine.connect() as conn:
        queue = workspace_review_queue(conn, queue_id, reviewer.workspace_id)
        made = conn.execute(
            text(
                "SELECT result FROM workflow_step_executions "
                "WHERE step_type = 'human_calibration' "
                "AND json_extract(result, '$.summary.queue_id') = :q LIMIT 1"
            ),
            {"q": queue_id},
        ).scalar()
        summary = json_object(json_object(made).get("summary"))
        if not summary.get("gold_set"):
            raise ApiError(
                404,
                "NOT_A_CALIBRATION_QUEUE",
                f"Queue '{queue_id}' was not made by a human_calibration step",
                {"queue_id": queue_id},
            )
        gold = read_gold_set(folder, str(summary["gold_set"])).gold
        by_record, _ = gold_records(conn, queue.workspace_id, gold)
        queued = {
            str(record_id)
            for (record_id,) in conn.execute(
                text("SELECT DISTINCT record_id FROM review_tasks WHERE queue_id = :q"),
                {"q": queue_id},
            ).fetchall()
        }
        in_queue = {r: item for r, item in by_record.items() if r in queued}
        fields = _label_fields(conn, queue.task_schema_id)
        scores = score_against_gold(
            in_queue, queue_review_events(conn, [queue_id]), fields
        )
        names = dict(
            conn.execute(
                text("SELECT id, display_name FROM reviewer_profiles")
            ).fetchall()
        )

    slug = gold.header.gold_set_id
    made_from = summary.get("gold_version")
    made_from_hash = summary.get("gold_content_hash")
    warnings = []
    if made_from is not None and made_from != gold.header.version:
        warnings.append(
            f"Gold set '{slug}' is at version {gold.header.version}; this queue "
            f"was made from version {made_from}. Each answer is scored against "
            "the current labels."
        )
    elif made_from_hash is not None and made_from_hash != gold.file_hash:
        warnings.append(
            f"Gold set '{slug}' changed since this queue was made, though its "
            f"version is still {gold.header.version}. Each answer is scored "
            "against the current labels."
        )
    if not gold.content_hash_matches:
        warnings.append(
            f"gold.jsonl of gold set '{slug}' does not match its header: it was "
            "edited outside MoLabel, or a write stopped partway. Version "
            f"{gold.header.version} describes the previous file."
        )
    if len(in_queue) < len(queued):
        warnings.append(
            f"{len(queued) - len(in_queue)} of the queue's records are no longer "
            "in the gold set and are not scored."
        )
    return CalibrationReport(
        queue_id=queue_id,
        gold_set_id=gold.header.gold_set_id,
        gold_version=gold.header.version,
        queue_gold_version=made_from,
        items=len(in_queue),
        fields=fields,
        reviewers=[
            ReviewerCalibration(
                **score.model_dump(),
                reviewer_name=str(names.get(score.reviewer_id, score.reviewer_id)),
            )
            for score in scores
        ],
        warnings=warnings,
    )

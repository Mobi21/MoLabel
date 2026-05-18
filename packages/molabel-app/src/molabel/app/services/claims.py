"""Claim service: atomic queue claims, expiry, draft management (SE-006 through SE-010).

Also implements:
- RV-001: Blind first-pass review (agent output hiding based on policy)
- RV-002: AI reveal mechanism with tracking
- RV-004: Review event append-only guarantee (corrections via supersedes_event_id)

Implements the queue claim model described in docs/architecture/session-and-identity.md.
All database access uses raw SQL via ``sqlalchemy.text()`` to avoid triggering
SQLAlchemy mapper configuration for the full model graph.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from molabel.app.utils import parse_bool
from molabel.core.review.queue_ordering import (
    OrderingConfig,
    build_priority_sql_expression,
)
from molabel.core.types import BlindReviewPolicy, ReviewDecision, ReviewEventSource

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_CLAIM_TIMEOUT_MINUTES: int = 30

# Reviewer status thresholds (minutes)
ACTIVE_THRESHOLD_MINUTES: int = 5
IDLE_THRESHOLD_MINUTES: int = 30

# In-memory store of recently expired claims per reviewer for notification.
# Maps reviewer_id (str) -> list of dicts with expiry info.
# NOTE: This dict is per-process. In a multi-worker deployment (e.g.
# gunicorn with N workers), notifications are only visible to the worker
# that expired the claim. Acceptable for local-first / Tauri single-worker
# deployments. For multi-worker, move to the database or a shared cache.
_expired_claim_notifications: dict[str, list[dict[str, Any]]] = {}

_REVIEW_LEAK_FIELDS = frozenset(
    {
        "source_label",
        "gold_label",
        "gold_labels",
        "ground_truth",
        "ground_truth_label",
        "ground_truth_labels",
    }
)


def reset_expired_notifications() -> None:
    """Clear the in-memory notification store (useful for testing)."""
    _expired_claim_notifications.clear()


# ---------------------------------------------------------------------------
# Helper: row dict builder
# ---------------------------------------------------------------------------

_TASK_COLUMNS = (
    "id, queue_id, record_id, task_schema_id, status, priority, "
    "priority_reason, claimed_by, claimed_at, claim_expired_count, "
    "is_overlap, is_calibration, draft_labels, ai_revealed, "
    "ai_revealed_at, submitted_at, created_at, updated_at, "
    "workspace_id, dataset_id"
)


def _row_to_task_dict(row) -> dict[str, Any]:
    """Convert a raw SQL row to a task dict."""
    draft = row[12]
    if isinstance(draft, str):
        try:
            draft = json.loads(draft)
        except (json.JSONDecodeError, TypeError):
            draft = None

    return {
        "id": str(row[0]),
        "queue_id": str(row[1]),
        "record_id": str(row[2]),
        "task_schema_id": str(row[3]),
        "status": str(row[4]),
        "priority": int(row[5]),
        "priority_reason": str(row[6]) if row[6] else None,
        "claimed_by": str(row[7]) if row[7] else None,
        "claimed_at": str(row[8]) if row[8] else None,
        "claim_expired_count": int(row[9]),
        "is_overlap": parse_bool(row[10]),
        "is_calibration": parse_bool(row[11]),
        "draft_labels": draft,
        "ai_revealed": parse_bool(row[13]),
        "ai_revealed_at": str(row[14]) if row[14] else None,
        "submitted_at": str(row[15]) if row[15] else None,
        "created_at": str(row[16]),
        "updated_at": str(row[17]),
        "workspace_id": str(row[18]),
        "dataset_id": str(row[19]),
    }


def _normalize_review_decision(
    decision: ReviewDecision | str | None,
) -> ReviewDecision | None:
    """Validate and normalize a review decision value."""
    if decision is None:
        return None
    if isinstance(decision, ReviewDecision):
        return decision
    return ReviewDecision(decision)


_STABLE_EVIDENCE_ATOM_RE = re.compile(
    r".+_(?:sentence_\d+|cell_\d+_\d+_\d+|header_cell_\d+_\d+_\d+)$"
)


def _parse_json_object(raw: Any) -> dict[str, Any] | None:
    """Best-effort parse for JSON object columns."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
    return raw if isinstance(raw, dict) else None


def _scrub_review_value(raw: Any) -> Any:
    """Recursively remove obvious gold-bearing fields from reviewer-visible data."""
    if isinstance(raw, dict):
        scrubbed: dict[str, Any] = {}
        for key, value in raw.items():
            if key.lower() in _REVIEW_LEAK_FIELDS:
                continue
            scrubbed[key] = _scrub_review_value(value)
        return scrubbed
    if isinstance(raw, list):
        return [_scrub_review_value(value) for value in raw]
    return raw


def _extract_record_text(payload: dict[str, Any] | None) -> str | None:
    """Return the best reviewer-facing text representation for a record payload."""
    if not isinstance(payload, dict):
        return None
    for key in ("text", "content", "message", "review", "body", "input"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ("post_tokens", "tokens"):
        value = payload.get(key)
        if isinstance(value, list):
            cleaned_tokens = [
                str(token).strip() for token in value if str(token).strip()
            ]
            joined = " ".join(cleaned_tokens)
            if joined:
                return joined
    rendered = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return rendered if rendered != "{}" else None


def _resolve_task_schema_version(conn, task_schema_id: str) -> int:
    """Best-effort lookup of the task schema version for review events."""
    try:
        row = conn.execute(
            text(
                """
                SELECT version
                FROM task_schemas
                WHERE id = :task_schema_id
                LIMIT 1
                """
            ),
            {"task_schema_id": task_schema_id},
        ).first()
    except SQLAlchemyError:
        return 1

    if row is None or row[0] is None:
        return 1

    return int(row[0])


def _normalize_submission_labels(
    conn,
    task_schema_id: str,
    labels: dict[str, Any],
) -> dict[str, Any]:
    """Normalize submitted labels against the task schema's field definitions.

    Performs case-insensitive matching for categorical/ordinal fields
    and returns canonical form.  Falls through silently if the schema
    or field definitions cannot be loaded.
    """
    if not labels:
        return labels

    raw = _load_task_schema_label_fields(conn, task_schema_id)
    if not raw:
        return labels

    from molabel.core.agents.output_validator import _normalize_labels
    from molabel.core.types import LabelFieldDefinition

    field_defs: list[LabelFieldDefinition] = []
    for entry in raw:
        if isinstance(entry, dict):
            try:
                field_defs.append(LabelFieldDefinition(**entry))
            except Exception:
                continue

    if not field_defs:
        return labels

    normalized, _ = _normalize_labels(labels, field_defs)
    return normalized if normalized else labels


def _load_task_schema_label_fields(
    conn,
    task_schema_id: str,
) -> list[dict[str, Any]]:
    """Return raw task-schema field definitions for submission validation."""
    try:
        row = conn.execute(
            text(
                "SELECT label_fields FROM task_schemas "
                "WHERE id = :task_schema_id LIMIT 1"
            ),
            {"task_schema_id": task_schema_id},
        ).first()
    except SQLAlchemyError:
        return []

    if row is None or row[0] is None:
        return []

    raw = row[0]
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []

    return raw if isinstance(raw, list) else []


def _load_record_payload(
    conn,
    record_id: str,
) -> dict[str, Any]:
    """Load the record payload for submission-time structural validation."""
    try:
        row = conn.execute(
            text("SELECT payload FROM records WHERE id = :record_id LIMIT 1"),
            {"record_id": record_id},
        ).first()
    except SQLAlchemyError:
        return {}

    if row is None or row[0] is None:
        return {}

    raw = row[0]
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
    return raw if isinstance(raw, dict) else {}


def _looks_like_stable_evidence_atom(value: Any) -> bool:
    """Return True when an evidence atom matches the benchmark ID format."""
    return isinstance(value, str) and bool(_STABLE_EVIDENCE_ATOM_RE.fullmatch(value))


def _validate_structured_submission_labels(
    conn,
    *,
    record_id: str,
    task_schema_id: str,
    labels: dict[str, Any],
) -> list[str]:
    """Validate evidence/rationale structures before persisting a review."""
    if not labels:
        return []

    label_fields = _load_task_schema_label_fields(conn, task_schema_id)
    if not label_fields:
        return []

    field_map = {
        str(field.get("name")): field
        for field in label_fields
        if isinstance(field, dict) and field.get("name")
    }
    errors: list[str] = []
    verdict = str(labels.get("verdict") or "").strip().lower()

    if "evidence_atoms" in field_map or "evidence_atoms" in labels:
        evidence_atoms = labels.get("evidence_atoms")
        evidence_field = field_map.get("evidence_atoms", {})
        if evidence_atoms is None:
            if evidence_field.get("required", True) and verdict != "nei":
                errors.append("evidence_atoms is required when verdict is not 'nei'")
        elif not isinstance(evidence_atoms, list):
            errors.append(
                "evidence_atoms must be a JSON array of stable evidence atom IDs"
            )
        else:
            bad_atoms = [
                atom
                for atom in evidence_atoms
                if not _looks_like_stable_evidence_atom(atom)
            ]
            if bad_atoms:
                rendered = ", ".join(repr(atom) for atom in bad_atoms[:3])
                errors.append(
                    "evidence_atoms must contain only stable sentence/cell IDs; "
                    f"got {rendered}"
                )
            if verdict != "nei" and not evidence_atoms:
                errors.append(
                    "evidence_atoms must include at least one supporting atom "
                    "when verdict is not 'nei'"
                )

    if "rationale_token_mask" in field_map or "rationale_token_mask" in labels:
        rationale_mask = labels.get("rationale_token_mask")
        if not isinstance(rationale_mask, list):
            errors.append("rationale_token_mask must be a JSON array of 0/1 integers")
        else:
            invalid_values = [
                value
                for value in rationale_mask
                if not isinstance(value, int) or value not in {0, 1}
            ]
            if invalid_values:
                rendered = ", ".join(repr(value) for value in invalid_values[:5])
                errors.append(
                    "rationale_token_mask must contain only binary integers; "
                    f"got {rendered}"
                )
            payload = _load_record_payload(conn, record_id)
            tokens = payload.get("tokens")
            if isinstance(tokens, list) and len(tokens) != len(rationale_mask):
                errors.append(
                    "rationale_token_mask length must match the record token count "
                    f"({len(tokens)}), got {len(rationale_mask)}"
                )

    return errors


def _resolve_effective_submission_labels(
    conn,
    *,
    task_id: uuid.UUID,
    explicit_labels: dict[str, Any],
    decision: ReviewDecision | None,
) -> dict[str, Any]:
    """Resolve the labels that should be persisted for a review submission."""
    if explicit_labels:
        return explicit_labels

    if decision != ReviewDecision.accept_ai:
        return explicit_labels

    row = conn.execute(
        text("SELECT agent_output_ids FROM review_tasks WHERE id = :task_id"),
        {"task_id": str(task_id)},
    ).first()
    if row is None or not row[0]:
        return explicit_labels

    try:
        output_ids = json.loads(str(row[0]))
    except (json.JSONDecodeError, TypeError):
        return explicit_labels

    if not isinstance(output_ids, list) or not output_ids:
        return explicit_labels

    output_row = conn.execute(
        text("SELECT labels FROM agent_outputs WHERE id = :id LIMIT 1"),
        {"id": str(output_ids[0])},
    ).first()
    if output_row is None:
        return explicit_labels

    labels = output_row[0]
    if isinstance(labels, str):
        try:
            labels = json.loads(labels)
        except (json.JSONDecodeError, TypeError):
            return explicit_labels
    return labels if isinstance(labels, dict) else explicit_labels


def _get_record_context(
    conn,
    record_id: str,
) -> dict[str, Any]:
    """Fetch reviewer-safe record context for a claimed task."""
    try:
        row = conn.execute(
            text(
                """
                SELECT external_id, stable_fields, payload
                FROM records
                WHERE id = :record_id
                LIMIT 1
                """
            ),
            {"record_id": record_id},
        ).first()
    except SQLAlchemyError:
        row = None

    if row is None:
        return {
            "record_external_id": None,
            "record_view": None,
            "record_text": None,
        }

    payload = _scrub_review_value(_parse_json_object(row[2]))

    return {
        "record_external_id": str(row[0]) if row[0] else None,
        "record_view": {
            "stable_fields": _scrub_review_value(_parse_json_object(row[1])),
            "payload": payload,
        },
        "record_text": _extract_record_text(payload),
    }


# ---------------------------------------------------------------------------
# SE-006: Atomic queue claim
# ---------------------------------------------------------------------------


def claim_next(
    engine: Engine,
    queue_id: str,
    reviewer_id: uuid.UUID,
    ordering_config: OrderingConfig | None = None,
) -> dict[str, Any] | None:
    """Atomically claim the next available item from a queue.

    Uses the UPDATE...WHERE...(SELECT...LIMIT 1) pattern to prevent
    double-assignment. Returns the claimed task dict, or None if the
    queue is empty.

    SE-006: One-item-at-a-time claims only, no bulk claim hoarding.
    RV-008: Priority ordering: active learning > workflow > general.
            Optional sticky assignment prefers previously drafted items.
    """
    now = datetime.now(UTC).isoformat()
    reviewer_str = str(reviewer_id)

    config = ordering_config or OrderingConfig()
    order_clause = build_priority_sql_expression(config)

    # When sticky assignment is enabled, prefer items the reviewer has
    # previously drafted (draft_labels IS NOT NULL for this reviewer).
    sticky_clause = ""
    if config.enable_sticky_assignment:
        sticky_clause = (
            "CASE WHEN id IN ("
            "  SELECT id FROM review_tasks"
            "  WHERE queue_id = :queue_id"
            "    AND draft_labels IS NOT NULL"
            "    AND claimed_by IS NULL"
            "    AND status = 'available'"
            ") THEN 0 ELSE 1 END ASC, "
        )

    with engine.connect() as conn:
        # Atomic claim: UPDATE ... WHERE id = (SELECT ... LIMIT 1)
        # Excludes records this reviewer has already claimed/submitted/skipped
        # in the same queue (overlap review support / duplicate prevention).
        result = conn.execute(
            text(
                f"""
                UPDATE review_tasks
                SET claimed_by = :reviewer_id,
                    claimed_at = :now,
                    status = 'claimed',
                    updated_at = :now
                WHERE id = (
                    SELECT id
                    FROM review_tasks
                    WHERE queue_id = :queue_id
                      AND status = 'available'
                      AND claimed_by IS NULL
                      AND record_id NOT IN (
                          SELECT record_id
                          FROM review_tasks
                          WHERE queue_id = :queue_id
                            AND claimed_by = :reviewer_id
                            AND status IN ('claimed', 'submitted', 'skipped')
                      )
                    -- SAFETY: sticky_clause and order_clause are built from
                    -- hardcoded SQL fragments in queue_ordering.py, never
                    -- from user input. _TASK_COLUMNS is a module constant.
                    ORDER BY {sticky_clause}{order_clause}
                    LIMIT 1
                )
                RETURNING {_TASK_COLUMNS}
                """
            ),
            {
                "reviewer_id": reviewer_str,
                "now": now,
                "queue_id": queue_id,
            },
        )
        row = result.first()
        conn.commit()

    if row is None:
        return None

    return _row_to_task_dict(row)


# ---------------------------------------------------------------------------
# Release claim
# ---------------------------------------------------------------------------


def release_claim(
    engine: Engine,
    task_id: uuid.UUID,
    reviewer_id: uuid.UUID,
) -> dict[str, Any] | None:
    """Release a claim back to the available pool.

    Returns the updated task dict, or None if the task was not claimed
    by this reviewer.
    """
    now = datetime.now(UTC).isoformat()

    with engine.connect() as conn:
        result = conn.execute(
            text(
                f"""
                UPDATE review_tasks
                SET claimed_by = NULL,
                    claimed_at = NULL,
                    status = 'available',
                    updated_at = :now
                WHERE id = :task_id
                  AND claimed_by = :reviewer_id
                  AND status = 'claimed'
                RETURNING {_TASK_COLUMNS}
                """
            ),
            {
                "task_id": str(task_id),
                "reviewer_id": str(reviewer_id),
                "now": now,
            },
        )
        row = result.first()
        conn.commit()

    if row is None:
        return None

    return _row_to_task_dict(row)


# ---------------------------------------------------------------------------
# Submit review
# ---------------------------------------------------------------------------


def submit_review(
    engine: Engine,
    task_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    labels: dict[str, Any],
    decision: ReviewDecision | str | None = None,
    rationale: str | None = None,
) -> dict[str, Any] | None:
    """Submit a review for a claimed task.

    Clears draft_labels, sets status to 'submitted', records submitted_at,
    and appends a human review event row for the submission.
    Returns the updated task dict, or None if the task was not claimed
    by this reviewer.
    """
    now = datetime.now(UTC).isoformat()
    normalized_decision = _normalize_review_decision(decision)

    with engine.begin() as conn:
        effective_labels = _resolve_effective_submission_labels(
            conn,
            task_id=task_id,
            explicit_labels=labels,
            decision=normalized_decision,
        )
        labels_json = json.dumps(effective_labels)
        result = conn.execute(
            text(
                f"""
                UPDATE review_tasks
                SET status = 'submitted',
                    draft_labels = NULL,
                    submitted_at = :now,
                    updated_at = :now
                WHERE id = :task_id
                  AND claimed_by = :reviewer_id
                  AND status = 'claimed'
                RETURNING {_TASK_COLUMNS}
                """
            ),
            {
                "task_id": str(task_id),
                "reviewer_id": str(reviewer_id),
                "now": now,
            },
        )
        row = result.first()

        if row is None:
            return None

        task_schema_id = str(row[3])
        effective_labels = _normalize_submission_labels(
            conn,
            task_schema_id,
            effective_labels,
        )
        validation_errors = _validate_structured_submission_labels(
            conn,
            record_id=str(row[2]),
            task_schema_id=task_schema_id,
            labels=effective_labels,
        )
        if validation_errors:
            raise ValueError("; ".join(validation_errors))
        labels_json = json.dumps(effective_labels)
        review_event_id = uuid.uuid4()
        task_schema_version = _resolve_task_schema_version(conn, task_schema_id)
        decision_value = (
            normalized_decision.value if normalized_decision is not None else None
        )

        conn.execute(
            text(
                """
                INSERT INTO review_events (
                    id,
                    review_task_id,
                    record_id,
                    task_schema_id,
                    task_schema_version,
                    reviewer_id,
                    source,
                    decision,
                    labels,
                    rationale,
                    ai_was_revealed,
                    created_at,
                    workspace_id
                ) VALUES (
                    :id,
                    :review_task_id,
                    :record_id,
                    :task_schema_id,
                    :task_schema_version,
                    :reviewer_id,
                    :source,
                    :decision,
                    :labels,
                    :rationale,
                    :ai_was_revealed,
                    :created_at,
                    :workspace_id
                )
                """
            ),
            {
                "id": str(review_event_id),
                "review_task_id": str(row[0]),
                "record_id": str(row[2]),
                "task_schema_id": task_schema_id,
                "task_schema_version": task_schema_version,
                "reviewer_id": str(row[7]),
                "source": ReviewEventSource.human.value,
                "decision": decision_value,
                "labels": labels_json,
                "rationale": rationale,
                "ai_was_revealed": parse_bool(row[13]),
                "created_at": now,
                "workspace_id": str(row[18]),
            },
        )

        if effective_labels:
            try:
                conn.execute(
                    text(
                        """
                        UPDATE records
                        SET latest_label = :latest_label,
                            label_count = COALESCE(label_count, 0) + 1,
                            updated_at = :updated_at
                        WHERE id = :record_id
                        """
                    ),
                    {
                        "latest_label": labels_json,
                        "updated_at": now,
                        "record_id": str(row[2]),
                    },
                )
            except SQLAlchemyError:
                logger.debug(
                    "Skipping record label projection for review task %s; "
                    "records table unavailable",
                    task_id,
                )

        return _row_to_task_dict(row)


# ---------------------------------------------------------------------------
# Skip task
# ---------------------------------------------------------------------------


def skip_task(
    engine: Engine,
    task_id: uuid.UUID,
    reviewer_id: uuid.UUID,
) -> dict[str, Any] | None:
    """Skip a claimed task, marking it as skipped by this reviewer.

    Sets status to 'skipped' and retains ``claimed_by`` so the queue
    knows which reviewer skipped it (the claim query excludes records
    already claimed/submitted/skipped by the same reviewer).  The task
    is not returned to the available pool -- it stays skipped.

    Returns the updated task dict, or None if the task was not claimed
    by this reviewer.
    """
    now = datetime.now(UTC).isoformat()

    with engine.connect() as conn:
        result = conn.execute(
            text(
                f"""
                UPDATE review_tasks
                SET status = 'skipped',
                    updated_at = :now
                WHERE id = :task_id
                  AND claimed_by = :reviewer_id
                  AND status = 'claimed'
                RETURNING {_TASK_COLUMNS}
                """
            ),
            {
                "task_id": str(task_id),
                "reviewer_id": str(reviewer_id),
                "now": now,
            },
        )
        row = result.first()
        conn.commit()

    if row is None:
        return None

    return _row_to_task_dict(row)


# ---------------------------------------------------------------------------
# SE-009: Draft save (last-write-wins)
# ---------------------------------------------------------------------------


def save_draft(
    engine: Engine,
    task_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    draft_labels: dict[str, Any],
) -> dict[str, Any] | None:
    """Save draft labels for a claimed task (last-write-wins).

    SE-009: In same-profile multi-session scenarios, the later save
    overwrites the earlier one. No conflict resolution is attempted.

    Returns the updated task dict, or None if the task was not claimed
    by this reviewer.
    """
    now = datetime.now(UTC).isoformat()
    draft_json = json.dumps(draft_labels)

    with engine.connect() as conn:
        result = conn.execute(
            text(
                f"""
                UPDATE review_tasks
                SET draft_labels = :draft_labels,
                    updated_at = :now
                WHERE id = :task_id
                  AND claimed_by = :reviewer_id
                  AND status = 'claimed'
                RETURNING {_TASK_COLUMNS}
                """
            ),
            {
                "task_id": str(task_id),
                "reviewer_id": str(reviewer_id),
                "now": now,
                "draft_labels": draft_json,
            },
        )
        row = result.first()
        conn.commit()

    if row is None:
        return None

    return _row_to_task_dict(row)


# ---------------------------------------------------------------------------
# SE-007: Claim expiry
# ---------------------------------------------------------------------------


def get_expired_claims(
    engine: Engine,
    timeout_minutes: int = DEFAULT_CLAIM_TIMEOUT_MINUTES,
) -> list[dict[str, Any]]:
    """Find all claims that have exceeded the timeout.

    Returns a list of task dicts for claims older than *timeout_minutes*.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT {_TASK_COLUMNS}
                FROM review_tasks
                WHERE claimed_by IS NOT NULL
                  AND status = 'claimed'
                  AND claimed_at < datetime('now', '-' || :timeout || ' minutes')
                """
            ),
            {"timeout": str(timeout_minutes)},
        ).all()

    return [_row_to_task_dict(row) for row in rows]


def expire_claims(
    engine: Engine,
    timeout_minutes: int = DEFAULT_CLAIM_TIMEOUT_MINUTES,
) -> list[dict[str, Any]]:
    """Release all expired claims back to the available pool.

    SE-007: Increments claim_expired_count for each expired claim.
    Preserves draft_labels so the next reviewer can see partial work.

    Also stores expiry info in the in-memory notification store so the
    next API call from the affected reviewer triggers a notification
    header (SE-008).

    Returns a list of task dicts that were expired.
    """
    now = datetime.now(UTC).isoformat()

    with engine.connect() as conn:
        # First, find expiring claims to record notification info.
        expiring = conn.execute(
            text(
                """
                SELECT id, queue_id, claimed_by, record_id
                FROM review_tasks
                WHERE claimed_by IS NOT NULL
                  AND status = 'claimed'
                  AND claimed_at < datetime('now', '-' || :timeout || ' minutes')
                """
            ),
            {"timeout": str(timeout_minutes)},
        ).all()

        # Record notifications for affected reviewers.
        for row in expiring:
            reviewer_str = str(row[2])
            notification = {
                "task_id": str(row[0]),
                "queue_id": str(row[1]),
                "record_id": str(row[3]),
                "expired_at": now,
                "timeout_minutes": timeout_minutes,
            }
            if reviewer_str not in _expired_claim_notifications:
                _expired_claim_notifications[reviewer_str] = []
            _expired_claim_notifications[reviewer_str].append(notification)

        # Now expire all stale claims atomically.
        result = conn.execute(
            text(
                f"""
                UPDATE review_tasks
                SET claimed_by = NULL,
                    claimed_at = NULL,
                    status = 'available',
                    claim_expired_count = claim_expired_count + 1,
                    updated_at = :now
                WHERE claimed_by IS NOT NULL
                  AND status = 'claimed'
                  AND claimed_at < datetime('now', '-' || :timeout || ' minutes')
                RETURNING {_TASK_COLUMNS}
                """
            ),
            {"now": now, "timeout": str(timeout_minutes)},
        )
        rows = result.all()
        conn.commit()

    expired_tasks = [_row_to_task_dict(row) for row in rows]

    if expired_tasks:
        logger.info(
            "Expired %d claim(s) (timeout=%d min)",
            len(expired_tasks),
            timeout_minutes,
        )

    return expired_tasks


# ---------------------------------------------------------------------------
# SE-008: Claim expiry notifications
# ---------------------------------------------------------------------------


def pop_expired_notifications(reviewer_id: uuid.UUID) -> list[dict[str, Any]]:
    """Return and clear any pending claim-expiry notifications for a reviewer.

    SE-008: Called on each API request to check if the reviewer had claims
    that expired while they were offline. Returns the list of expiry records
    and clears them so they are not sent again.
    """
    reviewer_str = str(reviewer_id)
    notifications = _expired_claim_notifications.pop(reviewer_str, [])
    return notifications


# ---------------------------------------------------------------------------
# SE-010: Mission control reviewer visibility
# ---------------------------------------------------------------------------


def get_reviewer_visibility(
    engine: Engine,
    workspace_id: uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    """Get reviewer status for mission control display.

    SE-010: Classifies reviewers as active/idle/offline based on
    last_active_at thresholds and includes their current queue positions.

    - Active: last_active_at within 5 minutes
    - Idle: last_active_at 5-30 minutes ago
    - Offline: last_active_at > 30 minutes or null
    """
    conditions = ["rp.is_active = 1"]
    params: dict[str, Any] = {
        "active_thr": f"-{ACTIVE_THRESHOLD_MINUTES} minutes",
        "idle_thr": f"-{IDLE_THRESHOLD_MINUTES} minutes",
    }

    if workspace_id is not None:
        conditions.append("rp.workspace_id = :workspace_id")
        params["workspace_id"] = str(workspace_id)

    where_clause = " AND ".join(conditions)

    query = f"""
    SELECT
        rp.id,
        rp.display_name,
        rp.avatar_color,
        rp.is_operator,
        rp.last_active_at,
        CASE
            WHEN rp.last_active_at IS NULL
                THEN 'offline'
            WHEN rp.last_active_at >= datetime('now', :active_thr)
                THEN 'active'
            WHEN rp.last_active_at >= datetime('now', :idle_thr)
                THEN 'idle'
            ELSE 'offline'
        END AS status,
        (
            SELECT COUNT(*)
            FROM review_tasks rt
            WHERE rt.claimed_by = rp.id
              AND rt.status = 'submitted'
        ) AS completed_count,
        (
            SELECT rt2.queue_id
            FROM review_tasks rt2
            WHERE rt2.claimed_by = rp.id
              AND rt2.status = 'claimed'
            LIMIT 1
        ) AS current_queue,
        (
            SELECT rt3.id
            FROM review_tasks rt3
            WHERE rt3.claimed_by = rp.id
              AND rt3.status = 'claimed'
            LIMIT 1
        ) AS current_task_id
    FROM reviewer_profiles rp
    WHERE {where_clause}
    ORDER BY
        CASE
            WHEN rp.last_active_at >= datetime('now', :active_thr)
                THEN 0
            WHEN rp.last_active_at >= datetime('now', :idle_thr)
                THEN 1
            ELSE 2
        END,
        rp.display_name
    """

    with engine.connect() as conn:
        rows = conn.execute(text(query), params).all()

    results = []
    for row in rows:
        results.append(
            {
                "reviewer_id": str(row[0]),
                "display_name": str(row[1]),
                "avatar_color": str(row[2]) if row[2] else None,
                "is_operator": parse_bool(row[3]),
                "last_active_at": str(row[4]) if row[4] else None,
                "status": str(row[5]),
                "completed_count": int(row[6]) if row[6] is not None else 0,
                "current_queue": str(row[7]) if row[7] else None,
                "current_task_id": str(row[8]) if row[8] else None,
            }
        )

    return results


# ---------------------------------------------------------------------------
# Queue status
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# RV-001: Blind review policy helpers
# ---------------------------------------------------------------------------

_AGENT_OUTPUT_COLUMNS = (
    "id, agent_run_id, record_id, task_schema_id, output_type, labels, "
    "raw_response, confidence_self_reported, confidence_self_consistency, "
    "confidence_logprobs, composite_confidence, tokens_input, tokens_output, "
    "latency_ms, validation_passed, validation_errors, created_at, workspace_id"
)


def _get_blind_review_policy(
    conn,
    task_schema_id: str,
) -> BlindReviewPolicy:
    """Look up the blind_review_policy for a task schema.

    Falls back to ``hide_agent_outputs_by_default`` if the schema is not found.
    """
    try:
        row = conn.execute(
            text(
                """
                SELECT blind_review_policy
                FROM task_schemas
                WHERE id = :task_schema_id
                LIMIT 1
                """
            ),
            {"task_schema_id": task_schema_id},
        ).first()
    except SQLAlchemyError:
        return BlindReviewPolicy.hide_agent_outputs_by_default

    if row is None or row[0] is None:
        return BlindReviewPolicy.hide_agent_outputs_by_default

    return BlindReviewPolicy(str(row[0]))


def _get_agent_output_for_task(
    conn,
    record_id: str,
    task_schema_id: str,
) -> dict[str, Any] | None:
    """Fetch the most recent agent output for a record + task schema.

    Returns a dict representation, or None if no agent output exists.
    """
    try:
        row = conn.execute(
            text(
                f"""
                SELECT {_AGENT_OUTPUT_COLUMNS}
                FROM agent_outputs
                WHERE record_id = :record_id
                  AND task_schema_id = :task_schema_id
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"record_id": record_id, "task_schema_id": task_schema_id},
        ).first()
    except SQLAlchemyError:
        return None

    if row is None:
        return None

    labels = row[5]
    if isinstance(labels, str):
        try:
            labels = json.loads(labels)
        except (json.JSONDecodeError, TypeError):
            labels = {}

    raw_response = row[6]
    if isinstance(raw_response, str):
        try:
            raw_response = json.loads(raw_response)
        except (json.JSONDecodeError, TypeError):
            raw_response = None

    validation_errors = row[15]
    if isinstance(validation_errors, str):
        try:
            validation_errors = json.loads(validation_errors)
        except (json.JSONDecodeError, TypeError):
            validation_errors = None

    return {
        "id": str(row[0]),
        "agent_run_id": str(row[1]),
        "record_id": str(row[2]),
        "task_schema_id": str(row[3]),
        "output_type": str(row[4]),
        "labels": labels,
        "raw_response": raw_response,
        "confidence_self_reported": float(row[7]) if row[7] is not None else None,
        "confidence_self_consistency": float(row[8]) if row[8] is not None else None,
        "confidence_logprobs": float(row[9]) if row[9] is not None else None,
        "composite_confidence": float(row[10]) if row[10] is not None else None,
        "tokens_input": int(row[11]) if row[11] is not None else None,
        "tokens_output": int(row[12]) if row[12] is not None else None,
        "latency_ms": int(row[13]) if row[13] is not None else None,
        "validation_passed": parse_bool(row[14]),
        "validation_errors": validation_errors,
        "created_at": str(row[16]) if row[16] else None,
        "workspace_id": str(row[17]),
    }


def apply_blind_review_policy(
    engine: Engine,
    task_dict: dict[str, Any],
) -> dict[str, Any]:
    """Apply blind review policy to a task dict before returning to the reviewer.

    RV-001: Based on the task schema's blind_review_policy:
    - ``hide_agent_outputs_by_default``: strip agent_output unless ai_revealed=True
    - ``show_agent_outputs``: always include agent_output
    - ``no_agent``: never include agent_output

    Adds an ``agent_output`` key to the task dict (or None).
    Also adds ``blind_review_policy`` so the frontend knows the mode.
    """
    task_schema_id = task_dict.get("task_schema_id", "")
    record_id = task_dict.get("record_id", "")
    ai_revealed = task_dict.get("ai_revealed", False)

    with engine.connect() as conn:
        task_dict.update(_get_record_context(conn, record_id))
        policy = _get_blind_review_policy(conn, task_schema_id)

        if policy == BlindReviewPolicy.no_agent:
            task_dict["agent_output"] = None
            task_dict["blind_review_policy"] = policy.value
            return task_dict

        if policy == BlindReviewPolicy.show_agent_outputs:
            agent_output = _get_agent_output_for_task(conn, record_id, task_schema_id)
            task_dict["agent_output"] = agent_output
            task_dict["blind_review_policy"] = policy.value
            return task_dict

        # hide_agent_outputs_by_default: only show if revealed
        if ai_revealed:
            agent_output = _get_agent_output_for_task(conn, record_id, task_schema_id)
            task_dict["agent_output"] = agent_output
        else:
            task_dict["agent_output"] = None

        task_dict["blind_review_policy"] = policy.value
        return task_dict


# ---------------------------------------------------------------------------
# RV-002: AI reveal mechanism
# ---------------------------------------------------------------------------


def reveal_ai(
    engine: Engine,
    task_id: uuid.UUID,
    reviewer_id: uuid.UUID,
) -> dict[str, Any] | None:
    """Reveal agent output for a claimed review task.

    RV-002: Sets ai_revealed=True and ai_revealed_at on the task, then
    returns the task dict with the agent output included.

    Returns None if:
    - The task is not found or not claimed by this reviewer
    - The blind_review_policy is ``no_agent`` (reveal not allowed)
    """
    now = datetime.now(UTC).isoformat()

    with engine.connect() as conn:
        # First, look up the task to check ownership and policy
        row = conn.execute(
            text(
                f"""
                SELECT {_TASK_COLUMNS}
                FROM review_tasks
                WHERE id = :task_id
                  AND claimed_by = :reviewer_id
                  AND status = 'claimed'
                """
            ),
            {
                "task_id": str(task_id),
                "reviewer_id": str(reviewer_id),
            },
        ).first()

        if row is None:
            return None

        task_dict = _row_to_task_dict(row)
        task_schema_id = task_dict["task_schema_id"]

        # Check policy: no_agent means reveal is forbidden
        policy = _get_blind_review_policy(conn, task_schema_id)
        if policy == BlindReviewPolicy.no_agent:
            return None

        # Set ai_revealed=True and ai_revealed_at
        result = conn.execute(
            text(
                f"""
                UPDATE review_tasks
                SET ai_revealed = 1,
                    ai_revealed_at = :now,
                    updated_at = :now
                WHERE id = :task_id
                  AND claimed_by = :reviewer_id
                  AND status = 'claimed'
                RETURNING {_TASK_COLUMNS}
                """
            ),
            {
                "task_id": str(task_id),
                "reviewer_id": str(reviewer_id),
                "now": now,
            },
        )
        updated_row = result.first()
        conn.commit()

    if updated_row is None:
        return None

    updated_task = _row_to_task_dict(updated_row)

    # Fetch and attach agent output
    with engine.connect() as conn:
        agent_output = _get_agent_output_for_task(
            conn,
            updated_task["record_id"],
            updated_task["task_schema_id"],
        )
        updated_task.update(_get_record_context(conn, updated_task["record_id"]))

    updated_task["agent_output"] = agent_output
    updated_task["blind_review_policy"] = policy.value
    return updated_task


# ---------------------------------------------------------------------------
# RV-004: Review event append-only corrections
# ---------------------------------------------------------------------------


def submit_correction(
    engine: Engine,
    task_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    labels: dict[str, Any],
    decision: ReviewDecision | str | None = None,
    rationale: str | None = None,
) -> dict[str, Any] | None:
    """Submit a correction for a previously reviewed task.

    RV-004: Creates a NEW review_event with ``supersedes_event_id`` pointing
    to the most recent event for this task. Never updates or deletes the
    original event, preserving the append-only audit trail.

    Returns a dict with the new correction event, or None if:
    - No existing review event is found for this task
    - The task does not belong to a submitted/claimed task by this reviewer
    """
    now = datetime.now(UTC).isoformat()
    normalized_decision = _normalize_review_decision(decision)

    with engine.begin() as conn:
        # Verify the task exists and belongs to this reviewer
        task_row = conn.execute(
            text(
                f"""
                SELECT {_TASK_COLUMNS}
                FROM review_tasks
                WHERE id = :task_id
                  AND claimed_by = :reviewer_id
                """
            ),
            {
                "task_id": str(task_id),
                "reviewer_id": str(reviewer_id),
            },
        ).first()

        if task_row is None:
            return None

        task_dict = _row_to_task_dict(task_row)

        # Find the most recent review event for this task
        latest_event = conn.execute(
            text(
                """
                SELECT id, record_id, task_schema_id, task_schema_version,
                       reviewer_id, source, decision, labels, rationale,
                       ai_was_revealed, workspace_id
                FROM review_events
                WHERE review_task_id = :task_id
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"task_id": str(task_id)},
        ).first()

        if latest_event is None:
            return None

        superseded_event_id = str(latest_event[0])
        record_id = str(latest_event[1])
        task_schema_id = str(latest_event[2])
        task_schema_version = int(latest_event[3])
        workspace_id = str(latest_event[10])

        normalized_labels = _normalize_submission_labels(conn, task_schema_id, labels)
        validation_errors = _validate_structured_submission_labels(
            conn,
            record_id=record_id,
            task_schema_id=task_schema_id,
            labels=normalized_labels,
        )
        if validation_errors:
            raise ValueError("; ".join(validation_errors))
        labels_json = json.dumps(normalized_labels)

        # Capture the previous labels for audit
        previous_labels_raw = latest_event[7]
        if isinstance(previous_labels_raw, str):
            try:
                previous_labels = json.loads(previous_labels_raw)
            except (json.JSONDecodeError, TypeError):
                previous_labels = {}
        else:
            previous_labels = previous_labels_raw if previous_labels_raw else {}

        # Create the new correction event
        new_event_id = uuid.uuid4()
        decision_value = (
            normalized_decision.value if normalized_decision is not None else None
        )
        ai_was_revealed = parse_bool(task_dict.get("ai_revealed", False))

        conn.execute(
            text(
                """
                INSERT INTO review_events (
                    id,
                    review_task_id,
                    record_id,
                    task_schema_id,
                    task_schema_version,
                    reviewer_id,
                    source,
                    decision,
                    labels,
                    previous_labels,
                    rationale,
                    ai_was_revealed,
                    supersedes_event_id,
                    created_at,
                    workspace_id
                ) VALUES (
                    :id,
                    :review_task_id,
                    :record_id,
                    :task_schema_id,
                    :task_schema_version,
                    :reviewer_id,
                    :source,
                    :decision,
                    :labels,
                    :previous_labels,
                    :rationale,
                    :ai_was_revealed,
                    :supersedes_event_id,
                    :created_at,
                    :workspace_id
                )
                """
            ),
            {
                "id": str(new_event_id),
                "review_task_id": str(task_id),
                "record_id": record_id,
                "task_schema_id": task_schema_id,
                "task_schema_version": task_schema_version,
                "reviewer_id": str(reviewer_id),
                "source": ReviewEventSource.human.value,
                "decision": decision_value,
                "labels": labels_json,
                "previous_labels": json.dumps(previous_labels),
                "rationale": rationale,
                "ai_was_revealed": 1 if ai_was_revealed else 0,
                "supersedes_event_id": superseded_event_id,
                "created_at": now,
                "workspace_id": workspace_id,
            },
        )

        return {
            "id": str(new_event_id),
            "review_task_id": str(task_id),
            "record_id": record_id,
            "task_schema_id": task_schema_id,
            "task_schema_version": task_schema_version,
            "reviewer_id": str(reviewer_id),
            "source": ReviewEventSource.human.value,
            "decision": decision_value,
            "labels": normalized_labels,
            "previous_labels": previous_labels,
            "rationale": rationale,
            "ai_was_revealed": ai_was_revealed,
            "supersedes_event_id": superseded_event_id,
            "created_at": now,
            "workspace_id": workspace_id,
        }


# ---------------------------------------------------------------------------
# Queue status
# ---------------------------------------------------------------------------


def get_queue_status(
    engine: Engine,
    queue_id: str,
) -> dict[str, Any]:
    """Get queue status including counts and active reviewers.

    Returns a dict with queue statistics and per-reviewer info.
    """
    with engine.connect() as conn:
        # Get status counts
        counts = conn.execute(
            text(
                """
                SELECT
                    status,
                    COUNT(*) as cnt
                FROM review_tasks
                WHERE queue_id = :queue_id
                GROUP BY status
                """
            ),
            {"queue_id": queue_id},
        ).all()

        # Get active reviewers on this queue
        reviewers = conn.execute(
            text(
                """
                SELECT
                    rp.id,
                    rp.display_name,
                    rp.avatar_color,
                    rt.id as task_id,
                    rt.record_id
                FROM review_tasks rt
                JOIN reviewer_profiles rp ON rt.claimed_by = rp.id
                WHERE rt.queue_id = :queue_id
                  AND rt.status = 'claimed'
                """
            ),
            {"queue_id": queue_id},
        ).all()

    status_counts: dict[str, int] = {
        "available": 0,
        "claimed": 0,
        "submitted": 0,
        "skipped": 0,
    }
    for row in counts:
        status_counts[str(row[0])] = int(row[1])

    total = sum(status_counts.values())

    active_reviewers = []
    for row in reviewers:
        active_reviewers.append(
            {
                "reviewer_id": str(row[0]),
                "display_name": str(row[1]),
                "avatar_color": str(row[2]) if row[2] else None,
                "current_task_id": str(row[3]),
                "current_record_id": str(row[4]),
            }
        )

    return {
        "queue_id": queue_id,
        "total": total,
        "available": status_counts["available"],
        "claimed": status_counts["claimed"],
        "submitted": status_counts["submitted"],
        "skipped": status_counts["skipped"],
        "active_reviewers": active_reviewers,
    }

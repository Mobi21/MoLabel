"""Pre-label import as review events with trust levels (DT-010).

Imports existing labels from external sources and stores them as review
events with trust-level attribution. Pre-labels are append-only review
events with source=import.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from pydantic import BaseModel

from molabel.core.database import get_session
from molabel.core.types import ReviewEventSource, TrustLevel

logger = logging.getLogger(__name__)


class PreLabelEntry(BaseModel):
    """A single pre-label to import as a review event."""

    record_id: uuid.UUID
    labels: dict[str, Any]
    trust_level: TrustLevel = TrustLevel.external
    source_system: str = ""
    source_file: str = ""
    confidence: float | None = None
    unmapped_fields: dict[str, Any] | None = None


class PreLabelImportResult(BaseModel):
    """Result of a pre-label import operation."""

    events_created: int = 0
    events_skipped: int = 0
    errors: list[dict[str, Any]] = []


class PreLabelImporter:
    """Imports pre-labels as review events with trust levels.

    Pre-labels from external systems (Label Studio, Argilla, Prodigy,
    model predictions, etc.) are stored as review events with
    ``source=import`` and an assigned trust level.
    """

    def import_prelabels(
        self,
        engine: Any,
        *,
        workspace_id: uuid.UUID,
        task_schema_id: uuid.UUID,
        task_schema_version: int = 1,
        entries: list[PreLabelEntry],
        default_trust_level: TrustLevel = TrustLevel.external,
        skip_duplicates: bool = True,
    ) -> PreLabelImportResult:
        """Import a batch of pre-labels as review events.

        Parameters
        ----------
        engine:
            SQLAlchemy engine.
        workspace_id:
            Target workspace.
        task_schema_id:
            Task schema the labels conform to.
        task_schema_version:
            Schema version number.
        entries:
            Pre-label entries to import.
        default_trust_level:
            Fallback trust level if entry does not specify one.
        skip_duplicates:
            If True, skip entries where a review event with the same
            record_id, source_system, and source_file already exists.
        """
        from molabel.core.models.review_event import ReviewEvent

        result = PreLabelImportResult()

        with get_session(engine) as session:
            for entry in entries:
                trust = entry.trust_level or default_trust_level

                if skip_duplicates and entry.source_system:
                    from sqlmodel import select

                    existing = session.exec(
                        select(ReviewEvent).where(
                            ReviewEvent.record_id == entry.record_id,
                            ReviewEvent.source == ReviewEventSource.import_,
                            ReviewEvent.source_system == entry.source_system,
                        )
                    ).first()
                    if existing:
                        result.events_skipped += 1
                        continue

                try:
                    event = ReviewEvent(
                        workspace_id=workspace_id,
                        record_id=entry.record_id,
                        task_schema_id=task_schema_id,
                        task_schema_version=task_schema_version,
                        source=ReviewEventSource.import_,
                        source_system=entry.source_system,
                        source_file=entry.source_file,
                        trust_level=trust,
                        labels=entry.labels,
                        confidence=entry.confidence,
                        unmapped_fields=entry.unmapped_fields,
                    )
                    session.add(event)
                    result.events_created += 1
                except Exception as exc:
                    logger.warning(
                        "Failed to import pre-label for record %s: %s",
                        entry.record_id,
                        exc,
                    )
                    result.errors.append(
                        {
                            "record_id": str(entry.record_id),
                            "error": str(exc),
                        }
                    )

            session.commit()

        return result

    def import_from_records(
        self,
        engine: Any,
        *,
        workspace_id: uuid.UUID,
        task_schema_id: uuid.UUID,
        task_schema_version: int = 1,
        records: list[Any],
        label_key: str = "pre_labels",
        trust_level: TrustLevel = TrustLevel.external,
        source_system: str = "",
        source_file: str = "",
    ) -> PreLabelImportResult:
        """Import pre-labels directly from records that contain a label payload.

        Extracts labels from each record's payload using *label_key* and
        creates review events for them.
        """
        entries: list[PreLabelEntry] = []

        for record in records:
            payload = record.payload if hasattr(record, "payload") else {}
            if not payload:
                continue
            labels = payload.get(label_key, {})
            if not labels:
                continue

            # Get source metadata if available
            src_meta = (
                record.source_metadata if hasattr(record, "source_metadata") else {}
            ) or {}

            entries.append(
                PreLabelEntry(
                    record_id=record.id,
                    labels=labels,
                    trust_level=trust_level,
                    source_system=source_system or src_meta.get("source_system", ""),
                    source_file=source_file or src_meta.get("source_file", ""),
                )
            )

        return self.import_prelabels(
            engine,
            workspace_id=workspace_id,
            task_schema_id=task_schema_id,
            task_schema_version=task_schema_version,
            entries=entries,
            default_trust_level=trust_level,
        )

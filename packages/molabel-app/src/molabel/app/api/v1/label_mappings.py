"""Label mapping endpoints — /api/v1/label-mappings.

Preview and save label mappings for data import (API-017, API-018).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import text

from molabel.app.middleware.session import CurrentReviewer
from molabel.app.utils import get_engine

router = APIRouter(prefix="/label-mappings", tags=["label-mappings"])

# ---------------------------------------------------------------------------
# Response / request models
# ---------------------------------------------------------------------------


class FieldMapping(BaseModel):
    """Mapping of a single source field to a target field."""

    source_field: str
    target_field: str
    transform: str | None = None  # "direct" | "rename" | "cast" | "expression"
    expression: str | None = None


class ValueTransformation(BaseModel):
    """Transformation rule for label values."""

    source_value: str
    target_value: str
    field_name: str | None = None


class LabelMappingPreview(BaseModel):
    """Request body for previewing a label mapping."""

    source_system: str
    source_format: str | None = None
    task_schema_id: str
    field_mappings: list[FieldMapping]
    value_mappings: list[ValueTransformation] = []
    sample_records: list[dict[str, Any]] = []


class MappedRecordPreview(BaseModel):
    """A single record after applying the label mapping."""

    original: dict[str, Any]
    mapped: dict[str, Any]
    warnings: list[str] = []
    errors: list[str] = []


class LabelMappingPreviewResult(BaseModel):
    """Result of a label mapping preview."""

    mapped_records: list[MappedRecordPreview]
    total_records: int = 0
    successful: int = 0
    warnings_count: int = 0
    errors_count: int = 0
    unmapped_fields: list[str] = []


class LabelMappingSave(BaseModel):
    """Request body for saving a label mapping."""

    name: str
    mapping_slug: str | None = None
    workspace_id: str
    source_system: str
    source_format: str | None = None
    task_schema_id: str
    field_mappings: list[FieldMapping]
    value_mappings: list[ValueTransformation] = []
    type_conversions: dict[str, str] | None = None
    unmapped_field_policy: str = "preserve_reference"
    default_trust_level: str = "external"
    file_path: str | None = None


class SavedLabelMapping(BaseModel):
    """Response model for a saved label mapping."""

    mapping_id: str
    mapping_slug: str
    name: str
    workspace_id: str
    source_system: str
    source_format: str | None = None
    task_schema_id: str
    field_mappings: list[FieldMapping]
    value_mappings: list[ValueTransformation] = []
    type_conversions: dict[str, str] | None = None
    unmapped_field_policy: str
    default_trust_level: str
    file_path: str | None = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/preview", response_model=LabelMappingPreviewResult)
async def preview_label_mapping(
    body: LabelMappingPreview,
    _reviewer: CurrentReviewer,
) -> LabelMappingPreviewResult:
    """Preview a label mapping against sample records (API-017).

    Applies the proposed field and value mappings to the sample records
    and returns the transformed results with any warnings or errors.
    """
    mapped_records: list[MappedRecordPreview] = []
    total_warnings = 0
    total_errors = 0
    all_source_fields: set[str] = set()
    mapped_source_fields: set[str] = {fm.source_field for fm in body.field_mappings}

    # Build value mapping lookup: (field, source_value) -> target_value
    value_map: dict[tuple[str | None, str], str] = {}
    for vm in body.value_mappings:
        value_map[(vm.field_name, vm.source_value)] = vm.target_value

    for record in body.sample_records:
        all_source_fields.update(record.keys())
        mapped: dict[str, Any] = {}
        warnings: list[str] = []
        errors: list[str] = []

        for fm in body.field_mappings:
            if fm.source_field in record:
                val = record[fm.source_field]
                # Apply value mapping if present
                str_val = str(val) if val is not None else ""
                fallback = value_map.get((None, str_val), val)
                mapped_val = value_map.get((fm.target_field, str_val), fallback)
                mapped[fm.target_field] = mapped_val
            else:
                warnings.append(f"Source field '{fm.source_field}' not found in record")

        total_warnings += len(warnings)
        total_errors += len(errors)
        mapped_records.append(
            MappedRecordPreview(
                original=record,
                mapped=mapped,
                warnings=warnings,
                errors=errors,
            )
        )

    unmapped = sorted(all_source_fields - mapped_source_fields)
    successful = len([r for r in mapped_records if not r.errors])

    return LabelMappingPreviewResult(
        mapped_records=mapped_records,
        total_records=len(body.sample_records),
        successful=successful,
        warnings_count=total_warnings,
        errors_count=total_errors,
        unmapped_fields=unmapped,
    )


@router.post("", response_model=SavedLabelMapping, status_code=201)
async def save_label_mapping(
    request: Request,
    body: LabelMappingSave,
    _reviewer: CurrentReviewer,
) -> SavedLabelMapping:
    """Save a label mapping (API-018)."""
    engine = get_engine(request)
    mapping_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    slug = body.mapping_slug or body.name.lower().replace(" ", "-")

    field_mappings_json = json.dumps(
        [fm.model_dump(mode="json") for fm in body.field_mappings]
    )
    value_mappings_json = json.dumps(
        [vm.model_dump(mode="json") for vm in body.value_mappings]
    )
    type_conversions_json = (
        json.dumps(body.type_conversions) if body.type_conversions else None
    )

    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO label_mappings "
                "(id, mapping_slug, name, source_system, source_format, "
                "task_schema_id, field_mappings, value_mappings, "
                "type_conversions, unmapped_field_policy, default_trust_level, "
                "file_path, workspace_id, created_at, updated_at) "
                "VALUES (:id, :slug, :name, :source, :format, "
                ":task_schema_id, :field_mappings, :value_mappings, "
                ":type_conversions, :unmapped_policy, :trust_level, "
                ":file_path, :wid, :now, :now)"
            ),
            {
                "id": mapping_id,
                "slug": slug,
                "name": body.name,
                "source": body.source_system,
                "format": body.source_format,
                "task_schema_id": body.task_schema_id,
                "field_mappings": field_mappings_json,
                "value_mappings": value_mappings_json,
                "type_conversions": type_conversions_json,
                "unmapped_policy": body.unmapped_field_policy,
                "trust_level": body.default_trust_level,
                "file_path": body.file_path,
                "wid": body.workspace_id,
                "now": now,
            },
        )
        conn.commit()

    return SavedLabelMapping(
        mapping_id=mapping_id,
        mapping_slug=slug,
        name=body.name,
        workspace_id=body.workspace_id,
        source_system=body.source_system,
        source_format=body.source_format,
        task_schema_id=body.task_schema_id,
        field_mappings=body.field_mappings,
        value_mappings=body.value_mappings,
        type_conversions=body.type_conversions,
        unmapped_field_policy=body.unmapped_field_policy,
        default_trust_level=body.default_trust_level,
        file_path=body.file_path,
        created_at=datetime.fromisoformat(now),
        updated_at=datetime.fromisoformat(now),
    )

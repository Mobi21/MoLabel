"""Dataset endpoints — /api/v1/datasets.

CRUD for datasets, records, analytics, snapshots, and imports
(API-007 through API-018).
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

router = APIRouter(prefix="/datasets", tags=["datasets"])

# ---------------------------------------------------------------------------
# Response / request models
# ---------------------------------------------------------------------------


class SchemaField(BaseModel):
    """A field within the dataset schema."""

    name: str
    field_type: str
    nullable: bool = True
    description: str | None = None


class DatasetSummary(BaseModel):
    """Dataset list item."""

    dataset_id: str
    dataset_name: str
    dataset_slug: str
    workspace_id: str
    source_type: str
    record_kind: str | None = None
    record_count: int | None = None
    labeled_count: int | None = None
    health_status: str | None = None
    tags: list[str] | None = None
    last_indexed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class DatasetDetail(BaseModel):
    """Full dataset detail."""

    dataset_id: str
    dataset_name: str
    dataset_slug: str
    workspace_id: str
    description: str | None = None
    source_type: str
    source_config: dict[str, Any] | None = None
    loader_plugin: str | None = None
    record_kind: str | None = None
    canonical_id_strategy: str
    indexing_mode: str
    record_count: int | None = None
    labeled_count: int | None = None
    health_status: str | None = None
    schema_fields: list[SchemaField] = []
    tags: list[str] | None = None
    last_indexed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class DatasetCreate(BaseModel):
    """Request body for creating a dataset."""

    dataset_name: str
    workspace_id: str
    source_type: str
    description: str | None = None
    source_config: dict[str, Any] | None = None
    loader_plugin: str | None = None
    record_kind: str | None = None
    canonical_id_strategy: str = "external_id"
    indexing_mode: str = "full"
    tags: list[str] | None = None


class PreLabel(BaseModel):
    """Pre-existing label attached to a record."""

    field_name: str
    value: Any
    source: str | None = None
    confidence: float | None = None


class AgentOutputSummary(BaseModel):
    """Summary of an agent output for a record."""

    agent_output_id: str
    agent_run_id: str
    output_type: str
    labels: dict[str, Any]
    composite_confidence: float | None = None
    created_at: datetime | None = None


class ReviewEventSummary(BaseModel):
    """Summary of a review event for a record."""

    review_event_id: str
    reviewer_id: str
    source: str
    decision: str | None = None
    labels: dict[str, Any]
    created_at: datetime | None = None


class AdjudicationSummary(BaseModel):
    """Summary of an adjudication for a record."""

    adjudication_id: str
    resolution: str
    resolved_labels: dict[str, Any] | None = None
    created_at: datetime | None = None


class RecordExportStatus(BaseModel):
    """Export eligibility information for a record."""

    export_eligible: bool = False
    last_exported_at: datetime | None = None


class QualitySignal(BaseModel):
    """A quality signal or flag on a record."""

    signal_type: str
    value: float | None = None
    message: str | None = None


class LineageEntry(BaseModel):
    """A lineage entry tracking record history."""

    event_type: str
    event_id: str
    timestamp: datetime | None = None
    actor: str | None = None
    summary: str | None = None


class RecordSummary(BaseModel):
    """Record list item."""

    record_id: str
    external_id: str | None = None
    record_kind: str | None = None
    label_count: int | None = 0
    composite_confidence: float | None = None
    export_eligible: bool = False
    flags: list[str] | None = None
    created_at: datetime
    updated_at: datetime


class RecordDetail(BaseModel):
    """Full record detail with all associated data."""

    record_id: str
    dataset_id: str
    external_id: str | None = None
    sequence_index: int | None = None
    content_hash: str | None = None
    stable_fields: dict[str, Any]
    payload: dict[str, Any] | None = None
    record_kind: str | None = None
    source_metadata: dict[str, Any] | None = None
    label_count: int | None = 0
    latest_label: dict[str, Any] | None = None
    composite_confidence: float | None = None
    export_eligible: bool = False
    flags: list[str] | None = None
    pre_labels: list[PreLabel] = []
    agent_outputs: list[AgentOutputSummary] = []
    review_events: list[ReviewEventSummary] = []
    adjudications: list[AdjudicationSummary] = []
    export_status: RecordExportStatus | None = None
    quality_signals: list[QualitySignal] = []
    lineage: list[LineageEntry] = []
    created_at: datetime
    updated_at: datetime


class LabelDistribution(BaseModel):
    """Label distribution for analytics."""

    field_name: str
    values: dict[str, int]
    total: int


class DatasetQualityMetrics(BaseModel):
    """Quality metrics for a dataset."""

    agreement_rate: float | None = None
    average_confidence: float | None = None
    adjudication_rate: float | None = None
    export_eligible_rate: float | None = None


class ActivitySummary(BaseModel):
    """Activity summary for analytics."""

    period: str
    labels_added: int = 0
    records_reviewed: int = 0
    agent_runs_completed: int = 0


class DriftIndicator(BaseModel):
    """Drift detection indicator."""

    metric_name: str
    current_value: float | None = None
    baseline_value: float | None = None
    drift_score: float | None = None
    status: str = "stable"  # "stable" | "drifting" | "alert"


class DatasetAnalytics(BaseModel):
    """Analytics overview for a dataset."""

    dataset_id: str
    record_count: int = 0
    labeled_count: int = 0
    label_distributions: list[LabelDistribution] = []
    quality_metrics: DatasetQualityMetrics | None = None
    activity_summary: list[ActivitySummary] = []
    drift_indicators: list[DriftIndicator] = []


class Snapshot(BaseModel):
    """A point-in-time snapshot of a dataset."""

    snapshot_id: str
    dataset_id: str
    name: str
    description: str | None = None
    snapshot_type: str  # "full" | "delta"
    parent_snapshot_id: str | None = None
    record_count: int
    labeled_count: int
    quality_metrics: dict[str, Any] | None = None
    label_summary: dict[str, Any] | None = None
    created_at: datetime


class FieldDiff(BaseModel):
    """Diff for a single field between two snapshots."""

    field_name: str
    added: int = 0
    removed: int = 0
    changed: int = 0


class ValueTransition(BaseModel):
    """Transition of a label value between snapshots."""

    field_name: str
    from_value: str | None = None
    to_value: str | None = None
    count: int = 0


class SnapshotDiff(BaseModel):
    """Comparison between two snapshots."""

    base_snapshot_id: str
    compare_snapshot_id: str
    records_added: int = 0
    records_removed: int = 0
    labels_changed: int = 0
    field_diffs: list[FieldDiff] = []
    value_transitions: list[ValueTransition] = []


class ImportError_(BaseModel):
    """A single error encountered during import."""

    row_index: int | None = None
    field: str | None = None
    message: str
    severity: str = "error"


class ImportStatus(BaseModel):
    """Status of an asynchronous import operation."""

    job_id: str
    status: str
    dataset_id: str
    records_total: int | None = None
    records_imported: int | None = None
    records_skipped: int | None = None
    errors: list[ImportError_] = []
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ImportRequest(BaseModel):
    """Request body for importing data into a dataset."""

    source_uri: str | None = None
    mapping_id: str | None = None
    options: dict[str, Any] | None = None


class SnapshotCreate(BaseModel):
    """Request body for creating a snapshot."""

    name: str
    description: str | None = None
    snapshot_type: str = "full"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_summary(row: Any) -> DatasetSummary:
    """Convert a database row to a DatasetSummary."""
    return DatasetSummary(
        dataset_id=str(row[0]),
        dataset_name=str(row[1]),
        dataset_slug=str(row[2]),
        workspace_id=str(row[3]),
        source_type=str(row[4]),
        record_kind=str(row[5]) if row[5] else None,
        record_count=int(row[6]) if row[6] is not None else None,
        labeled_count=int(row[7]) if row[7] is not None else None,
        health_status=str(row[8]) if row[8] else None,
        tags=None,
        last_indexed_at=(
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


def _row_to_detail(row: Any) -> DatasetDetail:
    """Convert a database row to a DatasetDetail."""
    return DatasetDetail(
        dataset_id=str(row[0]),
        dataset_name=str(row[1]),
        dataset_slug=str(row[2]),
        workspace_id=str(row[3]),
        description=str(row[4]) if row[4] else None,
        source_type=str(row[5]),
        source_config=None,
        loader_plugin=str(row[6]) if row[6] else None,
        record_kind=str(row[7]) if row[7] else None,
        canonical_id_strategy=str(row[8]),
        indexing_mode=str(row[9]),
        record_count=int(row[10]) if row[10] is not None else None,
        labeled_count=int(row[11]) if row[11] is not None else None,
        health_status=str(row[12]) if row[12] else None,
        schema_fields=[],
        tags=None,
        last_indexed_at=(
            datetime.fromisoformat(str(row[13])) if row[13] else None
        ),
        created_at=(
            datetime.fromisoformat(str(row[14]))
            if row[14]
            else datetime.now(UTC)
        ),
        updated_at=(
            datetime.fromisoformat(str(row[15]))
            if row[15]
            else datetime.now(UTC)
        ),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedResponse[DatasetSummary])
async def list_datasets(
    request: Request,
    params: Annotated[QueryParams, Depends()],
) -> PaginatedResponse[DatasetSummary]:
    """List all datasets (API-007)."""
    engine = get_engine(request)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, dataset_name, dataset_slug, workspace_id, "
                "source_type, record_kind, record_count, labeled_count, "
                "health_status, last_indexed_at, created_at, updated_at "
                "FROM datasets "
                "ORDER BY created_at DESC "
                "LIMIT :limit"
            ),
            {"limit": params.limit},
        ).fetchall()

    items = [_row_to_summary(r) for r in rows]
    return PaginatedResponse(items=items, cursor=None, has_more=False)


@router.get("/{dataset_id}", response_model=DatasetDetail)
async def get_dataset(
    request: Request,
    dataset_id: uuid.UUID,
) -> DatasetDetail:
    """Get dataset detail (API-008)."""
    engine = get_engine(request)
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, dataset_name, dataset_slug, workspace_id, "
                "description, source_type, loader_plugin, record_kind, "
                "canonical_id_strategy, indexing_mode, record_count, "
                "labeled_count, health_status, last_indexed_at, "
                "created_at, updated_at "
                "FROM datasets WHERE id = :id"
            ),
            {"id": str(dataset_id)},
        ).first()

    if row is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    return _row_to_detail(row)


@router.post("", response_model=DatasetDetail, status_code=201)
async def create_dataset(
    request: Request,
    body: DatasetCreate,
    _reviewer: CurrentReviewer,
) -> DatasetDetail:
    """Create a new dataset (API-009)."""
    engine = get_engine(request)
    dataset_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    slug = body.dataset_name.lower().replace(" ", "-")

    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO datasets "
                "(id, dataset_name, dataset_slug, workspace_id, description, "
                "source_type, loader_plugin, record_kind, canonical_id_strategy, "
                "indexing_mode, created_at, updated_at) "
                "VALUES (:id, :name, :slug, :wid, :desc, :source, :loader, "
                ":kind, :cid_strategy, :idx_mode, :now, :now)"
            ),
            {
                "id": dataset_id,
                "name": body.dataset_name,
                "slug": slug,
                "wid": body.workspace_id,
                "desc": body.description,
                "source": body.source_type,
                "loader": body.loader_plugin,
                "kind": body.record_kind,
                "cid_strategy": body.canonical_id_strategy,
                "idx_mode": body.indexing_mode,
                "now": now,
            },
        )
        conn.commit()

        row = conn.execute(
            text(
                "SELECT id, dataset_name, dataset_slug, workspace_id, "
                "description, source_type, loader_plugin, record_kind, "
                "canonical_id_strategy, indexing_mode, record_count, "
                "labeled_count, health_status, last_indexed_at, "
                "created_at, updated_at "
                "FROM datasets WHERE id = :id"
            ),
            {"id": dataset_id},
        ).first()

    return _row_to_detail(row)


@router.post(
    "/{dataset_id}/import",
    response_model=ImportStatus,
    status_code=202,
)
async def import_dataset(
    request: Request,
    dataset_id: uuid.UUID,
    body: ImportRequest,
    _reviewer: CurrentReviewer,
) -> ImportStatus:
    """Import data into a dataset with optional mapping (API-010).

    Returns a 202 with a job ID for the async import operation.
    """
    engine = get_engine(request)
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id FROM datasets WHERE id = :id"),
            {"id": str(dataset_id)},
        ).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Dataset not found")

    job_id = str(uuid.uuid4())
    return ImportStatus(
        job_id=job_id,
        status="queued",
        dataset_id=str(dataset_id),
        records_total=None,
        records_imported=None,
        records_skipped=None,
        errors=[],
        started_at=datetime.now(UTC),
    )


@router.get(
    "/{dataset_id}/records",
    response_model=PaginatedResponse[RecordSummary],
)
async def list_records(
    request: Request,
    dataset_id: uuid.UUID,
    params: Annotated[QueryParams, Depends()],
) -> PaginatedResponse[RecordSummary]:
    """List records in a dataset (API-011)."""
    engine = get_engine(request)
    with engine.connect() as conn:
        # Verify dataset exists
        ds_row = conn.execute(
            text("SELECT id FROM datasets WHERE id = :id"),
            {"id": str(dataset_id)},
        ).first()
        if ds_row is None:
            raise HTTPException(status_code=404, detail="Dataset not found")

        rows = conn.execute(
            text(
                "SELECT id, external_id, record_kind, label_count, "
                "composite_confidence, export_eligible, flags, "
                "created_at, updated_at "
                "FROM records WHERE dataset_id = :did "
                "ORDER BY created_at DESC "
                "LIMIT :limit"
            ),
            {"did": str(dataset_id), "limit": params.limit},
        ).fetchall()

    items = [
        RecordSummary(
            record_id=str(r[0]),
            external_id=str(r[1]) if r[1] else None,
            record_kind=str(r[2]) if r[2] else None,
            label_count=int(r[3]) if r[3] is not None else 0,
            composite_confidence=float(r[4]) if r[4] is not None else None,
            export_eligible=bool(r[5]) if r[5] is not None else False,
            flags=None,
            created_at=(
                datetime.fromisoformat(str(r[7]))
                if r[7]
                else datetime.now(UTC)
            ),
            updated_at=(
                datetime.fromisoformat(str(r[8]))
                if r[8]
                else datetime.now(UTC)
            ),
        )
        for r in rows
    ]
    return PaginatedResponse(items=items, cursor=None, has_more=False)


@router.get(
    "/{dataset_id}/records/{record_id}",
    response_model=RecordDetail,
)
async def get_record(
    request: Request,
    dataset_id: uuid.UUID,
    record_id: uuid.UUID,
) -> RecordDetail:
    """Get full record detail (API-012)."""
    engine = get_engine(request)
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, dataset_id, external_id, sequence_index, "
                "content_hash, stable_fields, payload, record_kind, "
                "source_metadata, label_count, latest_label, "
                "composite_confidence, export_eligible, flags, "
                "created_at, updated_at "
                "FROM records "
                "WHERE id = :rid AND dataset_id = :did"
            ),
            {"rid": str(record_id), "did": str(dataset_id)},
        ).first()

    if row is None:
        raise HTTPException(status_code=404, detail="Record not found")

    import json

    def _parse_json(val: Any) -> Any:
        if val is None:
            return None
        if isinstance(val, (dict, list)):
            return val
        try:
            return json.loads(str(val))
        except (json.JSONDecodeError, TypeError):
            return {}

    return RecordDetail(
        record_id=str(row[0]),
        dataset_id=str(row[1]),
        external_id=str(row[2]) if row[2] else None,
        sequence_index=int(row[3]) if row[3] is not None else None,
        content_hash=str(row[4]) if row[4] else None,
        stable_fields=_parse_json(row[5]) or {},
        payload=_parse_json(row[6]),
        record_kind=str(row[7]) if row[7] else None,
        source_metadata=_parse_json(row[8]),
        label_count=int(row[9]) if row[9] is not None else 0,
        latest_label=_parse_json(row[10]),
        composite_confidence=float(row[11]) if row[11] is not None else None,
        export_eligible=bool(row[12]) if row[12] is not None else False,
        flags=None,
        pre_labels=[],
        agent_outputs=[],
        review_events=[],
        adjudications=[],
        export_status=None,
        quality_signals=[],
        lineage=[],
        created_at=(
            datetime.fromisoformat(str(row[14]))
            if row[14]
            else datetime.now(UTC)
        ),
        updated_at=(
            datetime.fromisoformat(str(row[15]))
            if row[15]
            else datetime.now(UTC)
        ),
    )


@router.get(
    "/{dataset_id}/analytics",
    response_model=DatasetAnalytics,
)
async def get_dataset_analytics(
    request: Request,
    dataset_id: uuid.UUID,
) -> DatasetAnalytics:
    """Get analytics for a dataset (API-013)."""
    engine = get_engine(request)
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, record_count, labeled_count "
                "FROM datasets WHERE id = :id"
            ),
            {"id": str(dataset_id)},
        ).first()

    if row is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    return DatasetAnalytics(
        dataset_id=str(dataset_id),
        record_count=int(row[1]) if row[1] is not None else 0,
        labeled_count=int(row[2]) if row[2] is not None else 0,
        label_distributions=[],
        quality_metrics=None,
        activity_summary=[],
        drift_indicators=[],
    )


@router.post(
    "/{dataset_id}/snapshots",
    response_model=Snapshot,
    status_code=201,
)
async def create_snapshot(
    request: Request,
    dataset_id: uuid.UUID,
    body: SnapshotCreate,
    _reviewer: CurrentReviewer,
) -> Snapshot:
    """Create a snapshot of a dataset (API-014)."""
    engine = get_engine(request)
    with engine.connect() as conn:
        ds_row = conn.execute(
            text(
                "SELECT id, record_count, labeled_count "
                "FROM datasets WHERE id = :id"
            ),
            {"id": str(dataset_id)},
        ).first()
        if ds_row is None:
            raise HTTPException(status_code=404, detail="Dataset not found")

        snapshot_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        record_count = int(ds_row[1]) if ds_row[1] is not None else 0
        labeled_count = int(ds_row[2]) if ds_row[2] is not None else 0

        # Pick a workspace_id from the dataset
        ws_row = conn.execute(
            text("SELECT workspace_id FROM datasets WHERE id = :id"),
            {"id": str(dataset_id)},
        ).first()
        workspace_id = str(ws_row[0]) if ws_row else str(uuid.uuid4())

        conn.execute(
            text(
                "INSERT INTO dataset_snapshots "
                "(id, dataset_id, workspace_id, name, description, "
                "snapshot_type, record_count, labeled_count, created_at) "
                "VALUES (:id, :did, :wid, :name, :desc, :stype, :rc, :lc, :now)"
            ),
            {
                "id": snapshot_id,
                "did": str(dataset_id),
                "wid": workspace_id,
                "name": body.name,
                "desc": body.description,
                "stype": body.snapshot_type,
                "rc": record_count,
                "lc": labeled_count,
                "now": now,
            },
        )
        conn.commit()

    return Snapshot(
        snapshot_id=snapshot_id,
        dataset_id=str(dataset_id),
        name=body.name,
        description=body.description,
        snapshot_type=body.snapshot_type,
        parent_snapshot_id=None,
        record_count=record_count,
        labeled_count=labeled_count,
        quality_metrics=None,
        label_summary=None,
        created_at=datetime.fromisoformat(now),
    )


@router.get(
    "/{dataset_id}/snapshots",
    response_model=PaginatedResponse[Snapshot],
)
async def list_snapshots(
    request: Request,
    dataset_id: uuid.UUID,
    params: Annotated[QueryParams, Depends()],
) -> PaginatedResponse[Snapshot]:
    """List snapshots for a dataset (API-015)."""
    engine = get_engine(request)
    with engine.connect() as conn:
        ds_row = conn.execute(
            text("SELECT id FROM datasets WHERE id = :id"),
            {"id": str(dataset_id)},
        ).first()
        if ds_row is None:
            raise HTTPException(status_code=404, detail="Dataset not found")

        rows = conn.execute(
            text(
                "SELECT id, dataset_id, name, description, snapshot_type, "
                "parent_snapshot_id, record_count, labeled_count, "
                "quality_metrics, label_summary, created_at "
                "FROM dataset_snapshots "
                "WHERE dataset_id = :did "
                "ORDER BY created_at DESC "
                "LIMIT :limit"
            ),
            {"did": str(dataset_id), "limit": params.limit},
        ).fetchall()

    items = [
        Snapshot(
            snapshot_id=str(r[0]),
            dataset_id=str(r[1]),
            name=str(r[2]),
            description=str(r[3]) if r[3] else None,
            snapshot_type=str(r[4]),
            parent_snapshot_id=str(r[5]) if r[5] else None,
            record_count=int(r[6]) if r[6] is not None else 0,
            labeled_count=int(r[7]) if r[7] is not None else 0,
            quality_metrics=None,
            label_summary=None,
            created_at=(
                datetime.fromisoformat(str(r[10]))
                if r[10]
                else datetime.now(UTC)
            ),
        )
        for r in rows
    ]
    return PaginatedResponse(items=items, cursor=None, has_more=False)


@router.get(
    "/{dataset_id}/snapshots/{snapshot_id}/diff",
    response_model=SnapshotDiff,
)
async def get_snapshot_diff(
    request: Request,
    dataset_id: uuid.UUID,
    snapshot_id: uuid.UUID,
    compare_to: str | None = None,
) -> SnapshotDiff:
    """Compare two snapshots (API-016).

    Compares the given snapshot to ``compare_to`` (or its parent if omitted).
    """
    engine = get_engine(request)
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, parent_snapshot_id FROM dataset_snapshots "
                "WHERE id = :sid AND dataset_id = :did"
            ),
            {"sid": str(snapshot_id), "did": str(dataset_id)},
        ).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Snapshot not found")

    base_id = compare_to or (str(row[1]) if row[1] else str(snapshot_id))

    return SnapshotDiff(
        base_snapshot_id=base_id,
        compare_snapshot_id=str(snapshot_id),
        records_added=0,
        records_removed=0,
        labels_changed=0,
        field_diffs=[],
        value_transitions=[],
    )

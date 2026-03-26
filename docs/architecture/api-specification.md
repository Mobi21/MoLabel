# MoLabel REST API Specification

Date: 2026-03-23
Status: Draft
Related: PRD Sections 16-18, ADR-001

This document defines the REST API contract between the React frontend and the FastAPI backend. All endpoints return Pydantic response models so the OpenAPI spec can be used for TypeScript client codegen. The auto-generated TypeScript client is consumed via TanStack Query on the frontend.

> **Note:** All enum values and field definitions in this document must match the canonical data model (`data-model.md`). If there is a discrepancy, `data-model.md` is authoritative.

---

## Conventions

### Base URL

```
/api/v1/
```

All endpoints below are relative to this base. Example: `GET /api/v1/workspaces`.

### Pagination

Cursor-based pagination for all list endpoints. The cursor is an opaque string token. Clients must not parse or construct cursors.

**Response envelope:**

```json
{
  "items": [...],
  "cursor": "abc123",
  "has_more": true
}
```

**Query params:** `?cursor=abc123&limit=50`

| Param    | Type   | Default | Max | Description                        |
|----------|--------|---------|-----|------------------------------------|
| `cursor` | string | null    | -   | Opaque cursor from previous page   |
| `limit`  | int    | 50      | 200 | Number of items per page           |

When `has_more` is `false`, `cursor` is `null`.

### Error Envelope

All error responses use a consistent envelope:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Human readable message",
    "details": { ... }
  }
}
```

**Error codes:**

| HTTP Status | Code                  | When                                                |
|-------------|-----------------------|-----------------------------------------------------|
| 400         | `BAD_REQUEST`         | Malformed request body or params                    |
| 404         | `NOT_FOUND`           | Resource does not exist                             |
| 409         | `CONFLICT`            | Resource state conflict (e.g., duplicate create)    |
| 422         | `VALIDATION_ERROR`    | Pydantic validation failure                         |
| 423         | `LOCKED`              | Resource locked by another operation                |
| 500         | `INTERNAL_ERROR`      | Unexpected server error                             |

Additional domain-specific codes:

| Code                      | When                                                     |
|---------------------------|----------------------------------------------------------|
| `QUEUE_EMPTY`             | No items available in review queue                       |
| `ALREADY_CLAIMED`         | Review item already claimed by another reviewer          |
| `PROVIDER_UNAVAILABLE`    | Model provider is offline or unreachable                 |
| `SCHEMA_VERSION_CONFLICT` | Task schema was modified while in use                    |
| `EXPORT_IN_PROGRESS`      | Export lock prevents concurrent export                   |
| `RUN_NOT_CANCELLABLE`     | Agent run already completed or failed                    |
| `SNAPSHOT_NOT_FOUND`      | Referenced snapshot does not exist                       |
| `PLUGIN_INCOMPATIBLE`     | Plugin version incompatible with current workspace       |

### Filtering

List endpoints support filtering via query params. Filters use exact match unless noted otherwise:

```
GET /api/v1/agent-runs?status=running&dataset_id=abc&model_profile_id=xyz
```

Date range filters use `_after` and `_before` suffixes:

```
GET /api/v1/audit?created_after=2026-03-01T00:00:00Z&created_before=2026-03-23T00:00:00Z
```

### Sorting

List endpoints support sorting via `sort_by` and `sort_dir` params:

```
GET /api/v1/datasets?sort_by=created_at&sort_dir=desc
```

`sort_dir` is `asc` or `desc` (default `desc`).

### Authentication

MoLabel uses lightweight reviewer profiles. No password auth, no tokens.

- Session established via `molabel_session` HTTP cookie (signed token containing `reviewer_id`)
- `POST /api/v1/session` creates or switches the active session
- All mutation endpoints record the active `reviewer_id` in audit logs
- If no session cookie is present, the server returns HTTP 401 with a redirect hint to the profile selection screen. The frontend handles the redirect.

### Common Response Types

These Pydantic models are referenced throughout the spec.

```python
class PaginatedResponse[T](BaseModel):
    items: list[T]
    cursor: str | None
    has_more: bool

class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None

class ErrorResponse(BaseModel):
    error: ErrorDetail

class TimestampMixin(BaseModel):
    created_at: datetime
    updated_at: datetime
```

---

## Resource Groups

### Workspaces

Workspaces are the top-level project container. A workspace maps to a local project folder with an optional `workbench.project.yaml` manifest.

---

#### `GET /workspaces`

List all known workspaces.

**Query params:** standard pagination

**Response:** `200 OK`

```python
class WorkspaceSummary(BaseModel):
    workspace_id: str
    workspace_name: str
    path: str
    core_version: str
    health: WorkspaceHealth  # "healthy" | "stale" | "error"
    dataset_count: int
    plugin_count: int
    last_indexed_at: datetime | None
    created_at: datetime
    updated_at: datetime

# Response body
PaginatedResponse[WorkspaceSummary]
```

---

#### `GET /workspaces/{workspace_id}`

Get workspace details including health diagnostics.

**Response:** `200 OK`

```python
class WorkspaceDetail(BaseModel):
    workspace_id: str
    workspace_name: str
    path: str
    core_version: str
    health: WorkspaceHealth
    health_checks: list[HealthCheck]
    enabled_plugins: list[str]
    dataset_count: int
    active_workflow_count: int
    pending_review_count: int
    active_agent_runs: int
    last_indexed_at: datetime | None
    manifest_path: str | None
    created_at: datetime
    updated_at: datetime

class HealthCheck(BaseModel):
    name: str                    # e.g., "database", "plugins", "providers"
    status: str                  # "ok" | "warning" | "error"
    message: str | None
    checked_at: datetime
```

---

#### `POST /workspaces`

Create or bootstrap a new workspace from a local folder.

**Request:**

```python
class WorkspaceCreate(BaseModel):
    path: str                           # absolute path to project folder
    workspace_name: str | None = None   # defaults to folder name
    template: str | None = None         # project template plugin id
    enabled_plugins: list[str] = []
```

**Response:** `201 Created` -> `WorkspaceDetail`

---

#### `POST /workspaces/{workspace_id}/reindex`

Trigger a full reindex of workspace files. Returns immediately; reindex runs in background. Monitor progress via SSE.

**Request:**

```python
class ReindexRequest(BaseModel):
    dataset_ids: list[str] | None = None   # null = all datasets
    force: bool = False                     # ignore cached state
```

**Response:** `202 Accepted`

```python
class ReindexStatus(BaseModel):
    job_id: str
    status: str    # "queued" | "running"
    started_at: datetime | None
```

---

### Datasets

Datasets are registered collections of records within a workspace. Records stay on disk; the database stores metadata and projections.

---

#### `GET /datasets`

List datasets in the current workspace.

**Query params:** standard pagination + filters

| Param          | Type   | Description                              |
|----------------|--------|------------------------------------------|
| `workspace_id` | string | Filter by workspace (required)           |
| `record_kind`  | string | Filter by record kind                    |
| `health`       | string | Filter by health status                  |

**Response:** `200 OK`

```python
class DatasetSummary(BaseModel):
    dataset_id: str
    workspace_id: str
    name: str
    source_paths: list[str]
    record_kind: str
    loader_plugin: str
    record_count: int
    labeled_count: int
    reviewed_count: int
    health: str               # "healthy" | "stale" | "error"
    last_indexed_at: datetime | None
    created_at: datetime
    updated_at: datetime

PaginatedResponse[DatasetSummary]
```

---

#### `GET /datasets/{dataset_id}`

Get dataset detail with statistics.

**Response:** `200 OK`

```python
class DatasetDetail(BaseModel):
    dataset_id: str
    workspace_id: str
    name: str
    description: str | None
    source_paths: list[str]
    record_kind: str
    loader_plugin: str
    canonical_id_strategy: str
    indexing_mode: str
    record_count: int
    labeled_count: int
    reviewed_count: int
    agent_labeled_count: int
    adjudicated_count: int
    exported_count: int
    health: str
    schema_fields: list[SchemaField]
    task_schema_ids: list[str]
    last_indexed_at: datetime | None
    created_at: datetime
    updated_at: datetime

class SchemaField(BaseModel):
    name: str
    type: str           # "string" | "int" | "float" | "bool" | "json" | "list" | "datetime"
    nullable: bool
    sample_values: list[Any] | None
```

---

#### `POST /datasets`

Register or import a new dataset.

**Request:**

```python
class DatasetCreate(BaseModel):
    workspace_id: str
    name: str
    description: str | None = None
    source_paths: list[str]
    loader_plugin: str
    record_kind: str
    canonical_id_strategy: str = "source_record_id"
    indexing_mode: str = "projection"         # "projection" | "full_copy"
```

**Response:** `201 Created` -> `DatasetDetail`

---

#### `POST /datasets/{dataset_id}/import`

Import data with label mapping. Used for pre-label import from external sources (Label Studio, Argilla, Prodigy, etc.).

**Request:**

```python
class DataImportRequest(BaseModel):
    source_path: str
    source_format: str                        # "label_studio" | "argilla" | "prodigy" | "csv" | "jsonl" | "parquet" | "huggingface"
    trust_level: str = "untrusted"            # "ground_truth" | "expert" | "external" | "untrusted"
    label_mapping: LabelMapping | None = None
    task_schema_id: str | None = None

class LabelMapping(BaseModel):
    field_mappings: list[FieldMapping]
    value_transformations: list[ValueTransformation] | None = None

class FieldMapping(BaseModel):
    source_field: str
    target_field: str

class ValueTransformation(BaseModel):
    field: str
    transform_type: str    # "float_to_ordinal" | "category_map" | "threshold" | "custom"
    params: dict[str, Any]
```

**Response:** `202 Accepted`

```python
class ImportStatus(BaseModel):
    job_id: str
    status: str
    records_processed: int
    records_total: int | None
    errors: list[ImportError]

class ImportError(BaseModel):
    line: int | None
    record_id: str | None
    message: str
```

---

#### `GET /datasets/{dataset_id}/records`

List records with pagination and filtering. Supports the data explorer table view.

**Query params:** standard pagination + filters

| Param              | Type   | Description                                |
|--------------------|--------|--------------------------------------------|
| `status`           | string | `unlabeled`, `agent_labeled`, `reviewed`, `adjudicated`, `exported` |
| `label_field`      | string | Filter by specific label field name        |
| `label_value`      | string | Filter by label value (requires label_field) |
| `reviewer_id`      | string | Filter by reviewer                         |
| `agent_run_id`     | string | Filter by agent run                        |
| `has_disagreement` | bool   | Filter to records with reviewer disagreement |
| `flagged`          | bool   | Filter to flagged records                  |
| `search`           | string | Full-text search across record content     |
| `sort_by`          | string | Field to sort by                           |
| `sort_dir`         | string | `asc` or `desc`                            |

**Response:** `200 OK`

```python
class RecordSummary(BaseModel):
    record_id: str
    dataset_id: str
    source_id: str             # original ID from source file
    status: str
    preview: dict[str, Any]    # first N fields for table display
    label_summary: dict[str, Any] | None   # current labels if any
    agent_label_count: int
    review_count: int
    has_disagreement: bool
    flagged: bool
    created_at: datetime
    updated_at: datetime

PaginatedResponse[RecordSummary]
```

---

#### `GET /datasets/{dataset_id}/records/{record_id}`

Full record detail (360-degree view). Returns source data, all agent outputs, all review events, adjudication status, export status, and full lineage.

**Response:** `200 OK`

```python
class RecordDetail(BaseModel):
    record_id: str
    dataset_id: str
    source_id: str
    status: str
    source_data: dict[str, Any]              # full source record payload
    pre_labels: list[PreLabel]               # imported labels
    agent_outputs: list[AgentOutputSummary]   # all agent outputs across runs
    review_events: list[ReviewEventSummary]   # all human reviews
    adjudication: AdjudicationSummary | None
    current_labels: dict[str, Any] | None    # resolved current label state
    export_status: RecordExportStatus | None
    quality_signals: list[QualitySignal]
    lineage: list[LineageEntry]              # full activity trail
    created_at: datetime
    updated_at: datetime

class PreLabel(BaseModel):
    source: str
    trust_level: str
    labels: dict[str, Any]
    imported_at: datetime

class AgentOutputSummary(BaseModel):
    agent_output_id: str
    agent_run_id: str
    agent_role: str
    model_profile_id: str
    model_identifier: str
    labels: dict[str, Any]
    confidence: float | None
    normalization_status: str
    review_visibility: str       # "hidden" | "revealed" | "not_applicable"
    created_at: datetime

class ReviewEventSummary(BaseModel):
    review_event_id: str
    reviewer_id: str
    reviewer_name: str
    task_schema_id: str
    task_schema_version: int
    decision: str                # "accept" | "accept_ai" | "edit_ai" | "reject_ai" | "correct" | "reject" | "skip"
    labels: dict[str, Any]
    rationale: str | None
    ai_was_revealed: bool
    is_draft: bool
    review_duration_ms: int | None
    created_at: datetime

class AdjudicationSummary(BaseModel):
    adjudication_id: str
    status: str                  # "pending" | "resolved" | "preserved_disagreement" | "excluded"
    resolution: dict[str, Any] | None
    resolved_by: str | None
    reasoning: str | None
    created_at: datetime
    resolved_at: datetime | None

class RecordExportStatus(BaseModel):
    included_in_exports: list[str]   # export bundle IDs
    last_exported_at: datetime | None

class QualitySignal(BaseModel):
    signal_type: str             # "low_confidence" | "high_disagreement" | "edge_case" | "flagged"
    value: float | None
    source: str                  # "agent" | "quality_check" | "reviewer" | "system"
    details: dict[str, Any] | None

class LineageEntry(BaseModel):
    event_type: str              # "imported" | "indexed" | "agent_labeled" | "reviewed" | "adjudicated" | "exported" | "flagged"
    actor: str                   # reviewer name, agent run ID, or "system"
    summary: str
    timestamp: datetime
    details: dict[str, Any] | None
```

---

#### `GET /datasets/{dataset_id}/analytics`

Dataset-level analytics: label distributions, quality metrics, activity summaries.

**Response:** `200 OK`

```python
class DatasetAnalytics(BaseModel):
    dataset_id: str
    record_count: int
    status_distribution: dict[str, int]       # status -> count
    label_distributions: list[LabelDistribution]
    quality_metrics: DatasetQualityMetrics
    activity_summary: ActivitySummary
    drift_indicators: list[DriftIndicator] | None

class LabelDistribution(BaseModel):
    field_name: str
    value_counts: dict[str, int]              # label value -> count
    agent_value_counts: dict[str, int] | None # agent label value -> count
    agreement_rate: float | None              # human-agent agreement on this field

class DatasetQualityMetrics(BaseModel):
    overall_agreement: float | None
    human_agent_agreement: float | None
    inter_annotator_agreement: float | None
    review_coverage: float                    # fraction of records reviewed
    adjudication_rate: float | None           # fraction requiring adjudication

class ActivitySummary(BaseModel):
    reviews_today: int
    reviews_this_week: int
    agent_runs_completed: int
    last_review_at: datetime | None
    last_agent_run_at: datetime | None
    active_reviewers: list[str]

class DriftIndicator(BaseModel):
    metric: str
    baseline_value: float
    current_value: float
    drift_magnitude: float
    detected_at: datetime
```

---

#### `POST /datasets/{dataset_id}/snapshots`

Create a named point-in-time snapshot of the dataset state.

**Request:**

```python
class SnapshotCreate(BaseModel):
    name: str
    description: str | None = None
```

**Response:** `201 Created`

```python
class Snapshot(BaseModel):
    snapshot_id: str
    dataset_id: str
    name: str
    description: str | None
    record_count: int
    labeled_count: int
    agent_run_ids: list[str]
    review_event_count: int
    quality_metrics: dict[str, float]
    file_path: str                     # path under workbench/snapshots/
    created_at: datetime
    created_by: str
```

---

#### `GET /datasets/{dataset_id}/snapshots`

List snapshots for a dataset.

**Response:** `200 OK` -> `PaginatedResponse[Snapshot]`

---

#### `GET /datasets/{dataset_id}/snapshots/{snapshot_id}/diff`

Compare two snapshots. The target snapshot is in the path; the baseline is a query param.

**Query params:**

| Param       | Type   | Description                         |
|-------------|--------|-------------------------------------|
| `baseline`  | string | Snapshot ID to compare against      |

**Response:** `200 OK`

```python
class SnapshotDiff(BaseModel):
    target_snapshot_id: str
    baseline_snapshot_id: str
    records_added: int
    records_removed: int
    labels_changed: int
    label_field_diffs: list[FieldDiff]
    new_agent_runs: list[str]
    new_review_events: int
    quality_metric_deltas: dict[str, float]

class FieldDiff(BaseModel):
    field_name: str
    changes: int
    value_transitions: list[ValueTransition]

class ValueTransition(BaseModel):
    from_value: Any
    to_value: Any
    count: int
```

---

### Label Mappings

Label mappings transform imported labels from external formats to the target task schema.

---

#### `POST /label-mappings/preview`

Preview a label mapping applied to a sample of records. Does not persist anything.

**Request:**

```python
class LabelMappingPreview(BaseModel):
    dataset_id: str
    source_path: str
    source_format: str
    label_mapping: LabelMapping
    task_schema_id: str
    sample_size: int = 10
```

**Response:** `200 OK`

```python
class LabelMappingPreviewResult(BaseModel):
    sample_records: list[MappedRecordPreview]
    unmapped_source_fields: list[str]
    mapping_warnings: list[str]
    success_rate: float                   # fraction that mapped without error

class MappedRecordPreview(BaseModel):
    record_id: str
    source_labels: dict[str, Any]
    mapped_labels: dict[str, Any]
    mapping_errors: list[str]
```

---

#### `POST /label-mappings`

Save a reusable label mapping configuration.

**Request:**

```python
class LabelMappingSave(BaseModel):
    name: str
    source_format: str
    task_schema_id: str
    label_mapping: LabelMapping
```

**Response:** `201 Created`

```python
class SavedLabelMapping(BaseModel):
    mapping_id: str
    name: str
    source_format: str
    task_schema_id: str
    label_mapping: LabelMapping
    created_at: datetime
    updated_at: datetime
```

---

### Workflows

Workflows are composable directed graphs of steps defined as YAML files. The visual workflow builder in the GUI generates and edits the YAML. The YAML is the source of truth.

---

#### `GET /workflows`

List workflow definitions.

**Query params:** standard pagination

| Param          | Type   | Description                              |
|----------------|--------|------------------------------------------|
| `workspace_id` | string | Filter by workspace (required)           |
| `is_template`  | bool   | Filter to built-in templates only        |

**Response:** `200 OK`

```python
class WorkflowSummary(BaseModel):
    workflow_id: str
    workspace_id: str
    name: str
    description: str | None
    is_template: bool
    step_count: int
    execution_count: int
    last_executed_at: datetime | None
    file_path: str                    # YAML file path
    created_at: datetime
    updated_at: datetime

PaginatedResponse[WorkflowSummary]
```

---

#### `GET /workflows/{workflow_id}`

Get full workflow definition including YAML content and step metadata.

**Response:** `200 OK`

```python
class WorkflowDetail(BaseModel):
    workflow_id: str
    workspace_id: str
    name: str
    description: str | None
    is_template: bool
    yaml_content: str                 # raw YAML source
    steps: list[WorkflowStep]
    edges: list[WorkflowEdge]
    execution_count: int
    last_executed_at: datetime | None
    file_path: str
    created_at: datetime
    updated_at: datetime

class WorkflowStep(BaseModel):
    step_id: str
    step_type: str                    # see PRD 15.0.2 for full list
    category: str                     # "data" | "agent" | "human" | "quality" | "output" | "control"
    label: str
    config: dict[str, Any]            # step-type-specific configuration
    pause_before: bool                # debugger-style breakpoint
    position: StepPosition | None     # x/y for visual builder

class StepPosition(BaseModel):
    x: float
    y: float

class WorkflowEdge(BaseModel):
    source_step_id: str
    target_step_id: str
    condition: str | None             # for conditional branches
    label: str | None
```

---

#### `POST /workflows`

Create a new workflow definition. Can be created from YAML content, from a template, or empty.

**Request:**

```python
class WorkflowCreate(BaseModel):
    workspace_id: str
    name: str
    description: str | None = None
    template_id: str | None = None       # clone from built-in template
    yaml_content: str | None = None      # direct YAML (mutually exclusive with template_id)
```

**Response:** `201 Created` -> `WorkflowDetail`

---

#### `PUT /workflows/{workflow_id}`

Update a workflow definition. Writes the updated YAML to disk.

**Request:**

```python
class WorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    yaml_content: str | None = None
    steps: list[WorkflowStep] | None = None
    edges: list[WorkflowEdge] | None = None
```

**Response:** `200 OK` -> `WorkflowDetail`

**Errors:** `423 LOCKED` if an execution is currently running.

---

#### `POST /workflows/{workflow_id}/execute`

Start a new workflow execution.

**Request:**

```python
class WorkflowExecuteRequest(BaseModel):
    dataset_id: str | None = None           # override default dataset
    model_profile_id: str | None = None     # override default model
    params: dict[str, Any] | None = None    # step-level parameter overrides
    pause_at_every_step: bool = False        # full manual mode
```

**Response:** `202 Accepted`

```python
class WorkflowExecution(BaseModel):
    execution_id: str
    workflow_id: str
    status: str              # "pending" | "running" | "paused" | "completed" | "failed" | "cancelled" (WorkflowExecutionStatus)
    current_step_id: str | None
    steps_completed: int
    steps_total: int
    started_at: datetime
    completed_at: datetime | None
    params: dict[str, Any]
```

---

#### `GET /workflows/{workflow_id}/executions`

List executions for a workflow.

**Query params:** standard pagination + `status` filter

**Response:** `200 OK` -> `PaginatedResponse[WorkflowExecution]`

---

#### `GET /workflows/{workflow_id}/executions/{execution_id}`

Get execution status with per-step state.

**Response:** `200 OK`

```python
class WorkflowExecutionDetail(BaseModel):
    execution_id: str
    workflow_id: str
    status: str              # "pending" | "running" | "paused" | "completed" | "failed" | "cancelled" (WorkflowExecutionStatus)
    current_step_id: str | None
    steps_completed: int
    steps_total: int
    step_states: list[StepState]
    started_at: datetime
    completed_at: datetime | None
    error: str | None
    params: dict[str, Any]

class StepState(BaseModel):
    step_id: str
    step_type: str
    label: str
    status: str              # "pending" | "ready" | "running" | "waiting_for_human" | "waiting_for_gate" | "waiting_for_breakpoint" | "completed" | "failed" | "skipped" | "retrying" | "partially_failed" | "interrupted" | "cancelled"
    started_at: datetime | None
    completed_at: datetime | None
    duration_seconds: float | None
    error: str | None
    loop_iteration: int | None           # for loop steps
    loop_metric_value: float | None      # for metric-based loop termination
    outputs: dict[str, Any] | None       # step-specific output summary
```

---

#### `POST /workflows/{workflow_id}/executions/{execution_id}/steps/{step_id}/advance`

Manually advance a paused step (gate approval, manual loop termination, breakpoint resume).

**Request:**

```python
class StepAdvanceRequest(BaseModel):
    action: str = "continue"     # "continue" | "skip" | "retry"
    params: dict[str, Any] | None = None
```

**Response:** `200 OK` -> `WorkflowExecutionDetail`

---

#### `POST /workflows/{workflow_id}/executions/{execution_id}/pause`

Pause a running execution at the next step boundary.

**Response:** `200 OK` -> `WorkflowExecutionDetail`

---

#### `POST /workflows/{workflow_id}/executions/{execution_id}/cancel`

Cancel a running or paused execution.

**Response:** `200 OK` -> `WorkflowExecutionDetail`

---

### Task Schemas

Task schemas define what labels or rubric fields apply to a dataset, how review and adjudication work, and which agent roles are supported. Schemas are versioned and immutable once used in completed reviews.

---

#### `GET /task-schemas`

List task schemas.

**Query params:** standard pagination + filters

| Param          | Type   | Description                 |
|----------------|--------|-----------------------------|
| `workspace_id` | string | Filter by workspace         |
| `task_type`    | string | Filter by task type plugin  |

**Response:** `200 OK`

```python
class TaskSchemaSummary(BaseModel):
    task_schema_id: str
    workspace_id: str
    task_type: str
    version: int
    title: str
    label_field_count: int
    review_count: int              # reviews using this schema
    is_locked: bool                # true if used in completed reviews
    created_at: datetime
    updated_at: datetime

PaginatedResponse[TaskSchemaSummary]
```

---

#### `GET /task-schemas/{task_schema_id}`

Get full task schema detail.

**Response:** `200 OK`

```python
class TaskSchemaDetail(BaseModel):
    task_schema_id: str
    workspace_id: str
    task_type: str
    version: int
    title: str
    instructions: str | None              # path to instructions doc or inline text
    record_selector: RecordSelector
    label_fields: list[LabelFieldDef]
    required_fields: list[str]
    optional_fields: list[OptionalFieldDef]
    blind_review_policy: str              # "hide_agent_outputs_by_default" | "show_agent_outputs" | "no_agent"
    overlap_policy: OverlapPolicy
    adjudication_policy: AdjudicationPolicy
    supported_agent_roles: list[str]
    default_model_profile: str | None
    export_mapping: ExportMapping | None
    is_locked: bool
    file_path: str                        # YAML file on disk
    created_at: datetime
    updated_at: datetime

class RecordSelector(BaseModel):
    dataset_id: str
    filters: dict[str, Any] | None = None

class LabelFieldDef(BaseModel):
    name: str
    type: str                             # "ordinal" | "categorical" | "text" | "bool" | "numeric" | "multi_select"
    scale: list[Any] | None = None        # for ordinal/categorical
    options: list[str] | None = None      # for multi_select
    description: str | None = None

class OptionalFieldDef(BaseModel):
    name: str
    type: str
    description: str | None = None

class OverlapPolicy(BaseModel):
    mode: str                             # "no_overlap" | "full_overlap" | "sampled_overlap"
    overlap_rate: float | None = None     # for sampled_overlap, e.g. 0.2

class AdjudicationPolicy(BaseModel):
    plugin: str | None = None
    auto_resolve_threshold: float | None = None   # agreement threshold for auto-resolve
    require_human: bool = True

class ExportMapping(BaseModel):
    serializer: str
    params: dict[str, Any] | None = None
```

---

#### `POST /task-schemas`

Create a new task schema.

**Request:**

```python
class TaskSchemaCreate(BaseModel):
    workspace_id: str
    task_type: str
    title: str
    instructions: str | None = None
    record_selector: RecordSelector
    label_fields: list[LabelFieldDef]
    required_fields: list[str] = []
    optional_fields: list[OptionalFieldDef] = []
    blind_review_policy: str = "hide_agent_outputs_by_default"
    overlap_policy: OverlapPolicy | None = None
    adjudication_policy: AdjudicationPolicy | None = None
    supported_agent_roles: list[str] = []
    default_model_profile: str | None = None
    export_mapping: ExportMapping | None = None
```

**Response:** `201 Created` -> `TaskSchemaDetail`

---

#### `PUT /task-schemas/{task_schema_id}`

Update a task schema. If the schema has been used in completed reviews, this creates a new version rather than mutating the existing one.

**Request:** Same fields as `TaskSchemaCreate` (all optional).

**Response:** `200 OK` -> `TaskSchemaDetail`

If a new version is created, the response includes the bumped `version` number and the previous version remains immutable.

---

### Providers & Models

Provider and model management. The system auto-detects available providers and supports named model profiles and runtime profiles.

---

#### `GET /providers`

List discovered providers with health status.

**Response:** `200 OK`

```python
class Provider(BaseModel):
    provider_id: str
    provider_type: str          # "openai_compatible" | "openrouter" | "ollama" | "anthropic" | "custom"
    name: str
    status: str                 # "online" | "offline" | "error" | "unknown"
    endpoint: str | None
    latency_ms: int | None      # last measured latency
    available_models: list[str]
    auth_configured: bool
    last_checked_at: datetime | None

# Response body
list[Provider]
```

---

#### `POST /providers/scan`

Trigger provider auto-detection scan. Checks Ollama at localhost:11434, environment variables for known API keys, and configured custom endpoints.

**Response:** `200 OK`

```python
class ProviderScanResult(BaseModel):
    providers_found: list[Provider]
    new_providers: list[str]          # provider_ids not previously known
    offline_providers: list[str]      # previously online, now offline
```

---

#### `GET /model-profiles`

List configured model profiles.

**Query params:** `workspace_id` (required), `provider_id` (optional filter)

**Response:** `200 OK`

```python
class ModelProfile(BaseModel):
    model_profile_id: str
    workspace_id: str
    provider: str
    model: str
    transport: str                # "openai_compatible" | "ollama_http" | "anthropic_sdk" | "custom"
    auth_ref: str | None          # e.g., "env:OPENROUTER_API_KEY" — never the raw key
    structured_output_support: bool
    tool_use_support: bool
    context_window: int | None
    capability_tags: list[str]
    status: str                   # "online" | "offline" | "untested"
    created_at: datetime
    updated_at: datetime

# Response body
list[ModelProfile]
```

---

#### `POST /model-profiles`

Create a new model profile.

**Request:**

```python
class ModelProfileCreate(BaseModel):
    workspace_id: str
    model_profile_id: str              # user-chosen identifier
    provider: str
    model: str
    transport: str
    auth_ref: str | None = None
    structured_output_support: bool = False
    tool_use_support: bool = False
    context_window: int | None = None
    capability_tags: list[str] = []
```

**Response:** `201 Created` -> `ModelProfile`

---

#### `PUT /model-profiles/{model_profile_id}`

Update a model profile.

**Request:** Same fields as `ModelProfileCreate` (all optional except `workspace_id`).

**Response:** `200 OK` -> `ModelProfile`

---

#### `POST /model-profiles/{model_profile_id}/test`

Test connectivity and basic functionality of a model profile.

**Response:** `200 OK`

```python
class ModelTestResult(BaseModel):
    model_profile_id: str
    success: bool
    latency_ms: int | None
    error: str | None
    structured_output_works: bool | None
    model_response_sample: str | None     # short response to a test prompt
    tested_at: datetime
```

---

#### `GET /runtime-profiles`

List runtime profiles. Runtime profiles control routing behavior (local-only, hosted, hybrid).

**Query params:** `workspace_id` (required)

**Response:** `200 OK`

```python
class RuntimeProfile(BaseModel):
    runtime_profile_id: str
    workspace_id: str
    mode: str                     # "offline_preferred" | "hosted_only" | "hybrid" | "local_only"
    fallback_model_profile_id: str | None
    created_at: datetime
    updated_at: datetime

# Response body
list[RuntimeProfile]
```

---

#### `POST /runtime-profiles`

Create a runtime profile.

**Request:**

```python
class RuntimeProfileCreate(BaseModel):
    workspace_id: str
    runtime_profile_id: str
    mode: str
    fallback_model_profile_id: str | None = None
```

**Response:** `201 Created` -> `RuntimeProfile`

---

### Agent Runs

Agent runs execute configured agent roles against datasets or subsets. Runs have an explicit lifecycle: `pending` -> `planned` -> `running` -> `completed` | `partially_completed` | `failed` | `cancelled`.

---

#### `GET /agent-runs`

List agent runs with filtering.

**Query params:** standard pagination + filters

| Param              | Type   | Description                     |
|--------------------|--------|---------------------------------|
| `workspace_id`     | string | Filter by workspace (required)  |
| `dataset_id`       | string | Filter by dataset               |
| `status`           | string | Filter by run status            |
| `agent_role`       | string | Filter by agent role            |
| `model_profile_id` | string | Filter by model profile         |
| `comparison_id`    | string | Filter by comparison group      |

**Response:** `200 OK`

```python
class AgentRunSummary(BaseModel):
    agent_run_id: str
    workspace_id: str
    dataset_id: str
    agent_role: str
    model_profile_id: str
    model_identifier: str
    runtime_profile_id: str | None
    prompt_version: str
    status: str
    records_targeted: int
    records_completed: int
    records_failed: int
    comparison_id: str | None       # set if part of a multi-model comparison
    cost_estimate: CostInfo | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

class CostInfo(BaseModel):
    estimated_cost_usd: float | None
    actual_cost_usd: float | None
    tokens_input: int | None
    tokens_output: int | None

PaginatedResponse[AgentRunSummary]
```

---

#### `GET /agent-runs/{agent_run_id}`

Get agent run detail with progress.

**Response:** `200 OK`

```python
class AgentRunDetail(BaseModel):
    agent_run_id: str
    workspace_id: str
    dataset_id: str
    agent_role: str
    plugin_adapter: str
    model_profile_id: str
    model_identifier: str
    runtime_profile_id: str | None
    prompt_version: str
    prompt_content_hash: str
    task_schema_id: str
    status: str
    records_targeted: int
    records_completed: int
    records_failed: int
    retry_count: int
    partial_failure_summary: str | None
    comparison_id: str | None
    cost: CostInfo | None
    execution_params: dict[str, Any]
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    error: str | None
```

---

#### `POST /agent-runs`

Start a new agent run.

**Request:**

```python
class AgentRunCreate(BaseModel):
    workspace_id: str
    dataset_id: str
    agent_role: str                         # "proposer" | "critic" | "normalizer" | "disagreement_flagger" | "deduper" | "rubric_judge" | "edge_case_miner" | "export_prep"
    task_schema_id: str
    model_profile_id: str
    runtime_profile_id: str | None = None
    prompt_version: str | None = None       # null = latest
    record_filter: dict[str, Any] | None = None   # subset targeting
    params: dict[str, Any] | None = None
```

**Response:** `202 Accepted` -> `AgentRunDetail`

---

#### `POST /agent-runs/compare`

Start a multi-model comparison run. Runs the same agent task across multiple models simultaneously.

**Request:**

```python
class ComparisonRunCreate(BaseModel):
    workspace_id: str
    dataset_id: str
    agent_role: str
    task_schema_id: str
    model_profile_ids: list[str]            # 2+ model profiles
    runtime_profile_id: str | None = None
    prompt_version: str | None = None
    record_filter: dict[str, Any] | None = None
    params: dict[str, Any] | None = None
```

**Response:** `202 Accepted`

```python
class ComparisonRun(BaseModel):
    comparison_id: str
    agent_run_ids: list[str]                # one per model profile
    status: str                             # overall status
    created_at: datetime
```

---

#### `POST /agent-runs/{agent_run_id}/cancel`

Cancel a running or pending agent run.

**Response:** `200 OK` -> `AgentRunDetail`

**Errors:** `409 RUN_NOT_CANCELLABLE` if already completed or failed.

---

#### `GET /agent-runs/{agent_run_id}/outputs`

List agent outputs for a run.

**Query params:** standard pagination + `normalization_status` filter

**Response:** `200 OK`

```python
class AgentOutput(BaseModel):
    agent_output_id: str
    agent_run_id: str
    record_id: str
    output_type: str
    labels: dict[str, Any]                  # structured payload
    confidence: float | None
    confidence_signals: ConfidenceSignals | None
    normalization_status: str               # "raw" | "normalized" | "validation_failed"
    review_visibility: str                  # "hidden" | "revealed" | "not_applicable"
    eligible_actions: list[str]             # ["accept_ai", "edit_ai", "reject_ai"]
    validation_errors: list[str]
    created_at: datetime

class ConfidenceSignals(BaseModel):
    self_reported: float | None             # agent-reported confidence
    self_consistency: float | None          # multi-run agreement
    logprobs: float | None                  # from provider logprobs
    composite: float | None                 # weighted combination

PaginatedResponse[AgentOutput]
```

---

#### `GET /agent-runs/{agent_run_id}/outputs/{record_id}`

Get agent output for a specific record in a run.

**Response:** `200 OK` -> `AgentOutput`

---

#### `GET /agent-runs/comparison/{comparison_id}`

Get comparison results with aggregate metrics and per-record diffs.

**Response:** `200 OK`

```python
class ComparisonResult(BaseModel):
    comparison_id: str
    runs: list[ComparisonRunEntry]
    aggregate: ComparisonAggregate
    per_record_sample: list[ComparisonRecordDiff]   # first N records with diffs
    total_records: int

class ComparisonRunEntry(BaseModel):
    agent_run_id: str
    model_profile_id: str
    model_identifier: str
    status: str
    records_completed: int
    cost: CostInfo | None

class ComparisonAggregate(BaseModel):
    agreement_matrix: dict[str, dict[str, float]]   # model_id -> model_id -> agreement rate
    label_distributions: dict[str, dict[str, dict[str, int]]]  # model_id -> field -> value -> count
    cost_comparison: dict[str, CostInfo]            # model_id -> cost
    latency_comparison: dict[str, float]            # model_id -> avg ms per record

class ComparisonRecordDiff(BaseModel):
    record_id: str
    outputs: dict[str, dict[str, Any]]              # model_id -> labels
    all_agree: bool
    disagreement_fields: list[str]
```

---

#### `GET /agent-runs/analytics`

Agent performance analytics dashboard data.

**Query params:**

| Param              | Type   | Description                   |
|--------------------|--------|-------------------------------|
| `workspace_id`     | string | Required                      |
| `dataset_id`       | string | Optional filter               |
| `model_profile_id` | string | Optional filter               |
| `agent_role`       | string | Optional filter               |

**Response:** `200 OK`

```python
class AgentAnalytics(BaseModel):
    accuracy_by_field: dict[str, float]
    accuracy_by_label_value: dict[str, dict[str, float]]   # field -> value -> accuracy
    accuracy_overall: float | None
    agreement_trend: list[TrendPoint]
    error_patterns: list[ErrorPattern]
    cost_per_correct_label: float | None
    cost_per_label: float | None
    throughput_per_minute: float | None
    confidence_calibration: list[CalibrationBucket]
    prompt_version_comparison: list[PromptVersionMetrics]

class TrendPoint(BaseModel):
    timestamp: datetime
    value: float
    prompt_version: str | None

class ErrorPattern(BaseModel):
    pattern_type: str
    description: str
    affected_records: int
    example_record_ids: list[str]

class CalibrationBucket(BaseModel):
    confidence_range: tuple[float, float]
    predicted_accuracy: float
    actual_accuracy: float
    record_count: int

class PromptVersionMetrics(BaseModel):
    prompt_version: str
    accuracy: float | None
    records_evaluated: int
    cost_per_label: float | None
    created_at: datetime
```

---

### Prompts

Agent prompts are versioned YAML files under `workbench/prompts/`. Each version is immutable once used in a completed agent run.

---

#### `GET /prompts`

List prompt templates.

**Query params:** standard pagination + filters

| Param          | Type   | Description                  |
|----------------|--------|------------------------------|
| `workspace_id` | string | Required                     |
| `agent_role`   | string | Filter by agent role         |
| `task_schema_id` | string | Filter by task schema      |

**Response:** `200 OK`

```python
class PromptSummary(BaseModel):
    prompt_id: str
    workspace_id: str
    name: str
    agent_role: str
    task_schema_id: str
    current_version: str             # semantic version, e.g. "v1", "v1.2"
    version_count: int
    last_used_at: datetime | None
    file_path: str
    created_at: datetime
    updated_at: datetime

PaginatedResponse[PromptSummary]
```

---

#### `GET /prompts/{prompt_id}`

Get prompt detail with version history.

**Response:** `200 OK`

```python
class PromptDetail(BaseModel):
    prompt_id: str
    workspace_id: str
    name: str
    agent_role: str
    task_schema_id: str
    current_version: str             # semantic version, e.g. "v1", "v1.2"
    versions: list[PromptVersion]
    file_path: str
    created_at: datetime
    updated_at: datetime

class PromptVersion(BaseModel):
    version: str                             # semantic version, e.g. "v1", "v1.2"
    system_instructions: str
    task_rubric: str | None
    few_shot_examples: list[FewShotExample]
    correction_batch_id: str | None         # if generated from corrections
    content_hash: str
    is_locked: bool                          # true if used in completed run
    agent_run_ids: list[str]                 # runs that used this version
    created_at: datetime

class FewShotExample(BaseModel):
    record_id: str | None
    input_text: str
    expected_output: dict[str, Any]
    source: str                              # "manual" | "correction" | "curated"
```

---

#### `POST /prompts`

Create a new prompt template.

**Request:**

```python
class PromptCreate(BaseModel):
    workspace_id: str
    name: str
    agent_role: str
    task_schema_id: str
    system_instructions: str
    task_rubric: str | None = None
    few_shot_examples: list[FewShotExample] = []
```

**Response:** `201 Created` -> `PromptDetail`

---

#### `PUT /prompts/{prompt_id}`

Create a new version of a prompt. The previous version remains immutable.

**Request:**

```python
class PromptUpdate(BaseModel):
    system_instructions: str | None = None
    task_rubric: str | None = None
    few_shot_examples: list[FewShotExample] | None = None
```

**Response:** `200 OK` -> `PromptDetail` (with incremented version)

---

#### `GET /prompts/{prompt_id}/diff`

Diff between two prompt versions.

**Query params:**

| Param   | Type | Description              |
|---------|------|--------------------------|
| `v1`    | string | First version identifier   |
| `v2`    | string | Second version identifier  |

**Response:** `200 OK`

```python
class PromptDiff(BaseModel):
    prompt_id: str
    version_1: str
    version_2: str
    system_instructions_diff: str | None     # unified diff format
    task_rubric_diff: str | None
    few_shot_added: list[FewShotExample]
    few_shot_removed: list[FewShotExample]
```

---

#### `GET /corrections`

List correction batches. Corrections accumulate as humans correct agent labels.

**Query params:** standard pagination + `workspace_id`, `task_schema_id`, `prompt_template_id`, `status` filters

**Response:** `200 OK`

```python
class CorrectionBatch(BaseModel):
    batch_id: str
    workspace_id: str
    task_schema_id: str
    prompt_template_id: str          # UUID — corrections grouped by the prompt being refined
    correction_count: int
    status: str                  # "accumulating" | "ready_for_analysis" | "analyzed" | "refinements_pending" | "applied" | "dismissed"
    threshold: int               # batch threshold (default 25)
    created_at: datetime
    updated_at: datetime

PaginatedResponse[CorrectionBatch]
```

---

#### `POST /corrections/analyze`

Trigger refinement analysis on a correction batch. Analyzes correction patterns and generates prompt refinement suggestions.

**Request:**

```python
class CorrectionAnalyzeRequest(BaseModel):
    batch_id: str
    model_profile_id: str | None = None   # model to use for analysis; null = workspace default
```

**Response:** `202 Accepted`

```python
class AnalysisStatus(BaseModel):
    batch_id: str
    status: str           # "analyzing" | "completed"
    job_id: str
```

---

#### `GET /corrections/{batch_id}/refinement`

Get the suggested prompt refinement generated from a correction batch.

**Response:** `200 OK`

```python
class RefinementSuggestion(BaseModel):
    batch_id: str
    prompt_id: str
    current_version: str
    suggested_changes: RefinementChanges
    correction_summary: CorrectionSummary
    estimated_impact: str | None        # "high" | "medium" | "low" based on pattern frequency

class RefinementChanges(BaseModel):
    instruction_patches: list[str]       # suggested instruction additions/changes
    new_few_shot_examples: list[FewShotExample]
    fields_with_most_corrections: list[FieldCorrectionSummary]

class CorrectionSummary(BaseModel):
    total_corrections: int
    corrections_by_field: dict[str, int]
    most_common_patterns: list[CorrectionPattern]

class FieldCorrectionSummary(BaseModel):
    field_name: str
    correction_count: int
    most_common_from: Any
    most_common_to: Any

class CorrectionPattern(BaseModel):
    pattern: str
    frequency: int
    example_record_ids: list[str]
```

---

### Review

The review system supports blind human review, AI reveal tracking, drafts, and multi-reviewer overlap. Review events are append-only.

---

#### `GET /review/queue`

Get the next available item for the current reviewer (identified by `molabel_session` cookie). The item is atomically claimed for this reviewer upon retrieval — no other reviewer can receive the same item.

**Query params:**

| Param            | Type   | Description                                |
|------------------|--------|--------------------------------------------|
| `queue_id`       | string | Required — which queue to pull from        |
| `priority`       | string | `default`, `low_confidence`, `disagreement` |

**Response:** `200 OK`

The claim-based model ensures exactly one item is returned and atomically assigned. Review task status values are: `available`, `claimed`, `submitted`, `skipped`. When a claim expires, the task status is set back to `available` (not to a separate `expired` state), and `claim_expired_count` is incremented to track how many times this happened.

```python
class ReviewQueueItem(BaseModel):
    review_task_id: str                       # unique task ID for this claim
    record_id: str
    record_data: dict[str, Any]              # source data to review
    task_schema: TaskSchemaDetail             # full schema for rendering the review form
    queue_position_info: QueuePositionInfo
    priority: int                            # higher = more urgent (default 0)
    priority_reason: str | None              # e.g., "active_learning_low_confidence", "calibration", "overlap"
    claimed_at: datetime
    claim_expires_at: datetime               # auto-release if not submitted

class QueuePositionInfo(BaseModel):
    queue_id: str
    position: int                            # 1-based position of this reviewer in the queue
    total_remaining: int                     # items still available in the queue
    reviewer_completed: int                  # items this reviewer has completed
    estimated_time_remaining: str | None     # e.g., "~12 min"

# Returns 204 No Content if queue is empty (with QUEUE_EMPTY error code)
```

---

#### `GET /review/queue/stats`

Queue statistics for the current workspace.

**Query params:** `task_schema_id` (optional filter)

**Response:** `200 OK`

```python
class QueueStats(BaseModel):
    task_schema_id: str | None
    total_pending: int
    total_completed: int
    total_in_progress: int                   # currently claimed
    by_reviewer: list[ReviewerQueueStats]
    avg_review_time_seconds: float | None
    estimated_completion: str | None

class ReviewerQueueStats(BaseModel):
    reviewer_id: str
    reviewer_name: str
    completed: int
    in_progress: int
    avg_time_seconds: float | None
    last_active_at: datetime | None
```

---

#### `POST /review/events`

Submit a review event. This is the primary review submission endpoint.

**Request:**

```python
class ReviewEventCreate(BaseModel):
    review_task_id: str
    record_id: str
    task_schema_id: str
    decision: str                            # "accept" | "accept_ai" | "edit_ai" | "reject_ai" | "correct" | "reject" | "skip" (ReviewDecision enum)
    labels: dict[str, Any]                   # field_name -> value
    rationale: str | None = None
    ai_was_revealed: bool = False            # whether the reviewer saw the AI suggestion before deciding
    review_duration_ms: int | None = None
```

**Response:** `201 Created`

```python
class ReviewEvent(BaseModel):
    review_event_id: str
    reviewer_id: str
    reviewer_name: str
    record_id: str
    dataset_id: str
    task_schema_id: str
    task_schema_version: int
    decision: str                            # "accept" | "accept_ai" | "edit_ai" | "reject_ai" | "correct" | "reject" | "skip"
    labels: dict[str, Any]
    rationale: str | None
    ai_was_revealed: bool
    is_draft: bool
    review_duration_ms: int | None
    created_at: datetime
```

---

#### `POST /review/events/draft`

Save a draft review. Drafts are mutable (overwritten on re-save) until submitted as final.

**Request:** Same as `ReviewEventCreate`.

**Response:** `200 OK` -> `ReviewEvent` (with `is_draft: true`)

---

#### `POST /review/events/{review_event_id}/reveal-ai`

Record that the reviewer revealed the AI suggestion for a record. This is tracked separately for analytics on blind review integrity.

**Request:**

```python
class AIRevealRequest(BaseModel):
    record_id: str
    agent_output_id: str
    reveal_timestamp: datetime
```

**Response:** `200 OK`

```python
class AIRevealEvent(BaseModel):
    review_event_id: str
    record_id: str
    agent_output_id: str
    agent_labels: dict[str, Any]            # the revealed AI labels
    revealed_at: datetime
```

---

#### `GET /review/events`

List review events with filtering. Used for review history views.

**Query params:** standard pagination + filters

| Param            | Type   | Description                       |
|------------------|--------|-----------------------------------|
| `record_id`      | string | Filter to specific record         |
| `reviewer_id`    | string | Filter by reviewer                |
| `task_schema_id` | string | Filter by task schema             |
| `is_draft`       | bool   | Filter drafts vs. final           |
| `dataset_id`     | string | Filter by dataset                 |

**Response:** `200 OK` -> `PaginatedResponse[ReviewEvent]`

---

### Adjudication

Adjudication resolves disagreements between reviewers or between human and agent labels.

---

#### `GET /adjudication/queue`

Get the disagreement queue.

**Query params:** standard pagination + filters

| Param            | Type   | Description                          |
|------------------|--------|--------------------------------------|
| `task_schema_id` | string | Filter by task schema                |
| `dataset_id`     | string | Filter by dataset                    |
| `severity`       | string | `low`, `medium`, `high`              |

**Response:** `200 OK`

```python
class AdjudicationQueueItem(BaseModel):
    adjudication_id: str
    record_id: str
    dataset_id: str
    task_schema_id: str
    status: str                          # "pending" | "in_progress"
    disagreement_type: str               # "human_human" | "human_agent" | "multi_reviewer"
    disagreement_severity: str           # "low" | "medium" | "high"
    disagreeing_fields: list[str]
    reviewer_count: int
    agent_output_count: int
    created_at: datetime

PaginatedResponse[AdjudicationQueueItem]
```

---

#### `GET /adjudication/{adjudication_id}`

Get full adjudication detail with all reviewer labels, agent labels, and context.

**Response:** `200 OK`

```python
class AdjudicationDetail(BaseModel):
    adjudication_id: str
    record_id: str
    dataset_id: str
    task_schema_id: str
    status: str
    record_data: dict[str, Any]                    # source data
    reviewer_labels: list[ReviewerLabelSet]
    agent_labels: list[AgentLabelSet]
    disagreeing_fields: list[FieldDisagreement]
    policy_excerpt: str | None                      # relevant adjudication policy text
    history: list[AdjudicationHistoryEntry]
    created_at: datetime
    resolved_at: datetime | None

class ReviewerLabelSet(BaseModel):
    reviewer_id: str
    reviewer_name: str
    review_event_id: str
    decision: str                # "accept" | "accept_ai" | "edit_ai" | "reject_ai" | "correct" | "reject" | "skip"
    labels: dict[str, Any]
    rationale: str | None
    ai_was_revealed: bool
    created_at: datetime

class AgentLabelSet(BaseModel):
    agent_run_id: str
    agent_role: str
    model_profile_id: str
    model_identifier: str
    labels: dict[str, Any]
    confidence: float | None
    created_at: datetime

class FieldDisagreement(BaseModel):
    field_name: str
    values: dict[str, Any]               # source -> value (e.g., "reviewer_1": 3, "reviewer_2": 4, "agent": 3)
    spread: float | None                 # numeric distance for ordinal fields

class AdjudicationHistoryEntry(BaseModel):
    action: str
    actor: str
    details: dict[str, Any] | None
    timestamp: datetime
```

---

#### `POST /adjudication/{adjudication_id}/resolve`

Submit an adjudication resolution.

**Request:**

```python
class AdjudicationResolve(BaseModel):
    resolution_type: str                    # "resolve" | "preserve_disagreement" | "downgrade" | "exclude"
    resolved_labels: dict[str, Any] | None  # required for "resolve"
    reasoning: str
    tier: str | None = None                 # for downgrade decisions
```

**Response:** `200 OK`

```python
class AdjudicationResult(BaseModel):
    adjudication_id: str
    record_id: str
    resolution_type: str
    resolved_labels: dict[str, Any] | None
    reasoning: str
    resolved_by: str
    tier: str | None
    resolved_at: datetime
```

---

### Quality

Quality metrics, agreement analysis, and drift detection.

---

#### `GET /quality/dashboard`

Workspace-level quality metrics dashboard.

**Query params:** `workspace_id` (required), `dataset_id` (optional), `task_schema_id` (optional)

**Response:** `200 OK`

```python
class QualityDashboard(BaseModel):
    workspace_id: str
    overall_agreement: float | None
    human_agent_agreement: float | None
    inter_annotator_agreement: float | None
    review_coverage: float
    adjudication_rate: float | None
    readiness_gates: list[ReadinessGate]
    recent_quality_trend: list[QualityTrendPoint]

class ReadinessGate(BaseModel):
    gate_id: str
    name: str
    status: str                  # "passing" | "failing" | "not_evaluated"
    required_value: float | None
    current_value: float | None
    last_evaluated_at: datetime | None

class QualityTrendPoint(BaseModel):
    date: str                    # ISO date
    agreement: float | None
    review_count: int
    adjudication_count: int
```

---

#### `GET /quality/agreement`

Detailed agreement metrics.

**Query params:** `workspace_id` (required), `dataset_id` (optional), `task_schema_id` (optional)

**Response:** `200 OK`

```python
class AgreementMetrics(BaseModel):
    overall: AgreementDetail
    per_field: dict[str, AgreementDetail]
    per_reviewer: dict[str, ReviewerAgreement]
    per_label_value: dict[str, dict[str, float]]   # field -> value -> agreement rate
    confusion_matrices: dict[str, list[list[int]]]  # field -> matrix

class AgreementDetail(BaseModel):
    cohens_kappa: float | None
    percent_agreement: float | None
    krippendorffs_alpha: float | None
    sample_size: int

class ReviewerAgreement(BaseModel):
    reviewer_id: str
    reviewer_name: str
    agreement_with_consensus: float | None
    agreement_with_agent: float | None
    records_reviewed: int
    avg_review_time: float | None
```

---

#### `GET /quality/drift`

Drift detection results.

**Query params:** `workspace_id` (required), `dataset_id` (optional)

**Response:** `200 OK`

```python
class DriftReport(BaseModel):
    dataset_id: str | None
    indicators: list[DriftIndicator]
    last_analyzed_at: datetime | None
    baseline_snapshot_id: str | None
```

---

### Exports

Export packaging, validation, and delivery. Supports JSONL, Parquet, CSV, and HuggingFace Hub push.

---

#### `GET /exports`

List export bundles.

**Query params:** standard pagination + filters

| Param          | Type   | Description                |
|----------------|--------|----------------------------|
| `workspace_id` | string | Required                   |
| `dataset_id`   | string | Filter by source dataset   |
| `status`       | string | `pending`, `validating`, `validated`, `packaging`, `completed`, `failed` |

**Response:** `200 OK`

```python
class ExportSummary(BaseModel):
    export_id: str
    workspace_id: str
    dataset_id: str
    name: str
    format: str                    # "jsonl" | "parquet" | "csv" | "huggingface_hub" | "plugin_custom"
    status: str                    # "pending" | "validating" | "validated" | "packaging" | "completed" | "failed"
    record_count: int
    file_path: str | None
    file_size_bytes: int | None
    created_at: datetime
    completed_at: datetime | None

PaginatedResponse[ExportSummary]
```

---

#### `POST /exports`

Create an export bundle. Runs asynchronously.

**Request:**

```python
class ExportCreate(BaseModel):
    workspace_id: str
    dataset_id: str
    name: str
    format: str                              # "jsonl" | "parquet" | "csv" | "huggingface_hub" | "plugin_custom"
    packager_plugin: str | None = None       # for plugin_custom formats
    include: ExportInclusion
    filters: ExportFilters | None = None
    output_path: str | None = None           # null = default workbench/exports/ path

class ExportInclusion(BaseModel):
    record_data: bool = True
    human_labels: bool = True
    agent_labels: bool = False
    review_metadata: bool = False
    adjudication_history: bool = False
    record_ids: bool = True
    provenance: bool = False

class ExportFilters(BaseModel):
    status: list[str] | None = None
    min_agreement: float | None = None
    exclude_flagged: bool = False
    snapshot_id: str | None = None           # export based on snapshot state
    record_ids: list[str] | None = None      # explicit record subset
```

**Response:** `202 Accepted` -> `ExportDetail`

---

#### `POST /exports/preview`

Preview an export on a sample of records. Does not persist.

**Request:** Same as `ExportCreate` + `sample_size: int = 10`.

**Response:** `200 OK`

```python
class ExportPreview(BaseModel):
    sample_records: list[dict[str, Any]]
    total_matching: int
    estimated_file_size_bytes: int | None
    warnings: list[str]
```

---

#### `GET /exports/{export_id}`

Get export detail with validation status.

**Response:** `200 OK`

```python
class ExportDetail(BaseModel):
    export_id: str
    workspace_id: str
    dataset_id: str
    name: str
    format: str                    # "jsonl" | "parquet" | "csv" | "huggingface_hub" | "plugin_custom"
    status: str                    # "pending" | "validating" | "validated" | "packaging" | "completed" | "failed"
    record_count: int
    include: ExportInclusion
    filters: ExportFilters | None
    file_path: str | None
    file_size_bytes: int | None
    validation_status: str | None         # "pending" | "passed" | "failed" | "not_validated"
    validation_errors: list[str]
    output_hash: str | None               # SHA-256 of output file
    created_at: datetime
    completed_at: datetime | None
    error: str | None
```

---

#### `POST /exports/{export_id}/validate`

Run validation checks on an export bundle.

**Response:** `200 OK`

```python
class ExportValidation(BaseModel):
    export_id: str
    status: str                           # "passed" | "failed"
    checks: list[ValidationCheck]
    validated_at: datetime

class ValidationCheck(BaseModel):
    check_name: str
    status: str                           # "passed" | "failed" | "warning"
    message: str
    details: dict[str, Any] | None
```

---

#### `POST /exports/{export_id}/download`

Download the export file. Returns the file as an attachment.

**Response:** `200 OK` with `Content-Disposition: attachment; filename="..."` and appropriate content type.

---

#### `POST /exports/{export_id}/push-hf`

Push an export bundle to HuggingFace Hub.

**Request:**

```python
class HFPushRequest(BaseModel):
    repo_id: str                          # e.g., "username/dataset-name"
    split: str = "train"
    private: bool = True
    commit_message: str | None = None
```

**Response:** `202 Accepted`

```python
class HFPushStatus(BaseModel):
    export_id: str
    repo_id: str
    status: str                           # "pushing" | "completed" | "failed"
    url: str | None                       # HuggingFace dataset URL when completed
    error: str | None
```

---

### Releases

Releases represent gated dataset deliverables with validation reports and human signoff.

---

#### `GET /releases`

List releases.

**Query params:** standard pagination + `workspace_id` (required), `status` filter

**Response:** `200 OK`

```python
class ReleaseSummary(BaseModel):
    release_id: str
    workspace_id: str
    name: str
    version: str
    status: str                          # "draft" | "validating" | "pending_approval" | "approved" | "released" | "rejected" | "revoked"
    export_ids: list[str]
    validation_status: str | None
    approved_by: str | None
    created_at: datetime
    approved_at: datetime | None

PaginatedResponse[ReleaseSummary]
```

---

#### `POST /releases`

Create a release.

**Request:**

```python
class ReleaseCreate(BaseModel):
    workspace_id: str
    name: str
    version: str
    export_ids: list[str]                 # export bundles included
    validation_gate_ids: list[str] | None = None   # specific gates to run; null = all configured
    notes: str | None = None
```

**Response:** `201 Created` -> `ReleaseDetail`

---

#### `GET /releases/{release_id}`

Get release detail with validation report.

**Response:** `200 OK`

```python
class ReleaseDetail(BaseModel):
    release_id: str
    workspace_id: str
    name: str
    version: str
    status: str
    export_ids: list[str]
    exports: list[ExportSummary]
    validation_report: ValidationReport | None
    notes: str | None
    approved_by: str | None
    approved_at: datetime | None
    created_at: datetime

class ValidationReport(BaseModel):
    status: str                           # "passed" | "failed"
    gates: list[GateResult]
    generated_at: datetime

class GateResult(BaseModel):
    gate_id: str
    gate_name: str
    plugin: str
    status: str                           # "passed" | "failed" | "warning"
    required_value: float | None
    actual_value: float | None
    message: str
    details: dict[str, Any] | None
```

---

#### `POST /releases/{release_id}/approve`

Human signoff on a release. Requires all validation gates to pass.

**Request:**

```python
class ReleaseApproval(BaseModel):
    approved: bool
    notes: str | None = None
```

**Response:** `200 OK` -> `ReleaseDetail`

**Errors:** `409 CONFLICT` if validation gates have not passed.

---

### Plugins

Plugin discovery, management, and lifecycle.

---

#### `GET /plugins`

List installed plugins.

**Query params:** `workspace_id` (required)

**Response:** `200 OK`

```python
class PluginSummary(BaseModel):
    plugin_id: str
    version: str
    plugin_type: str                    # "data_loader" | "task_type" | "model_provider" | "record_renderer" | "review_workflow" | "adjudication" | "agent_adapter" | "validation" | "export_packager" | "reference_app"
    name: str
    enabled: bool
    compatible: bool
    compatible_core: str
    required_by_project: bool
    created_at: datetime

# Response body
list[PluginSummary]
```

---

#### `GET /plugins/{plugin_id}`

Get plugin detail with compatibility information.

**Response:** `200 OK`

```python
class PluginDetail(BaseModel):
    plugin_id: str
    version: str
    plugin_type: str
    name: str
    description: str | None
    enabled: bool
    compatible: bool
    compatible_core: str
    required_by_project: bool
    entrypoint: str
    supports: PluginSupports
    compatibility_errors: list[str]
    created_at: datetime

class PluginSupports(BaseModel):
    record_kinds: list[str]
    task_types: list[str]
    export_formats: list[str]
    validation_gates: list[str]
```

---

#### `POST /plugins/{plugin_id}/enable`

Enable a plugin for the current workspace.

**Response:** `200 OK` -> `PluginDetail`

**Errors:** `409 PLUGIN_INCOMPATIBLE` if version check fails.

---

#### `POST /plugins/{plugin_id}/disable`

Disable a plugin. Warns if the plugin is required by active task schemas or datasets.

**Response:** `200 OK` -> `PluginDetail`

**Errors:** `409 CONFLICT` if plugin is required by active project configuration.

---

### Assistant

Supportive AI assistant powered by the user's own configured model providers.

---

#### `POST /assistant/query`

Send a question or request to the AI assistant. The server assembles focused context (workflow state, queue stats, agent runs, validation results) and passes it to the user's chosen model.

**Request:**

```python
class AssistantQuery(BaseModel):
    query: str                                    # the user's question
    screen: str                                   # current screen name (e.g., "review", "mission_control", "data_explorer")
    record_id: str | None = None                  # if asking about a specific record
    model_profile_id: str | None = None           # null = workspace default
```

**Response:** `200 OK` (streamed via SSE within the POST response body using `text/event-stream` content type)

```python
class AssistantResponse(BaseModel):
    response: str
    context_used: list[ContextReference]
    suggested_actions: list[SuggestedAction]
    model_profile_id: str
    tokens_used: int | None

class ContextReference(BaseModel):
    type: str                                 # "workflow_state" | "queue_stats" | "agent_run" | "record" | "validation"
    id: str | None
    summary: str

class SuggestedAction(BaseModel):
    action_type: str                          # "navigate" | "api_call" | "explanation"
    label: str
    target: str | None                        # URL path or endpoint
    params: dict[str, Any] | None
```

---

#### `GET /assistant/context`

Get the current context summary the assistant would use. Useful for debugging and transparency.

**Response:** `200 OK`

```python
class AssistantContext(BaseModel):
    workspace_summary: dict[str, Any]
    active_workflow: dict[str, Any] | None
    queue_stats: dict[str, Any] | None
    recent_agent_runs: list[dict[str, Any]]
    recent_validation_results: list[dict[str, Any]]
    context_token_count: int
```

---

### Audit

Append-only audit log for all significant operations.

---

#### `GET /audit`

List audit events with filtering and pagination.

**Query params:** standard pagination + filters

| Param            | Type     | Description                              |
|------------------|----------|------------------------------------------|
| `workspace_id`   | string   | Required                                 |
| `event_type`     | string   | Filter by type                           |
| `actor`          | string   | Filter by actor (reviewer ID or "system")|
| `object_type`    | string   | Filter by affected object type           |
| `object_id`      | string   | Filter by affected object ID             |
| `created_after`  | datetime | Date range filter                        |
| `created_before` | datetime | Date range filter                        |

**Response:** `200 OK`

```python
class AuditEvent(BaseModel):
    audit_id: str
    workspace_id: str
    event_type: str           # "workspace_created" | "dataset_imported" | "dataset_reindexed" | "workflow_created" | "workflow_started" | "workflow_completed" | "task_schema_created" | "task_schema_updated" | "agent_run_started" | "agent_run_completed" | "agent_run_failed" | "review_submitted" | "review_draft_saved" | "ai_revealed" | "adjudication_resolved" | "export_created" | "export_validated" | "release_created" | "release_approved" | "release_rejected" | "snapshot_created" | "snapshot_restored" | "plugin_enabled" | "plugin_disabled" | "config_changed" | "file_written" | "reindex_triggered" | "prompt_created" | "prompt_refined" | "correction_analyzed" | "provider_detected"
    actor: str                # reviewer_id or "system"
    actor_name: str | None
    object_type: str          # "record" | "dataset" | "agent_run" | "export" | "release" | "task_schema" | etc.
    object_id: str
    summary: str              # human-readable summary
    details: dict[str, Any] | None
    created_at: datetime

PaginatedResponse[AuditEvent]
```

---

#### `GET /audit/{audit_id}`

Get a single audit event with full details.

**Response:** `200 OK` -> `AuditEvent`

---

### Session / Reviewer

Lightweight reviewer profile management and session control. No password auth.

---

#### `GET /session`

Get current session info based on the session cookie.

**Response:** `200 OK`

```python
class Session(BaseModel):
    reviewer_id: str
    reviewer_name: str
    workspace_id: str | None
    active_claims: list[ActiveClaim]      # currently claimed review items
    created_at: datetime

class ActiveClaim(BaseModel):
    review_task_id: str
    record_id: str
    task_schema_id: str
    claimed_at: datetime
    expires_at: datetime
```

---

#### `POST /session`

Create or switch the active reviewer session. Sets the session cookie.

**Request:**

```python
class SessionCreate(BaseModel):
    reviewer_id: str
    workspace_id: str | None = None   # workspace_id sets the active workspace for this session, not the reviewer's profile scope. Reviewer profiles are global.
```

**Response:** `200 OK` -> `Session`

Sets `Set-Cookie` header with `molabel_session` (signed token containing `reviewer_id`).

---

#### `GET /reviewers`

List reviewer profiles. Profiles are global (not workspace-scoped).

**Query params:** standard pagination

**Response:** `200 OK`

```python
class ReviewerProfile(BaseModel):
    id: UUID                           # server-generated, NOT user-chosen
    display_name: str
    avatar_color: str | None
    is_operator: bool
    is_active: bool
    created_at: datetime
    last_active_at: datetime | None
    preferences: dict[str, Any] | None

# Response body
list[ReviewerProfile]
```

---

#### `POST /reviewers`

Create a reviewer profile.

**Request:**

```python
class ReviewerCreate(BaseModel):
    display_name: str
    avatar_color: str | None = None   # hex color; server auto-assigns if null
```

**Response:** `201 Created` -> `ReviewerProfile`

---

### Cost

Cost tracking across projects, models, and time periods.

---

#### `GET /costs`

Get cost summary.

**Query params:**

| Param              | Type     | Description                    |
|--------------------|----------|--------------------------------|
| `workspace_id`     | string   | Required                       |
| `model_profile_id` | string   | Filter by model                |
| `agent_role`       | string   | Filter by role                 |
| `period`           | string   | `day`, `week`, `month`, `all`  |
| `created_after`    | datetime | Date range                     |
| `created_before`   | datetime | Date range                     |

**Response:** `200 OK`

```python
class CostSummary(BaseModel):
    workspace_id: str
    total_cost_usd: float
    total_tokens_input: int
    total_tokens_output: int
    total_runs: int
    by_model: list[ModelCost]
    by_role: list[RoleCost]
    daily_trend: list[DailyCost]

class ModelCost(BaseModel):
    model_profile_id: str
    model_identifier: str
    cost_usd: float
    tokens_input: int
    tokens_output: int
    runs: int

class RoleCost(BaseModel):
    agent_role: str
    cost_usd: float
    runs: int

class DailyCost(BaseModel):
    date: str                     # ISO date
    cost_usd: float
    runs: int
```

---

#### `GET /costs/estimate`

Estimate cost for a proposed agent run.

**Query params:**

| Param              | Type   | Description                        |
|--------------------|--------|------------------------------------|
| `workspace_id`     | string | Required                           |
| `dataset_id`       | string | Required                           |
| `model_profile_id` | string | Required                           |
| `agent_role`       | string | Required                           |
| `record_count`     | int    | Override record count (default: all) |

**Response:** `200 OK`

```python
class CostEstimate(BaseModel):
    model_profile_id: str
    model_identifier: str
    estimated_records: int
    estimated_tokens_input: int
    estimated_tokens_output: int
    estimated_cost_usd: float
    confidence: str                # "high" | "medium" | "low" based on pricing data availability
    pricing_source: str            # "configured" | "estimated" | "unknown"
    warnings: list[str]
```

---

## SSE Event Streams

All SSE endpoints use standard `text/event-stream` content type. Each event has a `type` field and a JSON `data` payload. The client connects with `EventSource` or the auto-generated client's SSE helper.

Connection management:
- Clients should implement automatic reconnection with exponential backoff
- The server sends a `:keepalive` comment every 15 seconds to prevent timeout
- Each event includes an `id` field; clients send `Last-Event-ID` on reconnect to resume

---

### `GET /api/v1/events/agent-runs/{agent_run_id}`

Stream real-time updates for an agent run.

**TypeScript event types:**

```typescript
// SSE event: type = "progress"
interface AgentRunProgressEvent {
  agent_run_id: string;
  records_completed: number;
  records_total: number;
  records_failed: number;
  percentage: number;           // 0-100
  current_record_id: string | null;
  estimated_time_remaining_seconds: number | null;
}

// SSE event: type = "log"
interface AgentRunLogEvent {
  agent_run_id: string;
  level: "info" | "warning" | "error";
  message: string;
  timestamp: string;            // ISO 8601
  record_id: string | null;
}

// SSE event: type = "status_change"
interface AgentRunStatusChangeEvent {
  agent_run_id: string;
  previous_status: string;
  new_status: string;
  timestamp: string;
  error: string | null;
}

// SSE event: type = "cost_update"
interface AgentRunCostUpdateEvent {
  agent_run_id: string;
  tokens_input: number;
  tokens_output: number;
  cost_so_far_usd: number;
  cost_estimate_total_usd: number | null;
}

// SSE event: type = "error"
interface AgentRunErrorEvent {
  agent_run_id: string;
  message: string;
  record_id: string | null;
  recoverable: boolean;
  timestamp: string;
}

// SSE event: type = "output"
interface AgentRunOutputEvent {
  agent_run_id: string;
  record_id: string;
  agent_output_id: string;
  labels: Record<string, unknown>;
  confidence: number | null;
  validation_status: "valid" | "invalid";
}
```

---

### `GET /api/v1/events/queue/{queue_id}`

Stream real-time queue updates. Used by the review screen and mission control.

**TypeScript event types:**

```typescript
// SSE event: type = "item_claimed"
interface QueueItemClaimedEvent {
  queue_id: string;
  record_id: string;
  review_task_id: string;
  reviewer_id: string;
  reviewer_name: string;
  timestamp: string;
}

// SSE event: type = "item_completed"
interface QueueItemCompletedEvent {
  queue_id: string;
  record_id: string;
  review_task_id: string;
  reviewer_id: string;
  reviewer_name: string;
  review_duration_ms: number;
  timestamp: string;
}

// SSE event: type = "item_released"
interface QueueItemReleasedEvent {
  queue_id: string;
  record_id: string;
  review_task_id: string;
  reason: "timeout" | "manual" | "error";
  timestamp: string;
}

// SSE event: type = "stats_update"
interface QueueStatsUpdateEvent {
  queue_id: string;
  pending: number;
  in_progress: number;
  completed: number;
  active_reviewers: Array<{
    reviewer_id: string;
    reviewer_name: string;
    current_record_id: string | null;
  }>;
  avg_review_time_seconds: number | null;
  estimated_completion: string | null;
  timestamp: string;
}
```

---

### `GET /api/v1/events/workflow/{execution_id}`

Stream workflow execution events. Used by the workflow screen and mission control.

**TypeScript event types:**

```typescript
// SSE event: type = "step_started"
interface WorkflowStepStartedEvent {
  execution_id: string;
  workflow_id: string;
  step_id: string;
  step_type: string;
  step_label: string;
  timestamp: string;
}

// SSE event: type = "step_completed"
interface WorkflowStepCompletedEvent {
  execution_id: string;
  workflow_id: string;
  step_id: string;
  step_type: string;
  step_label: string;
  duration_seconds: number;
  outputs: Record<string, unknown> | null;
  timestamp: string;
}

// SSE event: type = "step_failed"
interface WorkflowStepFailedEvent {
  execution_id: string;
  workflow_id: string;
  step_id: string;
  step_type: string;
  step_label: string;
  error: string;
  recoverable: boolean;
  timestamp: string;
}

// SSE event: type = "step_paused"
interface WorkflowStepPausedEvent {
  execution_id: string;
  workflow_id: string;
  step_id: string;
  step_type: string;
  step_label: string;
  pause_reason: "human_step" | "gate" | "breakpoint" | "manual";
  timestamp: string;
}

// SSE event: type = "loop_iteration"
interface WorkflowLoopIterationEvent {
  execution_id: string;
  workflow_id: string;
  step_id: string;
  iteration: number;
  metric_name: string | null;
  metric_value: number | null;
  termination_threshold: number | null;
  will_continue: boolean;
  timestamp: string;
}

// SSE event: type = "workflow_completed"
interface WorkflowCompletedEvent {
  execution_id: string;
  workflow_id: string;
  steps_completed: number;
  total_duration_seconds: number;
  timestamp: string;
}

// SSE event: type = "workflow_failed"
interface WorkflowFailedEvent {
  execution_id: string;
  workflow_id: string;
  failed_step_id: string;
  error: string;
  steps_completed: number;
  timestamp: string;
}
```

---

### `GET /api/v1/events/providers`

Stream provider health status changes. Used by the model configuration screen and mission control.

**TypeScript event types:**

```typescript
// SSE event: type = "provider_status"
interface ProviderStatusEvent {
  provider_id: string;
  provider_type: string;
  previous_status: string | null;
  status: "online" | "offline" | "error";
  latency_ms: number | null;
  error: string | null;
  available_models: string[];
  timestamp: string;
}

// SSE event: type = "model_status"
interface ModelStatusEvent {
  model_profile_id: string;
  provider_id: string;
  status: "online" | "offline" | "error";
  latency_ms: number | null;
  timestamp: string;
}
```

---

## OpenAPI Codegen Pipeline

The API contract is enforced through an automated pipeline:

1. **FastAPI endpoints** use Pydantic request/response models, which auto-generate the OpenAPI 3.1 spec at `/openapi.json`.
2. **openapi-typescript-codegen** (or equivalent) generates a fully typed TypeScript client from the spec.
3. **TanStack Query hooks** are generated or hand-written on top of the typed client.
4. **CI enforces sync**: the TypeScript client must match the current OpenAPI spec. A CI step regenerates the client and fails if the output differs from the committed version.

### Generated client structure (reference)

```
frontend/src/api/
  client.ts              # base HTTP client configuration
  models/                # generated Pydantic model -> TypeScript interfaces
  services/              # generated service classes per resource group
  hooks/                 # TanStack Query hooks (may be hand-maintained)
```

### TanStack Query integration notes

- All GET endpoints map to `useQuery` or `useSuspenseQuery` hooks
- All POST/PUT/DELETE endpoints map to `useMutation` hooks
- SSE streams map to custom hooks using `EventSource` with `useEffect` lifecycle
- Optimistic updates are used for review event submission and draft saving
- Query invalidation cascades: submitting a review invalidates queue stats, record detail, and dataset analytics queries

---

## Concurrency and Locking

The API respects the locking contract from PRD Section 18.7:

- **Workspace migration lock**: blocks all writes during schema migration
- **Dataset indexing lock**: blocks dataset writes during reindex (reads allowed)
- **Output namespace export lock**: blocks concurrent exports to the same namespace
- **Task schema edit lock**: blocks schema mutation while reviews are in progress
- **Queue item claim lock**: prevents two reviewers from claiming the same item

When a resource is locked, the API returns `423 Locked` with a body indicating the lock holder and expected duration:

```json
{
  "error": {
    "code": "LOCKED",
    "message": "Dataset is currently being reindexed",
    "details": {
      "lock_type": "dataset_indexing",
      "locked_by": "reindex_job_abc123",
      "locked_at": "2026-03-23T10:00:00Z",
      "estimated_release": "2026-03-23T10:02:00Z"
    }
  }
}
```

---

## Multi-Session Support

The local FastAPI server supports multiple concurrent reviewer sessions (PRD Section 18.8):

- Reviewer profiles are lightweight: name + identifier, no passwords
- Session identity is carried via HTTP cookie (`molabel_session`)
- Queue assignment uses database-level locking to prevent double-claiming
- SQLite WAL mode allows concurrent reads from multiple sessions
- Write operations use row-level queue locking
- The `/api/v1/events/queue/{queue_id}` SSE stream broadcasts claim/release events to all connected sessions so the mission control screen shows live reviewer activity

---

## Appendix: Endpoint Summary Table

| Method | Path | Description |
|--------|------|-------------|
| GET | `/workspaces` | List workspaces |
| GET | `/workspaces/{id}` | Workspace detail + health |
| POST | `/workspaces` | Create workspace |
| POST | `/workspaces/{id}/reindex` | Trigger reindex |
| GET | `/datasets` | List datasets |
| GET | `/datasets/{id}` | Dataset detail + stats |
| POST | `/datasets` | Register dataset |
| POST | `/datasets/{id}/import` | Import with label mapping |
| GET | `/datasets/{id}/records` | List records (paginated) |
| GET | `/datasets/{id}/records/{rid}` | Record 360 view |
| GET | `/datasets/{id}/analytics` | Dataset analytics |
| POST | `/datasets/{id}/snapshots` | Create snapshot |
| GET | `/datasets/{id}/snapshots` | List snapshots |
| GET | `/datasets/{id}/snapshots/{sid}/diff` | Diff snapshots |
| POST | `/label-mappings/preview` | Preview mapping |
| POST | `/label-mappings` | Save mapping config |
| GET | `/workflows` | List workflows |
| GET | `/workflows/{id}` | Workflow detail + YAML |
| POST | `/workflows` | Create workflow |
| PUT | `/workflows/{id}` | Update workflow |
| POST | `/workflows/{id}/execute` | Start execution |
| GET | `/workflows/{id}/executions` | List executions |
| GET | `/workflows/{id}/executions/{eid}` | Execution detail |
| POST | `/workflows/{id}/executions/{eid}/steps/{sid}/advance` | Advance paused step |
| POST | `/workflows/{id}/executions/{eid}/pause` | Pause execution |
| POST | `/workflows/{id}/executions/{eid}/cancel` | Cancel execution |
| GET | `/task-schemas` | List task schemas |
| GET | `/task-schemas/{id}` | Task schema detail |
| POST | `/task-schemas` | Create task schema |
| PUT | `/task-schemas/{id}` | Update task schema |
| GET | `/providers` | List providers + health |
| POST | `/providers/scan` | Auto-detect providers |
| GET | `/model-profiles` | List model profiles |
| POST | `/model-profiles` | Create model profile |
| PUT | `/model-profiles/{id}` | Update model profile |
| POST | `/model-profiles/{id}/test` | Test connectivity |
| GET | `/runtime-profiles` | List runtime profiles |
| POST | `/runtime-profiles` | Create runtime profile |
| GET | `/agent-runs` | List agent runs |
| GET | `/agent-runs/{id}` | Agent run detail |
| POST | `/agent-runs` | Start agent run |
| POST | `/agent-runs/compare` | Start comparison run |
| POST | `/agent-runs/{id}/cancel` | Cancel agent run |
| GET | `/agent-runs/{id}/outputs` | List outputs |
| GET | `/agent-runs/{id}/outputs/{rid}` | Output for record |
| GET | `/agent-runs/comparison/{cid}` | Comparison results |
| GET | `/agent-runs/analytics` | Performance dashboard |
| GET | `/prompts` | List prompts |
| GET | `/prompts/{id}` | Prompt + versions |
| POST | `/prompts` | Create prompt |
| PUT | `/prompts/{id}` | New prompt version |
| GET | `/prompts/{id}/diff` | Diff versions |
| GET | `/corrections` | List correction batches |
| POST | `/corrections/analyze` | Trigger analysis |
| GET | `/corrections/{bid}/refinement` | Get refinement |
| GET | `/review/queue` | Next queue item |
| GET | `/review/queue/stats` | Queue statistics |
| POST | `/review/events` | Submit review |
| POST | `/review/events/draft` | Save draft |
| POST | `/review/events/{id}/reveal-ai` | Record AI reveal |
| GET | `/review/events` | Review history |
| GET | `/adjudication/queue` | Disagreement queue |
| GET | `/adjudication/{id}` | Adjudication detail |
| POST | `/adjudication/{id}/resolve` | Submit resolution |
| GET | `/quality/dashboard` | Quality dashboard |
| GET | `/quality/agreement` | Agreement metrics |
| GET | `/quality/drift` | Drift detection |
| GET | `/exports` | List exports |
| POST | `/exports` | Create export |
| POST | `/exports/preview` | Preview export |
| GET | `/exports/{id}` | Export detail |
| POST | `/exports/{id}/validate` | Run validation |
| POST | `/exports/{id}/download` | Download file |
| POST | `/exports/{id}/push-hf` | Push to HuggingFace |
| GET | `/releases` | List releases |
| POST | `/releases` | Create release |
| GET | `/releases/{id}` | Release detail |
| POST | `/releases/{id}/approve` | Human signoff |
| GET | `/plugins` | List plugins |
| GET | `/plugins/{id}` | Plugin detail |
| POST | `/plugins/{id}/enable` | Enable plugin |
| POST | `/plugins/{id}/disable` | Disable plugin |
| POST | `/assistant/query` | AI assistant query |
| GET | `/assistant/context` | Assistant context |
| GET | `/audit` | List audit events |
| GET | `/audit/{id}` | Audit event detail |
| GET | `/session` | Current session |
| POST | `/session` | Create/switch session |
| GET | `/reviewers` | List reviewers |
| POST | `/reviewers` | Create reviewer |
| GET | `/costs` | Cost summary |
| GET | `/costs/estimate` | Cost estimate |
| GET | `/api/v1/events/agent-runs/{id}` | SSE: agent run events |
| GET | `/api/v1/events/queue/{queue_id}` | SSE: queue events |
| GET | `/api/v1/events/workflow/{execution_id}` | SSE: workflow events |
| GET | `/api/v1/events/providers` | SSE: provider health |

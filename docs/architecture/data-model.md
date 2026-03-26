# MoLabel Data Model

Date: 2026-03-23
Status: Draft
Related: PRD Section 19, ADR-003, ADR-004, ADR-005

## Canonical Status

This document is the single source of truth for all domain object schemas, field definitions, enum values, and relationships. All other documents (API specification, session-and-identity, workflow-execution) must reference this document. If there is a conflict between this document and another, this document is authoritative.

## Overview

MoLabel uses three storage layers with explicit ownership rules for every domain object.

**Layer 1 -- Files on disk (file-canonical).** Raw source data, project configuration, workflow definitions, prompt templates, export bundles, validation reports, and release manifests. These are the portable, version-controllable artifacts that survive a database reset. Large data never moves into SQLite; the database references file paths instead.

**Layer 2 -- SQLite operational database (DB-canonical).** Indexed metadata, queue state, review events, agent run records, reviewer profiles, saved views, audit entries, and draft state. SQLite runs in WAL mode to support concurrent reader sessions. Write operations use queue-level locking.

**Layer 3 -- Derived cache (derived).** Row-count caches, sampled preview caches, analytical materialized views, and clustering outputs. Authoritative for nothing; always regenerable from layers 1 and 2.

If the database and canonical files disagree, the application surfaces the conflict, identifies which side is canonical for that object type, and offers a repair path. The application never silently chooses one side.

## Enum Types

These enums are referenced throughout the domain objects below.

```python
class ReviewEventSource(str, Enum):
    human = "human"
    agent = "agent"
    import_ = "import"

class TrustLevel(str, Enum):
    ground_truth = "ground_truth"
    expert = "expert"
    external = "external"
    untrusted = "untrusted"

class AgentRunStatus(str, Enum):
    pending = "pending"
    planned = "planned"
    running = "running"
    partially_completed = "partially_completed"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"

class WorkflowStepType(str, Enum):
    data_ingest = "data_ingest"
    data_normalize = "data_normalize"
    data_filter = "data_filter"
    data_sample = "data_sample"
    data_deduplicate = "data_deduplicate"
    agent_run = "agent_run"
    agent_compare = "agent_compare"
    human_review = "human_review"
    human_triage = "human_triage"
    human_calibration = "human_calibration"
    human_adjudication = "human_adjudication"
    quality_check = "quality_check"
    agreement_analysis = "agreement_analysis"
    drift_detection = "drift_detection"
    export = "export"
    snapshot = "snapshot"
    release_validation = "release_validation"
    loop = "loop"
    conditional = "conditional"
    parallel = "parallel"
    gate = "gate"

class WorkflowStepCategory(str, Enum):
    data = "data"            # data ingestion and transformation steps
    agent = "agent"          # AI/model-powered steps
    human = "human"          # human review and annotation steps
    quality = "quality"      # quality analysis and validation steps
    output = "output"        # export, snapshot, and release steps
    control = "control"      # flow control: loops, conditionals, parallel, gates
```

Each WorkflowStepType belongs to exactly one category. The mapping is:
- **data**: data_ingest, data_normalize, data_filter, data_sample, data_deduplicate
- **agent**: agent_run, agent_compare
- **human**: human_review, human_triage, human_calibration, human_adjudication
- **quality**: quality_check, agreement_analysis, drift_detection
- **output**: export, snapshot, release_validation
- **control**: loop, conditional, parallel, gate

```python
class LoopTermination(str, Enum):
    count = "count"
    metric = "metric"
    coverage = "coverage"
    manual = "manual"

class AdjudicationResolution(str, Enum):
    preserve_disagreement = "preserve_disagreement"
    resolve = "resolve"
    downgrade = "downgrade"
    exclude = "exclude"

class ExportFormat(str, Enum):
    jsonl = "jsonl"
    parquet = "parquet"
    csv = "csv"
    huggingface_hub = "huggingface_hub"
    plugin_custom = "plugin_custom"

class ProviderType(str, Enum):
    openai_compatible = "openai_compatible"
    openrouter = "openrouter"
    ollama = "ollama"
    anthropic = "anthropic"
    custom = "custom"

class WorkflowExecutionStatus(str, Enum):
    pending = "pending"
    running = "running"
    paused = "paused"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"

class WorkflowStepExecutionStatus(str, Enum):
    pending = "pending"                        # step created, predecessors not yet complete
    ready = "ready"                            # all predecessors complete, step can execute
    running = "running"
    waiting_for_human = "waiting_for_human"
    waiting_for_gate = "waiting_for_gate"
    waiting_for_breakpoint = "waiting_for_breakpoint"  # step has a user-configured breakpoint
    completed = "completed"
    failed = "failed"
    skipped = "skipped"
    retrying = "retrying"                      # step failed and is being retried
    partially_failed = "partially_failed"      # parallel step where some children failed
    interrupted = "interrupted"                # app crashed mid-execution, recovered on restart
    cancelled = "cancelled"

class AgentRole(str, Enum):
    proposer = "proposer"
    critic = "critic"
    normalizer = "normalizer"
    disagreement_flagger = "disagreement_flagger"
    deduper = "deduper"
    rubric_judge = "rubric_judge"
    edge_case_miner = "edge_case_miner"
    export_prep = "export_prep"

class AgentEventType(str, Enum):
    run_started = "run_started"
    batch_started = "batch_started"
    record_completed = "record_completed"
    record_failed = "record_failed"
    batch_completed = "batch_completed"
    retry_attempted = "retry_attempted"
    run_completed = "run_completed"
    run_failed = "run_failed"
    run_cancelled = "run_cancelled"

class ReviewDecision(str, Enum):
    accept = "accept"
    accept_ai = "accept_ai"
    edit_ai = "edit_ai"
    reject_ai = "reject_ai"
    correct = "correct"
    reject = "reject"
    skip = "skip"

class ValidationStatus(str, Enum):
    pending = "pending"
    running = "running"
    passed = "passed"
    failed = "failed"
    warning = "warning"

class ReleaseStatus(str, Enum):
    draft = "draft"
    validating = "validating"
    pending_approval = "pending_approval"
    approved = "approved"
    released = "released"
    rejected = "rejected"
    revoked = "revoked"

class AuditAction(str, Enum):
    workspace_created = "workspace_created"
    dataset_imported = "dataset_imported"
    dataset_reindexed = "dataset_reindexed"
    workflow_created = "workflow_created"
    workflow_started = "workflow_started"
    workflow_completed = "workflow_completed"
    task_schema_created = "task_schema_created"
    task_schema_updated = "task_schema_updated"
    agent_run_started = "agent_run_started"
    agent_run_completed = "agent_run_completed"
    agent_run_failed = "agent_run_failed"
    review_submitted = "review_submitted"
    review_draft_saved = "review_draft_saved"
    ai_revealed = "ai_revealed"
    adjudication_resolved = "adjudication_resolved"
    export_created = "export_created"
    export_validated = "export_validated"
    release_created = "release_created"
    release_approved = "release_approved"
    release_rejected = "release_rejected"
    snapshot_created = "snapshot_created"
    snapshot_restored = "snapshot_restored"
    plugin_enabled = "plugin_enabled"
    plugin_disabled = "plugin_disabled"
    config_changed = "config_changed"
    file_written = "file_written"
    reindex_triggered = "reindex_triggered"
    prompt_created = "prompt_created"
    prompt_refined = "prompt_refined"
    correction_analyzed = "correction_analyzed"
    provider_detected = "provider_detected"

class BlindReviewPolicy(str, Enum):
    hide_agent_outputs_by_default = "hide_agent_outputs_by_default"
    show_agent_outputs = "show_agent_outputs"
    no_agent = "no_agent"

class CorrectionBatchStatus(str, Enum):
    accumulating = "accumulating"              # corrections are still being collected
    ready_for_analysis = "ready_for_analysis"
    analyzed = "analyzed"
    refinements_pending = "refinements_pending"
    applied = "applied"
    dismissed = "dismissed"

class ReviewTaskStatus(str, Enum):
    available = "available"
    claimed = "claimed"
    submitted = "submitted"
    skipped = "skipped"

class DatasetHealthStatus(str, Enum):
    healthy = "healthy"                        # indexed and up to date
    stale = "stale"                            # files changed since last index
    error = "error"                            # plugin missing or schema mismatch

class ExportBundleStatus(str, Enum):
    pending = "pending"
    validating = "validating"
    validated = "validated"
    packaging = "packaging"
    completed = "completed"
    failed = "failed"
```

## Entity Relationship Summary

```
workspace
 |
 +-- dataset -------+-- record
 |                   |    |
 +-- task_schema     |    +-- review_event
 |    |              |    |    |
 |    +-- review_task +    |    +-- (links to reviewer_profile)
 |         |              |
 |         +-- (links to record, task_schema)
 |                        |
 +-- model_profile        +-- agent_output
 |    |                        |
 +-- runtime_profile           +-- (links to agent_run)
 |    |
 +-- agent_run --------+-- agent_event
 |    |                 +-- agent_output
 |    +-- (links to model_profile, runtime_profile,
 |        prompt_template, dataset, task_schema)
 |
 +-- adjudication --------- (links to record, review_events)
 |
 +-- workflow_definition
 |    |
 |    +-- workflow_execution
 |         |
 |         +-- workflow_step_execution
 |
 +-- prompt_template ---+-- correction_batch
 |
 +-- validation_run
 +-- export_bundle
 +-- release
 +-- dataset_snapshot
 +-- plugin_installation
 +-- audit_entry
 +-- saved_view
 +-- label_mapping

reviewer_profile (global, not workspace-scoped)
 +-- review_task (claimed)
 +-- review_event (authored)
 +-- adjudication (authored)
 +-- saved_view (owned)
 +-- cost_record
```

## Domain Objects

---

### Workspace

- **Storage**: DB-canonical (manifest file at `workbench.project.yaml` is file-canonical for configuration)
- **Table/Path**: `workspaces` table; `workbench.project.yaml` on disk

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | UUID | yes | Primary key |
| workspace_name | str | yes | Human-readable project name |
| workspace_slug | str | yes | URL-safe identifier derived from name |
| core_version | str | yes | MoLabel core version this workspace was created with |
| root_path | str | yes | Absolute path to workspace root directory on disk |
| manifest_path | str | yes | Relative path to `workbench.project.yaml` from root |
| reference_app | str | no | Reference app plugin ID (e.g., `depolarize`) |
| settings | JSON | no | Workspace-level settings (indexing mode, default profiles, etc.) |
| created_at | datetime | yes | When the workspace was bootstrapped |
| updated_at | datetime | yes | Last modification timestamp |

**Relationships:**
- has_many: dataset, task_schema, model_profile, runtime_profile, agent_run, workflow_definition, prompt_template, validation_run, export_bundle, release, plugin_installation, audit_entry, saved_view, label_mapping, dataset_snapshot

**Constraints:**
- One active workspace per running application instance.
- `workspace_slug` is unique and stable across sessions; used in cross-file references.
- If the database is reset, the workspace can be re-bootstrapped from `workbench.project.yaml` and files on disk.

---

### Artifact

- **Storage**: File-canonical (files on disk); DB stores indexed metadata
- **Table/Path**: `artifacts` table; source files at paths declared in workspace manifest

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | UUID | yes | Primary key |
| workspace_id | UUID | yes | FK to workspace |
| dataset_id | UUID | no | FK to dataset (set after dataset association) |
| file_path | str | yes | Relative path from workspace root to the source file |
| file_hash | str | yes | SHA-256 hash of the file at last index time |
| file_size_bytes | int | yes | File size for change detection |
| file_format | str | yes | Detected format: csv, jsonl, parquet, json, yaml, markdown |
| record_count | int | no | Number of records extracted from this file |
| loader_plugin | str | no | Plugin ID used to parse this file |
| metadata | JSON | no | Extracted file-level metadata (headers, encoding, schema summary) |
| indexed_at | datetime | yes | When this artifact was last indexed |
| stale | bool | yes | True if file has changed on disk since last index |
| created_at | datetime | yes | When the artifact was first discovered |

**Relationships:**
- belongs_to: workspace, dataset
- has_many: record (records extracted from this artifact)

**Constraints:**
- `file_path` is unique within a workspace.
- If `stale` is true, the application marks dependent views as needing reindex and blocks writes that depend on this artifact.
- Raw file content is never copied into SQLite.

---

### Dataset

- **Storage**: DB-canonical (metadata and membership); source data is file-canonical via artifacts
- **Table/Path**: `datasets` table

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | UUID | yes | Primary key |
| workspace_id | UUID | yes | FK to workspace |
| dataset_name | str | yes | Human-readable name |
| dataset_slug | str | yes | Stable identifier used in exports and cross-references |
| description | str | no | Optional description |
| source_type | str | yes | Origin: local_file, huggingface, import, derived |
| source_config | JSON | no | Source-specific config (HF repo, file glob, import format) |
| loader_plugin | str | no | Plugin ID for data loading |
| record_kind | str | no | Record kind tag (e.g., text_turn, conversation_window) |
| canonical_id_strategy | str | yes | How record IDs are assigned: source_record_id, content_hash, sequential |
| indexing_mode | str | yes | How records are indexed: projection, full_copy |
| record_count | int | no | Cached total record count |
| labeled_count | int | no | Cached count of records with at least one label |
| health_status | DatasetHealthStatus | no | Dataset health: healthy, stale, error |
| tags | JSON | no | User-defined tags for grouping |
| created_at | datetime | yes | Creation timestamp |
| updated_at | datetime | yes | Last modification timestamp |
| last_indexed_at | datetime | no | When records were last re-indexed from source |

**Relationships:**
- belongs_to: workspace
- has_many: artifact, record, dataset_snapshot

**Constraints:**
- `dataset_slug` is unique within a workspace.
- Deleting a dataset does not delete source files on disk.
- `record_count` and `labeled_count` are cached derived values; the application refreshes them after indexing or review operations.

---

### Record

- **Storage**: DB-canonical (indexed projection); raw payload stays in source files on disk
- **Table/Path**: `records` table

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | UUID | yes | Primary key |
| workspace_id | UUID | yes | FK to workspace |
| dataset_id | UUID | yes | FK to dataset |
| artifact_id | UUID | no | FK to source artifact (null for derived records) |
| external_id | str | no | Original ID from source data, preserved for traceability |
| sequence_index | int | no | Position within source file (line number, row index) |
| content_hash | str | no | Hash of record content for deduplication |
| stable_fields | JSON | yes | Typed fields extracted per task schema (normalized) |
| payload | JSON | no | Full plugin-specific record payload |
| record_kind | str | no | Record kind tag inherited from dataset |
| source_metadata | JSON | no | Origin metadata: file, line, import timestamp, source system |
| label_count | int | no | Cached count of review events for this record |
| latest_label | JSON | no | Cached latest accepted/resolved label values |
| composite_confidence | float | no | Cached composite confidence score from agent signals |
| export_eligible | bool | no | Whether this record meets export quality thresholds |
| flags | JSON | no | System and user flags (duplicate, outlier, agent_error, etc.) |
| created_at | datetime | yes | When this record was first indexed |
| updated_at | datetime | yes | Last modification timestamp |

**Relationships:**
- belongs_to: workspace, dataset, artifact
- has_many: review_event, agent_output, review_task, adjudication

**Constraints:**
- `external_id` + `dataset_id` is unique when `external_id` is not null (prevents duplicate imports).
- `stable_fields` holds the normalized schema-mapped fields; `payload` holds the full original data.
- `latest_label`, `label_count`, `composite_confidence`, and `export_eligible` are cached projections updated after review events or agent outputs.

---

### TaskSchema

- **Storage**: File-canonical (YAML at `workbench/config/task-schemas/`); DB stores indexed copy
- **Table/Path**: `task_schemas` table; `workbench/config/task-schemas/{task_schema_slug}_v{version}.yaml`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | UUID | yes | Primary key |
| workspace_id | UUID | yes | FK to workspace |
| task_schema_slug | str | yes | Stable identifier (e.g., `asset_a_review`) |
| version | int | yes | Monotonically increasing version number |
| task_type | str | yes | Task type plugin ID (e.g., `ordinal_text_review`) |
| title | str | yes | Human-readable title |
| instructions | str | no | Path to instruction document or inline instructions |
| record_selector | JSON | no | Criteria for which records this schema applies to |
| label_fields | JSON | yes | Array of field definitions (name, type, scale, options) |
| required_fields | JSON | no | Subset of label_fields that are required |
| optional_fields | JSON | no | Optional fields (e.g., rationale, notes) |
| blind_review_policy | BlindReviewPolicy | yes | How agent outputs are shown during review |
| overlap_policy | JSON | no | Overlap review configuration (mode, rate, strategy) |
| adjudication_policy | JSON | no | Adjudication plugin and rules |
| supported_agent_roles | JSON | no | List of agent roles this schema supports |
| default_model_profile_id | UUID | no | FK to model_profile for default agent runs |
| export_mapping | JSON | no | Export serializer configuration |
| is_active | bool | yes | Whether this version is the current active version |
| is_frozen | bool | yes | True once used in a completed review event |
| file_path | str | no | Relative path to canonical YAML file |
| created_at | datetime | yes | Creation timestamp |

**Relationships:**
- belongs_to: workspace, model_profile (default)
- has_many: review_task

**Constraints:**
- `task_schema_slug` + `version` is unique within a workspace.
- **Immutable once frozen**: once `is_frozen` is true, the record cannot be modified. Edits create a new version.
- Only one version per slug may have `is_active = true`.

---

### ModelProfile

- **Storage**: File-canonical (declared in `workbench.project.yaml`); DB stores indexed copy
- **Table/Path**: `model_profiles` table

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | UUID | yes | Primary key |
| workspace_id | UUID | yes | FK to workspace |
| model_profile_slug | str | yes | Stable identifier (e.g., `openrouter_general`) |
| provider_type | ProviderType | yes | Provider adapter type |
| provider_name | str | no | Human-readable provider name |
| model_identifier | str | yes | Model name as recognized by the provider |
| transport | str | yes | Transport type (openai_compatible, ollama_http, etc.) |
| auth_ref | str | no | Credential reference (e.g., `env:OPENROUTER_API_KEY`) |
| supports_structured_output | bool | no | Whether the provider supports native structured output |
| supports_tool_use | bool | no | Whether the provider supports tool/function calling |
| context_window | int | no | Maximum context window in tokens |
| capability_tags | JSON | no | Capability metadata (vision, code, etc.) |
| routing_metadata | JSON | no | Routing policy hints (cost tier, latency tier) |
| cost_per_input_token | float | no | Known or configured cost per input token |
| cost_per_output_token | float | no | Known or configured cost per output token |
| is_available | bool | no | Cached availability status from last health check |
| created_at | datetime | yes | Creation timestamp |
| updated_at | datetime | yes | Last modification timestamp |

**Relationships:**
- belongs_to: workspace
- has_many: agent_run

**Constraints:**
- `model_profile_slug` is unique within a workspace.
- Credential values are never stored directly; only references to environment variables or secret stores.

---

### RuntimeProfile

- **Storage**: File-canonical (declared in `workbench.project.yaml`); DB stores indexed copy
- **Table/Path**: `runtime_profiles` table

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | UUID | yes | Primary key |
| workspace_id | UUID | yes | FK to workspace |
| runtime_profile_slug | str | yes | Stable identifier (e.g., `local_only`) |
| mode | str | yes | Routing mode: offline_preferred, cloud_preferred, hybrid, local_only |
| fallback_model_profile_id | UUID | no | FK to model_profile used when primary is unavailable |
| provider_priority | JSON | no | Ordered list of provider preferences |
| max_concurrent_requests | int | no | Concurrency limit for this runtime |
| timeout_seconds | int | no | Per-request timeout |
| retry_config | JSON | no | Retry policy (max_retries, backoff) |
| created_at | datetime | yes | Creation timestamp |
| updated_at | datetime | yes | Last modification timestamp |

**Relationships:**
- belongs_to: workspace, model_profile (fallback)
- has_many: agent_run

**Constraints:**
- `runtime_profile_slug` is unique within a workspace.

---

### ReviewTask

- **Storage**: DB-canonical
- **Table/Path**: `review_tasks` table

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | UUID | yes | Primary key |
| queue_id | str | yes | Identifies which workflow step's queue this task belongs to |
| record_id | UUID | yes | FK to record |
| task_schema_id | UUID | yes | FK to task_schema |
| dataset_id | UUID | yes | FK to dataset |
| status | ReviewTaskStatus | yes | available, claimed, submitted, skipped |
| priority | int | yes | Higher = more urgent (default 0) |
| priority_reason | str | no | Why this priority was assigned (e.g., "active_learning_low_confidence", "calibration", "overlap") |
| claimed_by | UUID | no | FK to reviewer_profile |
| claimed_at | datetime | no | When the current claim was acquired |
| claim_expired_count | int | yes | How many times a claim has expired (default 0) |
| is_overlap | bool | yes | Whether this is an overlap review task (default false) |
| is_calibration | bool | yes | Whether this is a calibration task (default false) |
| draft_labels | JSON | no | Saved draft label values; preserved if claim expires |
| ai_revealed | bool | yes | Whether the reviewer has viewed agent suggestions (default false) |
| ai_revealed_at | datetime | no | When AI suggestions were revealed |
| submitted_at | datetime | no | When the review was submitted |
| created_at | datetime | yes | Creation timestamp |
| updated_at | datetime | yes | Last modification timestamp |

**Relationships:**
- belongs_to: record, dataset, task_schema, reviewer_profile (claimed_by)
- has_many: review_event

**Constraints:**
- Claims expire after a configurable timeout (default 30 minutes). Expired claims reset status to `available` and preserve `draft_labels`.
- `draft_labels` is ephemeral DB state; it survives app restarts and claim expiration but is not exported.
- For overlap tasks, multiple review_task rows exist for the same record (one per required review).

---

### ReviewEvent

- **Storage**: DB-canonical (exported to file for archival)
- **Table/Path**: `review_events` table

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | UUID | yes | Primary key |
| workspace_id | UUID | yes | FK to workspace |
| record_id | UUID | yes | FK to record |
| review_task_id | UUID | no | FK to review_task (null for imported pre-labels) |
| task_schema_id | UUID | yes | FK to task_schema active at time of review |
| task_schema_version | int | yes | Snapshot of task schema version used |
| reviewer_id | UUID | no | FK to reviewer_profile (null for agent/import sources) |
| source | ReviewEventSource | yes | Who produced this event: human, agent, import |
| source_system | str | no | For imports: originating system (label-studio, argilla, etc.) |
| source_file | str | no | For imports: source file path |
| trust_level | TrustLevel | no | For imports: ground_truth, expert, external, untrusted |
| decision | ReviewDecision | no | Human decision: accept, accept_ai, edit_ai, reject_ai, correct, reject, skip |
| labels | JSON | yes | Structured label values keyed by field name |
| previous_labels | JSON | no | For corrections: the labels being corrected |
| rationale | str | no | Reviewer's explanation or notes |
| confidence | float | no | Reviewer's self-reported confidence (0.0-1.0) |
| ai_was_revealed | bool | no | Whether agent output was visible when this event was created |
| review_duration_ms | int | no | Time spent on this review in milliseconds |
| agent_run_id | UUID | no | FK to agent_run (when source is agent) |
| agent_output_id | UUID | no | FK to agent_output (when reviewing a specific agent output) |
| unmapped_fields | JSON | no | For imports: source fields that did not map to the task schema |
| supersedes_event_id | UUID | no | FK to review_event this event corrects (self-referential) |
| created_at | datetime | yes | When this event was recorded |

**Relationships:**
- belongs_to: workspace, record, review_task, task_schema, reviewer_profile, agent_run, agent_output
- self-referential: supersedes review_event

**Constraints:**
- **Append-only**: review events are never updated or deleted. Corrections create a new event with `supersedes_event_id` pointing to the original.
- `task_schema_version` is snapshotted at creation time to preserve audit trail even if the schema is later superseded.
- Pre-labels imported from external tools are stored as review events with `source = import` and an appropriate `trust_level`.

---

### AgentRun

- **Storage**: DB-canonical (run manifest exported to `workbench/runs/`)
- **Table/Path**: `agent_runs` table; manifest at `workbench/runs/{agent_run_id}.yaml`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | UUID | yes | Primary key |
| workspace_id | UUID | yes | FK to workspace |
| dataset_id | UUID | yes | FK to target dataset |
| task_schema_id | UUID | yes | FK to task_schema |
| workflow_step_execution_id | UUID | no | FK to the workflow step that triggered this run |
| model_profile_id | UUID | yes | FK to model_profile used |
| runtime_profile_id | UUID | no | FK to runtime_profile used |
| prompt_template_id | UUID | no | FK to prompt_template used |
| prompt_version | str | no | Snapshot of prompt template version |
| agent_role | AgentRole | yes | Role for this run (proposer, critic, etc.) |
| adapter_plugin | str | no | Agent adapter plugin ID |
| status | AgentRunStatus | yes | Current run status |
| config | JSON | no | Run-specific configuration overrides |
| record_filter | JSON | no | Criteria for which records to process |
| total_records | int | no | Total records targeted |
| completed_records | int | no | Records successfully processed |
| failed_records | int | no | Records that failed processing |
| retry_count | int | no | Number of retries attempted |
| error_summary | str | no | Summary of failure when status is failed |
| cost_estimate | JSON | no | Pre-run cost estimate (tokens, dollars) |
| cost_actual | JSON | no | Post-run actual cost (tokens, dollars) |
| started_at | datetime | no | When execution began |
| completed_at | datetime | no | When execution finished |
| created_at | datetime | yes | When the run was created |
| comparison_id | UUID | no | Set when this run is part of a multi-model comparison |
| updated_at | datetime | yes | Last status update |

**Relationships:**
- belongs_to: workspace, dataset, task_schema, model_profile, runtime_profile, prompt_template, workflow_step_execution
- has_many: agent_event, agent_output, cost_record
- comparison: agent_run (other runs sharing the same comparison_id)

**Constraints:**
- Run status transitions follow a state machine: pending -> planned -> running -> {completed, partially_completed, failed, cancelled}.
- `prompt_version` is snapshotted at run creation; the prompt cannot change mid-run.
- The same task can be re-run against a different model profile without redefining the task schema.
- When `comparison_id` is set, all agent_runs with the same `comparison_id` form a comparison group.

---

### AgentEvent

- **Storage**: DB-canonical
- **Table/Path**: `agent_events` table

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | UUID | yes | Primary key |
| workspace_id | UUID | yes | FK to workspace |
| agent_run_id | UUID | yes | FK to agent_run |
| event_type | AgentEventType | yes | Event type (run_started, record_completed, etc.) |
| record_id | UUID | no | FK to record (for record-level events) |
| sequence_number | int | yes | Monotonic event sequence within the run |
| payload | JSON | no | Event-specific data (error details, token counts, etc.) |
| created_at | datetime | yes | Event timestamp |

**Relationships:**
- belongs_to: workspace, agent_run, record

**Constraints:**
- Append-only within a run; events are never modified.
- `sequence_number` is unique per `agent_run_id` and monotonically increasing.
- Used for live mission control event timeline and post-run diagnostics.

---

### AgentOutput

- **Storage**: DB-canonical
- **Table/Path**: `agent_outputs` table

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | UUID | yes | Primary key |
| workspace_id | UUID | yes | FK to workspace |
| agent_run_id | UUID | yes | FK to agent_run |
| record_id | UUID | yes | FK to record |
| task_schema_id | UUID | yes | FK to task_schema |
| output_type | str | yes | Output classification (label, critique, normalization, etc.) |
| labels | JSON | yes | Structured output payload conforming to task schema |
| raw_response | JSON | no | Raw LLM response before parsing |
| confidence_self_reported | float | no | Agent's self-rated confidence (0.0-1.0) |
| confidence_self_consistency | float | no | Multi-run consistency score |
| confidence_logprobs | float | no | Log-probability based confidence |
| composite_confidence | float | no | Weighted composite of all confidence signals |
| tokens_input | int | no | Input tokens consumed |
| tokens_output | int | no | Output tokens generated |
| latency_ms | int | no | Request latency in milliseconds |
| validation_passed | bool | yes | Whether the output passed task schema validation |
| validation_errors | JSON | no | Validation error details if validation failed |
| retry_attempt | int | no | Which retry attempt produced this output (0 = first try) |
| is_visible_for_review | bool | yes | Whether this output is available for reviewer reveal |
| normalization_status | str | no | Whether output has been normalized (raw, normalized, failed) |
| created_at | datetime | yes | When this output was stored |

**Relationships:**
- belongs_to: workspace, agent_run, record, task_schema
- referenced_by: review_event (via agent_output_id), review_task (via agent_output_ids)

**Constraints:**
- `agent_run_id` + `record_id` + `retry_attempt` is unique.
- Outputs bind to review queues through explicit `review_task.agent_output_ids` references, not by heuristic matching.
- Outputs with `validation_passed = false` and max retries exhausted are flagged as `agent_error` on the record.

---

### Adjudication

- **Storage**: DB-canonical (exported to `workbench/exports/` for archival)
- **Table/Path**: `adjudications` table

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | UUID | yes | Primary key |
| workspace_id | UUID | yes | FK to workspace |
| record_id | UUID | yes | FK to record |
| dataset_id | UUID | yes | FK to dataset |
| task_schema_id | UUID | yes | FK to task_schema |
| adjudicator_id | UUID | yes | FK to reviewer_profile (the adjudicator) |
| workflow_step_execution_id | UUID | no | FK to workflow step that triggered adjudication |
| conflicting_event_ids | JSON | yes | Array of review_event IDs that are in disagreement |
| resolution | AdjudicationResolution | yes | Decision: preserve_disagreement, resolve, downgrade, exclude |
| resolved_labels | JSON | no | Final label values when resolution is `resolve` |
| rationale | str | no | Adjudicator's explanation for the decision |
| policy_reference | str | no | Reference to the adjudication policy section applied |
| metadata | JSON | no | Additional adjudication context (field-level notes, etc.) |
| created_at | datetime | yes | When the adjudication was recorded |

**Relationships:**
- belongs_to: workspace, record, dataset, task_schema, reviewer_profile (adjudicator), workflow_step_execution
- references: review_event (via conflicting_event_ids)

**Constraints:**
- An adjudication creates a corresponding review_event with `source = human` and `decision = correct` or a dedicated adjudication decision to maintain the append-only event log.
- `conflicting_event_ids` must reference at least two review events.
- Once created, adjudications are not modified. A new adjudication supersedes the old one if the decision changes.

---

### WorkflowDefinition

- **Storage**: File-canonical (YAML at `workbench/workflows/`)
- **Table/Path**: `workflow_definitions` table; `workbench/workflows/{slug}_v{version}.yaml`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | UUID | yes | Primary key |
| workspace_id | UUID | yes | FK to workspace |
| workflow_slug | str | yes | Stable identifier |
| version | int | yes | Version number; increments on edit after execution |
| name | str | yes | Human-readable name |
| description | str | no | Workflow description |
| steps | JSON | yes | Ordered array of step definitions (id, type, config, dependencies) |
| is_template | bool | yes | Whether this is a reusable template (built-in or user-saved) vs. a project-specific workflow instance (default false) |
| template_source | str | no | Built-in template this was derived from, if any |
| file_path | str | yes | Relative path to canonical YAML file |
| is_active | bool | yes | Whether this is the current active version |
| created_at | datetime | yes | Creation timestamp |
| updated_at | datetime | yes | Last modification timestamp |

**Relationships:**
- belongs_to: workspace
- has_many: workflow_execution

**Constraints:**
- `workflow_slug` + `version` is unique within a workspace.
- Once a version has been executed (has any workflow_execution), the version is frozen. Edits create version N+1.
- The YAML file on disk is the source of truth; the DB row is an indexed projection.

---

### WorkflowExecution

- **Storage**: DB-canonical
- **Table/Path**: `workflow_executions` table

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | UUID | yes | Primary key |
| workspace_id | UUID | yes | FK to workspace |
| workflow_definition_id | UUID | yes | FK to workflow_definition |
| workflow_version | int | yes | Snapshot of workflow version at execution start |
| status | WorkflowExecutionStatus | yes | pending, running, paused, completed, failed, cancelled |
| current_step_id | str | no | ID of the currently executing step (from workflow YAML) |
| step_execution_count | int | no | Total steps executed so far |
| context | JSON | no | Shared execution context (metrics, intermediate results) |
| error_summary | str | no | Summary when status is failed |
| started_at | datetime | no | When execution began |
| paused_at | datetime | no | When execution was last paused |
| completed_at | datetime | no | When execution finished |
| created_at | datetime | yes | Creation timestamp |
| updated_at | datetime | yes | Last status update |

**Relationships:**
- belongs_to: workspace, workflow_definition
- has_many: workflow_step_execution

**Constraints:**
- Execution state is persisted so workflows survive application restarts.
- Only one execution of a given workflow may be in `running` or `paused` state at a time.
- `workflow_version` is snapshotted at creation; the definition cannot change mid-execution.

---

### WorkflowStepExecution

- **Storage**: DB-canonical
- **Table/Path**: `workflow_step_executions` table

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | UUID | yes | Primary key |
| workspace_id | UUID | yes | FK to workspace |
| workflow_execution_id | UUID | yes | FK to workflow_execution |
| step_id | str | yes | Step ID from the workflow YAML definition |
| step_type | WorkflowStepType | yes | Step type enum value |
| step_config | JSON | no | Resolved step configuration at execution time |
| status | WorkflowStepExecutionStatus | yes | pending, ready, running, waiting_for_human, waiting_for_gate, waiting_for_breakpoint, completed, failed, skipped, retrying, partially_failed, interrupted, cancelled |
| iteration | int | no | Loop iteration number (0-based; null if not in a loop) |
| parent_step_execution_id | UUID | no | FK to parent step execution (for loop/parallel children) |
| result | JSON | no | Step output data (metrics computed, records processed, etc.) |
| error_summary | str | no | Error details when status is failed |
| started_at | datetime | no | When step execution began |
| completed_at | datetime | no | When step execution finished |
| created_at | datetime | yes | Creation timestamp |
| updated_at | datetime | yes | Last status update |

**Relationships:**
- belongs_to: workspace, workflow_execution
- self-referential: parent workflow_step_execution (for nested loops/parallel)
- has_many: review_task, agent_run (tasks/runs created by this step)

**Constraints:**
- `workflow_execution_id` + `step_id` + `iteration` is unique.
- Human steps (`human_*`) automatically set status to `waiting_for_human` and wait for review task completion.
- Gate steps set status to `waiting_for_gate` and require explicit operator approval.

---

### PromptTemplate

- **Storage**: File-canonical (YAML at `workbench/prompts/`)
- **Table/Path**: `prompt_templates` table; `workbench/prompts/{slug}-v{version}.yaml`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | UUID | yes | Primary key |
| workspace_id | UUID | yes | FK to workspace |
| prompt_slug | str | yes | Stable identifier (e.g., `sentiment`) |
| version | str | yes | Version identifier; supports semantic versioning (e.g., "v1", "v1.2") |
| name | str | yes | Human-readable name |
| description | str | no | What this prompt is for |
| system_instructions | str | yes | Base system instructions |
| task_rubric | str | no | Labeling guidelines and definitions |
| few_shot_examples | JSON | no | Array of input/output example pairs |
| instruction_patches | JSON | no | Targeted instructions from correction analysis |
| output_schema | JSON | no | Expected output JSON schema |
| parent_version_id | UUID | no | FK to the prompt_template this was refined from |
| refinement_source_batch_id | UUID | no | FK to correction_batch that triggered this refinement |
| is_frozen | bool | yes | True once used in a completed agent run |
| file_path | str | yes | Relative path to canonical YAML file |
| created_at | datetime | yes | Creation timestamp |

**Relationships:**
- belongs_to: workspace, prompt_template (parent version), correction_batch (refinement source)
- has_many: agent_run, correction_batch

**Constraints:**
- `prompt_slug` + `version` is unique within a workspace.
- **Immutable once frozen**: once used in a completed agent run, the prompt cannot be modified. Refinements create a new version.
- The YAML file is the source of truth; the DB row is an indexed projection.

Note: The plugin-interfaces.md PromptTemplate dataclass uses simplified field names for the plugin boundary. The full template fields in this data model are the canonical storage representation.

---

### CorrectionBatch

- **Storage**: File-canonical (YAML at `workbench/prompts/corrections/`)
- **Table/Path**: `correction_batches` table; `workbench/prompts/corrections/batch-{sequence}.yaml`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | UUID | yes | Primary key |
| workspace_id | UUID | yes | FK to workspace |
| prompt_template_id | UUID | yes | FK to prompt_template these corrections apply to |
| batch_sequence | int | yes | Sequential batch number |
| status | CorrectionBatchStatus | yes | accumulating, ready_for_analysis, analyzed, refinements_pending, applied, dismissed |
| correction_count | int | yes | Number of corrections in this batch |
| batch_threshold | int | yes | Configured threshold that triggered analysis |
| corrections | JSON | yes | Array of correction records (original output, corrected output, error category, notes) |
| analysis_results | JSON | no | Pattern extraction and error grouping output |
| proposed_refinements | JSON | no | Candidate prompt refinements (few-shot examples, instruction patches, rubric clarifications) |
| applied_prompt_version_id | UUID | no | FK to prompt_template version created from these refinements |
| file_path | str | yes | Relative path to canonical YAML file |
| created_at | datetime | yes | When the batch was opened |
| analyzed_at | datetime | no | When pattern analysis was run |
| applied_at | datetime | no | When refinements were applied to create a new prompt version |

**Relationships:**
- belongs_to: workspace, prompt_template
- referenced_by: prompt_template (via refinement_source_batch_id)

**Constraints:**
- `prompt_template_id` + `batch_sequence` is unique.
- Status transitions: accumulating -> ready_for_analysis -> analyzed -> refinements_pending -> {applied, dismissed}.
- Corrections within the batch are append-only while status is `accumulating`.

---

### DatasetSnapshot

- **Storage**: DB-canonical (delta references); snapshot metadata exported to `workbench/snapshots/`
- **Table/Path**: `dataset_snapshots` table

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | UUID | yes | Primary key |
| workspace_id | UUID | yes | FK to workspace |
| dataset_id | UUID | yes | FK to dataset |
| workflow_step_execution_id | UUID | no | FK to workflow step that triggered this snapshot |
| name | str | yes | User-provided snapshot name |
| description | str | no | Description of what this snapshot represents |
| snapshot_type | str | yes | full or delta |
| parent_snapshot_id | UUID | no | FK to previous snapshot (for delta snapshots) |
| record_count | int | yes | Record count at snapshot time |
| labeled_count | int | yes | Labeled record count at snapshot time |
| quality_metrics | JSON | no | Quality metric values at snapshot time |
| label_summary | JSON | no | Label distribution summary at snapshot time |
| dataset_membership | JSON | no | Record IDs and their membership at snapshot time |
| workflow_state | JSON | no | Workflow execution state at snapshot time |
| prompt_versions | JSON | no | Active prompt versions at snapshot time |
| project_config | JSON | no | Project configuration at snapshot time |
| delta_data | JSON | no | For delta snapshots: changes since parent |
| created_at | datetime | yes | Snapshot creation timestamp |

**Relationships:**
- belongs_to: workspace, dataset, workflow_step_execution
- self-referential: parent dataset_snapshot (for delta chain)

**Constraints:**
- The first snapshot for a dataset is always `snapshot_type = full`.
- Subsequent snapshots store only deltas from the parent.
- Restoring a snapshot creates a new snapshot of the current state first (non-destructive restore).

---

### LabelMapping

- **Storage**: DB-canonical (reusable mapping configs stored as YAML in `workbench/config/mappings/`)
- **Table/Path**: `label_mappings` table; `workbench/config/mappings/{slug}.yaml`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | UUID | yes | Primary key |
| workspace_id | UUID | yes | FK to workspace |
| mapping_slug | str | yes | Stable identifier |
| name | str | yes | Human-readable name |
| source_system | str | yes | Source system identifier (label-studio, argilla, prodigy, custom) |
| source_format | str | no | Expected source file format |
| task_schema_id | UUID | yes | FK to target task_schema |
| field_mappings | JSON | yes | Array of source_field -> target_field mappings |
| value_mappings | JSON | no | Categorical value transformations (e.g., "pos" -> "positive") |
| type_conversions | JSON | no | Type transformation rules (float -> ordinal, etc.) |
| unmapped_field_policy | str | yes | What to do with unmapped fields: preserve_reference, discard |
| default_trust_level | TrustLevel | yes | Trust level assigned to imports using this mapping |
| file_path | str | no | Relative path to canonical YAML file |
| created_at | datetime | yes | Creation timestamp |
| updated_at | datetime | yes | Last modification timestamp |

**Relationships:**
- belongs_to: workspace, task_schema

**Constraints:**
- `mapping_slug` is unique within a workspace.
- Mappings are reusable: the same mapping can be applied to multiple imports from the same source format.
- `unmapped_field_policy = preserve_reference` stores unmapped fields in `review_event.unmapped_fields`.

---

### CostRecord

- **Storage**: DB-canonical
- **Table/Path**: `cost_records` table

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | UUID | yes | Primary key |
| workspace_id | UUID | yes | FK to workspace |
| agent_run_id | UUID | yes | FK to agent_run |
| agent_output_id | UUID | no | FK to agent_output (for per-record cost) |
| model_profile_id | UUID | yes | FK to model_profile |
| tokens_input | int | yes | Input tokens consumed |
| tokens_output | int | yes | Output tokens generated |
| cost_input | float | no | Cost for input tokens in USD |
| cost_output | float | no | Cost for output tokens in USD |
| cost_total | float | no | Total cost in USD |
| latency_ms | int | no | Request latency in milliseconds |
| provider_response_metadata | JSON | no | Raw cost/usage data from provider response |
| created_at | datetime | yes | When this cost was recorded |

**Relationships:**
- belongs_to: workspace, agent_run, agent_output, model_profile

**Constraints:**
- Cost values may be null when pricing is unknown for a model profile.
- Aggregated per-project, per-model, and per-agent-role totals are derived queries, not stored.

---

### ValidationRun

- **Storage**: DB-canonical (reports exported to `workbench/reports/`)
- **Table/Path**: `validation_runs` table; reports at `workbench/reports/{validation_run_id}.json`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | UUID | yes | Primary key |
| workspace_id | UUID | yes | FK to workspace |
| target_type | str | yes | What was validated: dataset, export_bundle, release |
| target_id | UUID | yes | FK to the validated object |
| workflow_step_execution_id | UUID | no | FK to workflow step that triggered this validation |
| validation_plugin | str | no | Plugin ID that provided the validation gates |
| status | ValidationStatus | yes | pending, running, passed, failed, warning |
| gates | JSON | yes | Array of gate results: {gate_id, name, passed, message, details} |
| passed_gate_count | int | no | Number of gates that passed |
| total_gate_count | int | no | Total number of gates evaluated |
| summary | str | no | Human-readable summary of validation results |
| report_path | str | no | Relative path to exported report file |
| started_at | datetime | no | When validation began |
| completed_at | datetime | no | When validation finished |
| created_at | datetime | yes | Creation timestamp |

**Relationships:**
- belongs_to: workspace, workflow_step_execution
- polymorphic target: dataset, export_bundle, or release (via target_type + target_id)

**Constraints:**
- `target_type` must be one of: `dataset`, `export_bundle`, `release`.
- Gate results within `gates` are ordered and individually addressable.
- The report file on disk is a full copy; the DB stores the structured summary.

---

### ExportBundle

- **Storage**: File-canonical (packaged output at `workbench/exports/`)
- **Table/Path**: `export_bundles` table; `workbench/exports/{export_slug}/{timestamp}/`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | UUID | yes | Primary key |
| workspace_id | UUID | yes | FK to workspace |
| dataset_id | UUID | yes | FK to source dataset |
| task_schema_id | UUID | yes | FK to task_schema used for label structure |
| workflow_step_execution_id | UUID | no | FK to workflow step that triggered this export |
| export_slug | str | yes | Stable export identifier |
| status | ExportBundleStatus | yes | pending, validating, validated, packaging, completed, failed |
| format | ExportFormat | yes | Output format |
| output_path | str | yes | Relative path to exported files from workspace root |
| output_namespace | str | no | Plugin-declared output namespace |
| record_count | int | yes | Number of records in the export |
| include_config | JSON | no | What was included: record_data, human_labels, agent_labels, metadata, etc. |
| filter_config | JSON | no | Filters applied: min_agreement, exclude_flagged, etc. |
| file_hash | str | no | Hash of the exported file for integrity verification |
| file_size_bytes | int | no | Size of the exported file |
| source_snapshot_id | UUID | no | FK to dataset_snapshot used as export baseline |
| validation_run_id | UUID | no | FK to validation_run for this export |
| packager_plugin | str | no | Export packager plugin ID |
| created_at | datetime | yes | When the export was created |

**Relationships:**
- belongs_to: workspace, dataset, task_schema, workflow_step_execution, dataset_snapshot, validation_run
- referenced_by: release (via export_bundle_ids)

**Constraints:**
- Exports follow the atomic export flow: validate -> render to temp -> verify -> atomic replace.
- `output_path` is relative to workspace root and must be under `workbench/exports/`.
- Previous exports at the same path are preserved with timestamps; the application never silently overwrites.

---

### Release

- **Storage**: File-canonical (manifest at `workbench/releases/`)
- **Table/Path**: `releases` table; `workbench/releases/{release_slug}_v{version}.yaml`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | UUID | yes | Primary key |
| workspace_id | UUID | yes | FK to workspace |
| release_slug | str | yes | Stable release identifier |
| version | str | yes | Semantic version string |
| name | str | yes | Human-readable release name |
| description | str | no | Release notes |
| status | ReleaseStatus | yes | draft, validating, pending_approval, approved, released, rejected, revoked |
| export_bundle_ids | JSON | yes | Array of export_bundle IDs included in this release |
| validation_run_ids | JSON | no | Array of validation_run IDs for this release |
| dataset_snapshot_id | UUID | no | FK to dataset_snapshot at release point |
| quality_summary | JSON | no | Quality metrics at release time |
| signed_off_by | UUID | no | FK to reviewer_profile who approved the release |
| signed_off_at | datetime | no | When human signoff was recorded |
| release_metadata | JSON | no | Additional release metadata (license, privacy gates, etc.) |
| manifest_path | str | no | Relative path to release manifest YAML |
| created_at | datetime | yes | Creation timestamp |
| released_at | datetime | no | When the release was officially marked released |
| revoked_at | datetime | no | When the release was revoked (if applicable) |

**Relationships:**
- belongs_to: workspace, dataset_snapshot, reviewer_profile (signed_off_by)
- references: export_bundle (via export_bundle_ids), validation_run (via validation_run_ids)

**Constraints:**
- Status transitions: draft -> validating -> pending_approval -> approved -> released; released -> revoked; pending_approval -> rejected.
- `approved` and `released` statuses require a non-null `signed_off_by` (human signoff is mandatory).
- Revocation does not delete the release; it marks it as revoked with a timestamp and preserves the history.

---

### PluginInstallation

- **Storage**: DB-canonical
- **Table/Path**: `plugin_installations` table

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | UUID | yes | Primary key |
| workspace_id | UUID | yes | FK to workspace |
| plugin_id | str | yes | Plugin identifier (e.g., `depolarize.reference_app`) |
| plugin_version | str | yes | Installed version |
| plugin_type | str | yes | Plugin category: data_loader, task_type, model_provider, etc. |
| compatible_core_version | str | yes | Core version compatibility range |
| entrypoint | str | yes | Python entrypoint (e.g., `depolarize.plugin:register`) |
| is_enabled | bool | yes | Whether the plugin is currently active |
| is_compatible | bool | yes | Whether the plugin passes compatibility checks |
| capabilities | JSON | no | Declared capabilities: record_kinds, task_types, export_formats, etc. |
| config | JSON | no | Plugin-specific configuration |
| installed_at | datetime | yes | When the plugin was installed |
| updated_at | datetime | yes | Last state change |

**Relationships:**
- belongs_to: workspace

**Constraints:**
- `plugin_id` is unique within a workspace.
- If `is_compatible` is false, the application blocks writes that depend on this plugin but keeps the workspace readable.
- Plugin state survives database reset only via the `enabled_plugins` list in `workbench.project.yaml`.

---

### AuditEntry

- **Storage**: DB-canonical (periodically exported to `workbench/reports/audit/`)
- **Table/Path**: `audit_entries` table

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | UUID | yes | Primary key |
| workspace_id | UUID | yes | FK to workspace |
| action | AuditAction | yes | Compound event name describing what happened (e.g., workspace_created, review_submitted) |
| actor_type | str | yes | Who performed the action: user, system, agent, plugin |
| actor_id | str | no | Identifier of the actor (reviewer_profile ID, plugin ID, etc.) |
| target_type | str | yes | Object type affected (record, review_event, agent_run, etc.) |
| target_id | UUID | yes | ID of the affected object |
| detail | JSON | no | Action-specific details (changed fields, error info, etc.) |
| file_path | str | no | Affected file path (for file write events) |
| file_hash_before | str | no | File hash before the operation |
| file_hash_after | str | no | File hash after the operation |
| session_id | str | no | Session identifier for correlating related actions |
| created_at | datetime | yes | When the action occurred |

**Relationships:**
- belongs_to: workspace

**Constraints:**
- Append-only: audit entries are never modified or deleted from the database.
- Periodic export to disk preserves the audit trail beyond database lifecycle.
- Must support filtering by action, actor, target_type, target_id, and time range.

---

### SavedView

- **Storage**: DB-canonical
- **Table/Path**: `saved_views` table

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | UUID | yes | Primary key |
| workspace_id | UUID | yes | FK to workspace |
| owner_id | UUID | no | FK to reviewer_profile (null for workspace-level views) |
| name | str | yes | Human-readable view name |
| description | str | no | View description |
| view_type | str | yes | Which screen this view applies to: explorer, review_queue, quality, curation, etc. |
| target_dataset_id | UUID | no | FK to dataset (scoped views) |
| filters | JSON | yes | Filter definitions (field conditions, status filters, etc.) |
| sort_config | JSON | no | Sort column and direction |
| column_config | JSON | no | Visible columns and their order |
| grouping | JSON | no | Grouping configuration |
| is_default | bool | yes | Whether this is the default view for its type |
| is_shared | bool | yes | Whether this view is visible to all reviewers |
| created_at | datetime | yes | Creation timestamp |
| updated_at | datetime | yes | Last modification timestamp |

**Relationships:**
- belongs_to: workspace, reviewer_profile (owner), dataset

**Constraints:**
- At most one default view per `view_type` + `target_dataset_id` + `owner_id` combination.
- Saved views are purely operational DB state; they do not affect canonical data.

---

### ReviewerProfile

- **Storage**: DB-canonical (global, not workspace-scoped)
- **Table/Path**: `reviewer_profiles` table

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | UUID | yes | Primary key (auto-generated, server-assigned) |
| display_name | str | yes | Human-readable reviewer name |
| avatar_color | str | no | Hex color for UI identification (e.g., "#4A90D9") |
| is_operator | bool | yes | Whether this reviewer can manage workflows and exports (default false) |
| is_active | bool | yes | Whether this profile is currently active (default true) |
| created_at | datetime | yes | Creation timestamp |
| last_active_at | datetime | no | Last activity timestamp |
| preferences | JSON | no | UI preferences (theme, keyboard shortcuts, layout) |

**Relationships:**
- has_many: review_task (claimed), review_event (authored), adjudication (authored), saved_view (owned)

**Constraints:**
- Reviewer profiles are global across all workspaces; they are not scoped to a single workspace.
- No enterprise auth in v1; profiles are lightweight identifiers for claim-based queue assignment and provenance tracking.
- The claim-based model prevents two reviewers from working on the same task simultaneously.

---

## Index Recommendations

The following indexes support the primary access patterns described in PRD Section 19.5 and ADR-005.

**Records:**
- `idx_records_dataset_id` on `records(dataset_id)`
- `idx_records_dataset_export` on `records(dataset_id, export_eligible)`
- `idx_records_content_hash` on `records(content_hash)` for deduplication
- `idx_records_composite_confidence` on `records(dataset_id, composite_confidence)` for active learning

**Review events:**
- `idx_review_events_record_id` on `review_events(record_id)`
- `idx_review_events_task_schema` on `review_events(task_schema_id, created_at)`
- `idx_review_events_reviewer` on `review_events(reviewer_id, created_at)`
- `idx_review_events_source` on `review_events(source, created_at)`

**Review tasks:**
- `idx_review_tasks_queue` on `review_tasks(queue_id, status, priority)`
- `idx_review_tasks_claimed` on `review_tasks(claimed_by, status)`

**Agent runs:**
- `idx_agent_runs_dataset` on `agent_runs(dataset_id, status)`
- `idx_agent_runs_model` on `agent_runs(model_profile_id, created_at)`

**Agent outputs:**
- `idx_agent_outputs_record` on `agent_outputs(record_id, agent_run_id)`
- `idx_agent_outputs_run` on `agent_outputs(agent_run_id)`
- `idx_agent_outputs_confidence` on `agent_outputs(agent_run_id, composite_confidence)`

**Agent events:**
- `idx_agent_events_run` on `agent_events(agent_run_id, sequence_number)`

**Adjudications:**
- `idx_adjudications_record` on `adjudications(record_id)`

**Workflow step executions:**
- `idx_wf_step_exec_workflow` on `workflow_step_executions(workflow_execution_id, status)`

**Audit entries:**
- `idx_audit_target` on `audit_entries(target_type, target_id, created_at)`
- `idx_audit_action` on `audit_entries(action, created_at)`

**Cost records:**
- `idx_cost_records_run` on `cost_records(agent_run_id)`
- `idx_cost_records_model` on `cost_records(model_profile_id, created_at)`

## Storage Layer Assignment Summary

| Domain Object | Storage Layer | Canonical Location |
|---|---|---|
| workspace | DB + File | `workbench.project.yaml` |
| artifact | DB (projection) | Source files on disk |
| dataset | DB | `datasets` table |
| record | DB (projection) | `records` table; raw data in source files |
| task_schema | File + DB (projection) | `workbench/config/task-schemas/` |
| model_profile | File + DB (projection) | `workbench.project.yaml` |
| runtime_profile | File + DB (projection) | `workbench.project.yaml` |
| review_task | DB | `review_tasks` table |
| review_event | DB | `review_events` table |
| agent_run | DB + File (manifest) | `workbench/runs/` |
| agent_event | DB | `agent_events` table |
| agent_output | DB | `agent_outputs` table |
| adjudication | DB | `adjudications` table |
| workflow_definition | File + DB (projection) | `workbench/workflows/` |
| workflow_execution | DB | `workflow_executions` table |
| workflow_step_execution | DB | `workflow_step_executions` table |
| prompt_template | File + DB (projection) | `workbench/prompts/` |
| correction_batch | File + DB (projection) | `workbench/prompts/corrections/` |
| dataset_snapshot | DB | `dataset_snapshots` table |
| label_mapping | File + DB (projection) | `workbench/config/mappings/` |
| cost_record | DB | `cost_records` table |
| validation_run | DB + File (report) | `workbench/reports/` |
| export_bundle | File + DB (metadata) | `workbench/exports/` |
| release | File + DB (metadata) | `workbench/releases/` |
| plugin_installation | DB | `plugin_installations` table |
| audit_entry | DB | `audit_entries` table |
| saved_view | DB | `saved_views` table |
| reviewer_profile | DB (global) | `reviewer_profiles` table |

## Cross-Reference: PRD Section 19.5 Join Paths

The data model supports all explicit join paths required by PRD Section 19.5:

| Join | Path |
|------|------|
| dataset <-> record | `record.dataset_id` |
| task_schema <-> review_task | `review_task.task_schema_id` |
| model_profile <-> agent_run | `agent_run.model_profile_id` |
| runtime_profile <-> agent_run | `agent_run.runtime_profile_id` |
| review_task <-> review_event | `review_event.review_task_id` |
| agent_run <-> agent_output | `agent_output.agent_run_id` |
| agent_run <-> agent_event | `agent_event.agent_run_id` |
| agent_output <-> review visibility | `review_task.agent_output_ids`, `agent_output.is_visible_for_review` |
| adjudication <-> reviewed object | `adjudication.record_id`, `adjudication.conflicting_event_ids` |
| export_bundle <-> source records | `export_bundle.dataset_id` + `export_bundle.filter_config` |
| validation_run <-> target | `validation_run.target_type` + `validation_run.target_id` |

## Design Notes

1. **UUID generation**: All primary keys use UUID v4. UUIDs are generated application-side, not database-side, so they are available before insertion and can be used in cross-file references and export manifests.

2. **Timestamp convention**: All `created_at` and `updated_at` fields store UTC datetime values. Display formatting is a frontend concern.

3. **JSON field convention**: JSON columns store Python dicts or lists serialized as JSON text in SQLite. Pydantic models define the shape of each JSON field for validation. These are documented inline in each domain object's description.

4. **Append-only guarantees**: `review_events` and `audit_entries` are never updated or deleted through application code. Corrections and supersession are modeled as new rows with backward references (`supersedes_event_id`). This is enforced at the repository/service layer, not via database triggers.

5. **Immutability for versioned objects**: `task_schema` (once frozen), `prompt_template` (once frozen), and `workflow_definition` (once executed) are immutable. Changes always create new versions. This guarantees that any agent output or review event can be traced back to the exact configuration that produced it.

6. **Polymorphic references**: `validation_run` uses `target_type` + `target_id` to reference different object types. This avoids separate join tables while keeping the validation system generic. Application code must validate that `target_id` references a valid object of the declared `target_type`.

7. **Cached projections**: Fields like `record.latest_label`, `record.composite_confidence`, `dataset.record_count`, and `reviewer_profile.stats` are denormalized caches. They improve read performance for common queries (queue ordering, dashboard stats) but must be refreshed after writes to the underlying data. These fields are marked as derived in their descriptions.

8. **File-canonical sync**: For objects that are file-canonical with a DB projection (task_schema, workflow_definition, prompt_template, label_mapping), the DB row includes a `file_path` field. On startup and after file change detection, the application re-reads the file and updates the DB projection. If the file and DB disagree, the file wins.

9. **ORM choice: SQLModel.** SQLModel is chosen because it integrates Pydantic validation (already used throughout the stack) with SQLAlchemy's ORM capabilities, reducing boilerplate for defining models that serve as both database schemas and API response types.

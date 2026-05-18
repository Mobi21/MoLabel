"""Core domain types and enums for MoLabel.

All enum definitions mirror the canonical data model
(docs/architecture/data-model.md). Plugin-facing value objects
(PluginMetadata, PluginContext) mirror the plugin interface spec
(docs/architecture/plugin-interfaces.md).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Sentinel values
# ---------------------------------------------------------------------------

SENTINEL_DATASET_ID = UUID("00000000-0000-0000-0000-000000000000")
"""Sentinel UUID used by loaders before the core assigns a real dataset ID."""

# ---------------------------------------------------------------------------
# Enum types (DM-003) — authoritative source: data-model.md
# ---------------------------------------------------------------------------


class ReviewEventSource(StrEnum):
    human = "human"
    agent = "agent"
    import_ = "import"


class TrustLevel(StrEnum):
    ground_truth = "ground_truth"
    expert = "expert"
    external = "external"
    untrusted = "untrusted"


class AgentRunStatus(StrEnum):
    pending = "pending"
    planned = "planned"
    running = "running"
    partially_completed = "partially_completed"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class WorkflowStepType(StrEnum):
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


class WorkflowStepCategory(StrEnum):
    data = "data"
    agent = "agent"
    human = "human"
    quality = "quality"
    output = "output"
    control = "control"


class LoopTermination(StrEnum):
    count = "count"
    metric = "metric"
    coverage = "coverage"
    manual = "manual"


class AdjudicationResolution(StrEnum):
    preserve_disagreement = "preserve_disagreement"
    resolve = "resolve"
    downgrade = "downgrade"
    exclude = "exclude"


class ExportFormat(StrEnum):
    jsonl = "jsonl"
    parquet = "parquet"
    csv = "csv"
    huggingface_hub = "huggingface_hub"
    plugin_custom = "plugin_custom"


class ProviderType(StrEnum):
    openai_compatible = "openai_compatible"
    openrouter = "openrouter"
    ollama = "ollama"
    anthropic = "anthropic"
    custom = "custom"


class WorkflowExecutionStatus(StrEnum):
    pending = "pending"
    running = "running"
    paused = "paused"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class WorkflowStepExecutionStatus(StrEnum):
    pending = "pending"
    ready = "ready"
    running = "running"
    waiting_for_human = "waiting_for_human"
    waiting_for_gate = "waiting_for_gate"
    waiting_for_breakpoint = "waiting_for_breakpoint"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"
    retrying = "retrying"
    partially_failed = "partially_failed"
    interrupted = "interrupted"
    cancelled = "cancelled"


class AgentRole(StrEnum):
    proposer = "proposer"
    critic = "critic"
    normalizer = "normalizer"
    disagreement_flagger = "disagreement_flagger"
    deduper = "deduper"
    rubric_judge = "rubric_judge"
    edge_case_miner = "edge_case_miner"
    export_prep = "export_prep"


class AgentEventType(StrEnum):
    run_started = "run_started"
    batch_started = "batch_started"
    record_completed = "record_completed"
    record_failed = "record_failed"
    batch_completed = "batch_completed"
    retry_attempted = "retry_attempted"
    run_completed = "run_completed"
    run_failed = "run_failed"
    run_cancelled = "run_cancelled"


class ReviewDecision(StrEnum):
    accept = "accept"
    accept_ai = "accept_ai"
    edit_ai = "edit_ai"
    reject_ai = "reject_ai"
    correct = "correct"
    reject = "reject"
    skip = "skip"


class ValidationStatus(StrEnum):
    pending = "pending"
    running = "running"
    passed = "passed"
    failed = "failed"
    warning = "warning"


class ReleaseStatus(StrEnum):
    draft = "draft"
    validating = "validating"
    pending_approval = "pending_approval"
    approved = "approved"
    released = "released"
    rejected = "rejected"
    revoked = "revoked"


class AuditAction(StrEnum):
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


class BlindReviewPolicy(StrEnum):
    hide_agent_outputs_by_default = "hide_agent_outputs_by_default"
    show_agent_outputs = "show_agent_outputs"
    no_agent = "no_agent"


class CorrectionBatchStatus(StrEnum):
    accumulating = "accumulating"
    ready_for_analysis = "ready_for_analysis"
    analyzed = "analyzed"
    refinements_pending = "refinements_pending"
    applied = "applied"
    dismissed = "dismissed"


class ReviewTaskStatus(StrEnum):
    available = "available"
    claimed = "claimed"
    submitted = "submitted"
    skipped = "skipped"


class DatasetHealthStatus(StrEnum):
    healthy = "healthy"
    stale = "stale"
    error = "error"


class ExportBundleStatus(StrEnum):
    pending = "pending"
    validating = "validating"
    validated = "validated"
    packaging = "packaging"
    completed = "completed"
    failed = "failed"


# ---------------------------------------------------------------------------
# Plugin value objects (PL-003, PL-018)
# ---------------------------------------------------------------------------


class PluginMetadata(BaseModel):
    """Identity and compatibility information declared by every plugin."""

    plugin_id: str
    """Globally unique dotted identifier, e.g. ``molabel.loaders.jsonl``."""

    version: str
    """SemVer string, e.g. ``0.1.0``."""

    compatible_core: str
    """PEP 440 version specifier for ``molabel-core``, e.g. ``>=0.1,<1.0``."""

    description: str
    """One-line human-readable summary shown in the plugin management UI."""

    author: str | None = None
    """Optional author or organization name."""

    url: str | None = None
    """Optional link to documentation or source repository."""

    tags: list[str] = []
    """Freeform tags for search and filtering in the plugin browser."""


class PluginContext(BaseModel):
    """Contextual information passed to plugin lifecycle hooks."""

    core_version: str
    """Running ``molabel-core`` version string."""

    workspace_root: Path | None = None
    """Absolute path to the workspace root directory."""

    plugin_data_dir: Path | None = None
    """Per-plugin writable directory at ``workbench/plugins/{plugin_id}/``."""

    settings: dict[str, Any] = {}
    """Plugin-specific settings from the workspace manifest."""


# ---------------------------------------------------------------------------
# Domain value objects (simplified projections of the canonical data model)
# ---------------------------------------------------------------------------


class Record(BaseModel):
    """A single data item within a dataset.

    Maps to the ``records`` table in the canonical data model.
    ``stable_fields`` contains schema-normalised values;
    ``payload`` contains the full original data.
    """

    id: UUID
    dataset_id: UUID
    external_id: str | None = None
    stable_fields: dict[str, Any] = {}
    payload: dict[str, Any] = {}
    record_kind: str | None = None
    source_metadata: dict[str, Any] | None = None
    flags: dict[str, Any] | None = None


class LabelFieldDefinition(BaseModel):
    """Specification for a single label field within a task schema."""

    name: str
    """Field identifier, e.g. ``sentiment``."""

    field_type: str
    """One of: ordinal, categorical, text, numeric, bool, multi_select, json."""

    required: bool = True

    options: list[str] | None = None
    """For categorical / ordinal / multi_select: the allowed values in order."""

    option_descriptions: dict[str, str] | None = None
    """Optional per-option rubric text for near-neighbor label decisions."""

    scale_min: float | None = None
    """For numeric / ordinal: minimum value."""

    scale_max: float | None = None
    """For numeric / ordinal: maximum value."""

    description: str = ""
    """Instruction text shown next to this field in the review form."""

    default: Any = None
    """Default value pre-filled in new review forms."""


class TaskSchema(BaseModel):
    """Configuration for a labeling task.

    Maps to the ``task_schemas`` table. Plugins receive this read-only; only
    the core may persist changes.
    """

    id: UUID
    task_schema_slug: str
    version: int
    task_type: str
    title: str
    label_fields: list[LabelFieldDefinition] = []
    required_fields: list[str] = []
    optional_fields: list[str] = []
    blind_review_policy: str = "hide_agent_outputs_by_default"
    instructions: str | None = None
    overlap_policy: dict[str, Any] | None = None
    adjudication_policy: dict[str, Any] | None = None
    export_mapping: dict[str, Any] | None = None


class ReviewEvent(BaseModel):
    """A single review action (human, agent, or import).

    Maps to the ``review_events`` table. Append-only -- plugins never
    mutate existing events.
    """

    id: UUID
    record_id: UUID
    reviewer_id: UUID | None = None
    source: str  # human | agent | import
    decision: str | None = None
    """One of: accept, accept_ai, edit_ai, reject_ai, correct, reject, skip."""
    labels: dict[str, Any] = {}
    rationale: str | None = None
    confidence: float | None = None
    ai_was_revealed: bool = False
    review_duration_ms: int | None = None
    task_schema_id: UUID | None = None
    task_schema_version: int | None = None
    agent_run_id: UUID | None = None
    agent_output_id: UUID | None = None
    previous_labels: dict[str, Any] | None = None
    created_at: datetime | None = None


class AgentOutput(BaseModel):
    """Structured output from an agent run for a single record.

    Maps to the ``agent_outputs`` table.
    """

    id: UUID
    agent_run_id: UUID
    record_id: UUID
    task_schema_id: UUID
    output_type: str  # label | critique | normalization
    labels: dict[str, Any] = {}
    raw_response: dict[str, Any] | None = None
    confidence_self_reported: float | None = None
    confidence_self_consistency: float | None = None
    confidence_logprobs: float | None = None
    composite_confidence: float | None = None
    tokens_input: int | None = None
    tokens_output: int | None = None
    latency_ms: int | None = None
    validation_passed: bool = True
    validation_errors: list[dict[str, Any]] | None = None
    created_at: datetime | None = None


class Adjudication(BaseModel):
    """Resolution of a disagreement between reviewers or between human and agent.

    Maps to the ``adjudications`` table.
    """

    id: UUID
    record_id: UUID
    dataset_id: UUID
    task_schema_id: UUID
    adjudicator_id: UUID
    conflicting_event_ids: list[UUID] = []
    resolution: str  # preserve_disagreement | resolve | downgrade | exclude
    resolved_labels: dict[str, Any] | None = None
    rationale: str | None = None
    metadata: dict[str, Any] | None = None
    created_at: datetime | None = None


class Dataset(BaseModel):
    """A collection of records within a workspace.

    Plugins receive this read-only for queue building and validation.
    """

    id: UUID
    workspace_id: UUID
    dataset_name: str
    dataset_slug: str
    source_type: str
    record_kind: str | None = None
    record_count: int | None = None
    labeled_count: int | None = None
    health_status: str | None = None


class ModelProfile(BaseModel):
    """A configured model endpoint.

    Maps to the ``model_profiles`` table.
    """

    id: UUID
    model_profile_slug: str
    provider_type: str  # openai_compatible | openrouter | ollama | anthropic | custom
    model_identifier: str
    transport: str
    supports_structured_output: bool = False
    supports_tool_use: bool = False
    context_window: int | None = None
    cost_per_input_token: float | None = None
    cost_per_output_token: float | None = None
    is_available: bool | None = None


# ---------------------------------------------------------------------------
# Result types returned by plugin methods
# ---------------------------------------------------------------------------


class ValidationError(BaseModel):
    """A single validation error."""

    field: str | None = None
    message: str
    code: str = ""


class ValidationWarning(BaseModel):
    """A single validation warning."""

    field: str | None = None
    message: str
    code: str = ""


class ValidationResult(BaseModel):
    """Outcome of a validation check."""

    is_valid: bool
    errors: list[ValidationError] = []
    warnings: list[ValidationWarning] = []


class ValidationCheckResult(BaseModel):
    """Result of an individual check within a validation gate."""

    check_name: str
    passed: bool
    message: str
    metric_value: float | None = None
    threshold: float | None = None


class ValidationReport(BaseModel):
    """Full report from a validation gate run."""

    gate_id: str
    status: str  # passed | failed | warning
    summary: str
    checks: list[ValidationCheckResult] = []
    metrics: dict[str, float] = {}
    created_at: datetime | None = None


# ---------------------------------------------------------------------------
# Model provider types (PV-001)
# ---------------------------------------------------------------------------


class HealthStatus(BaseModel):
    """Result of a model provider health check."""

    is_healthy: bool
    latency_ms: int | None = None
    error: str | None = None
    checked_at: datetime | None = None


class ModelInfo(BaseModel):
    """Descriptor for an available model within a provider."""

    model_id: str
    display_name: str
    context_window: int | None = None
    supports_structured_output: bool = False
    supports_logprobs: bool = False
    cost_per_input_token: float | None = None
    cost_per_output_token: float | None = None


class CompletionResult(BaseModel):
    """Response from a model completion call."""

    content: str
    parsed: dict[str, Any] | None = None
    finish_reason: str | None = None  # stop | length | tool_calls | content_filter
    tokens_input: int = 0
    tokens_output: int = 0
    latency_ms: int = 0
    model_id: str = ""
    logprobs: list[dict[str, Any]] | None = None


class CompletionChunk(BaseModel):
    """A single chunk in a streaming completion."""

    delta: str
    finish_reason: str | None = None
    tokens_so_far: int = 0


class CostEstimate(BaseModel):
    """Estimated cost for a model call."""

    input_cost: float
    output_cost: float
    total_cost: float
    currency: str = "USD"


class Message(BaseModel):
    """A single message in a chat completion prompt."""

    role: str  # system | user | assistant | tool
    content: str
    name: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


# ---------------------------------------------------------------------------
# Rendering / layout types
# ---------------------------------------------------------------------------


class ColumnDefinition(BaseModel):
    """Column specification for a table/list view."""

    key: str
    """Field path to extract from the record, e.g. ``stable_fields.sentiment``."""

    label: str
    """Display header text."""

    column_type: str = "text"
    """Render type: text, number, badge, progress, date, json."""

    width: int | None = None
    """Preferred width in pixels (None = auto)."""

    sortable: bool = True
    filterable: bool = True


class LayoutSection(BaseModel):
    """A section within a detail or review layout."""

    section_id: str
    title: str
    section_type: str  # fields | json | text | markdown | custom
    fields: list[str] | None = None
    config: dict[str, Any] | None = None
    collapse: bool = False


class LayoutSpec(BaseModel):
    """Full layout specification for a detail or review screen."""

    sections: list[LayoutSection] = []
    sidebar: list[LayoutSection] | None = None


# ---------------------------------------------------------------------------
# Review / queue types
# ---------------------------------------------------------------------------


class ReviewTask(BaseModel):
    """A single item in a review queue.

    Maps to the ``review_tasks`` table. Plugins build these; the core
    persists and manages claim state.
    """

    record_id: UUID
    task_schema_id: UUID
    dataset_id: UUID
    priority: int = 0
    priority_reason: str = ""
    is_overlap: bool = False
    is_calibration: bool = False


# ---------------------------------------------------------------------------
# Disagreement / adjudication types
# ---------------------------------------------------------------------------


class Disagreement(BaseModel):
    """A detected disagreement on a single record."""

    record_id: UUID
    conflicting_event_ids: list[UUID] = []
    disagreement_type: str  # inter_annotator | human_agent | field_level
    fields_in_conflict: list[str] = []
    severity: str = "medium"  # low | medium | high
    details: dict[str, Any] | None = None


class ResolutionSuggestion(BaseModel):
    """An AI-assisted suggestion for resolving a disagreement."""

    suggested_labels: dict[str, Any] = {}
    confidence: float
    rationale: str
    source_evidence: list[str] | None = None


# ---------------------------------------------------------------------------
# Export types
# ---------------------------------------------------------------------------


class ExportArtifact(BaseModel):
    """The output of an export packager."""

    data: bytes | None = None
    """In-memory export content (mutually exclusive with ``path``)."""

    path: Path | None = None
    """Path to the exported file on disk (mutually exclusive with ``data``)."""

    format: str = ""
    """Export format identifier, e.g. ``jsonl``, ``parquet``."""

    record_count: int = 0
    checksum: str = ""
    metadata: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Reference app types
# ---------------------------------------------------------------------------


class WorkflowTemplateDefinition(BaseModel):
    """A workflow template provided by a reference app plugin."""

    template_id: str
    name: str
    description: str
    workflow_yaml: str
    """The YAML content defining the workflow steps."""

    tags: list[str] = []


class ScreenDefinition(BaseModel):
    """A custom screen contribution from a reference app plugin."""

    screen_id: str
    title: str
    route: str
    """React Router path, e.g. ``/depolarize/dashboard``."""

    component_bundle: str
    """Relative path to the ES module bundle, e.g. ``ui/dashboard.mjs``."""

    icon: str = ""
    nav_section: str = "project"
    """Where in the nav sidebar: project | data | review | settings."""

    nav_order: int = 100


class ValidationGateConfig(BaseModel):
    """Configuration for a validation gate contributed by a reference app."""

    gate_id: str
    plugin_id: str
    description: str
    required_for_release: bool = True
    config: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Prompt / agent types
# ---------------------------------------------------------------------------


class PromptTemplate(BaseModel):
    """A prompt template for agent labeling."""

    id: UUID
    name: str
    version: str
    system_prompt: str
    user_prompt_template: str
    """Jinja2 template. Variables: ``record``, ``task_schema``,
    ``few_shot_examples``."""

    few_shot_strategy: str = "none"
    """none | static | dynamic_similar | dynamic_diverse."""

    output_schema: dict[str, Any] | None = None
    """JSON Schema for structured output when the model supports it."""


# ---------------------------------------------------------------------------
# Plugin lifecycle types  (PL-017)
# ---------------------------------------------------------------------------


class CompatibilityResult(BaseModel):
    """Outcome of a plugin compatibility check."""

    is_compatible: bool
    reason: str = ""
    suggested_action: str = ""  # upgrade_plugin | upgrade_core | none


class MigrationResult(BaseModel):
    """Outcome of a plugin migration between versions."""

    success: bool
    from_version: str = ""
    to_version: str = ""
    actions_taken: list[str] = []
    error: str = ""


class CleanupResult(BaseModel):
    """Outcome of plugin uninstall cleanup."""

    success: bool
    files_removed: list[str] = []
    warnings: list[str] = []


# ---------------------------------------------------------------------------
# Plugin manifest and capability contract  (PL-019)
# ---------------------------------------------------------------------------


class PluginCapability(BaseModel):
    """Describes a single capability provided by a plugin."""

    capability_type: str
    """The protocol name: ``data_loader``, ``task_type``, ``model_provider``, etc."""

    identifier: str
    """Capability-specific identifier (e.g., format name, task type id, gate id)."""

    description: str = ""
    """Human-readable description of what this capability provides."""

    config_schema: dict[str, Any] | None = None
    """JSON Schema for capability-specific configuration."""


class PluginManifest(BaseModel):
    """Full manifest describing a plugin's identity and capabilities.

    Provides richer introspection than ``PluginMetadata`` alone, listing
    all supported schemas, tasks, renderers, export formats, validation
    hooks, and job/command surfaces.
    """

    plugin_id: str
    """Must match ``PluginMetadata.plugin_id``."""

    version: str
    """Must match ``PluginMetadata.version``."""

    entrypoint: str
    """Python dotted path to the ``register`` function."""

    capabilities: list[PluginCapability] = []
    """All capabilities this plugin registers."""

    supported_task_types: list[str] = []
    """Task type identifiers this plugin works with."""

    supported_formats: list[str] = []
    """Data or export format identifiers this plugin handles."""

    ui_components: dict[str, str] = {}
    """Map of component slot to relative bundle path,
    e.g. ``{"record_renderer": "ui/renderer.mjs"}``."""

    config_schema: dict[str, Any] | None = None
    """JSON Schema for plugin-level settings in the workspace manifest."""

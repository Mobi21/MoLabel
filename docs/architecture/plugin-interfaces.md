# MoLabel Plugin Interface Specification

Date: 2026-03-23
Status: Draft
Related: PRD Section 17

## Overview

MoLabel uses Python `typing.Protocol` classes to define plugin interfaces. Plugins implement these protocols and register via Python entry points. The core never imports plugin code directly -- it discovers plugins through the protocol contract.

All protocol definitions live in `molabel.core.plugins.protocols`. Shared domain types live in `molabel.core.types`. Plugin authors depend only on `molabel-core` for type information; they never import from `molabel-app` or other plugins.

> **Canonical types:** Field names, enum values, and domain object schemas in this document must match `data-model.md`. If there is a discrepancy, `data-model.md` is authoritative for domain objects; this document is authoritative for plugin interface shapes.

## Plugin Discovery

Plugins register via `pyproject.toml` entry points:

```toml
[project.entry-points."molabel.plugins"]
my_plugin = "my_package.plugin:register"
```

The `register` function receives a `PluginRegistry` and registers one or more capabilities. A single package may register multiple plugin types.

```python
from __future__ import annotations

from molabel.core.plugins.protocols import PluginRegistry


def register(registry: PluginRegistry) -> None:
    from my_package.loader import MyJsonlLoader
    from my_package.task import MySentimentTask

    registry.register_data_loader(MyJsonlLoader())
    registry.register_task_type(MySentimentTask())
```

At startup the core calls `importlib.metadata.entry_points(group="molabel.plugins")`, loads each entry point, and invokes the callable with a concrete `PluginRegistry`. Loading errors are caught per-plugin and surfaced in the plugin management UI without preventing other plugins from loading.

## Plugin Registry

```python
from __future__ import annotations

from typing import Protocol

from molabel.core.plugins.protocols import (
    AdjudicationPlugin,
    AgentAdapterPlugin,
    DataLoaderPlugin,
    ExportPackagerPlugin,
    ModelProviderPlugin,
    RecordRendererPlugin,
    ReferenceAppPlugin,
    ReviewWorkflowPlugin,
    TaskTypePlugin,
    ValidationPlugin,
)


class PluginRegistry(Protocol):
    """Central registry where plugins declare their capabilities at startup."""

    def register_data_loader(self, loader: DataLoaderPlugin) -> None: ...
    def register_task_type(self, task_type: TaskTypePlugin) -> None: ...
    def register_model_provider(self, provider: ModelProviderPlugin) -> None: ...
    def register_record_renderer(self, renderer: RecordRendererPlugin) -> None: ...
    def register_review_workflow(self, workflow: ReviewWorkflowPlugin) -> None: ...
    def register_adjudication(self, adjudication: AdjudicationPlugin) -> None: ...
    def register_agent_adapter(self, adapter: AgentAdapterPlugin) -> None: ...
    def register_validation(self, validation: ValidationPlugin) -> None: ...
    def register_export_packager(self, packager: ExportPackagerPlugin) -> None: ...
    def register_reference_app(self, app: ReferenceAppPlugin) -> None: ...
```

## Common Types

These dataclasses are the shared vocabulary used across all plugin interfaces. They live in `molabel.core.types` and mirror the canonical data model.

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID


# ---------------------------------------------------------------------------
# Plugin metadata -- every plugin exposes this
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PluginMetadata:
    """Identity and compatibility information declared by every plugin."""

    plugin_id: str
    """Globally unique dotted identifier, e.g. ``molabel.loaders.jsonl``."""

    version: str
    """SemVer string, e.g. ``0.1.0``."""

    compatible_core: str
    """PEP 440 version specifier for ``molabel-core``, e.g. ``>=0.1,<1.0``."""

    description: str
    """One-line human-readable summary shown in the plugin management UI."""

    author: str = ""
    """Optional author or organization name."""

    url: str = ""
    """Optional link to documentation or source repository."""

    tags: list[str] = field(default_factory=list)
    """Freeform tags for search and filtering in the plugin browser."""


# ---------------------------------------------------------------------------
# Domain value objects (simplified projections of the canonical data model)
# ---------------------------------------------------------------------------

@dataclass
class Record:
    """A single data item within a dataset.

    Maps to the ``records`` table in the canonical data model.
    ``stable_fields`` contains schema-normalized values;
    ``payload`` contains the full original data.
    """

    id: UUID
    dataset_id: UUID
    external_id: str | None
    stable_fields: dict[str, Any]
    payload: dict[str, Any]
    record_kind: str | None
    source_metadata: dict[str, Any] | None = None
    flags: dict[str, Any] | None = None


@dataclass
class LabelFieldDefinition:
    """Specification for a single label field within a task schema."""

    name: str
    """Field identifier, e.g. ``sentiment``."""

    field_type: str
    """One of: ordinal, categorical, text, numeric, bool, multi_select, json."""

    required: bool = True

    options: list[str] | None = None
    """For categorical / ordinal / multi_select: the allowed values in order."""

    scale_min: float | None = None
    """For numeric / ordinal: minimum value."""

    scale_max: float | None = None
    """For numeric / ordinal: maximum value."""

    description: str = ""
    """Instruction text shown next to this field in the review form."""

    default: Any = None
    """Default value pre-filled in new review forms."""


@dataclass
class TaskSchema:
    """Configuration for a labeling task.

    Maps to the ``task_schemas`` table. Plugins receive this read-only; only
    the core may persist changes.
    """

    id: UUID
    task_schema_slug: str
    version: int
    task_type: str
    title: str
    label_fields: list[LabelFieldDefinition]
    required_fields: list[str]
    optional_fields: list[str]
    blind_review_policy: str
    instructions: str | None = None
    overlap_policy: dict[str, Any] | None = None
    adjudication_policy: dict[str, Any] | None = None
    export_mapping: dict[str, Any] | None = None


@dataclass
class ReviewEvent:
    """A single review action (human, agent, or import).

    Maps to the ``review_events`` table.  Append-only -- plugins never
    mutate existing events.
    """

    id: UUID
    record_id: UUID
    reviewer_id: UUID | None
    source: str  # human | agent | import
    decision: str | None  # accept, accept_ai, edit_ai, reject_ai, correct, reject, skip
    labels: dict[str, Any]
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


@dataclass
class AgentOutput:
    """Structured output from an agent run for a single record.

    Maps to the ``agent_outputs`` table.
    """

    id: UUID
    agent_run_id: UUID
    record_id: UUID
    task_schema_id: UUID
    output_type: str  # label | critique | normalization
    labels: dict[str, Any]
    raw_response: dict[str, Any] | None = None
    confidence_self_reported: float | None = None
    confidence_self_consistency: float | None = None  # Agreement rate across multiple runs (0.0-1.0)
    confidence_logprobs: float | None = None
    composite_confidence: float | None = None
    tokens_input: int | None = None
    tokens_output: int | None = None
    latency_ms: int | None = None
    validation_passed: bool = True
    validation_errors: list[dict[str, Any]] | None = None
    created_at: datetime | None = None


@dataclass
class Adjudication:
    """Resolution of a disagreement between reviewers or between human and agent.

    Maps to the ``adjudications`` table.
    """

    id: UUID
    record_id: UUID
    dataset_id: UUID
    task_schema_id: UUID
    adjudicator_id: UUID
    conflicting_event_ids: list[UUID]
    resolution: str  # preserve_disagreement | resolve | downgrade | exclude
    resolved_labels: dict[str, Any] | None = None
    rationale: str | None = None
    metadata: dict[str, Any] | None = None
    created_at: datetime | None = None


@dataclass
class Dataset:
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


@dataclass
class ModelProfile:
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

@dataclass
class ValidationResult:
    """Outcome of a validation check."""

    is_valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationWarning] = field(default_factory=list)


@dataclass
class ValidationError:
    field: str | None
    message: str
    code: str = ""


@dataclass
class ValidationWarning:
    field: str | None
    message: str
    code: str = ""


@dataclass
class ValidationReport:
    """Full report from a validation gate run."""

    gate_id: str
    status: str  # passed | failed | warning
    summary: str
    checks: list[ValidationCheckResult] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    created_at: datetime | None = None


@dataclass
class ValidationCheckResult:
    check_name: str
    passed: bool
    message: str
    metric_value: float | None = None
    threshold: float | None = None


@dataclass
class HealthStatus:
    """Result of a model provider health check."""

    is_healthy: bool
    latency_ms: int | None = None
    error: str | None = None
    checked_at: datetime | None = None


@dataclass
class ModelInfo:
    """Descriptor for an available model within a provider."""

    model_id: str
    display_name: str
    context_window: int | None = None
    supports_structured_output: bool = False
    supports_logprobs: bool = False
    cost_per_input_token: float | None = None
    cost_per_output_token: float | None = None


@dataclass
class CompletionResult:
    """Response from a model completion call."""

    content: str
    parsed: dict[str, Any] | None = None
    finish_reason: str | None = None  # stop | length | tool_calls | content_filter
    tokens_input: int = 0
    tokens_output: int = 0
    latency_ms: int = 0
    model_id: str = ""
    logprobs: list[dict[str, Any]] | None = None


@dataclass
class CompletionChunk:
    """A single chunk in a streaming completion."""

    delta: str
    finish_reason: str | None = None
    tokens_so_far: int = 0


@dataclass
class CostEstimate:
    """Estimated cost for a model call."""

    input_cost: float
    output_cost: float
    total_cost: float
    currency: str = "USD"


@dataclass
class Message:
    """A single message in a chat completion prompt."""

    role: str  # system | user | assistant | tool
    content: str
    name: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


@dataclass
class ColumnDefinition:
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


@dataclass
class LayoutSection:
    """A section within a detail or review layout."""

    section_id: str
    title: str
    section_type: str  # fields | json | text | markdown | custom
    fields: list[str] | None = None
    config: dict[str, Any] | None = None
    collapse: bool = False


@dataclass
class LayoutSpec:
    """Full layout specification for a detail or review screen."""

    sections: list[LayoutSection]
    sidebar: list[LayoutSection] | None = None


@dataclass
class ReviewTask:
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


@dataclass
class Disagreement:
    """A detected disagreement on a single record."""

    record_id: UUID
    conflicting_event_ids: list[UUID]
    disagreement_type: str  # inter_annotator | human_agent | field_level
    fields_in_conflict: list[str]
    severity: str = "medium"  # low | medium | high
    details: dict[str, Any] | None = None


@dataclass
class ResolutionSuggestion:
    """An AI-assisted suggestion for resolving a disagreement."""

    suggested_labels: dict[str, Any]
    confidence: float
    rationale: str
    source_evidence: list[str] | None = None


@dataclass
class ExportArtifact:
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


@dataclass
class WorkflowTemplateDefinition:
    """A workflow template provided by a reference app plugin."""

    template_id: str
    name: str
    description: str
    workflow_yaml: str
    """The YAML content defining the workflow steps."""

    tags: list[str] = field(default_factory=list)


@dataclass
class ScreenDefinition:
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


@dataclass
class ValidationGateConfig:
    """Configuration for a validation gate contributed by a reference app."""

    gate_id: str
    plugin_id: str
    description: str
    required_for_release: bool = True
    config: dict[str, Any] | None = None


@dataclass
class PromptTemplate:
    """A prompt template for agent labeling."""

    id: UUID
    name: str
    version: str
    system_prompt: str
    user_prompt_template: str
    """A Jinja2 template string. Available variables: ``record``, ``task_schema``, ``few_shot_examples``."""

    few_shot_strategy: str = "none"
    """none | static | dynamic_similar | dynamic_diverse."""

    output_schema: dict[str, Any] | None = None
    """JSON Schema for structured output when the model supports it."""

# Note: This is the plugin-facing view of prompt templates. The canonical storage
# schema in data-model.md has additional fields (instruction_patches,
# correction_batch_ids, etc.). Plugins receive this simplified view through the
# agent adapter interface.


# ---------------------------------------------------------------------------
# Plugin lifecycle types
# ---------------------------------------------------------------------------

@dataclass
class PluginContext:
    """Contextual information passed to plugin lifecycle hooks."""

    core_version: str
    workspace_root: Path | None
    plugin_data_dir: Path | None
    """Per-plugin writable directory at ``workbench/plugins/{plugin_id}/``."""

    settings: dict[str, Any] | None = None
    """Plugin-specific settings from the workspace manifest."""


@dataclass
class CompatibilityResult:
    """Outcome of a plugin compatibility check."""

    is_compatible: bool
    reason: str = ""
    suggested_action: str = ""  # upgrade_plugin | upgrade_core | none


@dataclass
class MigrationResult:
    """Outcome of a plugin migration between versions."""

    success: bool
    from_version: str = ""
    to_version: str = ""
    actions_taken: list[str] = field(default_factory=list)
    error: str = ""


@dataclass
class CleanupResult:
    """Outcome of plugin uninstall cleanup."""

    success: bool
    files_removed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
```

---

## Plugin Interfaces

Each interface below is a `typing.Protocol`. A plugin class satisfies the protocol by implementing the required methods -- no explicit inheritance or registration decorator is needed (structural subtyping).

All protocols use `from __future__ import annotations` for forward reference support.

---

### DataLoaderPlugin

Responsible for reading external data sources and yielding normalized records. Invoked during `data_ingest` workflow steps.

```python
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any, Protocol

from molabel.core.types import PluginMetadata, Record


class DataLoaderPlugin(Protocol):
    """Loads records from external data sources."""

    @property
    def metadata(self) -> PluginMetadata:
        """Plugin identity and compatibility information."""
        ...

    @property
    def supported_formats(self) -> list[str]:
        """File extensions or format identifiers this loader handles.

        Examples: ``["jsonl", "json", "csv"]``, ``["huggingface"]``.
        """
        ...

    def can_load(self, path: Path) -> bool:
        """Return True if this loader can handle the given file or directory.

        Called during plugin selection. The core iterates registered loaders
        and uses the first one where ``can_load`` returns True. Implementations
        should be fast (check extension, magic bytes, or directory markers)
        and must not read the entire file.
        """
        ...

    def load_records(
        self,
        path: Path,
        config: dict[str, Any],
    ) -> Iterator[Record]:
        """Yield records from the data source.

        Args:
            path: Absolute path to the file or directory.
            config: Loader-specific configuration from the workflow step
                    (e.g., ``{"delimiter": ",", "id_column": "uid"}``).

        Yields:
            Record instances with at minimum ``stable_fields`` populated.
            The ``id`` field may use a sentinel UUID; the core assigns final
            IDs based on the dataset's ``canonical_id_strategy``.

        Raises:
            ValueError: If the file cannot be parsed.
        """
        ...

    def get_schema(self, path: Path) -> dict[str, Any]:
        """Return the inferred schema for the data source.

        Returns a JSON-Schema-compatible dict describing the fields, types,
        and sample values found in the source. Used by the schema mapping UI
        to help users configure ``data_normalize`` steps.
        """
        ...

    def estimate_record_count(self, path: Path) -> int | None:
        """Return estimated record count, or None if unknown.

        Used for progress bars and cost estimation. Implementations may
        count newlines, read Parquet metadata, or return None if the cost
        of counting is too high.
        """
        ...
```

---

### TaskTypePlugin

Defines a labeling task type (e.g., ordinal text review, pairwise ranking, extraction). The core ships with built-in task types in `molabel-plugins`; third-party packages can register additional ones.

```python
from __future__ import annotations

from typing import Any, Protocol

from molabel.core.types import (
    LabelFieldDefinition,
    PluginMetadata,
    TaskSchema,
    ValidationResult,
)


class TaskTypePlugin(Protocol):
    """Defines the shape and behavior of a labeling task type."""

    @property
    def metadata(self) -> PluginMetadata:
        """Plugin identity and compatibility information."""
        ...

    @property
    def task_type_id(self) -> str:
        """Unique task type identifier.

        This value is stored in ``TaskSchema.task_type`` and must be stable
        across versions. Examples: ``ordinal_text_review``,
        ``pairwise_ranking``, ``extraction``.
        """
        ...

    def get_label_field_definitions(self) -> list[LabelFieldDefinition]:
        """Return the default label fields for this task type.

        These serve as a starting template when a user creates a new task
        schema of this type. Users may customize the fields afterward.
        """
        ...

    def get_default_review_form_schema(self) -> dict[str, Any]:
        """Return a JSON Schema describing the review form for this task type.

        The React frontend renders this schema using a generic form renderer
        (Tier 1 UI). Plugins that need custom rendering should also register
        a ``RecordRendererPlugin`` with a Tier 2 component bundle.
        """
        ...

    def validate_labels(
        self,
        labels: dict[str, Any],
        task_schema: TaskSchema,
    ) -> ValidationResult:
        """Validate a set of labels against the task schema.

        Called before persisting a review event or agent output. The core
        rejects submissions where ``is_valid`` is False and surfaces the
        errors in the review UI.

        Args:
            labels: The label values keyed by field name.
            task_schema: The active task schema (includes field definitions,
                         allowed values, required fields).
        """
        ...

    def get_default_agent_prompt_template(self) -> str:
        """Return a Jinja2 prompt template suitable for this task type.

        Used as the starting point when a user creates an agent run for a
        task of this type. The template may reference ``{{ record }}``,
        ``{{ task_schema }}``, and ``{{ few_shot_examples }}``.
        """
        ...

    def get_export_columns(self) -> list[dict[str, str]]:
        """Return the default export column mapping for this task type.

        Each dict has keys ``source`` (field path in labels) and ``target``
        (column name in export). Used to configure ``ExportPackagerPlugin``
        when no custom export mapping is defined.
        """
        ...
```

---

### ModelProviderPlugin

Adapts a model hosting backend (OpenAI-compatible API, Ollama, Anthropic, OpenRouter, etc.) to MoLabel's uniform completion interface. The core uses model providers for agent runs and AI-assisted features.

```python
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

from molabel.core.types import (
    CompletionChunk,
    CompletionResult,
    CostEstimate,
    HealthStatus,
    Message,
    ModelInfo,
    PluginMetadata,
)


class ModelProviderPlugin(Protocol):
    """Adapts a model hosting backend to MoLabel's completion interface."""

    @property
    def metadata(self) -> PluginMetadata:
        """Plugin identity and compatibility information."""
        ...

    @property
    def provider_type(self) -> str:
        """Provider type identifier matching ``ProviderType`` enum values.

        One of: ``openai_compatible``, ``openrouter``, ``ollama``,
        ``anthropic``, ``custom``.
        """
        ...

    def check_health(self) -> HealthStatus:
        """Probe the provider endpoint and return availability status.

        Called during provider auto-detection and periodic health checks
        shown in the provider management UI.
        """
        ...

    def list_models(self) -> list[ModelInfo]:
        """Return the models available from this provider.

        For remote APIs this may call a ``/models`` endpoint. For Ollama
        it lists locally pulled models. The result populates the model
        selection dropdown in the model profile editor.
        """
        ...

    def supports_structured_output(self) -> bool:
        """Return True if this provider supports native JSON schema output.

        When True, the core passes an ``output_schema`` to ``complete()``
        and expects the response to conform. When False, the core falls
        back to prompt-based output formatting with post-hoc parsing.
        """
        ...

    def supports_logprobs(self) -> bool:
        """Return True if this provider can return token log-probabilities.

        Used for log-prob-based confidence scoring in agent outputs.
        """
        ...

    def complete(
        self,
        messages: list[Message],
        model: str,
        *,
        output_schema: dict[str, Any] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
        logprobs: bool = False,
        top_logprobs: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> CompletionResult:
        """Execute a synchronous chat completion.

        Args:
            messages: The conversation history.
            model: Model identifier as known by this provider.
            output_schema: JSON Schema for structured output (provider
                           support required; check ``supports_structured_output``).
            temperature: Sampling temperature (0.0 = deterministic).
            max_tokens: Maximum tokens to generate (None = provider default).
            stop: Stop sequences.
            logprobs: Whether to return log-probabilities.
            top_logprobs: Number of top log-probs per token.
            extra: Provider-specific parameters passed through verbatim.

        Returns:
            CompletionResult with content, token counts, and optional parsed output.

        Raises:
            ProviderError: On network, auth, rate-limit, or content-filter errors.
        """
        ...

    async def stream_complete(
        self,
        messages: list[Message],
        model: str,
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> AsyncIterator[CompletionChunk]:
        """Execute a streaming chat completion.

        Yields chunks as they arrive from the provider. Used for real-time
        progress display in the mission control UI during agent runs.

        Args:
            messages: The conversation history.
            model: Model identifier as known by this provider.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.
            stop: Stop sequences.
            extra: Provider-specific parameters.

        Yields:
            CompletionChunk instances with incremental content deltas.
        """
        ...

    def estimate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        model: str,
    ) -> CostEstimate:
        """Estimate the cost of a completion call.

        Used for pre-run cost estimation in the agent run confirmation
        dialog. Implementations may use hard-coded pricing tables, query
        the provider API, or return zero-cost estimates for local models.
        """
        ...
```

---

### RecordRendererPlugin

Controls how records appear in the data explorer table, record detail inspector, and review screen. The default rendering uses JSON schema declarations (Tier 1); plugins may optionally provide custom React component bundles (Tier 2, see **Plugin UI Contract** section below).

```python
from __future__ import annotations

from typing import Protocol

from molabel.core.types import (
    ColumnDefinition,
    LayoutSpec,
    PluginMetadata,
    Record,
)


class RecordRendererPlugin(Protocol):
    """Defines how records are displayed across MoLabel's UI surfaces."""

    @property
    def metadata(self) -> PluginMetadata:
        """Plugin identity and compatibility information."""
        ...

    def get_list_columns(self, record_kind: str) -> list[ColumnDefinition]:
        """Return column definitions for the data explorer table view.

        Args:
            record_kind: The record kind tag (e.g., ``text_turn``,
                         ``conversation_window``). Allows a single plugin
                         to handle multiple record types.

        Returns:
            Ordered list of columns. The core merges these with system
            columns (id, status, confidence) and renders via TanStack Table.
        """
        ...

    def get_detail_layout(self, record_kind: str) -> LayoutSpec:
        """Return the layout for the record detail inspector panel.

        The layout is rendered generically by the core. Each section may
        display fields, JSON, markdown, or plain text.
        """
        ...

    def get_review_layout(self, record_kind: str) -> LayoutSpec:
        """Return the layout for the review screen's record pane.

        This controls the left side of the review screen (the record being
        reviewed). The right side (label form) is controlled by the
        ``TaskTypePlugin``'s review form schema.
        """
        ...

    def render_preview(self, record: Record) -> str:
        """Return a plain-text or HTML snippet previewing the record.

        Used in hover tooltips, search result cards, and notification
        summaries. Must be safe for rendering (the core sanitizes HTML).
        Keep output under 500 characters.
        """
        ...
```

---

### ReviewWorkflowPlugin

Manages the construction and behavior of human review queues. Invoked during `human_review`, `human_calibration`, and overlap assignment workflow steps.

```python
from __future__ import annotations

from typing import Any, Protocol

from molabel.core.types import (
    Dataset,
    PluginMetadata,
    ReviewEvent,
    ReviewTask,
    TaskSchema,
    ValidationResult,
)


class ReviewWorkflowPlugin(Protocol):
    """Builds and manages human review queues."""

    @property
    def metadata(self) -> PluginMetadata:
        """Plugin identity and compatibility information."""
        ...

    def build_queue(
        self,
        dataset: Dataset,
        task_schema: TaskSchema,
        config: dict[str, Any],
    ) -> list[ReviewTask]:
        """Build an ordered list of review tasks for a review step.

        Args:
            dataset: The target dataset.
            task_schema: The active task schema.
            config: Step-specific configuration from the workflow YAML,
                    including keys like ``sample_strategy`` (random,
                    low_confidence, stratified, all), ``sample_size``,
                    ``priority_rules``, and ``exclude_reviewed``.

        Returns:
            Ordered list of ReviewTask instances. The core persists these
            and manages claim/release lifecycle.
        """
        ...

    def validate_submission(
        self,
        review_event: ReviewEvent,
        task_schema: TaskSchema,
    ) -> ValidationResult:
        """Validate a review submission before persisting.

        Called after ``TaskTypePlugin.validate_labels()`` passes. This
        method can enforce workflow-level rules such as minimum review
        time, rationale requirements for rejections, or calibration
        consistency checks.
        """
        ...

    def compute_overlap_assignments(
        self,
        dataset: Dataset,
        config: dict[str, Any],
    ) -> list[ReviewTask]:
        """Generate overlap review tasks for inter-annotator agreement.

        Args:
            dataset: The target dataset.
            config: Overlap configuration from the task schema's
                    ``overlap_policy``, including ``mode`` (random,
                    stratified, all), ``rate`` (fraction of records
                    to double-review), and ``max_reviewers_per_record``.

        Returns:
            Additional ReviewTask instances with ``is_overlap=True``.
        """
        ...

    def get_calibration_items(
        self,
        dataset: Dataset,
        config: dict[str, Any],
    ) -> list[ReviewTask]:
        """Select records for calibration sessions.

        Calibration items are shown to all reviewers before the main review
        begins, with known correct answers, to align reviewer understanding.

        Args:
            dataset: The target dataset.
            config: Calibration configuration including ``size`` (number of
                    items), ``source`` (gold_set, expert_reviewed, random),
                    and ``agreement_threshold`` (minimum required agreement
                    to pass calibration).

        Returns:
            ReviewTask instances with ``is_calibration=True``.
        """
        ...
```

---

### AdjudicationPlugin

Detects disagreements between reviewers (or between humans and agents) and supports resolution. Invoked during `human_adjudication` workflow steps.

```python
from __future__ import annotations

from typing import Any, Protocol

from molabel.core.types import (
    Adjudication,
    AgentOutput,
    Disagreement,
    LayoutSpec,
    PluginMetadata,
    Record,
    ResolutionSuggestion,
    ReviewEvent,
    ValidationResult,
)


class AdjudicationPlugin(Protocol):
    """Detects and helps resolve disagreements in review data."""

    @property
    def metadata(self) -> PluginMetadata:
        """Plugin identity and compatibility information."""
        ...

    def detect_disagreements(
        self,
        review_events_per_record: dict[str, list[ReviewEvent]],
    ) -> list[Disagreement]:
        """Identify records where reviewers disagree.

        Args:
            review_events_per_record: Mapping of record ID (as string) to
                the list of review events for that record. Includes both
                human and agent events.

        Returns:
            List of Disagreement instances, one per conflicting record.
            The core uses this to build the adjudication queue.
        """
        ...

    def get_adjudication_layout(
        self,
        record: Record,
        reviews: list[ReviewEvent],
    ) -> LayoutSpec:
        """Return the layout for the adjudication screen.

        The layout should present the conflicting reviews side by side
        and highlight the fields in disagreement.
        """
        ...

    def validate_resolution(
        self,
        resolution: Adjudication,
        reviews: list[ReviewEvent],
    ) -> ValidationResult:
        """Validate an adjudication resolution before persisting.

        Checks that the resolution is consistent with the conflicting
        events (e.g., ``resolved_labels`` covers all disputed fields,
        ``conflicting_event_ids`` match the actual disagreement).
        """
        ...

    def compute_resolution_suggestion(
        self,
        reviews: list[ReviewEvent],
        agent_outputs: list[AgentOutput],
    ) -> ResolutionSuggestion | None:
        """Generate an AI-assisted resolution suggestion.

        Uses the conflicting reviews and any available agent outputs to
        propose a resolution. Returns None if the plugin cannot suggest
        a resolution (e.g., insufficient evidence).

        The suggestion is shown to the adjudicator as a starting point;
        it is never auto-applied.
        """
        ...
```

---

### AgentAdapterPlugin

Bridges the gap between MoLabel's record/task model and the specific prompt engineering required for a given agent role. Each adapter handles prompt construction, output parsing, and confidence extraction for one agent role.

```python
from __future__ import annotations

from typing import Any, Protocol

from molabel.core.types import (
    AgentOutput,
    Message,
    PluginMetadata,
    PromptTemplate,
    Record,
    TaskSchema,
)


class AgentAdapterPlugin(Protocol):
    """Adapts record data and task schemas into model prompts and parses outputs."""

    @property
    def metadata(self) -> PluginMetadata:
        """Plugin identity and compatibility information."""
        ...

    @property
    def agent_role(self) -> str:
        """The agent role this adapter supports.

        Must match one of the ``AgentRole`` enum values: ``proposer``,
        ``critic``, ``normalizer``, ``disagreement_flagger``, ``deduper``,
        ``rubric_judge``, ``edge_case_miner``, ``export_prep``.
        """
        ...

    def build_prompt(
        self,
        record: Record,
        task_schema: TaskSchema,
        prompt_template: PromptTemplate,
        few_shot_examples: list[dict[str, Any]] | None = None,
    ) -> list[Message]:
        """Construct the message list for a model completion call.

        Args:
            record: The record to label.
            task_schema: The active task schema.
            prompt_template: The prompt template with system and user
                             templates (Jinja2).
            few_shot_examples: Optional list of example dicts with keys
                               ``record`` and ``labels`` for in-context learning.

        Returns:
            Ordered list of Message instances ready for
            ``ModelProviderPlugin.complete()``.
        """
        ...

    def parse_output(
        self,
        raw_response: dict[str, Any],
        task_schema: TaskSchema,
    ) -> AgentOutput:
        """Parse raw model output into a structured AgentOutput.

        Args:
            raw_response: The raw response dict from the model provider,
                          including at minimum ``{"content": "..."}`` and
                          optionally ``{"parsed": {...}}`` for structured
                          output.
            task_schema: The active task schema for validation context.

        Returns:
            An AgentOutput with ``labels`` populated. The ``id``,
            ``agent_run_id``, and ``record_id`` fields may be sentinel
            values; the core assigns final IDs.

        Raises:
            ValueError: If the response cannot be parsed into valid labels.
        """
        ...

    def compute_confidence(
        self,
        raw_response: dict[str, Any],
    ) -> float:
        """Extract or compute a confidence score from the raw response.

        Implementations may use self-reported confidence from the model
        output, log-probability analysis, or heuristic scoring. The
        returned value must be in the range [0.0, 1.0].
        """
        ...

    def supports_batch(self) -> bool:
        """Return True if this adapter can process multiple records per call.

        Batch adapters receive multiple records in a single prompt (e.g.,
        for models that handle batched JSON arrays). When False, the core
        calls ``build_prompt`` once per record.
        """
        ...

    def batch_size_limit(self) -> int:
        """Return the maximum number of records per batch call.

        Only meaningful when ``supports_batch()`` returns True. The core
        will not exceed this limit. Return 1 for non-batch adapters.
        """
        ...
```

---

### ValidationPlugin

Implements a validation gate that checks dataset quality, completeness, or readiness before allowing workflow progression or release. Invoked during `quality_check` and `release_validation` workflow steps.

```python
from __future__ import annotations

from typing import Any, Protocol

from molabel.core.types import (
    Dataset,
    ExportArtifact,
    PluginMetadata,
    ValidationReport,
)


class ValidationPlugin(Protocol):
    """Implements a validation gate for quality and release checks."""

    @property
    def metadata(self) -> PluginMetadata:
        """Plugin identity and compatibility information."""
        ...

    @property
    def gate_id(self) -> str:
        """Unique identifier for this validation gate.

        Referenced in workflow YAML configs and reference app readiness
        gate lists. Example: ``min_agreement_check``,
        ``depolarize.release_readiness``.
        """
        ...

    def validate(
        self,
        dataset: Dataset,
        export_artifact: ExportArtifact | None,
        config: dict[str, Any],
    ) -> ValidationReport:
        """Run the validation gate and return a report.

        Args:
            dataset: The target dataset.
            export_artifact: The export bundle to validate, or None if
                             this gate runs before export (e.g., during
                             ``quality_check`` steps).
            config: Gate-specific configuration from the workflow step
                    or reference app manifest (e.g., ``{"min_agreement": 0.85,
                    "min_coverage": 0.95, "exclude_flagged": true}``).

        Returns:
            A ValidationReport with status, summary, individual check
            results, and computed metrics.
        """
        ...

    def get_gate_description(self) -> str:
        """Return a human-readable description of what this gate validates.

        Shown in the workflow builder and release readiness dashboard
        to help users understand the purpose of each gate.
        """
        ...

    def get_required_metrics(self) -> list[str]:
        """Return the metric names this gate checks.

        Examples: ``["inter_annotator_agreement", "label_coverage",
        "confidence_floor"]``. Used by the quality dashboard to display
        relevant metrics alongside gate status.
        """
        ...
```

---

### ExportPackagerPlugin

Packages labeled data into distributable formats. Invoked during `export` workflow steps.

```python
from __future__ import annotations

from typing import Any, Protocol

from molabel.core.types import (
    ExportArtifact,
    PluginMetadata,
    Record,
    ReviewEvent,
    ValidationResult,
)


class ExportPackagerPlugin(Protocol):
    """Packages labeled records into distributable export formats."""

    @property
    def metadata(self) -> PluginMetadata:
        """Plugin identity and compatibility information."""
        ...

    @property
    def supported_formats(self) -> list[str]:
        """Export format identifiers this packager handles.

        Examples: ``["jsonl"]``, ``["parquet", "csv"]``,
        ``["huggingface_hub"]``.
        """
        ...

    def package(
        self,
        records: list[Record],
        labels: dict[str, list[ReviewEvent]],
        config: dict[str, Any],
    ) -> ExportArtifact:
        """Package records and their labels into an export artifact.

        Args:
            records: The records to export.
            labels: Mapping of record ID (as string) to the list of
                    review events for that record. The packager selects
                    which labels to include (e.g., latest accepted, all
                    events, adjudicated only) based on ``config``.
            config: Export configuration from the workflow step, including
                    keys like ``format``, ``destination``, ``columns``,
                    ``include_metadata``, ``include_agent_outputs``.

        Returns:
            An ExportArtifact with either ``data`` (in-memory bytes) or
            ``path`` (written file on disk).
        """
        ...

    def validate_export(
        self,
        artifact: ExportArtifact,
    ) -> ValidationResult:
        """Validate an export artifact after packaging.

        Checks structural integrity (e.g., valid JSONL, readable Parquet),
        completeness (expected record count), and consistency (no
        duplicate IDs, all required columns present).
        """
        ...

    def get_export_schema(self) -> dict[str, Any]:
        """Describe the output format for documentation and UI.

        Returns a JSON-Schema-compatible dict or a descriptive dict with
        keys ``columns`` (list of column dicts with ``name``, ``type``,
        ``description``) and ``format_notes``.
        """
        ...
```

---

### ReferenceAppPlugin

Bundles domain-specific project configuration, workflow templates, custom screens, and readiness gates into a cohesive package. DePolarize is the first reference app; other domain-specific bundles (benchmark creation, red-teaming, etc.) follow the same interface.

```python
from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from molabel.core.types import (
    PluginMetadata,
    ScreenDefinition,
    ValidationGateConfig,
    WorkflowTemplateDefinition,
)


class ReferenceAppPlugin(Protocol):
    """Bundles domain-specific project configuration and workflows."""

    @property
    def metadata(self) -> PluginMetadata:
        """Plugin identity and compatibility information."""
        ...

    @property
    def app_id(self) -> str:
        """Unique reference app identifier.

        Stored in ``Workspace.reference_app``. Examples: ``depolarize``,
        ``benchmark_authority``, ``red_team_review``.
        """
        ...

    def detect_project(self, workspace_path: Path) -> bool:
        """Return True if this reference app can handle the given workspace.

        Called during heuristic project detection (PRD Section 18.10).
        Implementations should check for marker files, directory structure,
        or manifest fields specific to this domain.

        Args:
            workspace_path: Absolute path to the workspace root directory.
        """
        ...

    def get_bootstrap_config(
        self,
        workspace_path: Path,
    ) -> dict[str, Any]:
        """Return default workspace manifest values for this reference app.

        Called when bootstrapping a new project using this reference app.
        The returned dict is merged into ``workbench.project.yaml`` with
        user overrides taking precedence.

        The dict should include keys like ``datasets``, ``task_schemas``,
        ``model_profiles``, ``runtime_profiles``, and ``workflows`` with
        sensible defaults for the domain.
        """
        ...

    def get_project_templates(self) -> list[WorkflowTemplateDefinition]:
        """Return workflow templates specific to this reference app.

        These appear alongside the built-in templates in the workflow
        creation dialog, tagged with this reference app's identity.
        """
        ...

    def get_custom_screens(self) -> list[ScreenDefinition]:
        """Return custom React screen definitions for this reference app.

        Each screen is a Tier 2 custom component loaded via dynamic import.
        The ES module bundles must be placed in
        ``workbench/plugins/{plugin_id}/ui/``.
        """
        ...

    def get_readiness_gates(self) -> list[ValidationGateConfig]:
        """Return validation gate configurations for release readiness.

        Each gate references a ``ValidationPlugin`` by ``gate_id``. The
        core checks all gates before allowing a release to be approved.
        """
        ...
```

---

## Plugin Lifecycle Hooks

All plugins may optionally implement lifecycle hooks. These are defined as a separate protocol; the core checks for method existence at runtime and calls them when present.

```python
from __future__ import annotations

from typing import Protocol

from molabel.core.types import (
    CleanupResult,
    CompatibilityResult,
    MigrationResult,
    PluginContext,
)


class PluginLifecycle(Protocol):
    """Optional lifecycle hooks called by the core at key moments.

    Plugins are not required to implement all methods. The core checks
    for each method's existence via ``hasattr`` and skips missing hooks.
    """

    def on_install(self, context: PluginContext) -> None:
        """Called when the plugin is first installed in a workspace.

        Use this to create plugin-specific directories, seed configuration
        files, or register default settings.
        """
        ...

    def on_activate(self, context: PluginContext) -> None:
        """Called each time the plugin is activated (application startup).

        Use this for runtime initialization: opening connections, warming
        caches, or validating that external dependencies are available.
        """
        ...

    def on_compatibility_check(self, core_version: str) -> CompatibilityResult:
        """Called to verify the plugin is compatible with the running core.

        The core calls this before activation. If the result indicates
        incompatibility, the plugin is disabled and the workspace remains
        readable -- only writes that depend on this plugin are blocked.
        """
        ...

    def on_migrate(
        self,
        from_version: str,
        to_version: str,
    ) -> MigrationResult:
        """Called when the plugin version changes between activations.

        Use this to migrate plugin-specific data, rename configuration
        keys, or update stored schemas.

        Args:
            from_version: The previously installed plugin version.
            to_version: The newly installed plugin version.
        """
        ...

    def on_disable(self, context: PluginContext) -> None:
        """Called when the plugin is disabled (but not uninstalled).

        Use this to release resources while preserving plugin data.
        """
        ...

    def on_uninstall(self, context: PluginContext) -> CleanupResult:
        """Called when the plugin is fully removed from the workspace.

        Use this to clean up plugin-specific files and database entries.
        Return a CleanupResult describing what was removed and any warnings.
        """
        ...
```

---

## Plugin UI Contract (React)

Plugins that provide custom React components (Tier 2 rendering) must conform to the following TypeScript prop contracts. The core wraps each plugin component in a React error boundary so a broken plugin cannot crash the application.

Plugin component bundles are ES modules (`.mjs`) placed in `workbench/plugins/{plugin_id}/ui/`. They are loaded via `React.lazy(() => import(...))`.

Plugin components must NOT import from the core app bundle. Everything is received through props.

```typescript
import type { UUID } from "crypto";

// --- Domain types (mirrors Python types above) ---

interface Record {
  id: string;
  dataset_id: string;
  external_id: string | null;
  stable_fields: Record<string, unknown>;
  payload: Record<string, unknown>;
  record_kind: string | null;
  source_metadata: Record<string, unknown> | null;
  flags: Record<string, unknown> | null;
}

interface TaskSchema {
  id: string;
  task_schema_slug: string;
  version: number;
  task_type: string;
  title: string;
  label_fields: LabelFieldDefinition[];
  required_fields: string[];
  optional_fields: string[];
  blind_review_policy: string;
  instructions: string | null;
}

interface LabelFieldDefinition {
  name: string;
  field_type: string;
  required: boolean;
  options: string[] | null;
  scale_min: number | null;
  scale_max: number | null;
  description: string;
  default_value: unknown;
}

interface AgentOutput {
  id: string;
  agent_run_id: string;
  record_id: string;
  output_type: string;
  labels: Record<string, unknown>;
  composite_confidence: number | null;
  validation_passed: boolean;
}

interface ReviewEvent {
  id: string;
  record_id: string;
  reviewer_id: string | null;
  source: "human" | "agent" | "import";
  decision: string | null;
  labels: Record<string, unknown>;
  rationale: string | null;
  confidence: number | null;
  ai_was_revealed: boolean;
  created_at: string;
}

interface Adjudication {
  id: string;
  record_id: string;
  resolution: string;
  resolved_labels: Record<string, unknown> | null;
  rationale: string | null;
  conflicting_event_ids: string[];
}

// --- Plugin component prop contracts ---

/**
 * Props passed to plugin record renderers.
 *
 * Used in the data explorer detail panel and anywhere a record
 * needs custom visual rendering.
 */
interface PluginRecordRendererProps {
  record: Record;
  taskSchema: TaskSchema;
  onNavigate: (recordId: string) => void;
}

/**
 * Props passed to plugin review forms.
 *
 * Rendered on the right side of the review screen. The plugin
 * owns the entire label input surface.
 */
interface PluginReviewFormProps {
  record: Record;
  taskSchema: TaskSchema;
  agentOutputs: AgentOutput[];
  existingLabels: Record<string, unknown> | null;
  isBlindReview: boolean;
  onSubmit: (labels: Record<string, unknown>, rationale?: string) => void;
  onSaveDraft: (labels: Record<string, unknown>) => void;
  onRevealAI: () => void;
}

/**
 * Props passed to plugin detail panels.
 *
 * Used in the record inspector sidebar and adjudication screens.
 */
interface PluginDetailPanelProps {
  record: Record;
  taskSchema: TaskSchema;
  reviewEvents: ReviewEvent[];
  agentOutputs: AgentOutput[];
  adjudication: Adjudication | null;
}
```

### Component registration

Plugins declare their UI components in the plugin manifest or via the Python interface:

```yaml
# In plugin manifest (workbench.project.yaml or plugin metadata)
ui_components:
  record_renderer: "ui/record-renderer.mjs"
  review_form: "ui/review-form.mjs"
  detail_panel: "ui/detail-panel.mjs"
```

Each `.mjs` file must export a default React component:

```typescript
// ui/record-renderer.mjs
import React from "react";

export default function MyRecordRenderer(props: PluginRecordRendererProps) {
  const { record, taskSchema, onNavigate } = props;
  // ... render the record
}
```

---

## Error Handling

Plugin methods should raise standard Python exceptions. The core catches exceptions at the boundary and translates them:

| Exception | Core behavior |
|-----------|---------------|
| `ValueError` | Surfaced as a validation error in the UI. |
| `FileNotFoundError` | Surfaced as a data source error. The workflow step fails gracefully. |
| `NotImplementedError` | The capability is marked as unsupported. The core falls back to defaults. |
| `TimeoutError` | The operation is retried according to the runtime profile's retry config. |
| Any other exception | Logged with full traceback. The workflow step is marked as failed. The user sees a generic error with a link to logs. |

Plugins must never call `sys.exit()`, mutate global state, or spawn unmanaged background threads.

---

## Versioning and Stability

Plugin interfaces follow these stability rules:

- **Protocol methods are additive.** New optional methods may be added to protocols in minor releases. Existing method signatures are not changed in minor releases.
- **Breaking changes require a major version bump** of `molabel-core` and a deprecation cycle of at least one minor release.
- **The `compatible_core` field in `PluginMetadata`** is checked against the running core version using PEP 440 specifier matching. Incompatible plugins are disabled, not loaded.
- **Plugin data directories** (`workbench/plugins/{plugin_id}/`) are owned by the plugin. The core never reads or writes plugin data except through the plugin's own methods.

---

## Complete Example: Minimal DataLoaderPlugin

```python
"""Example: a minimal JSONL data loader plugin."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

from molabel.core.types import PluginMetadata, Record


class JsonlLoader:
    """Loads records from newline-delimited JSON files."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            plugin_id="example.loaders.jsonl",
            version="0.1.0",
            compatible_core=">=0.1,<1.0",
            description="Loads records from .jsonl files.",
        )

    @property
    def supported_formats(self) -> list[str]:
        return ["jsonl"]

    def can_load(self, path: Path) -> bool:
        return path.is_file() and path.suffix == ".jsonl"

    def load_records(
        self,
        path: Path,
        config: dict[str, Any],
    ) -> Iterator[Record]:
        id_field = config.get("id_field", "id")
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                raw = json.loads(line)
                yield Record(
                    id=uuid4(),
                    dataset_id=uuid4(),  # sentinel; core assigns real ID
                    external_id=raw.get(id_field),
                    stable_fields=raw,
                    payload=raw,
                    record_kind=None,
                )

    def get_schema(self, path: Path) -> dict[str, Any]:
        with path.open() as f:
            first_line = f.readline().strip()
        if not first_line:
            return {"type": "object", "properties": {}}
        sample = json.loads(first_line)
        properties = {}
        for key, value in sample.items():
            if isinstance(value, str):
                properties[key] = {"type": "string"}
            elif isinstance(value, (int, float)):
                properties[key] = {"type": "number"}
            elif isinstance(value, bool):
                properties[key] = {"type": "boolean"}
            elif isinstance(value, list):
                properties[key] = {"type": "array"}
            else:
                properties[key] = {"type": "object"}
        return {"type": "object", "properties": properties}

    def estimate_record_count(self, path: Path) -> int | None:
        try:
            with path.open() as f:
                return sum(1 for line in f if line.strip())
        except OSError:
            return None


def register(registry):
    """Entry point called by molabel-core at startup."""
    registry.register_data_loader(JsonlLoader())
```

Corresponding `pyproject.toml` entry:

```toml
[project.entry-points."molabel.plugins"]
example_jsonl = "example_jsonl.plugin:register"
```

"""Plugin protocol definitions for MoLabel.

Each protocol class defines the interface contract for a plugin capability.
Plugins satisfy a protocol by implementing the required methods — no explicit
inheritance is needed (structural subtyping via ``typing.Protocol``).

All protocols are ``@runtime_checkable`` so that the registry can verify
plugin conformance with ``isinstance()``.

Authoritative spec: ``docs/architecture/plugin-interfaces.md``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from molabel.core.types import (
    Adjudication,
    AgentOutput,
    ColumnDefinition,
    CompletionChunk,
    CompletionResult,
    CostEstimate,
    Dataset,
    Disagreement,
    ExportArtifact,
    HealthStatus,
    LabelFieldDefinition,
    LayoutSpec,
    Message,
    ModelInfo,
    PluginCapability,
    PluginManifest,
    PluginMetadata,
    PromptTemplate,
    Record,
    ResolutionSuggestion,
    ReviewEvent,
    ReviewTask,
    ScreenDefinition,
    TaskSchema,
    ValidationGateConfig,
    ValidationReport,
    ValidationResult,
    WorkflowTemplateDefinition,
)

# ---------------------------------------------------------------------------
# PL-005 — DataLoaderPlugin  (DT-006)
# ---------------------------------------------------------------------------


@runtime_checkable
class DataLoaderPlugin(Protocol):
    """Loads records from external data sources.

    Invoked during ``data_ingest`` workflow steps. Plugins declare which
    file formats they support and yield normalised :class:`Record` instances.
    """

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


# ---------------------------------------------------------------------------
# PL-006 — TaskTypePlugin
# ---------------------------------------------------------------------------


@runtime_checkable
class TaskTypePlugin(Protocol):
    """Defines the shape and behaviour of a labeling task type.

    Task types describe the label fields, review form schema, validation
    logic, and default prompt templates for a category of annotation work
    (e.g. ordinal text review, pairwise ranking, extraction).
    """

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
        schema of this type. Users may customise the fields afterward.
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


# ---------------------------------------------------------------------------
# PV-001 — ModelProviderPlugin
# ---------------------------------------------------------------------------


@runtime_checkable
class ModelProviderPlugin(Protocol):
    """Adapts a model hosting backend to MoLabel's completion interface.

    Supports OpenAI-compatible APIs, Ollama, Anthropic, OpenRouter, and
    custom providers. The core uses model providers for agent runs and
    AI-assisted features.
    """

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


# ---------------------------------------------------------------------------
# PL-007 — RecordRendererPlugin
# ---------------------------------------------------------------------------


@runtime_checkable
class RecordRendererPlugin(Protocol):
    """Defines how records are displayed across MoLabel's UI surfaces.

    Controls column definitions for table views, detail inspector layouts,
    review screen layouts, and plain-text preview snippets.
    """

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
        summaries. Must be safe for rendering (the core sanitises HTML).
        Keep output under 500 characters.
        """
        ...


# ---------------------------------------------------------------------------
# PL-008 — ReviewWorkflowPlugin  (RV-009)
# ---------------------------------------------------------------------------


@runtime_checkable
class ReviewWorkflowPlugin(Protocol):
    """Builds and manages human review queues.

    Invoked during ``human_review``, ``human_calibration``, and overlap
    assignment workflow steps.
    """

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


# ---------------------------------------------------------------------------
# PL-009 — AdjudicationPlugin  (AJ-006)
# ---------------------------------------------------------------------------


@runtime_checkable
class AdjudicationPlugin(Protocol):
    """Detects and helps resolve disagreements in review data.

    Invoked during ``human_adjudication`` workflow steps.
    """

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


# ---------------------------------------------------------------------------
# PL-010 — AgentAdapterPlugin  (AG-016)
# ---------------------------------------------------------------------------


@runtime_checkable
class AgentAdapterPlugin(Protocol):
    """Adapts record data and task schemas into model prompts and parses outputs.

    Bridges the gap between MoLabel's record/task model and the specific
    prompt engineering required for a given agent role. Each adapter handles
    prompt construction, output parsing, and confidence extraction for one
    agent role.
    """

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


# ---------------------------------------------------------------------------
# PL-011 — ValidationPlugin  (QA-009)
# ---------------------------------------------------------------------------


@runtime_checkable
class ValidationPlugin(Protocol):
    """Implements a validation gate for quality and release checks.

    Invoked during ``quality_check`` and ``release_validation`` workflow
    steps. Gates may check dataset quality, completeness, agreement
    thresholds, or export integrity.
    """

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


# ---------------------------------------------------------------------------
# PL-012 — ExportPackagerPlugin  (EX-012)
# ---------------------------------------------------------------------------


@runtime_checkable
class ExportPackagerPlugin(Protocol):
    """Packages labeled records into distributable export formats.

    Invoked during ``export`` workflow steps.
    """

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


# ---------------------------------------------------------------------------
# PL-013 — ReferenceAppPlugin
# ---------------------------------------------------------------------------


@runtime_checkable
class ReferenceAppPlugin(Protocol):
    """Bundles domain-specific project configuration and workflows.

    Reference apps package workspace templates, custom screens,
    validation gates, project dashboards, and bootstrap rules into a
    cohesive domain package. DePolarize is the first reference app.
    """

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


# ---------------------------------------------------------------------------
# PL-020 — Additional extension APIs
# ---------------------------------------------------------------------------


@runtime_checkable
class RecordNormalizerPlugin(Protocol):
    """Normalises raw records during data ingest.

    Transforms incoming data into the canonical stable-fields shape
    expected by the task schema.
    """

    @property
    def metadata(self) -> PluginMetadata:
        """Plugin identity and compatibility information."""
        ...

    def normalize(
        self,
        record: Record,
        config: dict[str, Any],
    ) -> Record:
        """Return a normalised copy of *record*.

        The implementation must not mutate the input record. It should
        populate or reshape ``stable_fields`` according to the schema
        mapping in *config*.
        """
        ...


@runtime_checkable
class WorkflowStageProviderPlugin(Protocol):
    """Provides custom workflow stage types.

    Allows plugins to introduce new kinds of workflow steps beyond
    the built-in set.
    """

    @property
    def metadata(self) -> PluginMetadata:
        """Plugin identity and compatibility information."""
        ...

    @property
    def stage_type(self) -> str:
        """Unique identifier for this workflow stage type."""
        ...

    def execute(
        self,
        config: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute the workflow stage and return its result.

        Args:
            config: Stage-specific configuration from the workflow YAML.
            context: Runtime context including dataset, task schema, and
                     previous step outputs.

        Returns:
            A result dict whose shape is stage-type-specific.
        """
        ...


@runtime_checkable
class DashboardPanelPlugin(Protocol):
    """Provides a custom dashboard panel for the project overview.

    Dashboard panels display summary metrics, charts, or status
    indicators in the project dashboard screen.
    """

    @property
    def metadata(self) -> PluginMetadata:
        """Plugin identity and compatibility information."""
        ...

    @property
    def panel_id(self) -> str:
        """Unique identifier for this dashboard panel."""
        ...

    def get_panel_data(
        self,
        dataset: Dataset,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """Compute panel data for display.

        Returns a dict whose shape is panel-specific. The frontend uses
        the panel's component bundle (if any) or a generic renderer to
        display the data.
        """
        ...


@runtime_checkable
class ProjectTemplatePlugin(Protocol):
    """Provides preconfigured project templates.

    Project templates bundle task schemas, queues, agent roles,
    validation gates, export mappings, and provider/runtime profiles
    into a single reusable configuration.
    """

    @property
    def metadata(self) -> PluginMetadata:
        """Plugin identity and compatibility information."""
        ...

    @property
    def template_id(self) -> str:
        """Unique identifier for this project template."""
        ...

    def get_template_config(self) -> dict[str, Any]:
        """Return the full template configuration.

        The returned dict is a workspace manifest fragment with keys like
        ``task_schemas``, ``queues``, ``agent_roles``, ``validation_gates``,
        ``export_mappings``, ``model_profiles``, and ``runtime_profiles``.
        """
        ...

    def get_template_description(self) -> str:
        """Return a human-readable description of this template.

        Shown in the project creation wizard to help users choose.
        """
        ...


# ---------------------------------------------------------------------------
# Plugin lifecycle protocol  (PL-016, PL-017)
# ---------------------------------------------------------------------------


@runtime_checkable
class PluginLifecycle(Protocol):
    """Optional lifecycle hooks called by the core at key moments.

    Plugins are not required to implement all methods. The core checks
    for each method's existence via ``hasattr`` and skips missing hooks.
    """

    def on_install(self, context: Any) -> None:
        """Called when the plugin is first installed in a workspace."""
        ...

    def on_activate(self, context: Any) -> None:
        """Called each time the plugin is activated (application startup)."""
        ...

    def on_compatibility_check(self, core_version: str) -> Any:
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
    ) -> Any:
        """Called when the plugin version changes between activations."""
        ...

    def on_disable(self, context: Any) -> None:
        """Called when the plugin is disabled (but not uninstalled)."""
        ...

    def on_uninstall(self, context: Any) -> Any:
        """Called when the plugin is fully removed from the workspace."""
        ...


# ---------------------------------------------------------------------------
# PL-019 — Plugin manifest and capability contract
# ---------------------------------------------------------------------------


@runtime_checkable
class PluginManifestProvider(Protocol):
    """Optional protocol for plugins that provide a full manifest.

    The manifest describes the plugin's entry point, supported schemas/tasks,
    renderers, export formats, validation hooks, and job/command surfaces.
    Plugins may implement this protocol to enable richer introspection by
    the plugin management UI.
    """

    @property
    def metadata(self) -> PluginMetadata:
        """Plugin identity and compatibility information."""
        ...

    def get_manifest(self) -> PluginManifest:
        """Return the full plugin manifest describing all capabilities."""
        ...


__all__ = [
    # Core plugin protocols
    "DataLoaderPlugin",
    "TaskTypePlugin",
    "ModelProviderPlugin",
    "RecordRendererPlugin",
    "ReviewWorkflowPlugin",
    "AdjudicationPlugin",
    "AgentAdapterPlugin",
    "ValidationPlugin",
    "ExportPackagerPlugin",
    "ReferenceAppPlugin",
    # Extension protocols (PL-020)
    "RecordNormalizerPlugin",
    "WorkflowStageProviderPlugin",
    "DashboardPanelPlugin",
    "ProjectTemplatePlugin",
    # Lifecycle & manifest
    "PluginLifecycle",
    "PluginManifestProvider",
    # Re-exported types
    "PluginManifest",
    "PluginCapability",
]

"""Tests for plugin protocol definitions (Step 2.A.1) and provider adapter
framework (Step 2.B.1).

Verifies:
- Each Protocol is ``@runtime_checkable`` and satisfied by a minimal impl.
- The registry accepts properly typed plugins via ``register_*`` methods.
- Incompatible core versions are rejected (PL-017).
- Plugin manifest and capability types are correctly structured (PL-019).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from molabel.core.plugins.protocols import (
    AdjudicationPlugin,
    AgentAdapterPlugin,
    DashboardPanelPlugin,
    DataLoaderPlugin,
    ExportPackagerPlugin,
    ModelProviderPlugin,
    PluginManifestProvider,
    ProjectTemplatePlugin,
    RecordNormalizerPlugin,
    RecordRendererPlugin,
    ReferenceAppPlugin,
    ReviewWorkflowPlugin,
    TaskTypePlugin,
    ValidationPlugin,
    WorkflowStageProviderPlugin,
)
from molabel.core.plugins.registry import (
    IncompatiblePluginError,
    PluginRegistry,
    check_compatibility,
)
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
    LayoutSection,
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
# Helpers — minimal metadata fixture
# ---------------------------------------------------------------------------

_SENTINEL_UUID = uuid4()


def _meta(
    plugin_id: str = "test.plugin",
    compatible_core: str = ">=0.1,<1.0",
) -> PluginMetadata:
    return PluginMetadata(
        plugin_id=plugin_id,
        version="0.1.0",
        compatible_core=compatible_core,
        description="Test plugin",
    )


# ---------------------------------------------------------------------------
# Minimal implementations for each Protocol
# ---------------------------------------------------------------------------


class _MinimalDataLoader:
    @property
    def metadata(self) -> PluginMetadata:
        return _meta("test.loader")

    @property
    def supported_formats(self) -> list[str]:
        return ["jsonl"]

    def can_load(self, path: Path) -> bool:
        return path.suffix == ".jsonl"

    def load_records(self, path: Path, config: dict[str, Any]) -> Iterator[Record]:
        yield Record(
            id=_SENTINEL_UUID,
            dataset_id=_SENTINEL_UUID,
            external_id=None,
            stable_fields={"text": "hello"},
            payload={"text": "hello"},
            record_kind=None,
        )

    def get_schema(self, path: Path) -> dict[str, Any]:
        return {"type": "object", "properties": {"text": {"type": "string"}}}

    def estimate_record_count(self, path: Path) -> int | None:
        return 42


class _MinimalTaskType:
    @property
    def metadata(self) -> PluginMetadata:
        return _meta("test.task_type")

    @property
    def task_type_id(self) -> str:
        return "ordinal_text_review"

    def get_label_field_definitions(self) -> list[LabelFieldDefinition]:
        return [LabelFieldDefinition(name="sentiment", field_type="categorical")]

    def get_default_review_form_schema(self) -> dict[str, Any]:
        return {"type": "object"}

    def validate_labels(
        self, labels: dict[str, Any], task_schema: TaskSchema
    ) -> ValidationResult:
        return ValidationResult(is_valid=True)

    def get_default_agent_prompt_template(self) -> str:
        return "Label the following: {{ record }}"

    def get_export_columns(self) -> list[dict[str, str]]:
        return [{"source": "sentiment", "target": "label"}]


class _MinimalModelProvider:
    @property
    def metadata(self) -> PluginMetadata:
        return _meta("test.provider")

    @property
    def provider_type(self) -> str:
        return "openai_compatible"

    def check_health(self) -> HealthStatus:
        return HealthStatus(is_healthy=True)

    def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(model_id="gpt-4o", display_name="GPT-4o")]

    def supports_structured_output(self) -> bool:
        return True

    def supports_logprobs(self) -> bool:
        return False

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
        return CompletionResult(content="test response")

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
        yield CompletionChunk(delta="chunk")

    def estimate_cost(
        self, input_tokens: int, output_tokens: int, model: str
    ) -> CostEstimate:
        return CostEstimate(input_cost=0.0, output_cost=0.0, total_cost=0.0)


class _MinimalRecordRenderer:
    @property
    def metadata(self) -> PluginMetadata:
        return _meta("test.renderer")

    def get_list_columns(self, record_kind: str) -> list[ColumnDefinition]:
        return [ColumnDefinition(key="stable_fields.text", label="Text")]

    def get_detail_layout(self, record_kind: str) -> LayoutSpec:
        return LayoutSpec(
            sections=[
                LayoutSection(
                    section_id="main",
                    title="Content",
                    section_type="fields",
                )
            ]
        )

    def get_review_layout(self, record_kind: str) -> LayoutSpec:
        return LayoutSpec(
            sections=[
                LayoutSection(
                    section_id="main",
                    title="Content",
                    section_type="fields",
                )
            ]
        )

    def render_preview(self, record: Record) -> str:
        return str(record.stable_fields.get("text", ""))[:200]


class _MinimalReviewWorkflow:
    @property
    def metadata(self) -> PluginMetadata:
        return _meta("test.workflow")

    def build_queue(
        self,
        dataset: Dataset,
        task_schema: TaskSchema,
        config: dict[str, Any],
    ) -> list[ReviewTask]:
        return []

    def validate_submission(
        self,
        review_event: ReviewEvent,
        task_schema: TaskSchema,
    ) -> ValidationResult:
        return ValidationResult(is_valid=True)

    def compute_overlap_assignments(
        self,
        dataset: Dataset,
        config: dict[str, Any],
    ) -> list[ReviewTask]:
        return []

    def get_calibration_items(
        self,
        dataset: Dataset,
        config: dict[str, Any],
    ) -> list[ReviewTask]:
        return []


class _MinimalAdjudication:
    @property
    def metadata(self) -> PluginMetadata:
        return _meta("test.adjudication")

    def detect_disagreements(
        self,
        review_events_per_record: dict[str, list[ReviewEvent]],
    ) -> list[Disagreement]:
        return []

    def get_adjudication_layout(
        self,
        record: Record,
        reviews: list[ReviewEvent],
    ) -> LayoutSpec:
        return LayoutSpec(sections=[])

    def validate_resolution(
        self,
        resolution: Adjudication,
        reviews: list[ReviewEvent],
    ) -> ValidationResult:
        return ValidationResult(is_valid=True)

    def compute_resolution_suggestion(
        self,
        reviews: list[ReviewEvent],
        agent_outputs: list[AgentOutput],
    ) -> ResolutionSuggestion | None:
        return None


class _MinimalAgentAdapter:
    @property
    def metadata(self) -> PluginMetadata:
        return _meta("test.adapter")

    @property
    def agent_role(self) -> str:
        return "proposer"

    def build_prompt(
        self,
        record: Record,
        task_schema: TaskSchema,
        prompt_template: PromptTemplate,
        few_shot_examples: list[dict[str, Any]] | None = None,
    ) -> list[Message]:
        return [Message(role="user", content="label this")]

    def parse_output(
        self,
        raw_response: dict[str, Any],
        task_schema: TaskSchema,
    ) -> AgentOutput:
        return AgentOutput(
            id=_SENTINEL_UUID,
            agent_run_id=_SENTINEL_UUID,
            record_id=_SENTINEL_UUID,
            task_schema_id=_SENTINEL_UUID,
            output_type="label",
            labels={"sentiment": "positive"},
        )

    def compute_confidence(self, raw_response: dict[str, Any]) -> float:
        return 0.95

    def supports_batch(self) -> bool:
        return False

    def batch_size_limit(self) -> int:
        return 1


class _MinimalValidation:
    @property
    def metadata(self) -> PluginMetadata:
        return _meta("test.validation")

    @property
    def gate_id(self) -> str:
        return "min_agreement_check"

    def validate(
        self,
        dataset: Dataset,
        export_artifact: ExportArtifact | None,
        config: dict[str, Any],
    ) -> ValidationReport:
        return ValidationReport(
            gate_id="min_agreement_check",
            status="passed",
            summary="OK",
        )

    def get_gate_description(self) -> str:
        return "Checks minimum inter-annotator agreement."

    def get_required_metrics(self) -> list[str]:
        return ["inter_annotator_agreement"]


class _MinimalExportPackager:
    @property
    def metadata(self) -> PluginMetadata:
        return _meta("test.packager")

    @property
    def supported_formats(self) -> list[str]:
        return ["jsonl"]

    def package(
        self,
        records: list[Record],
        labels: dict[str, list[ReviewEvent]],
        config: dict[str, Any],
    ) -> ExportArtifact:
        return ExportArtifact(data=b"", format="jsonl", record_count=len(records))

    def validate_export(self, artifact: ExportArtifact) -> ValidationResult:
        return ValidationResult(is_valid=True)

    def get_export_schema(self) -> dict[str, Any]:
        return {"columns": []}


class _MinimalReferenceApp:
    @property
    def metadata(self) -> PluginMetadata:
        return _meta("test.refapp")

    @property
    def app_id(self) -> str:
        return "test_app"

    def detect_project(self, workspace_path: Path) -> bool:
        return False

    def get_bootstrap_config(self, workspace_path: Path) -> dict[str, Any]:
        return {}

    def get_project_templates(self) -> list[WorkflowTemplateDefinition]:
        return []

    def get_custom_screens(self) -> list[ScreenDefinition]:
        return []

    def get_readiness_gates(self) -> list[ValidationGateConfig]:
        return []


class _MinimalRecordNormalizer:
    @property
    def metadata(self) -> PluginMetadata:
        return _meta("test.normalizer")

    def normalize(self, record: Record, config: dict[str, Any]) -> Record:
        return record


class _MinimalWorkflowStageProvider:
    @property
    def metadata(self) -> PluginMetadata:
        return _meta("test.stage")

    @property
    def stage_type(self) -> str:
        return "custom_stage"

    def execute(
        self, config: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]:
        return {"status": "completed"}


class _MinimalDashboardPanel:
    @property
    def metadata(self) -> PluginMetadata:
        return _meta("test.panel")

    @property
    def panel_id(self) -> str:
        return "test_panel"

    def get_panel_data(
        self, dataset: Dataset, config: dict[str, Any]
    ) -> dict[str, Any]:
        return {"records_processed": 0}


class _MinimalProjectTemplate:
    @property
    def metadata(self) -> PluginMetadata:
        return _meta("test.template")

    @property
    def template_id(self) -> str:
        return "test_template"

    def get_template_config(self) -> dict[str, Any]:
        return {}

    def get_template_description(self) -> str:
        return "A test template."


class _MinimalManifestProvider:
    @property
    def metadata(self) -> PluginMetadata:
        return _meta("test.manifest")

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            plugin_id="test.manifest",
            version="0.1.0",
            entrypoint="test_pkg.plugin:register",
            capabilities=[
                PluginCapability(
                    capability_type="data_loader",
                    identifier="jsonl",
                    description="Loads JSONL files",
                )
            ],
        )


# ===================================================================
# Protocol isinstance() tests  (runtime_checkable)
# ===================================================================


class TestDataLoaderProtocol:
    def test_isinstance(self) -> None:
        loader = _MinimalDataLoader()
        assert isinstance(loader, DataLoaderPlugin)

    def test_metadata(self) -> None:
        loader = _MinimalDataLoader()
        assert loader.metadata.plugin_id == "test.loader"

    def test_supported_formats(self) -> None:
        loader = _MinimalDataLoader()
        assert "jsonl" in loader.supported_formats

    def test_can_load(self) -> None:
        loader = _MinimalDataLoader()
        assert loader.can_load(Path("test.jsonl")) is True
        assert loader.can_load(Path("test.csv")) is False

    def test_load_records(self) -> None:
        loader = _MinimalDataLoader()
        records = list(loader.load_records(Path("test.jsonl"), {}))
        assert len(records) == 1
        assert records[0].stable_fields["text"] == "hello"

    def test_get_schema(self) -> None:
        loader = _MinimalDataLoader()
        schema = loader.get_schema(Path("test.jsonl"))
        assert schema["type"] == "object"

    def test_estimate_record_count(self) -> None:
        loader = _MinimalDataLoader()
        assert loader.estimate_record_count(Path("test.jsonl")) == 42


class TestTaskTypeProtocol:
    def test_isinstance(self) -> None:
        assert isinstance(_MinimalTaskType(), TaskTypePlugin)

    def test_task_type_id(self) -> None:
        assert _MinimalTaskType().task_type_id == "ordinal_text_review"

    def test_validate_labels_returns_valid(self) -> None:
        ts = TaskSchema(
            id=_SENTINEL_UUID,
            task_schema_slug="test",
            version=1,
            task_type="ordinal_text_review",
            title="Test",
        )
        result = _MinimalTaskType().validate_labels({"sentiment": "positive"}, ts)
        assert result.is_valid is True


class TestModelProviderProtocol:
    def test_isinstance(self) -> None:
        assert isinstance(_MinimalModelProvider(), ModelProviderPlugin)

    def test_check_health(self) -> None:
        status = _MinimalModelProvider().check_health()
        assert status.is_healthy is True

    def test_list_models(self) -> None:
        models = _MinimalModelProvider().list_models()
        assert len(models) == 1
        assert models[0].model_id == "gpt-4o"

    def test_supports_structured_output(self) -> None:
        assert _MinimalModelProvider().supports_structured_output() is True

    def test_supports_logprobs(self) -> None:
        assert _MinimalModelProvider().supports_logprobs() is False

    def test_complete(self) -> None:
        provider = _MinimalModelProvider()
        result = provider.complete(
            messages=[Message(role="user", content="hello")],
            model="gpt-4o",
        )
        assert result.content == "test response"

    def test_estimate_cost(self) -> None:
        provider = _MinimalModelProvider()
        est = provider.estimate_cost(100, 50, "gpt-4o")
        assert est.total_cost == 0.0


class TestRecordRendererProtocol:
    def test_isinstance(self) -> None:
        assert isinstance(_MinimalRecordRenderer(), RecordRendererPlugin)


class TestReviewWorkflowProtocol:
    def test_isinstance(self) -> None:
        assert isinstance(_MinimalReviewWorkflow(), ReviewWorkflowPlugin)

    def test_build_queue_returns_list(self) -> None:
        ds = Dataset(
            id=_SENTINEL_UUID,
            workspace_id=_SENTINEL_UUID,
            dataset_name="test",
            dataset_slug="test",
            source_type="file",
        )
        ts = TaskSchema(
            id=_SENTINEL_UUID,
            task_schema_slug="test",
            version=1,
            task_type="ordinal_text_review",
            title="Test",
        )
        queue = _MinimalReviewWorkflow().build_queue(ds, ts, {})
        assert isinstance(queue, list)


class TestAdjudicationProtocol:
    def test_isinstance(self) -> None:
        assert isinstance(_MinimalAdjudication(), AdjudicationPlugin)

    def test_detect_disagreements_empty(self) -> None:
        result = _MinimalAdjudication().detect_disagreements({})
        assert result == []


class TestAgentAdapterProtocol:
    def test_isinstance(self) -> None:
        assert isinstance(_MinimalAgentAdapter(), AgentAdapterPlugin)

    def test_agent_role(self) -> None:
        assert _MinimalAgentAdapter().agent_role == "proposer"

    def test_supports_batch(self) -> None:
        assert _MinimalAgentAdapter().supports_batch() is False

    def test_batch_size_limit(self) -> None:
        assert _MinimalAgentAdapter().batch_size_limit() == 1


class TestValidationProtocol:
    def test_isinstance(self) -> None:
        assert isinstance(_MinimalValidation(), ValidationPlugin)

    def test_gate_id(self) -> None:
        assert _MinimalValidation().gate_id == "min_agreement_check"


class TestExportPackagerProtocol:
    def test_isinstance(self) -> None:
        assert isinstance(_MinimalExportPackager(), ExportPackagerPlugin)

    def test_supported_formats(self) -> None:
        assert "jsonl" in _MinimalExportPackager().supported_formats


class TestReferenceAppProtocol:
    def test_isinstance(self) -> None:
        assert isinstance(_MinimalReferenceApp(), ReferenceAppPlugin)

    def test_app_id(self) -> None:
        assert _MinimalReferenceApp().app_id == "test_app"


class TestRecordNormalizerProtocol:
    def test_isinstance(self) -> None:
        assert isinstance(_MinimalRecordNormalizer(), RecordNormalizerPlugin)


class TestWorkflowStageProviderProtocol:
    def test_isinstance(self) -> None:
        assert isinstance(_MinimalWorkflowStageProvider(), WorkflowStageProviderPlugin)


class TestDashboardPanelProtocol:
    def test_isinstance(self) -> None:
        assert isinstance(_MinimalDashboardPanel(), DashboardPanelPlugin)


class TestProjectTemplateProtocol:
    def test_isinstance(self) -> None:
        assert isinstance(_MinimalProjectTemplate(), ProjectTemplatePlugin)


class TestPluginManifestProviderProtocol:
    def test_isinstance(self) -> None:
        assert isinstance(_MinimalManifestProvider(), PluginManifestProvider)

    def test_manifest_structure(self) -> None:
        manifest = _MinimalManifestProvider().get_manifest()
        assert manifest.plugin_id == "test.manifest"
        assert len(manifest.capabilities) == 1
        assert manifest.capabilities[0].capability_type == "data_loader"


# ===================================================================
# Registry tests
# ===================================================================


class TestRegistryRegistration:
    """Test that the registry accepts typed plugins and extracts plugin_id."""

    def test_register_data_loader(self) -> None:
        reg = PluginRegistry()
        reg.register_data_loader(_MinimalDataLoader())
        assert "test.loader" in reg.list_data_loaders()
        loader = reg.get_data_loader("test.loader")
        assert loader is not None
        assert loader.metadata.plugin_id == "test.loader"

    def test_register_task_type(self) -> None:
        reg = PluginRegistry()
        reg.register_task_type(_MinimalTaskType())
        assert "test.task_type" in reg.list_task_types()

    def test_register_model_provider(self) -> None:
        reg = PluginRegistry()
        reg.register_model_provider(_MinimalModelProvider())
        assert "test.provider" in reg.list_model_providers()

    def test_register_record_renderer(self) -> None:
        reg = PluginRegistry()
        reg.register_record_renderer(_MinimalRecordRenderer())
        assert "test.renderer" in reg.list_record_renderers()

    def test_register_review_workflow(self) -> None:
        reg = PluginRegistry()
        reg.register_review_workflow(_MinimalReviewWorkflow())
        assert "test.workflow" in reg.list_review_workflows()

    def test_register_adjudication(self) -> None:
        reg = PluginRegistry()
        reg.register_adjudication(_MinimalAdjudication())
        assert "test.adjudication" in reg.list_adjudications()

    def test_register_agent_adapter(self) -> None:
        reg = PluginRegistry()
        reg.register_agent_adapter(_MinimalAgentAdapter())
        assert "test.adapter" in reg.list_agent_adapters()

    def test_register_validation(self) -> None:
        reg = PluginRegistry()
        reg.register_validation(_MinimalValidation())
        assert "test.validation" in reg.list_validations()

    def test_register_export_packager(self) -> None:
        reg = PluginRegistry()
        reg.register_export_packager(_MinimalExportPackager())
        assert "test.packager" in reg.list_export_packagers()

    def test_register_reference_app(self) -> None:
        reg = PluginRegistry()
        reg.register_reference_app(_MinimalReferenceApp())
        assert "test.refapp" in reg.list_reference_apps()

    def test_register_record_normalizer(self) -> None:
        reg = PluginRegistry()
        reg.register_record_normalizer(_MinimalRecordNormalizer())
        assert "test.normalizer" in reg.list_record_normalizers()

    def test_register_workflow_stage_provider(self) -> None:
        reg = PluginRegistry()
        reg.register_workflow_stage_provider(_MinimalWorkflowStageProvider())
        assert "test.stage" in reg.list_workflow_stage_providers()

    def test_register_dashboard_panel(self) -> None:
        reg = PluginRegistry()
        reg.register_dashboard_panel(_MinimalDashboardPanel())
        assert "test.panel" in reg.list_dashboard_panels()

    def test_register_project_template(self) -> None:
        reg = PluginRegistry()
        reg.register_project_template(_MinimalProjectTemplate())
        assert "test.template" in reg.list_project_templates()

    def test_metadata_stored_on_register(self) -> None:
        reg = PluginRegistry()
        reg.register_data_loader(_MinimalDataLoader())
        meta = reg.get_plugin_metadata("test.loader")
        assert meta is not None
        assert meta.version == "0.1.0"

    def test_get_nonexistent_returns_none(self) -> None:
        reg = PluginRegistry()
        assert reg.get_data_loader("nonexistent") is None
        assert reg.get_model_provider("nonexistent") is None


# ===================================================================
# Compatibility enforcement tests  (PL-017)
# ===================================================================


class TestCompatibilityEnforcement:
    """Test that incompatible plugins are rejected clearly."""

    def test_compatible_plugin_accepted(self) -> None:
        meta = _meta(compatible_core=">=0.1,<1.0")
        # Should not raise
        check_compatibility(meta, core_version="0.1.0")

    def test_incompatible_plugin_rejected(self) -> None:
        meta = _meta(compatible_core=">=2.0")
        with pytest.raises(IncompatiblePluginError) as exc_info:
            check_compatibility(meta, core_version="0.1.0")
        assert "test.plugin" in str(exc_info.value)
        assert ">=2.0" in str(exc_info.value)
        assert "0.1.0" in str(exc_info.value)

    def test_invalid_specifier_rejected(self) -> None:
        meta = _meta(compatible_core="not_a_valid_specifier!!!")
        with pytest.raises(IncompatiblePluginError):
            check_compatibility(meta, core_version="0.1.0")

    def test_registry_rejects_incompatible_plugin(self) -> None:
        """Incompatible plugins fail clearly during registration."""

        class _IncompatibleLoader(_MinimalDataLoader):
            @property
            def metadata(self) -> PluginMetadata:
                return _meta("test.incompat_loader", compatible_core=">=99.0")

        reg = PluginRegistry(core_version="0.1.0")
        with pytest.raises(IncompatiblePluginError):
            reg.register_data_loader(_IncompatibleLoader())

        # Verify it was not registered
        assert reg.get_data_loader("test.incompat_loader") is None

    def test_exact_version_boundary(self) -> None:
        """Plugin requiring >=0.1,<0.2 should accept 0.1.0 but reject 0.2.0."""
        meta = _meta(compatible_core=">=0.1,<0.2")
        check_compatibility(meta, core_version="0.1.0")

        with pytest.raises(IncompatiblePluginError):
            check_compatibility(meta, core_version="0.2.0")

    def test_workspace_remains_readable_message(self) -> None:
        """Error message mentions workspace remains readable."""
        meta = _meta(compatible_core=">=99.0")
        with pytest.raises(IncompatiblePluginError, match="workspace remains readable"):
            check_compatibility(meta, core_version="0.1.0")


# ===================================================================
# Domain type tests (smoke tests for new Pydantic models)
# ===================================================================


class TestDomainTypes:
    """Verify new domain types can be constructed correctly."""

    def test_record_construction(self) -> None:
        r = Record(
            id=uuid4(),
            dataset_id=uuid4(),
            stable_fields={"text": "hello"},
            payload={"text": "hello"},
        )
        assert r.stable_fields["text"] == "hello"

    def test_validation_result_with_errors(self) -> None:
        from molabel.core.types import ValidationError

        result = ValidationResult(
            is_valid=False,
            errors=[ValidationError(field="name", message="required")],
        )
        assert result.is_valid is False
        assert len(result.errors) == 1

    def test_health_status(self) -> None:
        hs = HealthStatus(is_healthy=True, latency_ms=42)
        assert hs.is_healthy is True
        assert hs.latency_ms == 42

    def test_completion_result(self) -> None:
        cr = CompletionResult(content="hello world", tokens_input=10, tokens_output=5)
        assert cr.content == "hello world"

    def test_cost_estimate(self) -> None:
        ce = CostEstimate(input_cost=0.001, output_cost=0.002, total_cost=0.003)
        assert ce.currency == "USD"

    def test_message(self) -> None:
        m = Message(role="user", content="hello")
        assert m.role == "user"

    def test_plugin_manifest(self) -> None:
        pm = PluginManifest(
            plugin_id="test.plugin",
            version="0.1.0",
            entrypoint="test_pkg:register",
            capabilities=[
                PluginCapability(
                    capability_type="data_loader",
                    identifier="jsonl",
                )
            ],
            supported_formats=["jsonl"],
        )
        assert len(pm.capabilities) == 1

    def test_export_artifact(self) -> None:
        ea = ExportArtifact(data=b'{"key":"val"}', format="jsonl", record_count=1)
        assert ea.data is not None
        assert ea.record_count == 1

    def test_disagreement(self) -> None:
        d = Disagreement(
            record_id=uuid4(),
            conflicting_event_ids=[uuid4(), uuid4()],
            disagreement_type="inter_annotator",
            fields_in_conflict=["sentiment"],
        )
        assert d.severity == "medium"

    def test_resolution_suggestion(self) -> None:
        rs = ResolutionSuggestion(
            suggested_labels={"sentiment": "positive"},
            confidence=0.85,
            rationale="Majority vote",
        )
        assert rs.confidence == 0.85

    def test_review_task(self) -> None:
        rt = ReviewTask(
            record_id=uuid4(),
            task_schema_id=uuid4(),
            dataset_id=uuid4(),
            is_overlap=True,
        )
        assert rt.is_overlap is True

    def test_screen_definition(self) -> None:
        sd = ScreenDefinition(
            screen_id="dash",
            title="Dashboard",
            route="/dashboard",
            component_bundle="ui/dashboard.mjs",
        )
        assert sd.nav_section == "project"

    def test_validation_gate_config(self) -> None:
        vgc = ValidationGateConfig(
            gate_id="min_agreement",
            plugin_id="test.validation",
            description="Checks agreement",
        )
        assert vgc.required_for_release is True

    def test_workflow_template_definition(self) -> None:
        wtd = WorkflowTemplateDefinition(
            template_id="default",
            name="Default Workflow",
            description="A default workflow",
            workflow_yaml="steps: []",
        )
        assert wtd.template_id == "default"

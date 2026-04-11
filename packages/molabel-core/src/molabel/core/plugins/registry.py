"""Plugin registry: central store for plugin capabilities and metadata."""

from __future__ import annotations

import logging
from typing import Any

from packaging.specifiers import InvalidSpecifier, SpecifierSet

from molabel.core.plugins.protocols import (
    AdjudicationPlugin,
    AgentAdapterPlugin,
    DashboardPanelPlugin,
    DataLoaderPlugin,
    ExportPackagerPlugin,
    ModelProviderPlugin,
    ProjectTemplatePlugin,
    RecordNormalizerPlugin,
    RecordRendererPlugin,
    ReferenceAppPlugin,
    ReviewWorkflowPlugin,
    TaskTypePlugin,
    ValidationPlugin,
    WorkflowStageProviderPlugin,
)
from molabel.core.types import PluginContext, PluginMetadata

logger = logging.getLogger(__name__)

# Version of molabel-core for compatibility checking.
_CORE_VERSION = "0.1.0"


class IncompatiblePluginError(Exception):
    """Raised when a plugin declares an incompatible ``compatible_core`` specifier."""

    def __init__(self, plugin_id: str, compatible_core: str, core_version: str) -> None:
        self.plugin_id = plugin_id
        self.compatible_core = compatible_core
        self.core_version = core_version
        super().__init__(
            f"Plugin '{plugin_id}' requires molabel-core "
            f"{compatible_core}, but version {core_version} is "
            f"installed. The workspace remains readable but writes "
            f"through this plugin are blocked."
        )


def check_compatibility(
    metadata: PluginMetadata,
    core_version: str | None = None,
) -> None:
    """Verify that a plugin's ``compatible_core`` specifier matches the running core.

    Args:
        metadata: The plugin's metadata containing the compatibility specifier.
        core_version: The running core version. Defaults to the package version.

    Raises:
        IncompatiblePluginError: If the specifier does not match.
    """
    version = core_version or _CORE_VERSION
    try:
        specifier = SpecifierSet(metadata.compatible_core)
    except InvalidSpecifier as exc:
        raise IncompatiblePluginError(
            plugin_id=metadata.plugin_id,
            compatible_core=metadata.compatible_core,
            core_version=version,
        ) from exc
    if version not in specifier:
        raise IncompatiblePluginError(
            plugin_id=metadata.plugin_id,
            compatible_core=metadata.compatible_core,
            core_version=version,
        )


class PluginRegistry:
    """Central registry where plugins declare their capabilities at startup.

    Each ``register_*`` method accepts a typed plugin instance, extracts its
    ``plugin_id`` from ``plugin.metadata``, validates core compatibility
    (PL-017), and stores the plugin object keyed by *plugin_id*.

    Retrieval methods look up by the same key.  The registry is a plain
    instantiable class -- the application creates one at startup and passes
    it to every plugin's ``register()`` function.
    """

    def __init__(self, *, core_version: str | None = None) -> None:
        self._core_version = core_version or _CORE_VERSION

        # ---- capability stores (plugin_id -> plugin object) ----
        self._data_loaders: dict[str, DataLoaderPlugin] = {}
        self._task_types: dict[str, TaskTypePlugin] = {}
        self._model_providers: dict[str, ModelProviderPlugin] = {}
        self._record_renderers: dict[str, RecordRendererPlugin] = {}
        self._review_workflows: dict[str, ReviewWorkflowPlugin] = {}
        self._adjudications: dict[str, AdjudicationPlugin] = {}
        self._agent_adapters: dict[str, AgentAdapterPlugin] = {}
        self._validations: dict[str, ValidationPlugin] = {}
        self._export_packagers: dict[str, ExportPackagerPlugin] = {}
        self._reference_apps: dict[str, ReferenceAppPlugin] = {}
        self._record_normalizers: dict[str, RecordNormalizerPlugin] = {}
        self._workflow_stage_providers: dict[str, WorkflowStageProviderPlugin] = {}
        self._dashboard_panels: dict[str, DashboardPanelPlugin] = {}
        self._project_templates: dict[str, ProjectTemplatePlugin] = {}

        # ---- per-plugin metadata (populated by plugins during registration) ----
        self._metadata: dict[str, PluginMetadata] = {}

        # ---- error tracking (PL-004) ----
        self._errors: dict[str, Exception] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_and_store_metadata(self, plugin: Any) -> str:
        """Extract metadata, check compatibility, store, return id.

        Raises:
            IncompatiblePluginError: If the plugin's
                ``compatible_core`` specifier does not match.
        """
        metadata: PluginMetadata = plugin.metadata
        check_compatibility(metadata, self._core_version)
        self._metadata[metadata.plugin_id] = metadata
        return metadata.plugin_id

    # ------------------------------------------------------------------
    # Plugin metadata
    # ------------------------------------------------------------------

    def set_plugin_metadata(self, plugin_id: str, metadata: PluginMetadata) -> None:
        """Store metadata for a plugin.  Called by the plugin during registration."""
        self._metadata[plugin_id] = metadata

    def get_plugin_metadata(self, plugin_id: str) -> PluginMetadata | None:
        """Return metadata for *plugin_id*, or ``None`` if not found."""
        return self._metadata.get(plugin_id)

    def list_plugin_ids(self) -> list[str]:
        """Return the canonical plugin IDs registered in metadata."""
        return list(self._metadata)

    # ------------------------------------------------------------------
    # Error tracking  (PL-004)
    # ------------------------------------------------------------------

    def record_error(self, plugin_id: str, error: Exception) -> None:
        """Store an error that occurred while loading/registering *plugin_id*."""
        self._errors[plugin_id] = error

    def get_plugin_errors(self) -> dict[str, Exception]:
        """Return a dict mapping plugin_id to the error that prevented loading."""
        return dict(self._errors)

    # ------------------------------------------------------------------
    # Registration methods
    #
    # Each method accepts a typed plugin argument and extracts plugin_id
    # from plugin.metadata.plugin_id.  Compatibility is checked against
    # the running core version (PL-017).
    # ------------------------------------------------------------------

    def register_data_loader(self, loader: DataLoaderPlugin) -> None:
        """Register a data-loader capability."""
        plugin_id = self._validate_and_store_metadata(loader)
        self._data_loaders[plugin_id] = loader
        logger.debug("Registered data_loader: %s", plugin_id)

    def register_task_type(self, task_type: TaskTypePlugin) -> None:
        """Register a task-type capability."""
        plugin_id = self._validate_and_store_metadata(task_type)
        self._task_types[plugin_id] = task_type
        logger.debug("Registered task_type: %s", plugin_id)

    def register_model_provider(self, provider: ModelProviderPlugin) -> None:
        """Register a model-provider capability."""
        plugin_id = self._validate_and_store_metadata(provider)
        self._model_providers[plugin_id] = provider
        logger.debug("Registered model_provider: %s", plugin_id)

    def register_record_renderer(self, renderer: RecordRendererPlugin) -> None:
        """Register a record-renderer capability."""
        plugin_id = self._validate_and_store_metadata(renderer)
        self._record_renderers[plugin_id] = renderer
        logger.debug("Registered record_renderer: %s", plugin_id)

    def register_review_workflow(self, workflow: ReviewWorkflowPlugin) -> None:
        """Register a review-workflow capability."""
        plugin_id = self._validate_and_store_metadata(workflow)
        self._review_workflows[plugin_id] = workflow
        logger.debug("Registered review_workflow: %s", plugin_id)

    def register_adjudication(self, adjudication: AdjudicationPlugin) -> None:
        """Register an adjudication capability."""
        plugin_id = self._validate_and_store_metadata(adjudication)
        self._adjudications[plugin_id] = adjudication
        logger.debug("Registered adjudication: %s", plugin_id)

    def register_agent_adapter(self, adapter: AgentAdapterPlugin) -> None:
        """Register an agent-adapter capability."""
        plugin_id = self._validate_and_store_metadata(adapter)
        self._agent_adapters[plugin_id] = adapter
        logger.debug("Registered agent_adapter: %s", plugin_id)

    def register_validation(self, validation: ValidationPlugin) -> None:
        """Register a validation capability."""
        plugin_id = self._validate_and_store_metadata(validation)
        self._validations[plugin_id] = validation
        logger.debug("Registered validation: %s", plugin_id)

    def register_export_packager(self, packager: ExportPackagerPlugin) -> None:
        """Register an export-packager capability."""
        plugin_id = self._validate_and_store_metadata(packager)
        self._export_packagers[plugin_id] = packager
        logger.debug("Registered export_packager: %s", plugin_id)

    def register_reference_app(self, app: ReferenceAppPlugin) -> None:
        """Register a reference-app capability."""
        plugin_id = self._validate_and_store_metadata(app)
        self._reference_apps[plugin_id] = app
        logger.debug("Registered reference_app: %s", plugin_id)

    def register_record_normalizer(self, normalizer: RecordNormalizerPlugin) -> None:
        """Register a record-normalizer capability."""
        plugin_id = self._validate_and_store_metadata(normalizer)
        self._record_normalizers[plugin_id] = normalizer
        logger.debug("Registered record_normalizer: %s", plugin_id)

    def register_workflow_stage_provider(
        self, provider: WorkflowStageProviderPlugin
    ) -> None:
        """Register a workflow-stage-provider capability."""
        plugin_id = self._validate_and_store_metadata(provider)
        self._workflow_stage_providers[plugin_id] = provider
        logger.debug("Registered workflow_stage_provider: %s", plugin_id)

    def register_dashboard_panel(self, panel: DashboardPanelPlugin) -> None:
        """Register a dashboard-panel capability."""
        plugin_id = self._validate_and_store_metadata(panel)
        self._dashboard_panels[plugin_id] = panel
        logger.debug("Registered dashboard_panel: %s", plugin_id)

    def register_project_template(self, template: ProjectTemplatePlugin) -> None:
        """Register a project-template capability."""
        plugin_id = self._validate_and_store_metadata(template)
        self._project_templates[plugin_id] = template
        logger.debug("Registered project_template: %s", plugin_id)

    # ------------------------------------------------------------------
    # Retrieval methods  (get_* and list_*)
    # ------------------------------------------------------------------

    def get_data_loader(self, plugin_id: str) -> DataLoaderPlugin | None:
        """Return the data-loader registered under *plugin_id*, or ``None``."""
        return self._data_loaders.get(plugin_id)

    def list_data_loaders(self) -> list[str]:
        """Return plugin_ids of all registered data-loaders."""
        return list(self._data_loaders)

    def get_task_type(self, plugin_id: str) -> TaskTypePlugin | None:
        return self._task_types.get(plugin_id)

    def list_task_types(self) -> list[str]:
        return list(self._task_types)

    def get_model_provider(self, plugin_id: str) -> ModelProviderPlugin | None:
        return self._model_providers.get(plugin_id)

    def list_model_providers(self) -> list[str]:
        return list(self._model_providers)

    def get_record_renderer(self, plugin_id: str) -> RecordRendererPlugin | None:
        return self._record_renderers.get(plugin_id)

    def list_record_renderers(self) -> list[str]:
        return list(self._record_renderers)

    def get_review_workflow(self, plugin_id: str) -> ReviewWorkflowPlugin | None:
        return self._review_workflows.get(plugin_id)

    def list_review_workflows(self) -> list[str]:
        return list(self._review_workflows)

    def get_adjudication(self, plugin_id: str) -> AdjudicationPlugin | None:
        return self._adjudications.get(plugin_id)

    def list_adjudications(self) -> list[str]:
        return list(self._adjudications)

    def get_agent_adapter(self, plugin_id: str) -> AgentAdapterPlugin | None:
        return self._agent_adapters.get(plugin_id)

    def list_agent_adapters(self) -> list[str]:
        return list(self._agent_adapters)

    def get_validation(self, plugin_id: str) -> ValidationPlugin | None:
        return self._validations.get(plugin_id)

    def list_validations(self) -> list[str]:
        return list(self._validations)

    def get_export_packager(self, plugin_id: str) -> ExportPackagerPlugin | None:
        return self._export_packagers.get(plugin_id)

    def list_export_packagers(self) -> list[str]:
        return list(self._export_packagers)

    def get_reference_app(self, plugin_id: str) -> ReferenceAppPlugin | None:
        return self._reference_apps.get(plugin_id)

    def list_reference_apps(self) -> list[str]:
        return list(self._reference_apps)

    def get_record_normalizer(self, plugin_id: str) -> RecordNormalizerPlugin | None:
        return self._record_normalizers.get(plugin_id)

    def list_record_normalizers(self) -> list[str]:
        return list(self._record_normalizers)

    def get_workflow_stage_provider(
        self, plugin_id: str
    ) -> WorkflowStageProviderPlugin | None:
        return self._workflow_stage_providers.get(plugin_id)

    def list_workflow_stage_providers(self) -> list[str]:
        return list(self._workflow_stage_providers)

    def get_dashboard_panel(self, plugin_id: str) -> DashboardPanelPlugin | None:
        return self._dashboard_panels.get(plugin_id)

    def list_dashboard_panels(self) -> list[str]:
        return list(self._dashboard_panels)

    def get_project_template(self, plugin_id: str) -> ProjectTemplatePlugin | None:
        return self._project_templates.get(plugin_id)

    def list_project_templates(self) -> list[str]:
        return list(self._project_templates)

    # ------------------------------------------------------------------
    # Lifecycle hooks  (PL-016, PL-017)
    #
    # Method names match the ``PluginLifecycle`` protocol defined in
    # ``protocols.py``: on_install, on_activate, on_compatibility_check,
    # on_migrate, on_disable, on_uninstall.
    # ------------------------------------------------------------------

    def call_on_install(
        self, plugin_id: str, plugin: Any, context: PluginContext
    ) -> None:
        """Invoke ``on_install`` on *plugin* if it implements the hook."""
        if hasattr(plugin, "on_install"):
            try:
                plugin.on_install(context)
                logger.debug("on_install succeeded for %s", plugin_id)
            except Exception:
                logger.exception("on_install failed for plugin %s", plugin_id)

    def call_on_activate(
        self, plugin_id: str, plugin: Any, context: PluginContext
    ) -> None:
        """Invoke ``on_activate`` on *plugin* if it implements the hook."""
        if hasattr(plugin, "on_activate"):
            try:
                plugin.on_activate(context)
                logger.debug("on_activate succeeded for %s", plugin_id)
            except Exception:
                logger.exception("on_activate failed for plugin %s", plugin_id)

    def call_on_compatibility_check(
        self, plugin_id: str, plugin: Any, core_version: str
    ) -> Any:
        """Invoke ``on_compatibility_check`` on *plugin* if it implements the hook."""
        if hasattr(plugin, "on_compatibility_check"):
            try:
                result = plugin.on_compatibility_check(core_version)
                logger.debug("on_compatibility_check succeeded for %s", plugin_id)
                return result
            except Exception:
                logger.exception(
                    "on_compatibility_check failed for plugin %s", plugin_id
                )
        return None

    def call_on_migrate(
        self,
        plugin_id: str,
        plugin: Any,
        from_version: str,
        to_version: str,
    ) -> Any:
        """Invoke ``on_migrate`` on *plugin* if it implements the hook."""
        if hasattr(plugin, "on_migrate"):
            try:
                result = plugin.on_migrate(from_version, to_version)
                logger.debug("on_migrate succeeded for %s", plugin_id)
                return result
            except Exception:
                logger.exception("on_migrate failed for plugin %s", plugin_id)
        return None

    def call_on_disable(
        self, plugin_id: str, plugin: Any, context: PluginContext
    ) -> None:
        """Invoke ``on_disable`` on *plugin* if it implements the hook."""
        if hasattr(plugin, "on_disable"):
            try:
                plugin.on_disable(context)
                logger.debug("on_disable succeeded for %s", plugin_id)
            except Exception:
                logger.exception("on_disable failed for plugin %s", plugin_id)

    def call_on_uninstall(
        self, plugin_id: str, plugin: Any, context: PluginContext
    ) -> Any:
        """Invoke ``on_uninstall`` on *plugin* if it implements the hook."""
        if hasattr(plugin, "on_uninstall"):
            try:
                result = plugin.on_uninstall(context)
                logger.debug("on_uninstall succeeded for %s", plugin_id)
                return result
            except Exception:
                logger.exception("on_uninstall failed for plugin %s", plugin_id)
        return None

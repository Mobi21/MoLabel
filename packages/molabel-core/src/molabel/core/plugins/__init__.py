"""Plugin discovery, registry, and protocol definitions for MoLabel.

Public API::

    from molabel.core.plugins import PluginRegistry, discover_plugins
    from molabel.core.plugins import DataLoaderPlugin, ModelProviderPlugin, ...
"""

from __future__ import annotations

from molabel.core.plugins.discovery import discover_plugins
from molabel.core.plugins.protocols import (
    AdjudicationPlugin,
    AgentAdapterPlugin,
    DashboardPanelPlugin,
    DataLoaderPlugin,
    ExportPackagerPlugin,
    ModelProviderPlugin,
    PluginCapability,
    PluginLifecycle,
    PluginManifest,
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

__all__ = [
    # Registry and discovery
    "PluginRegistry",
    "discover_plugins",
    "check_compatibility",
    "IncompatiblePluginError",
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
    "PluginManifest",
    "PluginCapability",
]

"""Prompt management system with composable layers and immutability (AG-013).

Manages prompt templates as composable layers (base, rubric, few-shot, patches)
with content-hash-based versioning and immutable-once-used enforcement.
"""

from __future__ import annotations

import hashlib
import logging
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


class PromptLayerType(StrEnum):
    """Types of prompt layers that can be composed."""

    base = "base"
    rubric = "rubric"
    few_shot = "few_shot"
    patch = "patch"


@dataclass
class PromptLayer:
    """A single composable layer of a prompt template."""

    layer_type: str
    content: str
    name: str = ""
    priority: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        """SHA-256 hash of this layer's content."""
        return _compute_hash(self.content)


@dataclass
class PromptVersion:
    """An immutable version of a prompt template, identified by content hash."""

    version_hash: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    parent_hash: str | None = None
    change_description: str = ""


@dataclass
class PromptTemplate:
    """A managed prompt template with composable layers and versioning."""

    name: str
    version: str = ""
    layers: list[PromptLayer] = field(default_factory=list)
    content_hash: str = ""
    is_used: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)
    version_history: list[PromptVersion] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.content_hash:
            self.content_hash = self._compute_content_hash()
        if not self.version:
            self.version = self.content_hash[:12]

    def _compute_content_hash(self) -> str:
        """Compute a content hash from all layers."""
        parts = []
        for layer in sorted(
            self.layers,
            key=lambda ly: (ly.layer_type, ly.priority, ly.name),
        ):
            parts.append(f"{layer.layer_type}:{layer.priority}:{layer.content}")
        combined = "|".join(parts)
        return _compute_hash(combined)


@dataclass
class ComposedPrompt:
    """The final composed prompt text from merging all layers."""

    text: str
    content_hash: str
    source_template_name: str = ""
    layer_count: int = 0
    composed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    layer_hashes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class PromptImmutabilityError(RuntimeError):
    """Raised when attempting to modify a prompt template that has been used."""

    def __init__(self, template_name: str) -> None:
        super().__init__(
            f"Cannot modify prompt template '{template_name}': "
            "it has been marked as used and is immutable."
        )
        self.template_name = template_name


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class PromptManager:
    """Manage prompt templates with composable layers and content addressing.

    Templates are built from composable layers (base, rubric, few-shot, patches).
    Once a template is marked as used (e.g., in an agent run), it becomes
    immutable. New versions can be created by forking.
    """

    def __init__(self) -> None:
        self._templates: dict[str, PromptTemplate] = {}

    @property
    def templates(self) -> dict[str, PromptTemplate]:
        """All managed templates by name."""
        return dict(self._templates)

    def create_template(
        self,
        name: str,
        layers: list[PromptLayer],
        *,
        metadata: dict[str, Any] | None = None,
    ) -> PromptTemplate:
        """Create a new prompt template from layers.

        Parameters
        ----------
        name:
            Unique template name.
        layers:
            List of prompt layers to compose.
        metadata:
            Optional metadata to attach to the template.

        Returns
        -------
        PromptTemplate
            The created template.
        """
        template = PromptTemplate(
            name=name,
            layers=list(layers),
            metadata=metadata or {},
        )
        template.content_hash = template._compute_content_hash()
        template.version = template.content_hash[:12]
        template.version_history.append(
            PromptVersion(
                version_hash=template.content_hash,
                change_description="Initial version",
            )
        )
        self._templates[name] = template
        return template

    def get_template(self, name: str) -> PromptTemplate | None:
        """Retrieve a template by name, or None if not found."""
        return self._templates.get(name)

    def add_layer(
        self,
        template_name: str,
        layer: PromptLayer,
    ) -> PromptTemplate:
        """Add a layer to an existing template.

        Parameters
        ----------
        template_name:
            Name of the template to modify.
        layer:
            The layer to add.

        Returns
        -------
        PromptTemplate
            The updated template.

        Raises
        ------
        PromptImmutabilityError
            If the template has been marked as used.
        KeyError
            If the template does not exist.
        """
        template = self._templates.get(template_name)
        if template is None:
            raise KeyError(f"Template '{template_name}' not found")

        if template.is_used:
            raise PromptImmutabilityError(template_name)

        old_hash = template.content_hash
        template.layers.append(layer)
        template.content_hash = template._compute_content_hash()
        template.version = template.content_hash[:12]
        template.version_history.append(
            PromptVersion(
                version_hash=template.content_hash,
                parent_hash=old_hash,
                change_description=f"Added {layer.layer_type} layer: {layer.name}",
            )
        )
        return template

    def remove_layer(
        self,
        template_name: str,
        layer_name: str,
    ) -> PromptTemplate:
        """Remove a named layer from a template.

        Parameters
        ----------
        template_name:
            Name of the template to modify.
        layer_name:
            Name of the layer to remove.

        Returns
        -------
        PromptTemplate
            The updated template.

        Raises
        ------
        PromptImmutabilityError
            If the template has been marked as used.
        KeyError
            If the template or layer does not exist.
        """
        template = self._templates.get(template_name)
        if template is None:
            raise KeyError(f"Template '{template_name}' not found")

        if template.is_used:
            raise PromptImmutabilityError(template_name)

        original_count = len(template.layers)
        template.layers = [ly for ly in template.layers if ly.name != layer_name]

        if len(template.layers) == original_count:
            raise KeyError(
                f"Layer '{layer_name}' not found in template '{template_name}'"
            )

        old_hash = template.content_hash
        template.content_hash = template._compute_content_hash()
        template.version = template.content_hash[:12]
        template.version_history.append(
            PromptVersion(
                version_hash=template.content_hash,
                parent_hash=old_hash,
                change_description=f"Removed layer: {layer_name}",
            )
        )
        return template

    def mark_used(self, template_name: str) -> None:
        """Mark a template as used, making it immutable.

        Parameters
        ----------
        template_name:
            Name of the template to mark.

        Raises
        ------
        KeyError
            If the template does not exist.
        """
        template = self._templates.get(template_name)
        if template is None:
            raise KeyError(f"Template '{template_name}' not found")
        template.is_used = True

    def fork_template(
        self,
        source_name: str,
        new_name: str,
        *,
        additional_layers: list[PromptLayer] | None = None,
    ) -> PromptTemplate:
        """Create a new template by forking an existing one.

        The source template remains unchanged. The fork starts with copies
        of all source layers plus any additional layers.

        Parameters
        ----------
        source_name:
            Name of the template to fork from.
        new_name:
            Name for the new template.
        additional_layers:
            Optional layers to add on top of the forked layers.

        Returns
        -------
        PromptTemplate
            The newly created template.

        Raises
        ------
        KeyError
            If the source template does not exist.
        """
        source = self._templates.get(source_name)
        if source is None:
            raise KeyError(f"Template '{source_name}' not found")

        layers = [deepcopy(ly) for ly in source.layers]
        if additional_layers:
            layers.extend(additional_layers)

        template = PromptTemplate(
            name=new_name,
            layers=layers,
            metadata=deepcopy(source.metadata),
        )
        template.content_hash = template._compute_content_hash()
        template.version = template.content_hash[:12]
        template.version_history.append(
            PromptVersion(
                version_hash=template.content_hash,
                parent_hash=source.content_hash,
                change_description=f"Forked from '{source_name}'",
            )
        )
        self._templates[new_name] = template
        return template

    def compose(self, template_name: str) -> ComposedPrompt:
        """Compose all layers of a template into a single prompt text.

        Layers are merged in priority order within each type, with the
        canonical order: base -> rubric -> few_shot -> patch.

        Parameters
        ----------
        template_name:
            Name of the template to compose.

        Returns
        -------
        ComposedPrompt
            The composed prompt with full text and hash.

        Raises
        ------
        KeyError
            If the template does not exist.
        """
        template = self._templates.get(template_name)
        if template is None:
            raise KeyError(f"Template '{template_name}' not found")

        return self._compose_layers(template)

    def compose_from_layers(self, layers: list[PromptLayer]) -> ComposedPrompt:
        """Compose a prompt directly from a list of layers.

        Parameters
        ----------
        layers:
            List of layers to compose (does not require a stored template).

        Returns
        -------
        ComposedPrompt
            The composed prompt.
        """
        template = PromptTemplate(name="__anonymous__", layers=list(layers))
        return self._compose_layers(template)

    def to_yaml_dict(self, template_name: str) -> dict[str, Any]:
        """Serialize a template to a dict suitable for YAML output.

        Parameters
        ----------
        template_name:
            Name of the template to serialize.

        Returns
        -------
        dict
            YAML-serializable representation.

        Raises
        ------
        KeyError
            If the template does not exist.
        """
        template = self._templates.get(template_name)
        if template is None:
            raise KeyError(f"Template '{template_name}' not found")

        return {
            "name": template.name,
            "version": template.version,
            "content_hash": template.content_hash,
            "is_used": template.is_used,
            "created_at": template.created_at.isoformat(),
            "metadata": template.metadata,
            "layers": [
                {
                    "layer_type": ly.layer_type,
                    "name": ly.name,
                    "priority": ly.priority,
                    "content": ly.content,
                    "metadata": ly.metadata,
                }
                for ly in template.layers
            ],
            "version_history": [
                {
                    "version_hash": v.version_hash,
                    "parent_hash": v.parent_hash,
                    "created_at": v.created_at.isoformat(),
                    "change_description": v.change_description,
                }
                for v in template.version_history
            ],
        }

    def from_yaml_dict(self, data: dict[str, Any]) -> PromptTemplate:
        """Load a template from a YAML-parsed dict.

        Parameters
        ----------
        data:
            Dict with template data (as produced by ``to_yaml_dict``).

        Returns
        -------
        PromptTemplate
            The loaded template, registered in the manager.
        """
        layers = [
            PromptLayer(
                layer_type=ly["layer_type"],
                name=ly.get("name", ""),
                priority=ly.get("priority", 0),
                content=ly["content"],
                metadata=ly.get("metadata", {}),
            )
            for ly in data.get("layers", [])
        ]

        version_history = [
            PromptVersion(
                version_hash=v["version_hash"],
                parent_hash=v.get("parent_hash"),
                created_at=datetime.fromisoformat(v["created_at"])
                if "created_at" in v
                else datetime.now(UTC),
                change_description=v.get("change_description", ""),
            )
            for v in data.get("version_history", [])
        ]

        template = PromptTemplate(
            name=data["name"],
            version=data.get("version", ""),
            layers=layers,
            content_hash=data.get("content_hash", ""),
            is_used=data.get("is_used", False),
            created_at=datetime.fromisoformat(data["created_at"])
            if "created_at" in data
            else datetime.now(UTC),
            metadata=data.get("metadata", {}),
            version_history=version_history,
        )

        # Recompute hash if not provided or empty
        if not template.content_hash:
            template.content_hash = template._compute_content_hash()
        if not template.version:
            template.version = template.content_hash[:12]

        self._templates[template.name] = template
        return template

    # -- Private helpers --

    def _compose_layers(self, template: PromptTemplate) -> ComposedPrompt:
        """Compose layers in canonical order: base, rubric, few_shot, patch."""
        type_order = {
            PromptLayerType.base: 0,
            PromptLayerType.rubric: 1,
            PromptLayerType.few_shot: 2,
            PromptLayerType.patch: 3,
        }

        sorted_layers = sorted(
            template.layers,
            key=lambda ly: (  # type: ignore[arg-type]
                type_order.get(ly.layer_type, 99),
                ly.priority,
                ly.name,
            ),
        )

        parts: list[str] = []
        layer_hashes: list[str] = []
        for layer in sorted_layers:
            if layer.content.strip():
                parts.append(layer.content)
                layer_hashes.append(layer.content_hash)

        text = "\n\n".join(parts)
        content_hash = _compute_hash(text)

        return ComposedPrompt(
            text=text,
            content_hash=content_hash,
            source_template_name=template.name,
            layer_count=len(sorted_layers),
            layer_hashes=layer_hashes,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_hash(content: str) -> str:
    """Compute SHA-256 hex digest of content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()

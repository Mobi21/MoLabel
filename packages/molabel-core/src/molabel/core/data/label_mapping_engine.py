"""Label mapping engine (DT-011, DT-012).

Provides field mapping, value transformation, partial mapping, unmapped
field preservation, and saved/reusable mapping configurations.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from pydantic import BaseModel

from molabel.core.database import get_session
from molabel.core.types import TrustLevel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Mapping types
# ---------------------------------------------------------------------------


class FieldMapping(BaseModel):
    """Maps a source field to a target field with optional value transforms."""

    source_field: str
    target_field: str
    value_map: dict[str, str] | None = None
    """For categorical fields: source_value -> target_value."""
    type_conversion: str | None = None
    """Optional type conversion: ``str``, ``int``, ``float``, ``bool``."""
    default_value: Any = None
    """Default value when the source field is missing."""


class MappingConfig(BaseModel):
    """A complete mapping configuration."""

    name: str
    source_system: str
    field_mappings: list[FieldMapping]
    default_trust_level: TrustLevel = TrustLevel.external
    unmapped_field_policy: str = "preserve_reference"
    """One of: ``preserve_reference``, ``discard``, ``error``."""


class MappingResult(BaseModel):
    """Result of applying a label mapping to a set of labels."""

    mapped_labels: dict[str, Any]
    unmapped_fields: dict[str, Any]
    warnings: list[str] = []


# ---------------------------------------------------------------------------
# LabelMappingEngine
# ---------------------------------------------------------------------------


class LabelMappingEngine:
    """Maps labels from external formats to MoLabel's internal schema.

    Supports field mapping, value transformation, partial mapping, and
    unmapped field preservation. Mapping configurations can be saved and
    reused.
    """

    def apply_mapping(
        self,
        source_labels: dict[str, Any],
        config: MappingConfig,
    ) -> MappingResult:
        """Apply a mapping configuration to source labels.

        Parameters
        ----------
        source_labels:
            The original label dict from the external source.
        config:
            The mapping configuration to apply.

        Returns
        -------
        MappingResult:
            Contains the mapped labels, unmapped fields, and warnings.
        """
        mapped: dict[str, Any] = {}
        unmapped: dict[str, Any] = {}
        warnings: list[str] = []

        mapped_source_fields: set[str] = set()

        for fm in config.field_mappings:
            source_val = source_labels.get(fm.source_field)
            mapped_source_fields.add(fm.source_field)

            if source_val is None:
                if fm.default_value is not None:
                    mapped[fm.target_field] = fm.default_value
                else:
                    warnings.append(
                        f"Source field '{fm.source_field}' not found in source labels"
                    )
                continue

            # Apply value mapping if present.
            if fm.value_map is not None:
                str_val = str(source_val)
                if str_val in fm.value_map:
                    source_val = fm.value_map[str_val]
                elif isinstance(source_val, list):
                    source_val = [fm.value_map.get(str(v), v) for v in source_val]
                else:
                    warnings.append(
                        f"Value '{source_val}' for field "
                        f"'{fm.source_field}' not in value map"
                    )

            # Apply type conversion.
            if fm.type_conversion:
                source_val = self._convert_type(
                    source_val, fm.type_conversion, warnings
                )

            mapped[fm.target_field] = source_val

        # Handle unmapped fields.
        for key, value in source_labels.items():
            if key not in mapped_source_fields:
                if config.unmapped_field_policy == "preserve_reference":
                    unmapped[key] = value
                elif config.unmapped_field_policy == "error":
                    warnings.append(f"Unmapped field '{key}' with policy 'error'")

        return MappingResult(
            mapped_labels=mapped,
            unmapped_fields=unmapped,
            warnings=warnings,
        )

    def apply_mapping_batch(
        self,
        source_labels_list: list[dict[str, Any]],
        config: MappingConfig,
    ) -> list[MappingResult]:
        """Apply mapping to a batch of label dicts."""
        return [self.apply_mapping(labels, config) for labels in source_labels_list]

    def save_mapping(
        self,
        engine: Any,
        *,
        workspace_id: uuid.UUID,
        task_schema_id: uuid.UUID,
        config: MappingConfig,
        file_path: str | None = None,
    ) -> uuid.UUID:
        """Save a mapping configuration to the database.

        Returns the mapping ID.
        """
        from molabel.core.models.label_mapping import LabelMapping

        slug = _slugify(config.name)

        field_mappings_dict = {
            fm.source_field: {
                "target_field": fm.target_field,
                "value_map": fm.value_map,
                "type_conversion": fm.type_conversion,
                "default_value": fm.default_value,
            }
            for fm in config.field_mappings
        }

        value_mappings_dict = {}
        for fm in config.field_mappings:
            if fm.value_map:
                value_mappings_dict[fm.source_field] = fm.value_map

        type_conversions_dict = {}
        for fm in config.field_mappings:
            if fm.type_conversion:
                type_conversions_dict[fm.source_field] = fm.type_conversion

        with get_session(engine) as session:
            mapping = LabelMapping(
                workspace_id=workspace_id,
                mapping_slug=slug,
                name=config.name,
                source_system=config.source_system,
                task_schema_id=task_schema_id,
                field_mappings=field_mappings_dict,
                value_mappings=value_mappings_dict or None,
                type_conversions=type_conversions_dict or None,
                unmapped_field_policy=config.unmapped_field_policy,
                default_trust_level=config.default_trust_level,
                file_path=file_path,
            )
            session.add(mapping)
            session.commit()
            session.refresh(mapping)
            return mapping.id

    def load_mapping(
        self,
        engine: Any,
        *,
        mapping_id: uuid.UUID | None = None,
        mapping_slug: str | None = None,
        workspace_id: uuid.UUID | None = None,
    ) -> MappingConfig | None:
        """Load a saved mapping configuration from the database.

        Looks up by ID or slug+workspace.
        """
        from molabel.core.models.label_mapping import LabelMapping

        with get_session(engine) as session:
            if mapping_id:
                lm = session.get(LabelMapping, mapping_id)
            elif mapping_slug and workspace_id:
                from sqlmodel import select

                stmt = select(LabelMapping).where(
                    LabelMapping.workspace_id == workspace_id,
                    LabelMapping.mapping_slug == mapping_slug,
                )
                lm = session.exec(stmt).first()
            else:
                return None

            if not lm:
                return None

            field_mappings = []
            for source_field, fm_data in lm.field_mappings.items():
                field_mappings.append(
                    FieldMapping(
                        source_field=source_field,
                        target_field=fm_data["target_field"],
                        value_map=fm_data.get("value_map"),
                        type_conversion=fm_data.get("type_conversion"),
                        default_value=fm_data.get("default_value"),
                    )
                )

            return MappingConfig(
                name=lm.name,
                source_system=lm.source_system,
                field_mappings=field_mappings,
                default_trust_level=lm.default_trust_level,
                unmapped_field_policy=lm.unmapped_field_policy,
            )

    def list_mappings(
        self,
        engine: Any,
        *,
        workspace_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        """List all saved mapping configurations for a workspace."""
        from molabel.core.models.label_mapping import LabelMapping

        with get_session(engine) as session:
            from sqlmodel import select

            stmt = select(LabelMapping).where(LabelMapping.workspace_id == workspace_id)
            mappings = list(session.exec(stmt).all())

        return [
            {
                "id": str(m.id),
                "name": m.name,
                "slug": m.mapping_slug,
                "source_system": m.source_system,
                "trust_level": m.default_trust_level,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in mappings
        ]

    def delete_mapping(
        self,
        engine: Any,
        *,
        mapping_id: uuid.UUID,
    ) -> bool:
        """Delete a saved mapping configuration. Returns True if deleted."""
        from molabel.core.models.label_mapping import LabelMapping

        with get_session(engine) as session:
            lm = session.get(LabelMapping, mapping_id)
            if not lm:
                return False
            session.delete(lm)
            session.commit()
            return True

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _convert_type(
        value: Any,
        target_type: str,
        warnings: list[str],
    ) -> Any:
        """Convert *value* to *target_type*."""
        try:
            if target_type == "str":
                return str(value)
            elif target_type == "int":
                return int(value)
            elif target_type == "float":
                return float(value)
            elif target_type == "bool":
                if isinstance(value, str):
                    return value.lower() in ("true", "1", "yes")
                return bool(value)
            else:
                warnings.append(f"Unknown type conversion: {target_type}")
                return value
        except (ValueError, TypeError) as exc:
            warnings.append(
                f"Type conversion to {target_type} failed for value '{value}': {exc}"
            )
            return value


def _slugify(name: str) -> str:
    """Create a slug from a mapping name."""
    import re

    slug = re.sub(r"[^\w\s-]", "", name.lower())
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug.strip("-")[:64]

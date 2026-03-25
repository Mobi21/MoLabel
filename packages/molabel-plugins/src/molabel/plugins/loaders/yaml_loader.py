"""YAML data loader plugin."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from molabel.core.plugins.registry import PluginRegistry
from molabel.core.types import SENTINEL_DATASET_ID, PluginMetadata, Record


class YamlLoader:
    """Loads records from YAML files.

    Expects the YAML file to contain either:
    - A list of mappings (each mapping becomes a record).
    - A mapping with a key pointing to a list (use ``records_path`` config).

    Supports config options:
    - ``id_field``: field name to use as ``external_id``.
    - ``records_path``: dot-separated path to the list within the YAML.
    - ``encoding``: file encoding (default ``"utf-8"``).
    """

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            plugin_id="molabel.loaders.yaml",
            version="0.1.0",
            compatible_core=">=0.1,<1.0",
            description="Loads records from YAML files.",
            author="MoLabel",
            tags=["loader", "yaml"],
        )

    @property
    def supported_formats(self) -> list[str]:
        return ["yaml", "yml"]

    def can_load(self, path: Path) -> bool:
        return path.is_file() and path.suffix.lower() in {".yaml", ".yml"}

    def _extract_records(
        self, data: Any, records_path: str | None
    ) -> list[dict[str, Any]]:
        if records_path:
            obj = data
            for part in records_path.split("."):
                if isinstance(obj, dict):
                    obj = obj[part]
                else:
                    raise ValueError(
                        f"Cannot traverse path '{records_path}': "
                        f"expected dict at '{part}', got {type(obj).__name__}"
                    )
            data = obj
        if not isinstance(data, list):
            raise ValueError(
                f"Expected a YAML list of mappings, got {type(data).__name__}"
            )
        return data

    def load_records(
        self,
        path: Path,
        config: dict[str, Any],
    ) -> Iterator[Record]:
        id_field = config.get("id_field")
        records_path = config.get("records_path")
        encoding = config.get("encoding", "utf-8")

        with path.open(encoding=encoding) as f:
            data = yaml.safe_load(f)

        items = self._extract_records(data, records_path)
        for raw in items:
            if not isinstance(raw, dict):
                continue
            external_id = str(raw[id_field]) if id_field and id_field in raw else None
            yield Record(
                id=uuid4(),
                dataset_id=SENTINEL_DATASET_ID,
                external_id=external_id,
                stable_fields=raw,
                payload=raw,
                record_kind=None,
            )

    def get_schema(self, path: Path) -> dict[str, Any]:
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = None
            for val in data.values():
                if isinstance(val, list) and val and isinstance(val[0], dict):
                    items = val
                    break
            if items is None:
                items = [data]
        else:
            return {"type": "object", "properties": {}}

        if not items:
            return {"type": "object", "properties": {}}

        sample = items[0] if isinstance(items[0], dict) else {}
        properties: dict[str, Any] = {}
        for key, value in sample.items():
            if isinstance(value, str):
                properties[key] = {"type": "string"}
            elif isinstance(value, bool):
                properties[key] = {"type": "boolean"}
            elif isinstance(value, int):
                properties[key] = {"type": "integer"}
            elif isinstance(value, float):
                properties[key] = {"type": "number"}
            elif isinstance(value, list):
                properties[key] = {"type": "array"}
            elif isinstance(value, dict):
                properties[key] = {"type": "object"}
            elif value is None:
                properties[key] = {"type": "null"}
            else:
                properties[key] = {"type": "string"}
        return {"type": "object", "properties": properties}

    def estimate_record_count(self, path: Path) -> int | None:
        try:
            with path.open(encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if isinstance(data, list):
                return len(data)
            return None
        except (OSError, yaml.YAMLError):
            return None


def register(registry: PluginRegistry) -> None:
    """Entry point called by molabel-core at startup."""
    registry.register_data_loader(YamlLoader())

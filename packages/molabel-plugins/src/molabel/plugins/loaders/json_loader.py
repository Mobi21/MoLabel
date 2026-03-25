"""JSON data loader plugin."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

from molabel.core.plugins.registry import PluginRegistry
from molabel.core.types import SENTINEL_DATASET_ID, PluginMetadata, Record


class JsonLoader:
    """Loads records from JSON files containing an array of objects.

    Supports config options:
    - ``id_field``: field name to use as ``external_id``.
    - ``records_path``: dot-separated path to the array in the JSON
      (e.g. ``"data.items"``). Defaults to root.
    - ``encoding``: file encoding (default ``"utf-8"``).
    """

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            plugin_id="molabel.loaders.json",
            version="0.1.0",
            compatible_core=">=0.1,<1.0",
            description="Loads records from JSON files (array of objects).",
            author="MoLabel",
            tags=["loader", "json"],
        )

    @property
    def supported_formats(self) -> list[str]:
        return ["json"]

    def can_load(self, path: Path) -> bool:
        return path.is_file() and path.suffix.lower() == ".json"

    def _extract_records_array(
        self, data: Any, records_path: str | None
    ) -> list[dict[str, Any]]:
        """Navigate a dot-path into the parsed JSON and return the list."""
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
                f"Expected a JSON array of objects, got {type(data).__name__}"
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
            data = json.load(f)

        items = self._extract_records_array(data, records_path)
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
            data = json.load(f)

        # Try to find a list to sample from
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            # Look for the first list-valued key
            items = None
            for val in data.values():
                if isinstance(val, list) and val and isinstance(val[0], dict):
                    items = val
                    break
            if items is None:
                # Treat the dict itself as the schema source
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
            # Return None for files over 10 MB — counting is too expensive.
            if path.stat().st_size > 10 * 1024 * 1024:
                return None
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return len(data)
            return None
        except (OSError, json.JSONDecodeError):
            return None


def register(registry: PluginRegistry) -> None:
    """Entry point called by molabel-core at startup."""
    registry.register_data_loader(JsonLoader())

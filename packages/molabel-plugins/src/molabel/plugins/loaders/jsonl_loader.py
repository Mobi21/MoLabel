"""JSONL (JSON Lines) data loader plugin."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

from molabel.core.plugins.registry import PluginRegistry
from molabel.core.types import SENTINEL_DATASET_ID, PluginMetadata, Record


class JsonlLoader:
    """Loads records from JSONL files (one JSON object per line).

    Supports config options:
    - ``id_field``: field name to use as ``external_id``.
    - ``encoding``: file encoding (default ``"utf-8"``).
    """

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            plugin_id="molabel.loaders.jsonl",
            version="0.1.0",
            compatible_core=">=0.1,<1.0",
            description="Loads records from JSONL files.",
            author="MoLabel",
            tags=["loader", "jsonl", "json-lines"],
        )

    @property
    def supported_formats(self) -> list[str]:
        return ["jsonl"]

    def can_load(self, path: Path) -> bool:
        return path.is_file() and path.suffix.lower() == ".jsonl"

    def load_records(
        self,
        path: Path,
        config: dict[str, Any],
    ) -> Iterator[Record]:
        id_field = config.get("id_field")
        encoding = config.get("encoding", "utf-8")

        with path.open(encoding=encoding) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                raw = json.loads(line)
                external_id = (
                    str(raw[id_field]) if id_field and id_field in raw else None
                )
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
            first_line = f.readline().strip()
        if not first_line:
            return {"type": "object", "properties": {}}
        sample = json.loads(first_line)
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
                return sum(1 for line in f if line.strip())
        except OSError:
            return None


def register(registry: PluginRegistry) -> None:
    """Entry point called by molabel-core at startup."""
    registry.register_data_loader(JsonlLoader())

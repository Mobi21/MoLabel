"""CSV data loader plugin."""

from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

from molabel.core.plugins.registry import PluginRegistry
from molabel.core.types import SENTINEL_DATASET_ID, PluginMetadata, Record


class CsvLoader:
    """Loads records from CSV files using the Python ``csv`` module.

    Supports config options:
    - ``delimiter``: field delimiter (default ``","``).
    - ``id_column``: column name to use as ``external_id``.
    - ``encoding``: file encoding (default ``"utf-8"``).
    - ``has_header``: whether the file has a header row (default ``True``).
    """

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            plugin_id="molabel.loaders.csv",
            version="0.1.0",
            compatible_core=">=0.1,<1.0",
            description="Loads records from CSV files.",
            author="MoLabel",
            tags=["loader", "csv", "tabular"],
        )

    @property
    def supported_formats(self) -> list[str]:
        return ["csv", "tsv"]

    def can_load(self, path: Path) -> bool:
        return path.is_file() and path.suffix.lower() in {".csv", ".tsv"}

    def load_records(
        self,
        path: Path,
        config: dict[str, Any],
    ) -> Iterator[Record]:
        default_delim = "\t" if path.suffix.lower() == ".tsv" else ","
        delimiter = config.get("delimiter", default_delim)
        id_column = config.get("id_column")
        encoding = config.get("encoding", "utf-8")
        has_header = config.get("has_header", True)

        with path.open(encoding=encoding, newline="") as f:
            if has_header:
                reader = csv.DictReader(f, delimiter=delimiter)
                for row in reader:
                    raw = dict(row)
                    external_id = (
                        str(raw[id_column]) if id_column and id_column in raw else None
                    )
                    yield Record(
                        id=uuid4(),
                        dataset_id=SENTINEL_DATASET_ID,
                        external_id=external_id,
                        stable_fields=raw,
                        payload=raw,
                        record_kind=None,
                    )
            else:
                reader_list = csv.reader(f, delimiter=delimiter)
                for idx, row in enumerate(reader_list):
                    raw = {f"col_{i}": val for i, val in enumerate(row)}
                    yield Record(
                        id=uuid4(),
                        dataset_id=SENTINEL_DATASET_ID,
                        external_id=str(idx),
                        stable_fields=raw,
                        payload=raw,
                        record_kind=None,
                    )

    def get_schema(self, path: Path) -> dict[str, Any]:
        encoding = "utf-8"
        with path.open(encoding=encoding, newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            # Read first row for type inference
            sample_row = next(reader, None)

        properties: dict[str, Any] = {}
        for name in fieldnames:
            sample_val = sample_row.get(name, "") if sample_row else ""
            # Simple type inference from sample value
            if sample_val is not None:
                try:
                    int(sample_val)
                    properties[name] = {"type": "integer"}
                    continue
                except (ValueError, TypeError):
                    pass
                try:
                    float(sample_val)
                    properties[name] = {"type": "number"}
                    continue
                except (ValueError, TypeError):
                    pass
            properties[name] = {"type": "string"}

        return {"type": "object", "properties": properties}

    def estimate_record_count(self, path: Path) -> int | None:
        try:
            with path.open(encoding="utf-8") as f:
                # Subtract 1 for header row
                count = sum(1 for line in f if line.strip())
                return max(0, count - 1)
        except OSError:
            return None


def register(registry: PluginRegistry) -> None:
    """Entry point called by molabel-core at startup."""
    registry.register_data_loader(CsvLoader())

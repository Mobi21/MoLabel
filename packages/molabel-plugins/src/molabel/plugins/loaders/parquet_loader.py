"""Parquet data loader plugin.

Uses ``pyarrow`` when available, otherwise raises a helpful ImportError.
The ``pyarrow`` dependency is optional in ``molabel-plugins`` to keep the
default install lightweight.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

from molabel.core.plugins.registry import PluginRegistry
from molabel.core.types import SENTINEL_DATASET_ID, PluginMetadata, Record

_PYARROW_TYPE_MAP = {
    "string": "string",
    "large_string": "string",
    "utf8": "string",
    "large_utf8": "string",
    "int8": "integer",
    "int16": "integer",
    "int32": "integer",
    "int64": "integer",
    "uint8": "integer",
    "uint16": "integer",
    "uint32": "integer",
    "uint64": "integer",
    "float16": "number",
    "float32": "number",
    "float64": "number",
    "double": "number",
    "float": "number",
    "bool": "boolean",
    "bool_": "boolean",
    "binary": "string",
    "large_binary": "string",
}


def _import_pyarrow():  # noqa: ANN202
    try:
        import pyarrow.parquet as pq  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "The Parquet loader requires 'pyarrow'. "
            "Install it with: pip install pyarrow"
        ) from exc
    return pq


class ParquetLoader:
    """Loads records from Parquet files via ``pyarrow``.

    Supports config options:
    - ``id_column``: column name to use as ``external_id``.
    - ``columns``: list of column names to read (default: all).
    - ``batch_size``: number of rows per read batch (default ``10_000``).
    """

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            plugin_id="molabel.loaders.parquet",
            version="0.1.0",
            compatible_core=">=0.1,<1.0",
            description="Loads records from Parquet files.",
            author="MoLabel",
            tags=["loader", "parquet", "columnar"],
        )

    @property
    def supported_formats(self) -> list[str]:
        return ["parquet"]

    def can_load(self, path: Path) -> bool:
        return path.is_file() and path.suffix.lower() == ".parquet"

    def load_records(
        self,
        path: Path,
        config: dict[str, Any],
    ) -> Iterator[Record]:
        pq = _import_pyarrow()

        id_column = config.get("id_column")
        columns = config.get("columns")
        batch_size = config.get("batch_size", 10_000)

        parquet_file = pq.ParquetFile(str(path))
        for batch in parquet_file.iter_batches(batch_size=batch_size, columns=columns):
            table = batch.to_pydict()
            num_rows = len(next(iter(table.values()))) if table else 0
            for i in range(num_rows):
                raw = {col: table[col][i] for col in table}
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

    def get_schema(self, path: Path) -> dict[str, Any]:
        pq = _import_pyarrow()

        schema = pq.read_schema(str(path))
        properties: dict[str, Any] = {}
        for i in range(len(schema)):
            field = schema.field(i)
            type_str = str(field.type)
            json_type = _PYARROW_TYPE_MAP.get(type_str, "string")
            properties[field.name] = {"type": json_type}
        return {"type": "object", "properties": properties}

    def estimate_record_count(self, path: Path) -> int | None:
        pq = _import_pyarrow()
        try:
            metadata = pq.read_metadata(str(path))
            return metadata.num_rows
        except Exception:
            return None


def register(registry: PluginRegistry) -> None:
    """Entry point called by molabel-core at startup."""
    registry.register_data_loader(ParquetLoader())

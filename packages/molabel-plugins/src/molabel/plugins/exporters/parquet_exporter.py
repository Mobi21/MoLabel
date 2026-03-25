"""Parquet export packager plugin.

Exports labeled records as Parquet files via optional ``pyarrow``.
The ``pyarrow`` dependency is optional in ``molabel-plugins`` to keep
the default install lightweight.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from molabel.core.plugins.registry import PluginRegistry
from molabel.core.types import (
    ExportArtifact,
    PluginMetadata,
    Record,
    ReviewEvent,
    ValidationError,
    ValidationResult,
)
from molabel.plugins.exporters._common import build_row, select_labels


def _import_pyarrow():  # noqa: ANN202
    try:
        import pyarrow as pa  # type: ignore[import-untyped]
        import pyarrow.parquet as pq  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "The Parquet exporter requires 'pyarrow'. "
            "Install it with: pip install pyarrow"
        ) from exc
    return pa, pq


def _normalize_value(value: Any) -> Any:
    """Convert complex values to Parquet-safe types."""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


class ParquetExporter:
    """Exports records as Parquet files via ``pyarrow``.

    Supports config options:
    - ``destination``: output file path (required for Parquet; if omitted,
      writes to a temp file and returns in-memory bytes).
    - ``label_strategy``: ``"latest"`` or ``"first"`` (default ``"latest"``).
    - ``include_metadata``: include record IDs in output (default ``False``).
    - ``columns``: list of column names to include (default: all).
    - ``compression``: Parquet compression codec (default ``"snappy"``).
    """

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            plugin_id="molabel.exporters.parquet",
            version="0.1.0",
            compatible_core=">=0.1,<1.0",
            description="Exports labeled records as Parquet files.",
            author="MoLabel",
            tags=["exporter", "parquet", "columnar"],
        )

    @property
    def supported_formats(self) -> list[str]:
        return ["parquet"]

    def package(
        self,
        records: list[Record],
        labels: dict[str, list[ReviewEvent]],
        config: dict[str, Any],
    ) -> ExportArtifact:
        pa, pq = _import_pyarrow()

        destination = config.get("destination")
        compression = config.get("compression", "snappy")
        columns_filter = config.get("columns")

        # Build all rows to determine column superset.
        rows: list[dict[str, Any]] = []
        all_keys: list[str] = []
        seen_keys: set[str] = set()

        for record in records:
            record_labels = select_labels(
                labels.get(str(record.id), []),
                config,
            )
            row = build_row(record, record_labels, config)
            rows.append(row)
            for key in row:
                if key not in seen_keys:
                    seen_keys.add(key)
                    all_keys.append(key)

        if columns_filter:
            all_keys = [k for k in all_keys if k in columns_filter]

        # Build columnar data.
        col_data: dict[str, list[Any]] = {k: [] for k in all_keys}
        for row in rows:
            for key in all_keys:
                col_data[key].append(_normalize_value(row.get(key)))

        table = pa.table(col_data)

        if destination:
            dest_path = Path(destination)
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            pq.write_table(table, str(dest_path), compression=compression)
            checksum = hashlib.sha256(dest_path.read_bytes()).hexdigest()
            return ExportArtifact(
                path=dest_path,
                format="parquet",
                record_count=len(records),
                checksum=checksum,
            )

        # No destination: write to temp file, read bytes, clean up.
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        pq.write_table(table, str(tmp_path), compression=compression)
        content_bytes = tmp_path.read_bytes()
        tmp_path.unlink()

        checksum = hashlib.sha256(content_bytes).hexdigest()
        return ExportArtifact(
            data=content_bytes,
            format="parquet",
            record_count=len(records),
            checksum=checksum,
        )

    def validate_export(
        self,
        artifact: ExportArtifact,
    ) -> ValidationResult:
        try:
            pa, pq = _import_pyarrow()

            if artifact.path is not None:
                pf = pq.ParquetFile(str(artifact.path))
            elif artifact.data is not None:
                import io

                pf = pq.ParquetFile(io.BytesIO(artifact.data))
            else:
                return ValidationResult(
                    is_valid=False,
                    errors=[
                        ValidationError(
                            field=None,
                            message="No data or path in artifact",
                            code="missing_content",
                        ),
                    ],
                )

            row_count = pf.metadata.num_rows

            if artifact.record_count and row_count != artifact.record_count:
                return ValidationResult(
                    is_valid=False,
                    errors=[
                        ValidationError(
                            field=None,
                            message=(
                                f"Expected {artifact.record_count} records, "
                                f"found {row_count}"
                            ),
                            code="count_mismatch",
                        ),
                    ],
                )

            return ValidationResult(is_valid=True)

        except ImportError:
            return ValidationResult(
                is_valid=False,
                errors=[
                    ValidationError(
                        field=None,
                        message="pyarrow is required to validate Parquet",
                        code="missing_dependency",
                    ),
                ],
            )
        except Exception as exc:
            return ValidationResult(
                is_valid=False,
                errors=[
                    ValidationError(
                        field=None,
                        message=str(exc),
                        code="validation_error",
                    ),
                ],
            )

    def get_export_schema(self) -> dict[str, Any]:
        return {
            "format_notes": (
                "Apache Parquet: columnar format with schema support. "
                "Complex values (dicts, lists) are JSON-encoded as strings. "
                "Compression is configurable (default: snappy)."
            ),
            "columns": [
                {
                    "name": "*",
                    "type": "varies",
                    "description": (
                        "All record stable fields plus label fields. "
                        "Types are inferred by pyarrow from the data."
                    ),
                },
            ],
        }


def register(registry: PluginRegistry) -> None:
    """Entry point called by molabel-core at startup."""
    registry.register_export_packager(ParquetExporter())

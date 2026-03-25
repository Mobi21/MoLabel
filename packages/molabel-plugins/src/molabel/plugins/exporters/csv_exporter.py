"""CSV export packager plugin.

Exports labeled records as CSV files with configurable delimiter
and column selection.
"""

from __future__ import annotations

import csv
import hashlib
import io
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


def _flatten_value(value: Any) -> str:
    """Flatten complex values to strings suitable for CSV cells."""
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        import json

        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


class CsvExporter:
    """Exports records as CSV files.

    Supports config options:
    - ``destination``: output file path (default: in-memory bytes).
    - ``delimiter``: field delimiter (default ``","``).
    - ``label_strategy``: ``"latest"`` or ``"first"`` (default ``"latest"``).
    - ``include_metadata``: include record IDs in output (default ``False``).
    - ``columns``: list of column names to include (default: all).
    - ``encoding``: file encoding (default ``"utf-8"``).
    """

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            plugin_id="molabel.exporters.csv",
            version="0.1.0",
            compatible_core=">=0.1,<1.0",
            description="Exports labeled records as CSV files.",
            author="MoLabel",
            tags=["exporter", "csv", "tabular"],
        )

    @property
    def supported_formats(self) -> list[str]:
        return ["csv"]

    def package(
        self,
        records: list[Record],
        labels: dict[str, list[ReviewEvent]],
        config: dict[str, Any],
    ) -> ExportArtifact:
        encoding = config.get("encoding", "utf-8")
        delimiter = config.get("delimiter", ",")
        destination = config.get("destination")
        columns = config.get("columns")

        # Build all rows first to determine the full set of columns.
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

        # Apply column filter if specified.
        if columns:
            all_keys = [k for k in all_keys if k in columns]

        buf = io.StringIO()
        writer = csv.DictWriter(
            buf,
            fieldnames=all_keys,
            delimiter=delimiter,
            extrasaction="ignore",
        )
        writer.writeheader()
        for row in rows:
            flat_row = {k: _flatten_value(row.get(k)) for k in all_keys}
            writer.writerow(flat_row)

        content_bytes = buf.getvalue().encode(encoding)
        checksum = hashlib.sha256(content_bytes).hexdigest()

        if destination:
            dest_path = Path(destination)
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(content_bytes)
            return ExportArtifact(
                path=dest_path,
                format="csv",
                record_count=len(records),
                checksum=checksum,
            )

        return ExportArtifact(
            data=content_bytes,
            format="csv",
            record_count=len(records),
            checksum=checksum,
        )

    def validate_export(
        self,
        artifact: ExportArtifact,
    ) -> ValidationResult:
        try:
            if artifact.data is not None:
                raw = artifact.data.decode("utf-8")
            elif artifact.path is not None:
                raw = artifact.path.read_text(encoding="utf-8")
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

            reader = csv.reader(io.StringIO(raw))
            header = next(reader, None)
            if header is None:
                return ValidationResult(
                    is_valid=False,
                    errors=[
                        ValidationError(
                            field=None,
                            message="CSV file is empty (no header)",
                            code="empty_csv",
                        ),
                    ],
                )

            row_count = sum(1 for _ in reader)

            if artifact.record_count and row_count != artifact.record_count:
                return ValidationResult(
                    is_valid=False,
                    errors=[
                        ValidationError(
                            field=None,
                            message=(
                                f"Expected {artifact.record_count} data rows, "
                                f"found {row_count}"
                            ),
                            code="count_mismatch",
                        ),
                    ],
                )

            return ValidationResult(is_valid=True)

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
                "CSV: comma-separated values with a header row. "
                "Complex values (dicts, lists) are JSON-encoded in cells."
            ),
            "columns": [
                {
                    "name": "*",
                    "type": "string",
                    "description": (
                        "All record stable fields plus label fields, "
                        "flattened to string representations."
                    ),
                },
            ],
        }


def register(registry: PluginRegistry) -> None:
    """Entry point called by molabel-core at startup."""
    registry.register_export_packager(CsvExporter())

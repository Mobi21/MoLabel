"""JSONL export packager plugin.

Exports labeled records as JSONL files (one JSON object per line).
Each line contains the record's stable fields merged with its labels.
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


class JsonlExporter:
    """Exports records as JSONL files.

    Supports config options:
    - ``destination``: output file path (default: in-memory bytes).
    - ``label_strategy``: ``"latest"`` or ``"first"`` (default ``"latest"``).
    - ``include_metadata``: include record IDs in output (default ``False``).
    - ``columns``: list of column names to include (default: all).
    - ``encoding``: file encoding (default ``"utf-8"``).
    """

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            plugin_id="molabel.exporters.jsonl",
            version="0.1.0",
            compatible_core=">=0.1,<1.0",
            description="Exports labeled records as JSONL files.",
            author="MoLabel",
            tags=["exporter", "jsonl", "json-lines"],
        )

    @property
    def supported_formats(self) -> list[str]:
        return ["jsonl"]

    def package(
        self,
        records: list[Record],
        labels: dict[str, list[ReviewEvent]],
        config: dict[str, Any],
    ) -> ExportArtifact:
        encoding = config.get("encoding", "utf-8")
        destination = config.get("destination")

        lines: list[str] = []
        for record in records:
            record_labels = select_labels(
                labels.get(str(record.id), []),
                config,
            )
            row = build_row(record, record_labels, config)
            lines.append(json.dumps(row, ensure_ascii=False, default=str))

        content = "\n".join(lines)
        if lines:
            content += "\n"
        content_bytes = content.encode(encoding)
        checksum = hashlib.sha256(content_bytes).hexdigest()

        if destination:
            dest_path = Path(destination)
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(content_bytes)
            return ExportArtifact(
                path=dest_path,
                format="jsonl",
                record_count=len(records),
                checksum=checksum,
            )

        return ExportArtifact(
            data=content_bytes,
            format="jsonl",
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

            line_count = 0
            for i, line in enumerate(raw.splitlines(), start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    json.loads(line)
                except json.JSONDecodeError as exc:
                    return ValidationResult(
                        is_valid=False,
                        errors=[
                            ValidationError(
                                field=None,
                                message=f"Invalid JSON on line {i}: {exc}",
                                code="invalid_json",
                            ),
                        ],
                    )
                line_count += 1

            if artifact.record_count and line_count != artifact.record_count:
                return ValidationResult(
                    is_valid=False,
                    errors=[
                        ValidationError(
                            field=None,
                            message=(
                                f"Expected {artifact.record_count} records, "
                                f"found {line_count}"
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
                "JSONL (JSON Lines): one JSON object per line. "
                "Each object contains the record's stable fields "
                "merged with the selected labels."
            ),
            "columns": [
                {
                    "name": "*",
                    "type": "any",
                    "description": (
                        "All record stable fields plus label fields. "
                        "Optionally filtered by 'columns' config."
                    ),
                },
            ],
        }


def register(registry: PluginRegistry) -> None:
    """Entry point called by molabel-core at startup."""
    registry.register_export_packager(JsonlExporter())

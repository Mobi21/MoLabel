"""HuggingFace Hub export packager plugin.

Pushes labeled records to a HuggingFace Hub dataset repository.
Uses ``molabel.core.providers.hf_auth`` for token validation and
the ``huggingface_hub`` library for the actual upload.
"""

from __future__ import annotations

import hashlib
import json
import logging
import tempfile
from pathlib import Path
from typing import Any

from molabel.core.plugins.registry import PluginRegistry
from molabel.core.providers.hf_auth import HuggingFaceAuth
from molabel.core.types import (
    ExportArtifact,
    PluginMetadata,
    Record,
    ReviewEvent,
    ValidationError,
    ValidationResult,
    ValidationWarning,
)
from molabel.plugins.exporters._common import build_row, select_labels

logger = logging.getLogger(__name__)


def _import_huggingface_hub():  # noqa: ANN202
    try:
        from huggingface_hub import HfApi  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "The HuggingFace exporter requires 'huggingface_hub'. "
            "Install it with: pip install huggingface_hub"
        ) from exc
    return HfApi


class HuggingFaceExporter:
    """Pushes labeled records to a HuggingFace Hub dataset.

    The exported data is first written as a local JSONL file, then
    uploaded to the specified Hub repository.

    Supports config options:
    - ``repo_id``: HuggingFace dataset repo (e.g. ``"user/my-dataset"``).
      **Required**.
    - ``split``: dataset split name (default ``"train"``).
    - ``token``: explicit HF token (falls back to env vars via ``hf_auth``).
    - ``private``: whether to create a private repo (default ``False``).
    - ``commit_message``: commit message for the upload (default auto).
    - ``label_strategy``: ``"latest"`` or ``"first"`` (default ``"latest"``).
    - ``include_metadata``: include record IDs in output (default ``False``).
    - ``columns``: list of column names to include (default: all).
    """

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            plugin_id="molabel.exporters.huggingface",
            version="0.1.0",
            compatible_core=">=0.1,<1.0",
            description="Pushes labeled records to HuggingFace Hub.",
            author="MoLabel",
            tags=["exporter", "huggingface", "hub"],
        )

    @property
    def supported_formats(self) -> list[str]:
        return ["huggingface_hub"]

    def package(
        self,
        records: list[Record],
        labels: dict[str, list[ReviewEvent]],
        config: dict[str, Any],
    ) -> ExportArtifact:
        repo_id = config.get("repo_id")
        if not repo_id:
            raise ValueError(
                "HuggingFace exporter requires 'repo_id' in config "
                "(e.g. 'username/dataset-name')."
            )

        split = config.get("split", "train")
        token = config.get("token")
        private = config.get("private", False)
        commit_message = config.get(
            "commit_message",
            f"Export {len(records)} records from MoLabel",
        )
        columns_filter = config.get("columns")

        # Resolve token via hf_auth.
        hf_auth = HuggingFaceAuth(token=token)
        resolved_token, _source = hf_auth.resolve_token()
        if not resolved_token:
            raise ValueError(
                "No HuggingFace token found. Set HF_TOKEN environment "
                "variable or pass 'token' in export config."
            )

        # Build JSONL content.
        lines: list[str] = []
        for record in records:
            record_labels = select_labels(
                labels.get(str(record.id), []),
                config,
            )
            row = build_row(record, record_labels, config)
            if columns_filter:
                row = {k: v for k, v in row.items() if k in columns_filter}
            lines.append(json.dumps(row, ensure_ascii=False, default=str))

        content = "\n".join(lines)
        if lines:
            content += "\n"
        content_bytes = content.encode("utf-8")
        checksum = hashlib.sha256(content_bytes).hexdigest()

        # Import huggingface_hub (deferred to after config validation).
        HfApi = _import_huggingface_hub()

        # Write to a temp file and upload.
        filename = f"{split}.jsonl"
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / filename
            tmp_path.write_bytes(content_bytes)

            api = HfApi(token=resolved_token)

            # Create repo if it doesn't exist.
            try:
                api.create_repo(
                    repo_id=repo_id,
                    repo_type="dataset",
                    private=private,
                    exist_ok=True,
                )
            except Exception:
                logger.debug("Could not create repo %s (may already exist)", repo_id)

            api.upload_file(
                path_or_fileobj=str(tmp_path),
                path_in_repo=filename,
                repo_id=repo_id,
                repo_type="dataset",
                commit_message=commit_message,
            )

        hub_url = f"https://huggingface.co/datasets/{repo_id}"
        return ExportArtifact(
            format="huggingface_hub",
            record_count=len(records),
            checksum=checksum,
            metadata={
                "repo_id": repo_id,
                "split": split,
                "url": hub_url,
                "filename": filename,
            },
        )

    def validate_export(
        self,
        artifact: ExportArtifact,
    ) -> ValidationResult:
        # For HF Hub exports, validation is limited to checking that the
        # artifact has the expected metadata fields set during package().
        if artifact.format != "huggingface_hub":
            return ValidationResult(
                is_valid=False,
                errors=[
                    ValidationError(
                        field=None,
                        message=(
                            f"Expected format 'huggingface_hub', "
                            f"got '{artifact.format}'"
                        ),
                        code="wrong_format",
                    ),
                ],
            )

        meta = artifact.metadata or {}
        if not meta.get("repo_id"):
            return ValidationResult(
                is_valid=False,
                errors=[
                    ValidationError(
                        field=None,
                        message="Missing 'repo_id' in artifact metadata",
                        code="missing_repo_id",
                    ),
                ],
            )

        if artifact.record_count == 0:
            return ValidationResult(
                is_valid=True,
                warnings=[
                    ValidationWarning(
                        field=None,
                        message="Export contains 0 records",
                        code="empty_export",
                    ),
                ],
            )

        return ValidationResult(is_valid=True)

    def get_export_schema(self) -> dict[str, Any]:
        return {
            "format_notes": (
                "HuggingFace Hub: uploads a JSONL file to a HuggingFace "
                "dataset repository. Requires authentication via HF_TOKEN "
                "environment variable or explicit 'token' in config."
            ),
            "columns": [
                {
                    "name": "*",
                    "type": "any",
                    "description": (
                        "All record stable fields plus label fields. "
                        "Uploaded as JSONL to the Hub repository."
                    ),
                },
            ],
            "required_config": {
                "repo_id": {
                    "type": "string",
                    "description": "HuggingFace dataset repo ID (e.g. 'user/dataset').",
                },
            },
        }


def register(registry: PluginRegistry) -> None:
    """Entry point called by molabel-core at startup."""
    registry.register_export_packager(HuggingFaceExporter())

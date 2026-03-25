"""HuggingFace datasets loader plugin.

Uses the ``datasets`` library to load datasets from the HuggingFace Hub
or local disk. The library is an optional dependency.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

from molabel.core.plugins.registry import PluginRegistry
from molabel.core.types import SENTINEL_DATASET_ID, PluginMetadata, Record


def _import_datasets():  # noqa: ANN202
    try:
        import datasets  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "The HuggingFace loader requires 'datasets'. "
            "Install it with: pip install datasets"
        ) from exc
    return datasets


def _infer_json_type(value: Any) -> str:
    """Map a Python value to a JSON Schema type string."""
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "string"


class HuggingFaceLoader:
    """Loads records from HuggingFace datasets.

    The ``path`` argument can be either:
    - A local directory containing a saved HuggingFace dataset.
    - A ``Path("huggingface://dataset_name")`` pseudo-path for Hub datasets.

    Supports config options:
    - ``dataset_name``: HuggingFace dataset identifier (e.g.
      ``"imdb"``, ``"tatsu-lab/alpaca_eval"``). Required if *path* is
      not a saved dataset directory.
    - ``split``: dataset split (default ``"train"``).
    - ``id_field``: field name to use as ``external_id``.
    - ``streaming``: if ``True``, use streaming mode (default ``False``).
    - ``trust_remote_code``: passed to ``load_dataset`` (default ``False``).
    """

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            plugin_id="molabel.loaders.huggingface",
            version="0.1.0",
            compatible_core=">=0.1,<1.0",
            description="Loads records from HuggingFace datasets.",
            author="MoLabel",
            tags=["loader", "huggingface", "datasets", "hub"],
        )

    @property
    def supported_formats(self) -> list[str]:
        return ["huggingface"]

    def can_load(self, path: Path) -> bool:
        # Check for saved HF dataset markers
        if path.is_dir():
            return (path / "dataset_info.json").exists() or (
                path / "state.json"
            ).exists()
        # Pseudo-path convention: Path("huggingface://x") normalises to
        # "huggingface:/x", so we check for both forms.
        path_str = str(path)
        return path_str.startswith("huggingface:/") or path_str.startswith(
            "huggingface://"
        )

    def _resolve_dataset_name(self, path: Path, config: dict[str, Any]) -> str | Path:
        """Return the HF dataset name or local path."""
        if config.get("dataset_name"):
            return config["dataset_name"]
        path_str = str(path)
        if path_str.startswith("huggingface://"):
            return path_str[len("huggingface://") :]
        if path_str.startswith("huggingface:/"):
            return path_str[len("huggingface:/") :]
        return path

    def load_records(
        self,
        path: Path,
        config: dict[str, Any],
    ) -> Iterator[Record]:
        datasets_lib = _import_datasets()

        dataset_name = self._resolve_dataset_name(path, config)
        split = config.get("split", "train")
        id_field = config.get("id_field")
        streaming = config.get("streaming", False)
        trust_remote_code = config.get("trust_remote_code", False)

        ds = datasets_lib.load_dataset(
            str(dataset_name) if isinstance(dataset_name, Path) else dataset_name,
            split=split,
            streaming=streaming,
            trust_remote_code=trust_remote_code,
        )

        for row in ds:
            raw = dict(row)
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
        # Try to load features from the dataset
        try:
            datasets_lib = _import_datasets()
            dataset_name = self._resolve_dataset_name(path, {})
            ds = datasets_lib.load_dataset(
                str(dataset_name) if isinstance(dataset_name, Path) else dataset_name,
                split="train",
                streaming=True,
            )
            sample = next(iter(ds))
            properties: dict[str, Any] = {}
            for key, value in sample.items():
                properties[key] = {"type": _infer_json_type(value)}
            return {"type": "object", "properties": properties}
        except Exception:
            return {"type": "object", "properties": {}}

    def estimate_record_count(self, path: Path) -> int | None:
        # HuggingFace datasets don't always expose count cheaply
        try:
            datasets_lib = _import_datasets()
            dataset_name = self._resolve_dataset_name(path, {})
            ds = datasets_lib.load_dataset(
                str(dataset_name) if isinstance(dataset_name, Path) else dataset_name,
                split="train",
            )
            return len(ds)
        except Exception:
            return None


def register(registry: PluginRegistry) -> None:
    """Entry point called by molabel-core at startup."""
    registry.register_data_loader(HuggingFaceLoader())

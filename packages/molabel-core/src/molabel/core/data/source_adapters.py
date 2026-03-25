"""Data source adapters (DT-003, DT-004, DT-005).

Provides adapters for local file ingest, HuggingFace dataset import,
and import from labeling tools (Label Studio, Argilla, Prodigy).
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from molabel.core.types import (
    SENTINEL_DATASET_ID,
    Record,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public result types
# ---------------------------------------------------------------------------


class IngestResult(BaseModel):
    """Result of a data source ingest operation."""

    records_ingested: int = 0
    errors: list[dict[str, Any]] = []
    source_type: str = ""
    metadata: dict[str, Any] = {}


class HuggingFaceSearchResult(BaseModel):
    """A single result from searching HuggingFace Hub."""

    dataset_id: str
    description: str = ""
    downloads: int = 0
    tags: list[str] = []


# ---------------------------------------------------------------------------
# LocalFileAdapter  (DT-003)
# ---------------------------------------------------------------------------


class LocalFileAdapter:
    """Ingests records from local files using the DataLoaderPlugin protocol.

    Supports CSV, JSONL, Parquet, JSON, YAML, and Markdown files through
    the plugin registry.
    """

    def ingest(
        self,
        path: Path,
        *,
        loader: Any | None = None,
        config: dict[str, Any] | None = None,
    ) -> Iterator[Record]:
        """Yield records from a local file or directory.

        Parameters
        ----------
        path:
            Absolute path to the file or directory.
        loader:
            A ``DataLoaderPlugin`` instance. If None, uses a simple
            built-in dispatch based on file extension.
        config:
            Loader-specific configuration.
        """
        cfg = config or {}

        if loader is not None:
            yield from loader.load_records(path, cfg)
            return

        # Built-in fallback: dispatch by extension.
        ext = path.suffix.lower().lstrip(".")
        yield from self._load_by_extension(path, ext, cfg)

    def get_schema(
        self,
        path: Path,
        *,
        loader: Any | None = None,
    ) -> dict[str, Any]:
        """Infer the schema of the data at *path*."""
        if loader is not None:
            return loader.get_schema(path)

        ext = path.suffix.lower().lstrip(".")
        return self._infer_schema(path, ext)

    def estimate_count(
        self,
        path: Path,
        *,
        loader: Any | None = None,
    ) -> int | None:
        """Estimate the record count at *path*."""
        if loader is not None:
            return loader.estimate_record_count(path)

        if path.suffix.lower() in (".csv", ".tsv"):
            with open(path) as f:
                return sum(1 for _ in f) - 1
        if path.suffix.lower() == ".jsonl":
            with open(path) as f:
                return sum(1 for line in f if line.strip())
        return None

    # ------------------------------------------------------------------
    # Built-in fallback loaders
    # ------------------------------------------------------------------

    def _load_by_extension(
        self,
        path: Path,
        ext: str,
        config: dict[str, Any],
    ) -> Iterator[Record]:
        if ext in ("csv", "tsv"):
            yield from self._load_csv(path, config)
        elif ext == "jsonl":
            yield from self._load_jsonl(path, config)
        elif ext == "json":
            yield from self._load_json(path, config)
        elif ext in ("yaml", "yml"):
            yield from self._load_yaml(path, config)
        else:
            raise ValueError(f"Unsupported file format: {ext}")

    def _load_csv(self, path: Path, config: dict[str, Any]) -> Iterator[Record]:
        import csv

        delimiter = config.get("delimiter", ",")
        if path.suffix.lower() == ".tsv":
            delimiter = config.get("delimiter", "\t")
        encoding = config.get("encoding", "utf-8")
        id_column = config.get("id_column")

        with open(path, encoding=encoding, newline="") as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            for i, row in enumerate(reader):
                external_id = row.get(id_column) if id_column else None
                yield Record(
                    id=uuid.uuid4(),
                    dataset_id=SENTINEL_DATASET_ID,
                    external_id=str(external_id) if external_id else None,
                    stable_fields=dict(row),
                    payload=dict(row),
                    source_metadata={"file": str(path), "line": i + 2},
                )

    def _load_jsonl(self, path: Path, config: dict[str, Any]) -> Iterator[Record]:
        id_field = config.get("id_field")
        encoding = config.get("encoding", "utf-8")

        with open(path, encoding=encoding) as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                external_id = obj.get(id_field) if id_field else None
                yield Record(
                    id=uuid.uuid4(),
                    dataset_id=SENTINEL_DATASET_ID,
                    external_id=str(external_id) if external_id else None,
                    stable_fields=obj,
                    payload=obj,
                    source_metadata={"file": str(path), "line": i + 1},
                )

    def _load_json(self, path: Path, config: dict[str, Any]) -> Iterator[Record]:
        encoding = config.get("encoding", "utf-8")
        records_path = config.get("records_path")
        id_field = config.get("id_field")

        with open(path, encoding=encoding) as f:
            data = json.load(f)

        if records_path:
            for key in records_path.split("."):
                if isinstance(data, dict) and key in data:
                    data = data[key]
                else:
                    raise ValueError(f"Cannot traverse path '{records_path}' in JSON")

        if not isinstance(data, list):
            raise ValueError("Expected a JSON array of records")

        for i, obj in enumerate(data):
            external_id = obj.get(id_field) if id_field else None
            yield Record(
                id=uuid.uuid4(),
                dataset_id=SENTINEL_DATASET_ID,
                external_id=str(external_id) if external_id else None,
                stable_fields=obj,
                payload=obj,
                source_metadata={"file": str(path), "index": i},
            )

    def _load_yaml(self, path: Path, config: dict[str, Any]) -> Iterator[Record]:
        import yaml

        records_path = config.get("records_path")
        id_field = config.get("id_field")

        with open(path) as f:
            data = yaml.safe_load(f)

        if records_path:
            for key in records_path.split("."):
                if isinstance(data, dict) and key in data:
                    data = data[key]
                else:
                    raise ValueError(f"Cannot traverse path '{records_path}' in YAML")

        if not isinstance(data, list):
            raise ValueError("Expected a YAML array of records")

        for i, obj in enumerate(data):
            external_id = obj.get(id_field) if id_field else None
            yield Record(
                id=uuid.uuid4(),
                dataset_id=SENTINEL_DATASET_ID,
                external_id=str(external_id) if external_id else None,
                stable_fields=obj,
                payload=obj,
                source_metadata={"file": str(path), "index": i},
            )

    def _infer_schema(self, path: Path, ext: str) -> dict[str, Any]:
        """Infer a JSON-Schema-compatible dict from the first records."""
        records = list(self._load_by_extension(path, ext, {}))
        if not records:
            return {"type": "object", "properties": {}}

        sample = records[0].stable_fields
        properties: dict[str, Any] = {}
        for key, value in sample.items():
            if isinstance(value, bool):
                properties[key] = {"type": "boolean"}
            elif isinstance(value, int):
                properties[key] = {"type": "integer"}
            elif isinstance(value, float):
                properties[key] = {"type": "number"}
            elif isinstance(value, list):
                properties[key] = {"type": "array"}
            elif isinstance(value, dict):
                properties[key] = {"type": "object"}
            else:
                properties[key] = {"type": "string"}

        return {"type": "object", "properties": properties}


# ---------------------------------------------------------------------------
# HuggingFaceAdapter  (DT-004)
# ---------------------------------------------------------------------------


class HuggingFaceAdapter:
    """Imports datasets from HuggingFace Hub.

    The ``datasets`` library is an optional dependency and is imported
    lazily at call time.
    """

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        token: str | None = None,
    ) -> list[HuggingFaceSearchResult]:
        """Search HuggingFace Hub for datasets matching *query*.

        Requires the ``huggingface_hub`` library.
        """
        try:
            from huggingface_hub import HfApi
        except ImportError as exc:
            raise ImportError(
                "huggingface_hub is required for HuggingFace search. "
                "Install with: pip install huggingface_hub"
            ) from exc

        api = HfApi(token=token)
        datasets = api.list_datasets(search=query, limit=limit)
        results = []
        for ds in datasets:
            results.append(
                HuggingFaceSearchResult(
                    dataset_id=ds.id,
                    description=ds.description or "",
                    downloads=ds.downloads or 0,
                    tags=list(ds.tags) if ds.tags else [],
                )
            )
        return results

    def load_dataset(
        self,
        dataset_id: str,
        *,
        split: str = "train",
        streaming: bool = False,
        token: str | None = None,
        max_records: int | None = None,
    ) -> Iterator[Record]:
        """Load records from a HuggingFace dataset.

        Parameters
        ----------
        dataset_id:
            HuggingFace dataset identifier (e.g. ``imdb``,
            ``user/dataset-name``).
        split:
            Dataset split to load.
        streaming:
            If True, streams records without downloading the full dataset.
        token:
            HuggingFace auth token for private datasets.
        max_records:
            Maximum number of records to yield. None means all.
        """
        try:
            from datasets import load_dataset
        except ImportError as exc:
            raise ImportError(
                "The 'datasets' library is required for HuggingFace import. "
                "Install with: pip install datasets"
            ) from exc

        ds = load_dataset(
            dataset_id,
            split=split,
            streaming=streaming,
            token=token,
        )

        import itertools

        items = enumerate(ds)
        if max_records is not None:
            items = itertools.islice(items, max_records)

        for i, example in items:
            yield Record(
                id=uuid.uuid4(),
                dataset_id=SENTINEL_DATASET_ID,
                external_id=str(i),
                stable_fields=dict(example),
                payload=dict(example),
                source_metadata={
                    "source": "huggingface",
                    "dataset_id": dataset_id,
                    "split": split,
                    "index": i,
                },
            )

    def get_splits(
        self,
        dataset_id: str,
        *,
        token: str | None = None,
    ) -> list[str]:
        """Return available splits for a HuggingFace dataset."""
        try:
            from datasets import get_dataset_split_names
        except ImportError as exc:
            raise ImportError(
                "The 'datasets' library is required. Install with: pip install datasets"
            ) from exc

        return list(get_dataset_split_names(dataset_id, token=token))


# ---------------------------------------------------------------------------
# LabelingToolAdapter  (DT-005)
# ---------------------------------------------------------------------------


class LabelingToolAdapter:
    """Imports data from labeling tools (Label Studio, Argilla, Prodigy).

    Uses a format-based approach: each tool's export format is parsed
    into MoLabel records with pre-label review events.
    """

    def import_label_studio(
        self,
        path: Path,
        *,
        config: dict[str, Any] | None = None,
    ) -> Iterator[Record]:
        """Import records from a Label Studio JSON export.

        Label Studio exports as a JSON array of annotation tasks with
        nested completions/annotations.
        """
        cfg = config or {}
        id_field = cfg.get("id_field", "id")

        with open(path) as f:
            data = json.load(f)

        if not isinstance(data, list):
            data = [data]

        for task in data:
            source_data = task.get("data", task)
            annotations = task.get("annotations", task.get("completions", []))
            external_id = str(task.get(id_field, ""))

            stable_fields = dict(source_data)
            pre_labels: dict[str, Any] = {}
            for ann in annotations:
                results = ann.get("result", [])
                for result in results:
                    field_name = result.get("from_name", "label")
                    value = result.get("value", {})
                    if "choices" in value:
                        pre_labels[field_name] = value["choices"]
                    elif "text" in value:
                        pre_labels[field_name] = value["text"]
                    elif "rating" in value:
                        pre_labels[field_name] = value["rating"]

            yield Record(
                id=uuid.uuid4(),
                dataset_id=SENTINEL_DATASET_ID,
                external_id=external_id if external_id else None,
                stable_fields=stable_fields,
                payload={
                    "source_data": source_data,
                    "pre_labels": pre_labels,
                    "annotations": annotations,
                },
                source_metadata={
                    "source_system": "label-studio",
                    "source_file": str(path),
                },
            )

    def import_argilla(
        self,
        path: Path,
        *,
        config: dict[str, Any] | None = None,
    ) -> Iterator[Record]:
        """Import records from an Argilla JSON/JSONL export."""
        cfg = config or {}
        id_field = cfg.get("id_field", "id")
        ext = path.suffix.lower()

        if ext == ".jsonl":
            records_data = []
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records_data.append(json.loads(line))
        else:
            with open(path) as f:
                data = json.load(f)
            records_data = data if isinstance(data, list) else [data]

        for entry in records_data:
            text_fields = {}
            if "text" in entry:
                text_fields["text"] = entry["text"]
            if "inputs" in entry:
                text_fields.update(entry["inputs"])
            if "fields" in entry:
                text_fields.update(entry["fields"])

            pre_labels = {}
            if "annotation" in entry:
                pre_labels = dict(entry["annotation"])
            elif "prediction" in entry:
                pred = entry["prediction"]
                if isinstance(pred, dict):
                    pre_labels = dict(pred)

            external_id = str(entry.get(id_field, ""))

            yield Record(
                id=uuid.uuid4(),
                dataset_id=SENTINEL_DATASET_ID,
                external_id=external_id if external_id else None,
                stable_fields=text_fields or dict(entry),
                payload={
                    "source_data": dict(entry),
                    "pre_labels": pre_labels,
                },
                source_metadata={
                    "source_system": "argilla",
                    "source_file": str(path),
                },
            )

    def import_prodigy(
        self,
        path: Path,
        *,
        config: dict[str, Any] | None = None,
    ) -> Iterator[Record]:
        """Import records from a Prodigy JSONL export.

        Prodigy uses JSONL where each line is a task with ``text``,
        ``label``, ``answer``, and ``spans`` fields.
        """
        cfg = config or {}
        id_field = cfg.get("id_field", "_input_hash")

        with open(path) as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue

                obj = json.loads(line)
                stable_fields = {}

                if "text" in obj:
                    stable_fields["text"] = obj["text"]
                if "html" in obj:
                    stable_fields["html"] = obj["html"]
                if "image" in obj:
                    stable_fields["image"] = obj["image"]

                pre_labels: dict[str, Any] = {}
                if "label" in obj:
                    pre_labels["label"] = obj["label"]
                if "accept" in obj:
                    pre_labels["accept"] = obj["accept"]
                if "spans" in obj:
                    pre_labels["spans"] = obj["spans"]

                external_id = str(obj.get(id_field, ""))

                yield Record(
                    id=uuid.uuid4(),
                    dataset_id=SENTINEL_DATASET_ID,
                    external_id=external_id if external_id else None,
                    stable_fields=stable_fields or dict(obj),
                    payload={
                        "source_data": dict(obj),
                        "pre_labels": pre_labels,
                        "answer": obj.get("answer"),
                    },
                    source_metadata={
                        "source_system": "prodigy",
                        "source_file": str(path),
                        "line": i + 1,
                    },
                )

    def detect_format(self, path: Path) -> str | None:
        """Attempt to detect the labeling tool format of a file.

        Returns one of ``label-studio``, ``argilla``, ``prodigy``, or None.
        """
        ext = path.suffix.lower()

        if ext == ".jsonl":
            # Try to detect prodigy vs argilla from first line.
            with open(path) as f:
                first_line = f.readline().strip()
                if not first_line:
                    return None
                try:
                    obj = json.loads(first_line)
                except json.JSONDecodeError:
                    return None
                if "_input_hash" in obj or "answer" in obj:
                    return "prodigy"
                if "inputs" in obj or "fields" in obj:
                    return "argilla"
            return None

        if ext == ".json":
            with open(path) as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    return None

            if isinstance(data, list) and data:
                first = data[0]
                if "annotations" in first or "completions" in first:
                    return "label-studio"
                if "inputs" in first or "fields" in first:
                    return "argilla"

        return None

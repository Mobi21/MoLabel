"""Tests for built-in export packager plugins (BP-007).

Tests cover: JsonlExporter, CsvExporter, ParquetExporter (conditional),
HuggingFaceExporter (non-network functionality only).
"""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from molabel.core.plugins.protocols import ExportPackagerPlugin
from molabel.core.types import (
    ExportArtifact,
    PluginMetadata,
    Record,
    ReviewEvent,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_DATASET_ID = UUID("00000000-0000-0000-0000-000000000001")


def _make_record(
    text: str = "sample text",
    label: str = "positive",
    record_id: UUID | None = None,
) -> Record:
    rid = record_id or uuid4()
    return Record(
        id=rid,
        dataset_id=_DATASET_ID,
        external_id=f"ext-{text[:8]}",
        stable_fields={"text": text, "category": label},
        payload={"text": text, "category": label},
    )


def _make_review_event(
    record_id: UUID,
    labels: dict[str, Any],
    created_at: datetime | None = None,
) -> ReviewEvent:
    return ReviewEvent(
        id=uuid4(),
        record_id=record_id,
        source="human",
        decision="accept",
        labels=labels,
        created_at=created_at,
    )


def _sample_records_and_labels() -> tuple[list[Record], dict[str, list[ReviewEvent]]]:
    """Build a small test dataset with 3 records and labels."""
    r1 = _make_record("First record", "positive")
    r2 = _make_record("Second record", "negative")
    r3 = _make_record("Third record", "neutral")

    t1 = datetime(2026, 1, 1, tzinfo=UTC)
    t2 = datetime(2026, 1, 2, tzinfo=UTC)

    labels: dict[str, list[ReviewEvent]] = {
        str(r1.id): [
            _make_review_event(r1.id, {"sentiment": "pos"}, t1),
            _make_review_event(r1.id, {"sentiment": "very_pos"}, t2),
        ],
        str(r2.id): [
            _make_review_event(r2.id, {"sentiment": "neg"}, t1),
        ],
        str(r3.id): [],
    }

    return [r1, r2, r3], labels


# ---------------------------------------------------------------------------
# JsonlExporter
# ---------------------------------------------------------------------------


class TestJsonlExporter:
    @pytest.fixture()
    def exporter(self):
        from molabel.plugins.exporters.jsonl_exporter import JsonlExporter

        return JsonlExporter()

    def test_protocol_conformance(self, exporter):
        assert isinstance(exporter, ExportPackagerPlugin)

    def test_metadata(self, exporter):
        meta = exporter.metadata
        assert isinstance(meta, PluginMetadata)
        assert meta.plugin_id == "molabel.exporters.jsonl"

    def test_supported_formats(self, exporter):
        assert exporter.supported_formats == ["jsonl"]

    def test_package_in_memory(self, exporter):
        records, labels = _sample_records_and_labels()
        artifact = exporter.package(records, labels, {})

        assert artifact.format == "jsonl"
        assert artifact.record_count == 3
        assert artifact.data is not None
        assert artifact.checksum

        lines = artifact.data.decode("utf-8").strip().split("\n")
        assert len(lines) == 3

        row0 = json.loads(lines[0])
        assert row0["text"] == "First record"
        # Default strategy is "latest", so second event's labels win.
        assert row0["sentiment"] == "very_pos"

    def test_package_latest_label_strategy(self, exporter):
        records, labels = _sample_records_and_labels()
        artifact = exporter.package(records, labels, {"label_strategy": "latest"})

        lines = artifact.data.decode("utf-8").strip().split("\n")
        row0 = json.loads(lines[0])
        assert row0["sentiment"] == "very_pos"

    def test_package_first_label_strategy(self, exporter):
        records, labels = _sample_records_and_labels()
        artifact = exporter.package(records, labels, {"label_strategy": "first"})

        lines = artifact.data.decode("utf-8").strip().split("\n")
        row0 = json.loads(lines[0])
        assert row0["sentiment"] == "pos"

    def test_package_with_metadata(self, exporter):
        records, labels = _sample_records_and_labels()
        artifact = exporter.package(records, labels, {"include_metadata": True})

        lines = artifact.data.decode("utf-8").strip().split("\n")
        row0 = json.loads(lines[0])
        assert "_record_id" in row0
        assert "_external_id" in row0

    def test_package_column_filter(self, exporter):
        records, labels = _sample_records_and_labels()
        artifact = exporter.package(records, labels, {"columns": ["text", "sentiment"]})

        lines = artifact.data.decode("utf-8").strip().split("\n")
        row0 = json.loads(lines[0])
        assert "text" in row0
        assert "sentiment" in row0
        assert "category" not in row0

    def test_package_to_file(self, exporter, tmp_path):
        records, labels = _sample_records_and_labels()
        dest = tmp_path / "output.jsonl"
        artifact = exporter.package(records, labels, {"destination": str(dest)})

        assert artifact.path == dest
        assert artifact.data is None
        assert dest.exists()

        lines = dest.read_text().strip().split("\n")
        assert len(lines) == 3

    def test_package_empty_records(self, exporter):
        artifact = exporter.package([], {}, {})
        assert artifact.record_count == 0
        assert artifact.data == b""

    def test_validate_valid_artifact(self, exporter):
        records, labels = _sample_records_and_labels()
        artifact = exporter.package(records, labels, {})
        result = exporter.validate_export(artifact)
        assert result.is_valid

    def test_validate_invalid_json(self, exporter):
        artifact = ExportArtifact(
            data=b"not valid json\n",
            format="jsonl",
            record_count=1,
        )
        result = exporter.validate_export(artifact)
        assert not result.is_valid

    def test_validate_count_mismatch(self, exporter):
        artifact = ExportArtifact(
            data=b'{"a": 1}\n',
            format="jsonl",
            record_count=5,
        )
        result = exporter.validate_export(artifact)
        assert not result.is_valid

    def test_validate_file_artifact(self, exporter, tmp_path):
        records, labels = _sample_records_and_labels()
        dest = tmp_path / "output.jsonl"
        artifact = exporter.package(records, labels, {"destination": str(dest)})
        result = exporter.validate_export(artifact)
        assert result.is_valid

    def test_get_export_schema(self, exporter):
        schema = exporter.get_export_schema()
        assert "format_notes" in schema
        assert "columns" in schema


# ---------------------------------------------------------------------------
# CsvExporter
# ---------------------------------------------------------------------------


class TestCsvExporter:
    @pytest.fixture()
    def exporter(self):
        from molabel.plugins.exporters.csv_exporter import CsvExporter

        return CsvExporter()

    def test_protocol_conformance(self, exporter):
        assert isinstance(exporter, ExportPackagerPlugin)

    def test_metadata(self, exporter):
        meta = exporter.metadata
        assert isinstance(meta, PluginMetadata)
        assert meta.plugin_id == "molabel.exporters.csv"

    def test_supported_formats(self, exporter):
        assert exporter.supported_formats == ["csv"]

    def test_package_in_memory(self, exporter):
        records, labels = _sample_records_and_labels()
        artifact = exporter.package(records, labels, {})

        assert artifact.format == "csv"
        assert artifact.record_count == 3
        assert artifact.data is not None

        reader = csv.DictReader(io.StringIO(artifact.data.decode("utf-8")))
        rows = list(reader)
        assert len(rows) == 3
        assert rows[0]["text"] == "First record"
        assert rows[0]["sentiment"] == "very_pos"

    def test_package_with_delimiter(self, exporter):
        records, labels = _sample_records_and_labels()
        artifact = exporter.package(records, labels, {"delimiter": "\t"})

        reader = csv.DictReader(
            io.StringIO(artifact.data.decode("utf-8")),
            delimiter="\t",
        )
        rows = list(reader)
        assert len(rows) == 3

    def test_package_with_metadata(self, exporter):
        records, labels = _sample_records_and_labels()
        artifact = exporter.package(records, labels, {"include_metadata": True})

        reader = csv.DictReader(io.StringIO(artifact.data.decode("utf-8")))
        rows = list(reader)
        assert "_record_id" in rows[0]
        assert "_external_id" in rows[0]

    def test_package_column_filter(self, exporter):
        records, labels = _sample_records_and_labels()
        artifact = exporter.package(records, labels, {"columns": ["text"]})

        reader = csv.DictReader(io.StringIO(artifact.data.decode("utf-8")))
        rows = list(reader)
        assert list(rows[0].keys()) == ["text"]

    def test_package_to_file(self, exporter, tmp_path):
        records, labels = _sample_records_and_labels()
        dest = tmp_path / "output.csv"
        artifact = exporter.package(records, labels, {"destination": str(dest)})

        assert artifact.path == dest
        assert dest.exists()

    def test_package_complex_values_flattened(self, exporter):
        """Dict/list values should be JSON-encoded in CSV cells."""
        r = _make_record("test", "pos")
        r.stable_fields["tags"] = ["a", "b"]
        r.stable_fields["meta"] = {"key": "val"}

        artifact = exporter.package([r], {}, {})
        reader = csv.DictReader(io.StringIO(artifact.data.decode("utf-8")))
        row = next(reader)
        assert json.loads(row["tags"]) == ["a", "b"]
        assert json.loads(row["meta"]) == {"key": "val"}

    def test_validate_valid_artifact(self, exporter):
        records, labels = _sample_records_and_labels()
        artifact = exporter.package(records, labels, {})
        result = exporter.validate_export(artifact)
        assert result.is_valid

    def test_validate_empty_csv(self, exporter):
        artifact = ExportArtifact(
            data=b"",
            format="csv",
            record_count=0,
        )
        result = exporter.validate_export(artifact)
        assert not result.is_valid

    def test_validate_count_mismatch(self, exporter):
        artifact = ExportArtifact(
            data=b"col1,col2\na,b\n",
            format="csv",
            record_count=5,
        )
        result = exporter.validate_export(artifact)
        assert not result.is_valid

    def test_get_export_schema(self, exporter):
        schema = exporter.get_export_schema()
        assert "format_notes" in schema


# ---------------------------------------------------------------------------
# ParquetExporter (conditional - requires pyarrow)
# ---------------------------------------------------------------------------


@pytest.fixture()
def _has_pyarrow():
    pytest.importorskip("pyarrow")


@pytest.mark.usefixtures("_has_pyarrow")
class TestParquetExporter:
    @pytest.fixture()
    def exporter(self):
        from molabel.plugins.exporters.parquet_exporter import ParquetExporter

        return ParquetExporter()

    def test_protocol_conformance(self, exporter):
        assert isinstance(exporter, ExportPackagerPlugin)

    def test_metadata(self, exporter):
        meta = exporter.metadata
        assert isinstance(meta, PluginMetadata)
        assert meta.plugin_id == "molabel.exporters.parquet"

    def test_supported_formats(self, exporter):
        assert exporter.supported_formats == ["parquet"]

    def test_package_in_memory(self, exporter):
        records, labels = _sample_records_and_labels()
        artifact = exporter.package(records, labels, {})

        assert artifact.format == "parquet"
        assert artifact.record_count == 3
        assert artifact.data is not None
        assert artifact.checksum

    def test_package_to_file(self, exporter, tmp_path):
        records, labels = _sample_records_and_labels()
        dest = tmp_path / "output.parquet"
        artifact = exporter.package(records, labels, {"destination": str(dest)})

        assert artifact.path == dest
        assert artifact.data is None
        assert dest.exists()

    def test_package_reads_back_correctly(self, exporter, tmp_path):
        import pyarrow.parquet as pq

        records, labels = _sample_records_and_labels()
        dest = tmp_path / "output.parquet"
        exporter.package(records, labels, {"destination": str(dest)})

        table = pq.read_table(str(dest))
        assert table.num_rows == 3
        assert "text" in table.column_names
        assert "sentiment" in table.column_names

    def test_package_with_metadata(self, exporter):
        records, labels = _sample_records_and_labels()
        artifact = exporter.package(records, labels, {"include_metadata": True})

        import pyarrow.parquet as pq

        table = pq.read_table(io.BytesIO(artifact.data))
        assert "_record_id" in table.column_names

    def test_package_column_filter(self, exporter):
        import pyarrow.parquet as pq

        records, labels = _sample_records_and_labels()
        artifact = exporter.package(records, labels, {"columns": ["text", "sentiment"]})

        table = pq.read_table(io.BytesIO(artifact.data))
        assert set(table.column_names) == {"text", "sentiment"}

    def test_validate_valid_artifact(self, exporter):
        records, labels = _sample_records_and_labels()
        artifact = exporter.package(records, labels, {})
        result = exporter.validate_export(artifact)
        assert result.is_valid

    def test_validate_from_file(self, exporter, tmp_path):
        records, labels = _sample_records_and_labels()
        dest = tmp_path / "output.parquet"
        artifact = exporter.package(records, labels, {"destination": str(dest)})
        result = exporter.validate_export(artifact)
        assert result.is_valid

    def test_validate_count_mismatch(self, exporter):
        records, labels = _sample_records_and_labels()
        artifact = exporter.package(records, labels, {})
        artifact.record_count = 999
        result = exporter.validate_export(artifact)
        assert not result.is_valid

    def test_validate_corrupt_data(self, exporter):
        artifact = ExportArtifact(
            data=b"this is not parquet data",
            format="parquet",
            record_count=1,
        )
        result = exporter.validate_export(artifact)
        assert not result.is_valid

    def test_get_export_schema(self, exporter):
        schema = exporter.get_export_schema()
        assert "format_notes" in schema


# ---------------------------------------------------------------------------
# HuggingFaceExporter (non-network tests)
# ---------------------------------------------------------------------------


class TestHuggingFaceExporterBasic:
    """Tests that do not require network access or the huggingface_hub library."""

    @pytest.fixture()
    def exporter(self):
        from molabel.plugins.exporters.huggingface_exporter import (
            HuggingFaceExporter,
        )

        return HuggingFaceExporter()

    def test_protocol_conformance(self, exporter):
        assert isinstance(exporter, ExportPackagerPlugin)

    def test_metadata(self, exporter):
        meta = exporter.metadata
        assert isinstance(meta, PluginMetadata)
        assert meta.plugin_id == "molabel.exporters.huggingface"

    def test_supported_formats(self, exporter):
        assert exporter.supported_formats == ["huggingface_hub"]

    def test_package_requires_repo_id(self, exporter):
        """Should raise ValueError when repo_id is missing."""
        records, labels = _sample_records_and_labels()
        with (
            patch.dict("os.environ", {"HF_TOKEN": "fake-token"}, clear=False),
            pytest.raises(ValueError, match="repo_id"),
        ):
            exporter.package(records, labels, {})

    def test_package_requires_token(self, exporter):
        """Should raise ValueError when no token is available."""
        records, labels = _sample_records_and_labels()
        with (
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(ValueError, match="token"),
        ):
            exporter.package(records, labels, {"repo_id": "user/test-dataset"})

    def test_package_calls_hub_api(self, exporter):
        """Verify the exporter calls HfApi correctly (mocked)."""
        records, labels = _sample_records_and_labels()

        mock_api_instance = MagicMock()
        mock_api_class = MagicMock(return_value=mock_api_instance)

        with (
            patch(
                "molabel.plugins.exporters.huggingface_exporter._import_huggingface_hub",
                return_value=mock_api_class,
            ),
            patch.dict("os.environ", {"HF_TOKEN": "test-token"}, clear=False),
        ):
            artifact = exporter.package(
                records,
                labels,
                {"repo_id": "testuser/test-ds"},
            )

        assert artifact.format == "huggingface_hub"
        assert artifact.record_count == 3
        assert artifact.metadata["repo_id"] == "testuser/test-ds"
        assert artifact.metadata["split"] == "train"

        mock_api_instance.create_repo.assert_called_once()
        mock_api_instance.upload_file.assert_called_once()

        upload_kwargs = mock_api_instance.upload_file.call_args
        assert upload_kwargs.kwargs["repo_id"] == "testuser/test-ds"
        assert upload_kwargs.kwargs["repo_type"] == "dataset"
        assert upload_kwargs.kwargs["path_in_repo"] == "train.jsonl"

    def test_validate_valid_artifact(self, exporter):
        artifact = ExportArtifact(
            format="huggingface_hub",
            record_count=3,
            checksum="abc123",
            metadata={"repo_id": "user/ds", "split": "train"},
        )
        result = exporter.validate_export(artifact)
        assert result.is_valid

    def test_validate_wrong_format(self, exporter):
        artifact = ExportArtifact(format="jsonl", record_count=1)
        result = exporter.validate_export(artifact)
        assert not result.is_valid

    def test_validate_missing_repo_id(self, exporter):
        artifact = ExportArtifact(
            format="huggingface_hub",
            record_count=1,
            metadata={},
        )
        result = exporter.validate_export(artifact)
        assert not result.is_valid

    def test_validate_empty_export_warns(self, exporter):
        artifact = ExportArtifact(
            format="huggingface_hub",
            record_count=0,
            metadata={"repo_id": "user/ds"},
        )
        result = exporter.validate_export(artifact)
        assert result.is_valid
        assert len(result.warnings) > 0

    def test_get_export_schema(self, exporter):
        schema = exporter.get_export_schema()
        assert "format_notes" in schema
        assert "required_config" in schema


# ---------------------------------------------------------------------------
# Registry registration
# ---------------------------------------------------------------------------


class TestExporterRegistration:
    """Verify that each exporter's register() function works with the registry."""

    def test_jsonl_register(self):
        from molabel.core.plugins.registry import PluginRegistry
        from molabel.plugins.exporters.jsonl_exporter import register

        registry = PluginRegistry()
        register(registry)
        assert "molabel.exporters.jsonl" in registry.list_export_packagers()

    def test_csv_register(self):
        from molabel.core.plugins.registry import PluginRegistry
        from molabel.plugins.exporters.csv_exporter import register

        registry = PluginRegistry()
        register(registry)
        assert "molabel.exporters.csv" in registry.list_export_packagers()

    def test_parquet_register(self):
        from molabel.core.plugins.registry import PluginRegistry
        from molabel.plugins.exporters.parquet_exporter import register

        registry = PluginRegistry()
        register(registry)
        assert "molabel.exporters.parquet" in registry.list_export_packagers()

    def test_huggingface_register(self):
        from molabel.core.plugins.registry import PluginRegistry
        from molabel.plugins.exporters.huggingface_exporter import register

        registry = PluginRegistry()
        register(registry)
        assert "molabel.exporters.huggingface" in registry.list_export_packagers()

    def test_all_exporters_register(self):
        """Register all exporters into one registry."""
        from molabel.core.plugins.registry import PluginRegistry
        from molabel.plugins.exporters.csv_exporter import register as reg_csv
        from molabel.plugins.exporters.huggingface_exporter import (
            register as reg_hf,
        )
        from molabel.plugins.exporters.jsonl_exporter import register as reg_jsonl
        from molabel.plugins.exporters.parquet_exporter import (
            register as reg_parquet,
        )

        registry = PluginRegistry()
        for reg_fn in [reg_jsonl, reg_csv, reg_parquet, reg_hf]:
            reg_fn(registry)

        assert len(registry.list_export_packagers()) == 4

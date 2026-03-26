"""Tests for built-in data loader plugins (BP-006).

Tests cover: CsvLoader, JsonlLoader, JsonLoader, YamlLoader,
MarkdownLoader. ParquetLoader and HuggingFaceLoader are tested
conditionally (require optional dependencies).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from molabel.core.plugins.protocols import DataLoaderPlugin
from molabel.core.types import PluginMetadata, Record

# Fixture directory with pre-built test data.
FIXTURES_DIR = (
    Path(__file__).resolve().parent.parent.parent / "fixtures" / "loader-test"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _collect_records(
    loader: Any,
    path: Path,
    config: dict[str, Any] | None = None,
) -> list[Record]:
    return list(loader.load_records(path, config or {}))


# ---------------------------------------------------------------------------
# CsvLoader
# ---------------------------------------------------------------------------


class TestCsvLoader:
    @pytest.fixture()
    def loader(self):
        from molabel.plugins.loaders.csv_loader import CsvLoader

        return CsvLoader()

    def test_protocol_conformance(self, loader):
        assert isinstance(loader, DataLoaderPlugin)

    def test_metadata(self, loader):
        meta = loader.metadata
        assert isinstance(meta, PluginMetadata)
        assert meta.plugin_id == "molabel.loaders.csv"

    def test_supported_formats(self, loader):
        assert "csv" in loader.supported_formats
        assert "tsv" in loader.supported_formats

    def test_can_load_csv(self, loader):
        assert loader.can_load(FIXTURES_DIR / "sample.csv")
        assert not loader.can_load(FIXTURES_DIR / "sample.jsonl")

    def test_can_load_nonexistent(self, loader):
        assert not loader.can_load(Path("/nonexistent/file.csv"))

    def test_load_records(self, loader):
        records = _collect_records(loader, FIXTURES_DIR / "sample.csv")
        assert len(records) == 3
        assert records[0].stable_fields["text"] == "This is a good example"
        assert records[0].stable_fields["label"] == "positive"

    def test_load_records_with_id_column(self, loader):
        records = _collect_records(
            loader, FIXTURES_DIR / "sample.csv", {"id_column": "id"}
        )
        assert records[0].external_id == "1"
        assert records[1].external_id == "2"

    def test_get_schema(self, loader):
        schema = loader.get_schema(FIXTURES_DIR / "sample.csv")
        assert schema["type"] == "object"
        assert "id" in schema["properties"]
        assert "text" in schema["properties"]

    def test_estimate_record_count(self, loader):
        count = loader.estimate_record_count(FIXTURES_DIR / "sample.csv")
        assert count == 3

    def test_load_records_no_header(self, loader):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("a,b,c\n")
            f.write("d,e,f\n")
            path = Path(f.name)
        try:
            records = _collect_records(loader, path, {"has_header": False})
            assert len(records) == 2
            assert records[0].stable_fields["col_0"] == "a"
        finally:
            path.unlink()

    def test_tsv_auto_delimiter(self, loader):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
            f.write("name\tvalue\n")
            f.write("foo\t42\n")
            path = Path(f.name)
        try:
            assert loader.can_load(path)
            records = _collect_records(loader, path)
            assert len(records) == 1
            assert records[0].stable_fields["name"] == "foo"
        finally:
            path.unlink()


# ---------------------------------------------------------------------------
# JsonlLoader
# ---------------------------------------------------------------------------


class TestJsonlLoader:
    @pytest.fixture()
    def loader(self):
        from molabel.plugins.loaders.jsonl_loader import JsonlLoader

        return JsonlLoader()

    def test_protocol_conformance(self, loader):
        assert isinstance(loader, DataLoaderPlugin)

    def test_metadata(self, loader):
        meta = loader.metadata
        assert meta.plugin_id == "molabel.loaders.jsonl"

    def test_supported_formats(self, loader):
        assert loader.supported_formats == ["jsonl"]

    def test_can_load(self, loader):
        assert loader.can_load(FIXTURES_DIR / "sample.jsonl")
        assert not loader.can_load(FIXTURES_DIR / "sample.csv")

    def test_load_records(self, loader):
        records = _collect_records(loader, FIXTURES_DIR / "sample.jsonl")
        assert len(records) == 3
        assert records[0].stable_fields["text"] == "First record"
        assert records[1].stable_fields["category"] == "B"

    def test_load_records_with_id_field(self, loader):
        records = _collect_records(
            loader, FIXTURES_DIR / "sample.jsonl", {"id_field": "id"}
        )
        assert records[0].external_id == "rec-001"
        assert records[2].external_id == "rec-003"

    def test_get_schema(self, loader):
        schema = loader.get_schema(FIXTURES_DIR / "sample.jsonl")
        assert schema["type"] == "object"
        props = schema["properties"]
        assert props["id"]["type"] == "string"
        assert props["score"]["type"] == "number"

    def test_estimate_record_count(self, loader):
        count = loader.estimate_record_count(FIXTURES_DIR / "sample.jsonl")
        assert count == 3

    def test_skips_blank_lines(self, loader):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"a": 1}\n\n{"b": 2}\n\n')
            path = Path(f.name)
        try:
            records = _collect_records(loader, path)
            assert len(records) == 2
        finally:
            path.unlink()


# ---------------------------------------------------------------------------
# JsonLoader
# ---------------------------------------------------------------------------


class TestJsonLoader:
    @pytest.fixture()
    def loader(self):
        from molabel.plugins.loaders.json_loader import JsonLoader

        return JsonLoader()

    def test_protocol_conformance(self, loader):
        assert isinstance(loader, DataLoaderPlugin)

    def test_metadata(self, loader):
        assert loader.metadata.plugin_id == "molabel.loaders.json"

    def test_can_load(self, loader):
        assert loader.can_load(FIXTURES_DIR / "sample.json")
        assert not loader.can_load(FIXTURES_DIR / "sample.csv")

    def test_load_records_array(self, loader):
        records = _collect_records(loader, FIXTURES_DIR / "sample.json")
        assert len(records) == 3
        assert records[0].stable_fields["text"] == "Hello world"

    def test_load_records_with_id_field(self, loader):
        records = _collect_records(
            loader, FIXTURES_DIR / "sample.json", {"id_field": "id"}
        )
        assert records[0].external_id == "j1"

    def test_load_records_nested_path(self, loader):
        records = _collect_records(
            loader,
            FIXTURES_DIR / "nested.json",
            {"records_path": "data.items"},
        )
        assert len(records) == 2
        assert records[0].stable_fields["content"] == "Nested item 1"

    def test_get_schema(self, loader):
        schema = loader.get_schema(FIXTURES_DIR / "sample.json")
        assert schema["type"] == "object"
        assert "text" in schema["properties"]
        assert schema["properties"]["tags"]["type"] == "array"

    def test_estimate_record_count(self, loader):
        count = loader.estimate_record_count(FIXTURES_DIR / "sample.json")
        assert count == 3

    def test_invalid_records_path_raises(self, loader):
        with pytest.raises(ValueError, match="Cannot traverse"):
            _collect_records(
                loader,
                FIXTURES_DIR / "sample.json",
                {"records_path": "nonexistent.path"},
            )

    def test_non_array_raises(self, loader):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"key": "value"}, f)
            path = Path(f.name)
        try:
            with pytest.raises(ValueError, match="Expected a JSON array"):
                _collect_records(loader, path)
        finally:
            path.unlink()


# ---------------------------------------------------------------------------
# YamlLoader
# ---------------------------------------------------------------------------


class TestYamlLoader:
    @pytest.fixture()
    def loader(self):
        from molabel.plugins.loaders.yaml_loader import YamlLoader

        return YamlLoader()

    def test_protocol_conformance(self, loader):
        assert isinstance(loader, DataLoaderPlugin)

    def test_metadata(self, loader):
        assert loader.metadata.plugin_id == "molabel.loaders.yaml"

    def test_supported_formats(self, loader):
        assert "yaml" in loader.supported_formats
        assert "yml" in loader.supported_formats

    def test_can_load(self, loader):
        assert loader.can_load(FIXTURES_DIR / "sample.yaml")
        assert not loader.can_load(FIXTURES_DIR / "sample.json")

    def test_can_load_yml_extension(self, loader):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write("- x: 1\n")
            path = Path(f.name)
        try:
            assert loader.can_load(path)
        finally:
            path.unlink()

    def test_load_records(self, loader):
        records = _collect_records(loader, FIXTURES_DIR / "sample.yaml")
        assert len(records) == 3
        assert records[0].stable_fields["text"] == "YAML record one"
        assert records[2].stable_fields["score"] == 0.4

    def test_load_records_with_id_field(self, loader):
        records = _collect_records(
            loader, FIXTURES_DIR / "sample.yaml", {"id_field": "id"}
        )
        assert records[0].external_id == "y1"

    def test_get_schema(self, loader):
        schema = loader.get_schema(FIXTURES_DIR / "sample.yaml")
        assert schema["type"] == "object"
        assert "text" in schema["properties"]

    def test_estimate_record_count(self, loader):
        count = loader.estimate_record_count(FIXTURES_DIR / "sample.yaml")
        assert count == 3

    def test_nested_records_path(self, loader):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("data:\n  items:\n    - x: 1\n    - x: 2\n")
            path = Path(f.name)
        try:
            records = _collect_records(loader, path, {"records_path": "data.items"})
            assert len(records) == 2
        finally:
            path.unlink()


# ---------------------------------------------------------------------------
# MarkdownLoader
# ---------------------------------------------------------------------------


class TestMarkdownLoader:
    @pytest.fixture()
    def loader(self):
        from molabel.plugins.loaders.markdown_loader import MarkdownLoader

        return MarkdownLoader()

    def test_protocol_conformance(self, loader):
        assert isinstance(loader, DataLoaderPlugin)

    def test_metadata(self, loader):
        assert loader.metadata.plugin_id == "molabel.loaders.markdown"

    def test_supported_formats(self, loader):
        assert "md" in loader.supported_formats

    def test_can_load(self, loader):
        assert loader.can_load(FIXTURES_DIR / "sample.md")
        assert not loader.can_load(FIXTURES_DIR / "sample.csv")

    def test_load_single_file(self, loader):
        records = _collect_records(loader, FIXTURES_DIR / "sample.md")
        assert len(records) == 1
        rec = records[0]
        assert rec.record_kind == "markdown"
        assert "Test Document" in rec.stable_fields["content"]
        assert rec.stable_fields["front_matter"]["author"] == "Test Author"
        assert rec.stable_fields["title"] == "Test Document"

    def test_load_with_id_field(self, loader):
        records = _collect_records(
            loader, FIXTURES_DIR / "sample.md", {"id_field": "id"}
        )
        assert records[0].external_id == "md-001"

    def test_load_directory(self, loader, tmp_path):
        (tmp_path / "a.md").write_text("# Doc A\nContent A")
        (tmp_path / "b.md").write_text("# Doc B\nContent B")
        records = _collect_records(loader, tmp_path)
        assert len(records) == 2

    def test_no_front_matter(self, loader, tmp_path):
        (tmp_path / "plain.md").write_text("# Just a heading\n\nSome text.")
        records = _collect_records(loader, tmp_path / "plain.md")
        assert len(records) == 1
        assert records[0].stable_fields["front_matter"] == {}
        assert records[0].stable_fields["title"] == "Just a heading"

    def test_get_schema(self, loader):
        schema = loader.get_schema(FIXTURES_DIR / "sample.md")
        assert schema["type"] == "object"
        assert "content" in schema["properties"]
        assert "front_matter" in schema["properties"]

    def test_estimate_record_count_file(self, loader):
        count = loader.estimate_record_count(FIXTURES_DIR / "sample.md")
        assert count == 1

    def test_estimate_record_count_dir(self, loader, tmp_path):
        (tmp_path / "a.md").write_text("x")
        (tmp_path / "b.md").write_text("y")
        count = loader.estimate_record_count(tmp_path)
        assert count == 2

    def test_can_load_directory(self, loader, tmp_path):
        (tmp_path / "doc.md").write_text("# H")
        assert loader.can_load(tmp_path)

    def test_cannot_load_empty_directory(self, loader, tmp_path):
        assert not loader.can_load(tmp_path)


# ---------------------------------------------------------------------------
# ParquetLoader (conditional — requires pyarrow)
# ---------------------------------------------------------------------------


@pytest.fixture()
def _has_pyarrow():
    pytest.importorskip("pyarrow")


@pytest.mark.usefixtures("_has_pyarrow")
class TestParquetLoader:
    @pytest.fixture()
    def loader(self):
        from molabel.plugins.loaders.parquet_loader import ParquetLoader

        return ParquetLoader()

    @pytest.fixture()
    def parquet_file(self, tmp_path):
        import pyarrow as pa
        import pyarrow.parquet as pq

        table = pa.table(
            {
                "id": ["p1", "p2", "p3"],
                "text": ["First", "Second", "Third"],
                "score": [0.9, 0.8, 0.7],
            }
        )
        path = tmp_path / "test.parquet"
        pq.write_table(table, str(path))
        return path

    def test_protocol_conformance(self, loader):
        assert isinstance(loader, DataLoaderPlugin)

    def test_metadata(self, loader):
        assert loader.metadata.plugin_id == "molabel.loaders.parquet"

    def test_can_load(self, loader, parquet_file):
        assert loader.can_load(parquet_file)
        assert not loader.can_load(FIXTURES_DIR / "sample.csv")

    def test_load_records(self, loader, parquet_file):
        records = _collect_records(loader, parquet_file)
        assert len(records) == 3
        assert records[0].stable_fields["text"] == "First"

    def test_load_with_id_column(self, loader, parquet_file):
        records = _collect_records(loader, parquet_file, {"id_column": "id"})
        assert records[0].external_id == "p1"

    def test_get_schema(self, loader, parquet_file):
        schema = loader.get_schema(parquet_file)
        assert schema["type"] == "object"
        assert "id" in schema["properties"]
        assert "score" in schema["properties"]

    def test_estimate_record_count(self, loader, parquet_file):
        count = loader.estimate_record_count(parquet_file)
        assert count == 3


# ---------------------------------------------------------------------------
# HuggingFaceLoader (only test non-network functionality)
# ---------------------------------------------------------------------------


class TestHuggingFaceLoaderBasic:
    """Tests that do not require the datasets library."""

    @pytest.fixture()
    def loader(self):
        from molabel.plugins.loaders.huggingface_loader import HuggingFaceLoader

        return HuggingFaceLoader()

    def test_protocol_conformance(self, loader):
        assert isinstance(loader, DataLoaderPlugin)

    def test_metadata(self, loader):
        assert loader.metadata.plugin_id == "molabel.loaders.huggingface"

    def test_supported_formats(self, loader):
        assert loader.supported_formats == ["huggingface"]

    def test_cannot_load_regular_file(self, loader):
        assert not loader.can_load(FIXTURES_DIR / "sample.csv")

    def test_can_load_pseudo_path(self, loader):
        assert loader.can_load(Path("huggingface://imdb"))

    def test_can_load_hf_dir(self, loader, tmp_path):
        (tmp_path / "dataset_info.json").write_text("{}")
        assert loader.can_load(tmp_path)


# ---------------------------------------------------------------------------
# Registry registration
# ---------------------------------------------------------------------------


class TestRegistration:
    """Verify that each loader's register() function works with the registry."""

    def test_csv_register(self):
        from molabel.core.plugins.registry import PluginRegistry
        from molabel.plugins.loaders.csv_loader import register

        registry = PluginRegistry()
        register(registry)
        assert "molabel.loaders.csv" in registry.list_data_loaders()

    def test_jsonl_register(self):
        from molabel.core.plugins.registry import PluginRegistry
        from molabel.plugins.loaders.jsonl_loader import register

        registry = PluginRegistry()
        register(registry)
        assert "molabel.loaders.jsonl" in registry.list_data_loaders()

    def test_json_register(self):
        from molabel.core.plugins.registry import PluginRegistry
        from molabel.plugins.loaders.json_loader import register

        registry = PluginRegistry()
        register(registry)
        assert "molabel.loaders.json" in registry.list_data_loaders()

    def test_parquet_register(self):
        from molabel.core.plugins.registry import PluginRegistry
        from molabel.plugins.loaders.parquet_loader import register

        registry = PluginRegistry()
        register(registry)
        assert "molabel.loaders.parquet" in registry.list_data_loaders()

    def test_yaml_register(self):
        from molabel.core.plugins.registry import PluginRegistry
        from molabel.plugins.loaders.yaml_loader import register

        registry = PluginRegistry()
        register(registry)
        assert "molabel.loaders.yaml" in registry.list_data_loaders()

    def test_markdown_register(self):
        from molabel.core.plugins.registry import PluginRegistry
        from molabel.plugins.loaders.markdown_loader import register

        registry = PluginRegistry()
        register(registry)
        assert "molabel.loaders.markdown" in registry.list_data_loaders()

    def test_huggingface_register(self):
        from molabel.core.plugins.registry import PluginRegistry
        from molabel.plugins.loaders.huggingface_loader import register

        registry = PluginRegistry()
        register(registry)
        assert "molabel.loaders.huggingface" in registry.list_data_loaders()

    def test_all_loaders_register(self):
        """Register all loaders into one registry."""
        from molabel.core.plugins.registry import PluginRegistry
        from molabel.plugins.loaders.csv_loader import register as reg_csv
        from molabel.plugins.loaders.huggingface_loader import register as reg_hf
        from molabel.plugins.loaders.json_loader import register as reg_json
        from molabel.plugins.loaders.jsonl_loader import register as reg_jsonl
        from molabel.plugins.loaders.markdown_loader import register as reg_md
        from molabel.plugins.loaders.parquet_loader import register as reg_pq
        from molabel.plugins.loaders.yaml_loader import register as reg_yaml

        registry = PluginRegistry()
        for reg_fn in [reg_csv, reg_jsonl, reg_json, reg_pq, reg_yaml, reg_md, reg_hf]:
            reg_fn(registry)

        assert len(registry.list_data_loaders()) == 7

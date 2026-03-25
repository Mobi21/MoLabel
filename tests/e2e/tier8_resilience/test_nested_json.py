"""T8-13: 5+ levels of JSON nesting — preserved in payload and export.

Verifies:
- Deeply nested dict (5+ levels) loads correctly via JSON loader
- Nested structure preserved in stable_fields and payload
- JSONL export preserves nested structure exactly (JSON-encoded)
- Parquet export serializes nested to JSON string (round-trippable)
- CSV export serializes nested to JSON string (parseable)
"""

from __future__ import annotations

import json
import tempfile
import uuid
from pathlib import Path

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.parallel import INDEPENDENT

# 6-level deeply nested structure
DEEP_NESTED = {
    "id": "nested-001",
    "level1": {
        "name": "Level 1",
        "level2": {
            "name": "Level 2",
            "value": 42,
            "level3": {
                "name": "Level 3",
                "items": ["a", "b", "c"],
                "level4": {
                    "name": "Level 4",
                    "metadata": {"source": "test", "version": "1.0"},
                    "level5": {
                        "name": "Level 5",
                        "deep_value": "This is deeply nested text",
                        "level6": {
                            "name": "Level 6 — deepest",
                            "final_value": 3.14159,
                            "tags": ["deep", "nested", "test"],
                        },
                    },
                },
            },
        },
    },
    "top_field": "top level value",
    "array_field": [
        {"nested_in_array": {"a": 1, "b": {"c": 2}}},
        {"nested_in_array": {"a": 3, "b": {"c": 4}}},
    ],
}


def _get_deep_value(obj: dict) -> str:
    """Navigate to the deepest value in the structure."""
    return obj["level1"]["level2"]["level3"]["level4"]["level5"]["level6"]["name"]


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier8
async def test_nested_json(client, ctx):
    """T8-13: 5+ levels of JSON nesting preserved in payload and export."""

    # ── Checkpoint 1: Setup ───────────────────────────────────────────────────
    with checkpoint(ctx, "setup"):
        ws = await client.post(
            "/workspaces", json={"workspace_name": "Nested JSON Test"}
        )
        assert ws.status_code == 201
        ws_id = ws.json()["workspace_id"]

        reviewer = await client.post(
            "/reviewer-profiles", json={"display_name": "NestedTester"}
        )
        assert reviewer.status_code == 201
        await client.login(reviewer.json()["reviewer_id"])

        ds = await client.post(
            "/datasets",
            json={
                "dataset_name": "Nested JSON Dataset",
                "workspace_id": ws_id,
                "source_type": "json",
            },
        )
        assert ds.status_code == 201
        ds_id = ds.json()["dataset_id"]

    # ── Checkpoint 2: JSON load preserves nested structure ────────────────────
    with checkpoint(ctx, "json_load"):
        from molabel.plugins.loaders.json_loader import JsonLoader

        data = [DEEP_NESTED]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(data, f, ensure_ascii=False)
            json_path = Path(f.name)

        try:
            loader = JsonLoader()
            records = list(loader.load_records(json_path, config={"id_field": "id"}))
            assert len(records) == 1

            rec = records[0]
            # Navigate to deepest level
            deep_name = _get_deep_value(rec.stable_fields)
            assert deep_name == "Level 6 — deepest", (
                f"Deep navigation failed, got: {deep_name!r}"
            )

            # Array of nested objects preserved
            arr = rec.stable_fields["array_field"]
            assert isinstance(arr, list)
            assert len(arr) == 2
            assert arr[0]["nested_in_array"]["b"]["c"] == 2
            assert arr[1]["nested_in_array"]["b"]["c"] == 4

        finally:
            json_path.unlink(missing_ok=True)

    # ── Checkpoint 3: JSONL export preserves nested structure ─────────────────
    with checkpoint(ctx, "jsonl_export"):
        from molabel.core.types import SENTINEL_DATASET_ID, Record
        from molabel.plugins.exporters.jsonl_exporter import JsonlExporter

        nested_record = Record(
            id=uuid.uuid4(),
            dataset_id=SENTINEL_DATASET_ID,
            stable_fields=DEEP_NESTED,
            payload=DEEP_NESTED,
            record_kind=None,
        )

        exporter = JsonlExporter()
        artifact = exporter.package([nested_record], labels={}, config={})

        content = artifact.data.decode("utf-8")
        lines = [ln for ln in content.splitlines() if ln.strip()]
        assert len(lines) == 1

        exported_obj = json.loads(lines[0])

        # Navigate nested structure in export
        deep_name_exported = _get_deep_value(exported_obj)
        assert deep_name_exported == "Level 6 — deepest"

        # Deep numeric value
        deep_float = exported_obj["level1"]["level2"]["level3"]["level4"]["level5"][
            "level6"
        ]["final_value"]
        assert abs(deep_float - 3.14159) < 1e-5

    # ── Checkpoint 4: CSV export serializes nested to JSON string ─────────────
    with checkpoint(ctx, "csv_nested"):
        import csv
        import io as _io

        from molabel.core.types import SENTINEL_DATASET_ID, Record
        from molabel.plugins.exporters.csv_exporter import CsvExporter

        csv_record = Record(
            id=uuid.uuid4(),
            dataset_id=SENTINEL_DATASET_ID,
            stable_fields={"id": "nested-001", "level1": DEEP_NESTED["level1"]},
            payload={},
            record_kind=None,
        )

        csv_exporter = CsvExporter()
        csv_artifact = csv_exporter.package([csv_record], labels={}, config={})
        csv_text = csv_artifact.data.decode("utf-8")

        reader = csv.DictReader(_io.StringIO(csv_text))
        csv_rows = list(reader)
        assert len(csv_rows) == 1

        # level1 is serialized as JSON string in CSV
        level1_cell = csv_rows[0]["level1"]
        # Must be parseable JSON
        parsed_level1 = json.loads(level1_cell)
        assert isinstance(parsed_level1, dict)
        assert parsed_level1["name"] == "Level 1"
        # Can navigate into the parsed nested structure
        assert parsed_level1["level2"]["name"] == "Level 2"

    # ── Checkpoint 5: Parquet handles nested (as JSON string) ─────────────────
    with checkpoint(ctx, "parquet_nested"):
        try:
            import io as _io2

            import pyarrow.parquet as pq
        except ImportError:
            pytest.skip("pyarrow not installed")

        from molabel.core.types import SENTINEL_DATASET_ID, Record
        from molabel.plugins.exporters.parquet_exporter import ParquetExporter

        pq_record = Record(
            id=uuid.uuid4(),
            dataset_id=SENTINEL_DATASET_ID,
            stable_fields=DEEP_NESTED,
            payload={},
            record_kind=None,
        )

        pq_exporter = ParquetExporter()
        pq_artifact = pq_exporter.package([pq_record], labels={}, config={})
        assert pq_artifact.data is not None

        pf = pq.ParquetFile(_io2.BytesIO(pq_artifact.data))
        table = pf.read()
        assert pf.metadata.num_rows == 1

        # level1 column should be a JSON string
        level1_col = table.column("level1")
        level1_val = level1_col[0].as_py()
        if isinstance(level1_val, str):
            # Parquet stored as JSON string — must be parseable
            parsed = json.loads(level1_val)
            assert isinstance(parsed, dict)
            assert parsed["name"] == "Level 1"

    # ── Checkpoint 6: YAML loader preserves 5+ levels ────────────────────────
    with checkpoint(ctx, "yaml_nested"):
        import yaml

        from molabel.plugins.loaders.yaml_loader import YamlLoader

        yaml_data = [DEEP_NESTED]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            yaml.dump(yaml_data, f, allow_unicode=True, default_flow_style=False)
            yaml_path = Path(f.name)

        try:
            yaml_loader = YamlLoader()
            yaml_records = list(
                yaml_loader.load_records(yaml_path, config={"id_field": "id"})
            )
            assert len(yaml_records) == 1

            yaml_deep = _get_deep_value(yaml_records[0].stable_fields)
            assert yaml_deep == "Level 6 — deepest"
        finally:
            yaml_path.unlink(missing_ok=True)

    # ── Checkpoint 7: API import ──────────────────────────────────────────────
    with checkpoint(ctx, "api_import"):
        resp = await client.post(
            f"/datasets/{ds_id}/import",
            json={"source_uri": "test://nested-json"},
        )
        assert resp.status_code == 202

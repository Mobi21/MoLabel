"""T7-06: YAML import via plugin loader.

Verifies:
- List of mappings: each mapping becomes a record
- Nested structure preserved in stable_fields
- records_path config navigates to nested list
- Schema inference from YAML structure
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.parallel import INDEPENDENT


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier7
async def test_import_yaml(client, ctx):
    """T7-06: YAML import — structure preserved in stable_fields."""

    # ── Checkpoint 1: Setup ───────────────────────────────────────────────────
    with checkpoint(ctx, "setup"):
        ws = await client.post(
            "/workspaces", json={"workspace_name": "YAML Import Test"}
        )
        assert ws.status_code == 201
        ws_id = ws.json()["workspace_id"]

        reviewer = await client.post(
            "/reviewer-profiles", json={"display_name": "Importer"}
        )
        assert reviewer.status_code == 201
        await client.login(reviewer.json()["reviewer_id"])

        ds = await client.post(
            "/datasets",
            json={
                "dataset_name": "YAML Dataset",
                "workspace_id": ws_id,
                "source_type": "yaml",
            },
        )
        assert ds.status_code == 201
        ds_id = ds.json()["dataset_id"]

    # ── Checkpoint 2: Simple list-of-mappings YAML ───────────────────────────
    with checkpoint(ctx, "list_of_mappings"):
        from molabel.plugins.loaders.yaml_loader import YamlLoader

        records_data = [
            {
                "id": "y1",
                "text": "First YAML record",
                "metadata": {"author": "Alice", "year": 2024},
                "tags": ["science", "research"],
            },
            {
                "id": "y2",
                "text": "Second YAML record",
                "metadata": {"author": "Bob", "year": 2023},
                "tags": ["tech"],
            },
        ]

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            yaml.dump(records_data, f, allow_unicode=True)
            yaml_path = Path(f.name)

        try:
            loader = YamlLoader()
            assert loader.can_load(yaml_path)

            records = list(loader.load_records(yaml_path, config={"id_field": "id"}))
            assert len(records) == 2

            # Nested dict preserved
            assert records[0].stable_fields["metadata"]["author"] == "Alice"
            assert records[1].stable_fields["metadata"]["year"] == 2023

            # Nested list preserved
            assert "science" in records[0].stable_fields["tags"]
            assert records[0].external_id == "y1"

            # estimate count
            count = loader.estimate_record_count(yaml_path)
            assert count == 2
        finally:
            yaml_path.unlink(missing_ok=True)

    # ── Checkpoint 3: Nested records_path ────────────────────────────────────
    with checkpoint(ctx, "nested_path"):
        from molabel.plugins.loaders.yaml_loader import YamlLoader

        nested = {
            "version": "2.0",
            "dataset": {
                "entries": [
                    {"entry_id": "e1", "value": 42, "flag": True},
                    {"entry_id": "e2", "value": 100, "flag": False},
                ]
            },
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yml", delete=False, encoding="utf-8"
        ) as f:
            yaml.dump(nested, f)
            nested_path = Path(f.name)

        try:
            loader2 = YamlLoader()
            assert loader2.can_load(nested_path)

            records2 = list(
                loader2.load_records(
                    nested_path,
                    config={"records_path": "dataset.entries", "id_field": "entry_id"},
                )
            )
            assert len(records2) == 2
            assert records2[0].external_id == "e1"
            assert records2[0].stable_fields["value"] == 42
            assert records2[0].stable_fields["flag"] is True
            assert records2[1].stable_fields["flag"] is False
        finally:
            nested_path.unlink(missing_ok=True)

    # ── Checkpoint 4: Schema inference ───────────────────────────────────────
    with checkpoint(ctx, "schema"):
        from molabel.plugins.loaders.yaml_loader import YamlLoader

        schema_data = [{"name": "Alice", "score": 9.5, "count": 3, "active": True}]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            yaml.dump(schema_data, f)
            schema_path = Path(f.name)

        try:
            loader3 = YamlLoader()
            schema = loader3.get_schema(schema_path)
            props = schema["properties"]
            assert props["name"]["type"] == "string"
            assert props["score"]["type"] in ("number", "float")
            assert props["count"]["type"] == "integer"
            assert props["active"]["type"] == "boolean"
        finally:
            schema_path.unlink(missing_ok=True)

    # ── Checkpoint 5: API import ──────────────────────────────────────────────
    with checkpoint(ctx, "api_import"):
        resp = await client.post(
            f"/datasets/{ds_id}/import",
            json={"source_uri": "test://yaml"},
        )
        assert resp.status_code == 202
        assert resp.json()["dataset_id"] == ds_id

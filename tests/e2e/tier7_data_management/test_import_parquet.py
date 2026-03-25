"""T7-04: Parquet import via plugin loader.

Verifies:
- Column types preserved (string, int, float, bool)
- id_column config maps to external_id
- Schema inference from Parquet metadata
- estimate_record_count reads Parquet metadata
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.parallel import INDEPENDENT


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier7
async def test_import_parquet(client, ctx):
    """T7-04: Parquet import — column types preserved."""

    # ── Checkpoint 1: Setup ───────────────────────────────────────────────────
    with checkpoint(ctx, "setup"):
        ws = await client.post(
            "/workspaces", json={"workspace_name": "Parquet Import Test"}
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
                "dataset_name": "Parquet Dataset",
                "workspace_id": ws_id,
                "source_type": "parquet",
            },
        )
        assert ds.status_code == 201
        ds_id = ds.json()["dataset_id"]

    # ── Checkpoint 2: Build and load Parquet file ─────────────────────────────
    with checkpoint(ctx, "loader_validation"):
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError:
            pytest.skip("pyarrow not installed")

        from molabel.plugins.loaders.parquet_loader import ParquetLoader

        table = pa.table(
            {
                "record_id": pa.array(["p1", "p2", "p3"], type=pa.string()),
                "score": pa.array([4, 2, 5], type=pa.int32()),
                "confidence": pa.array([0.9, 0.4, 0.95], type=pa.float64()),
                "approved": pa.array([True, False, True], type=pa.bool_()),
                "label": pa.array(
                    ["positive", "negative", "positive"], type=pa.string()
                ),
            }
        )

        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
            parquet_path = Path(f.name)

        pq.write_table(table, str(parquet_path))

        try:
            loader = ParquetLoader()
            assert loader.can_load(parquet_path)

            records = list(
                loader.load_records(parquet_path, config={"id_column": "record_id"})
            )
            assert len(records) == 3

            # Check types preserved in stable_fields
            scores = [r.stable_fields["score"] for r in records]
            assert all(isinstance(s, (int, float)) for s in scores), (
                f"Expected numeric scores, got: {scores}"
            )

            confidences = [r.stable_fields["confidence"] for r in records]
            assert all(isinstance(c, float) for c in confidences), (
                f"Expected float confidences, got: {confidences}"
            )

            booleans = [r.stable_fields["approved"] for r in records]
            assert all(isinstance(b, bool) for b in booleans), (
                f"Expected bool approved flags, got: {booleans}"
            )

            labels = [r.stable_fields["label"] for r in records]
            assert all(isinstance(lb, str) for lb in labels)

            # external_id from id_column
            assert records[0].external_id == "p1"
            assert records[1].external_id == "p2"
            assert records[2].external_id == "p3"

        finally:
            parquet_path.unlink(missing_ok=True)

    # ── Checkpoint 3: Schema inference ───────────────────────────────────────
    with checkpoint(ctx, "schema_inference"):
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError:
            pytest.skip("pyarrow not installed")

        from molabel.plugins.loaders.parquet_loader import ParquetLoader

        schema_table = pa.table(
            {
                "text_col": pa.array(["a", "b"], type=pa.string()),
                "int_col": pa.array([1, 2], type=pa.int64()),
                "float_col": pa.array([1.0, 2.0], type=pa.float32()),
            }
        )
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
            schema_path = Path(f.name)
        pq.write_table(schema_table, str(schema_path))

        try:
            loader2 = ParquetLoader()
            schema = loader2.get_schema(schema_path)
            assert schema["type"] == "object"
            props = schema["properties"]
            assert props["text_col"]["type"] == "string"
            assert props["int_col"]["type"] == "integer"
            assert props["float_col"]["type"] in ("number", "float")

            count = loader2.estimate_record_count(schema_path)
            assert count == 2
        finally:
            schema_path.unlink(missing_ok=True)

    # ── Checkpoint 4: API import ──────────────────────────────────────────────
    with checkpoint(ctx, "api_import"):
        resp = await client.post(
            f"/datasets/{ds_id}/import",
            json={"source_uri": "test://parquet"},
        )
        assert resp.status_code == 202
        assert resp.json()["dataset_id"] == ds_id

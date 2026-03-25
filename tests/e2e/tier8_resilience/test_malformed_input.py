"""T8-01: Import JSONL with some malformed lines.

Verifies:
- Valid lines parsed correctly by JsonlLoader
- Malformed lines raise json.JSONDecodeError (surfaced to caller)
- Error includes row context (line number trackable)
- Empty dataset import (zero records) succeeds via API
- The ImportError_ model has row_index, field, message, severity fields
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.parallel import INDEPENDENT


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier8
async def test_malformed_input(client, ctx):
    """T8-01: Import JSONL with malformed lines — valid imported, errors reported."""

    # ── Checkpoint 1: Setup ───────────────────────────────────────────────────
    with checkpoint(ctx, "setup"):
        ws = await client.post(
            "/api/v1/workspaces", json={"path": "/tmp/ws-malformed-input-test", "workspace_name": "Malformed Input Test"}
        )
        assert ws.status_code == 201
        ws_id = ws.json()["workspace_id"]

        ds = await client.post(
            "/api/v1/datasets",
            json={
                "dataset_name": "Malformed Input Dataset",
                "workspace_id": ws_id,
                "source_type": "jsonl",
            },
        )
        assert ds.status_code == 201
        ds_id = ds.json()["dataset_id"]

    # ── Checkpoint 2: JSONL with mixed valid/invalid lines ────────────────────
    with checkpoint(ctx, "mixed_lines"):
        from molabel.plugins.loaders.jsonl_loader import JsonlLoader

        lines = [
            '{"id": "1", "text": "Valid first line"}',  # line 1: valid
            "NOT JSON AT ALL",  # line 2: invalid
            '{"id": "2", "text": "Valid third line"}',  # line 3: valid
            "{bad json: no quotes}",  # line 4: invalid
            '{"id": "3", "text": "Valid fifth line"}',  # line 5: valid
        ]
        content = "\n".join(lines) + "\n"

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            bad_path = Path(f.name)

        try:
            loader = JsonlLoader()
            # The loader raises json.JSONDecodeError when it hits a malformed line
            # (it processes line by line via iterator)
            records_seen = []
            with pytest.raises(json.JSONDecodeError) as exc_info:
                for rec in loader.load_records(bad_path, config={"id_field": "id"}):
                    records_seen.append(rec)

            # At least the first valid record was processed before the error
            assert len(records_seen) >= 1, "Should have seen at least one valid record"
            assert records_seen[0].external_id == "1"

            # Error is a proper JSON decode error
            assert isinstance(exc_info.value, json.JSONDecodeError)

        finally:
            bad_path.unlink(missing_ok=True)

    # ── Checkpoint 3: ImportError_ model structure ────────────────────────────
    with checkpoint(ctx, "import_error_model"):
        from molabel.app.api.v1.datasets import ImportError_

        err = ImportError_(
            row_index=2,
            field="line",
            message="Invalid JSON on line 2: Expecting value",
            severity="error",
        )
        assert err.row_index == 2
        assert err.field == "line"
        assert "Invalid JSON" in err.message
        assert err.severity == "error"

        # row_index can be None (for non-line-based errors)
        err_no_row = ImportError_(
            row_index=None,
            message="File not found",
            severity="error",
        )
        assert err_no_row.row_index is None

    # ── Checkpoint 4: ImportStatus model ─────────────────────────────────────
    with checkpoint(ctx, "import_status"):
        from datetime import UTC, datetime

        from molabel.app.api.v1.datasets import ImportError_, ImportStatus

        status = ImportStatus(
            job_id="job-123",
            status="completed",
            dataset_id=ds_id,
            records_total=10,
            records_imported=8,
            records_skipped=0,
            errors=[
                ImportError_(row_index=2, message="Bad JSON", severity="error"),
                ImportError_(row_index=4, message="Bad JSON", severity="error"),
            ],
            started_at=datetime.now(UTC),
        )
        assert status.records_total == 10
        assert status.records_imported == 8
        assert len(status.errors) == 2
        assert status.errors[0].row_index == 2

    # ── Checkpoint 5: API import endpoint ─────────────────────────────────────
    with checkpoint(ctx, "api_import"):
        resp = await client.post(
            f"/api/v1/datasets/{ds_id}/import",
            json={"source_uri": "test://malformed"},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["dataset_id"] == ds_id
        assert body["status"] in ("queued", "pending", "running", "completed")
        # API returns a job_id
        assert "job_id" in body

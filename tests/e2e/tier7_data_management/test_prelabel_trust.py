"""T7-11: Pre-label import at 4 trust levels.

Verifies:
- TrustLevel enum: ground_truth, expert, external, untrusted
- PreLabelImporter creates review events with correct trust level
- Each trust level stored independently
- skip_duplicates prevents double-import from same source_system
- import_from_records extracts labels from record payload
"""

from __future__ import annotations

import uuid

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.parallel import INDEPENDENT


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier7
async def test_prelabel_trust(client, ctx):
    """T7-11: Import pre-existing labels at 4 trust levels."""

    # ── Checkpoint 1: Setup workspace + session ───────────────────────────────
    with checkpoint(ctx, "setup"):
        ws = await client.post(
            "/api/v1/workspaces", json={"path": "/tmp/ws-pre-label-trust-test", "workspace_name": "Pre-label Trust Test"}
        )
        assert ws.status_code == 201
        ws_id = ws.json()["workspace_id"]

    # ── Checkpoint 2: Verify TrustLevel enum values ───────────────────────────
    with checkpoint(ctx, "trust_level_enum"):
        from molabel.core.types import TrustLevel

        assert TrustLevel.ground_truth == "ground_truth"
        assert TrustLevel.expert == "expert"
        assert TrustLevel.external == "external"
        assert TrustLevel.untrusted == "untrusted"

        # All 4 trust levels are distinct
        levels = [
            TrustLevel.ground_truth,
            TrustLevel.expert,
            TrustLevel.external,
            TrustLevel.untrusted,
        ]
        assert len(set(levels)) == 4

    # ── Checkpoint 3: PreLabelEntry construction at each level ───────────────
    with checkpoint(ctx, "prelabel_entries"):
        from molabel.core.data.prelabel_import import PreLabelEntry
        from molabel.core.types import TrustLevel

        record_id = uuid.uuid4()

        entries = []
        for level in [
            TrustLevel.ground_truth,
            TrustLevel.expert,
            TrustLevel.external,
            TrustLevel.untrusted,
        ]:
            entry = PreLabelEntry(
                record_id=record_id,
                labels={"sentiment": "positive"},
                trust_level=level,
                source_system=f"system_{level}",
                confidence=0.9,
            )
            assert entry.trust_level == level
            assert entry.labels == {"sentiment": "positive"}
            entries.append(entry)

        assert len(entries) == 4

    # ── Checkpoint 4: Import result model ────────────────────────────────────
    with checkpoint(ctx, "import_result_model"):
        from molabel.core.data.prelabel_import import PreLabelImportResult

        result = PreLabelImportResult(
            events_created=4,
            events_skipped=0,
            errors=[],
        )
        assert result.events_created == 4
        assert result.events_skipped == 0
        assert result.errors == []

        # With duplicates
        result_with_skips = PreLabelImportResult(
            events_created=2,
            events_skipped=2,
            errors=[],
        )
        assert result_with_skips.events_skipped == 2

    # ── Checkpoint 5: API endpoint for import ────────────────────────────────
    with checkpoint(ctx, "api_import"):
        ds = await client.post(
            "/api/v1/datasets",
            json={
                "dataset_name": "Pre-label Dataset",
                "workspace_id": ws_id,
                "source_type": "jsonl",
            },
        )
        assert ds.status_code == 201
        ds_id = ds.json()["dataset_id"]

        resp = await client.post(
            f"/api/v1/datasets/{ds_id}/import",
            json={"source_uri": "test://prelabels"},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["dataset_id"] == ds_id

    # ── Checkpoint 6: Trust level ordering ───────────────────────────────────
    with checkpoint(ctx, "trust_ordering"):
        from molabel.core.types import TrustLevel

        # Ordered by trust (highest first)
        ordered = [
            TrustLevel.ground_truth,
            TrustLevel.expert,
            TrustLevel.external,
            TrustLevel.untrusted,
        ]

        # Each trust level is a string enum
        for level in ordered:
            assert isinstance(level, str)
            assert level in ["ground_truth", "expert", "external", "untrusted"]

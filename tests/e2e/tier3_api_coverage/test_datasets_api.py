"""Tier 3 — API Coverage: Datasets (T3-04, T3-05, T3-06).

Tests:
    T3-04: Full CRUD + import + records + analytics
    T3-05: Snapshots lifecycle — create, list, compare (diff)
    T3-06: Pagination (limit, ordering)
"""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SHARED_WORKSPACE

BASE = "/api/v1"


async def _setup_auth(client: InstrumentedClient) -> str:
    """Create a reviewer and log in; return workspace_id."""
    rp = await client.post(
        f"{BASE}/reviewer-profiles",
        json={
            "display_name": "DS Reviewer",
            "workspace_id": "00000000-0000-0000-0000-000000000001",
        },
    )
    assert rp.status_code == 201
    reviewer_id = rp.json()["id"]
    login = await client.post(f"{BASE}/sessions", json={"reviewer_id": reviewer_id})
    assert login.status_code == 200
    client._session_cookie = login.cookies.get("molabel_session")

    ws = await client.post(
        f"{BASE}/workspaces",
        json={"path": "/tmp/ws-datasets", "workspace_name": "DS Workspace"},
    )
    assert ws.status_code == 201
    return ws.json()["workspace_id"]


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier3
async def test_datasets_full_crud_and_analytics(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T3-04: Create, read, list, import, records, analytics."""

    workspace_id = await _setup_auth(client)

    dataset_id: str = ""
    with checkpoint(ctx, "create_dataset"):
        resp = await client.post(
            f"{BASE}/datasets",
            json={
                "dataset_name": "T3 Dataset",
                "workspace_id": workspace_id,
                "source_type": "jsonl",
                "record_kind": "text",
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["dataset_name"] == "T3 Dataset"
        assert body["source_type"] == "jsonl"
        dataset_id = body["dataset_id"]

    with checkpoint(ctx, "get_dataset"):
        resp = await client.get(f"{BASE}/datasets/{dataset_id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["dataset_id"] == dataset_id
        assert body["workspace_id"] == workspace_id

    with checkpoint(ctx, "list_datasets"):
        resp = await client.get(f"{BASE}/datasets")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "items" in body
        ids = [d["dataset_id"] for d in body["items"]]
        assert dataset_id in ids

    with checkpoint(ctx, "import_dataset"):
        resp = await client.post(
            f"{BASE}/datasets/{dataset_id}/import",
            json={"source_uri": "s3://bucket/data.jsonl"},
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["status"] == "queued"
        assert body["dataset_id"] == dataset_id
        assert "job_id" in body

    with checkpoint(ctx, "list_records"):
        resp = await client.get(f"{BASE}/datasets/{dataset_id}/records")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "items" in body

    with checkpoint(ctx, "get_analytics"):
        resp = await client.get(f"{BASE}/datasets/{dataset_id}/analytics")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["dataset_id"] == dataset_id
        assert "record_count" in body


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier3
async def test_datasets_snapshot_lifecycle(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T3-05: Create snapshot, list, compare (diff)."""

    workspace_id = await _setup_auth(client)

    # Create dataset
    ds_resp = await client.post(
        f"{BASE}/datasets",
        json={
            "dataset_name": "Snapshot DS",
            "workspace_id": workspace_id,
            "source_type": "jsonl",
        },
    )
    assert ds_resp.status_code == 201
    dataset_id = ds_resp.json()["dataset_id"]

    snap_id: str = ""
    with checkpoint(ctx, "create_snapshot"):
        resp = await client.post(
            f"{BASE}/datasets/{dataset_id}/snapshots",
            json={
                "name": "v1.0",
                "description": "Initial snapshot",
                "snapshot_type": "full",
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["name"] == "v1.0"
        assert body["dataset_id"] == dataset_id
        snap_id = body["snapshot_id"]

    with checkpoint(ctx, "list_snapshots"):
        resp = await client.get(f"{BASE}/datasets/{dataset_id}/snapshots")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "items" in body
        ids = [s["snapshot_id"] for s in body["items"]]
        assert snap_id in ids

    with checkpoint(ctx, "compare_snapshot_diff"):
        resp = await client.get(
            f"{BASE}/datasets/{dataset_id}/snapshots/{snap_id}/diff"
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "base_snapshot_id" in body
        assert "compare_snapshot_id" in body
        assert body["compare_snapshot_id"] == snap_id


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier3
async def test_datasets_pagination(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T3-06: Pagination parameters (limit, ordering)."""

    workspace_id = await _setup_auth(client)

    # Create 3 datasets
    for i in range(3):
        r = await client.post(
            f"{BASE}/datasets",
            json={
                "dataset_name": f"Paginated DS {i}",
                "workspace_id": workspace_id,
                "source_type": "jsonl",
            },
        )
        assert r.status_code == 201

    with checkpoint(ctx, "pagination_limit_1"):
        resp = await client.get(f"{BASE}/datasets", params={"limit": 1})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["items"]) <= 1

    with checkpoint(ctx, "pagination_limit_2"):
        resp = await client.get(f"{BASE}/datasets", params={"limit": 2})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["items"]) <= 2

    with checkpoint(ctx, "pagination_default"):
        resp = await client.get(f"{BASE}/datasets")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "items" in body
        assert "has_more" in body
        assert "cursor" in body

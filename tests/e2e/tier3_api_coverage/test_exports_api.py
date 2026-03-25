"""Tier 3 — API Coverage: Exports (T3-13).

Tests:
    T3-13: Preview, create (202), validate, download, push-hf
"""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SHARED_WORKSPACE

BASE = "/api/v1"


async def _setup(client: InstrumentedClient) -> tuple[str, str]:
    rp = await client.post(
        f"{BASE}/reviewer-profiles",
        json={
            "display_name": "Export Reviewer",
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
        json={"path": "/tmp/ws-exports", "workspace_name": "Export WS"},
    )
    assert ws.status_code == 201
    workspace_id = ws.json()["workspace_id"]

    ds = await client.post(
        f"{BASE}/datasets",
        json={
            "dataset_name": "Export DS",
            "workspace_id": workspace_id,
            "source_type": "jsonl",
        },
    )
    assert ds.status_code == 201
    dataset_id = ds.json()["dataset_id"]
    return workspace_id, dataset_id


def _export_create_body(workspace_id: str, dataset_id: str) -> dict:
    return {
        "workspace_id": workspace_id,
        "dataset_id": dataset_id,
        "name": "T3 Export",
        "format": "jsonl",
        "include": {
            "record_data": True,
            "human_labels": True,
            "agent_labels": False,
        },
        "filters": {"exclude_flagged": False},
    }


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier3
async def test_exports_preview_create_validate_download_pushh(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T3-13: Preview, create, validate, download, push-hf."""

    workspace_id, dataset_id = await _setup(client)

    with checkpoint(ctx, "preview_export"):
        resp = await client.post(
            f"{BASE}/exports/preview",
            json=_export_create_body(workspace_id, dataset_id),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "sample_records" in body
        assert "total_matching" in body
        assert "warnings" in body

    export_id: str = ""
    with checkpoint(ctx, "create_export"):
        resp = await client.post(
            f"{BASE}/exports",
            json=_export_create_body(workspace_id, dataset_id),
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["status"] == "pending"
        assert body["workspace_id"] == workspace_id
        assert body["dataset_id"] == dataset_id
        export_id = body["export_id"]

    with checkpoint(ctx, "list_exports"):
        resp = await client.get(
            f"{BASE}/exports",
            params={"workspace_id": workspace_id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "items" in body

    with checkpoint(ctx, "get_export_404"):
        # The in-memory stub doesn't persist, so GET by ID is 404
        resp = await client.get(f"{BASE}/exports/{export_id}")
        assert resp.status_code == 404, resp.text

    with checkpoint(ctx, "validate_export"):
        resp = await client.post(f"{BASE}/exports/{export_id}/validate")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["export_id"] == export_id
        assert "status" in body
        assert "validated_at" in body

    with checkpoint(ctx, "download_export"):
        resp = await client.post(f"{BASE}/exports/{export_id}/download")
        # Returns 404 JSON since export isn't completed
        assert resp.status_code == 404, resp.text

    with checkpoint(ctx, "push_hf"):
        resp = await client.post(
            f"{BASE}/exports/{export_id}/push-hf",
            json={"repo_id": "my-org/my-dataset", "split": "train", "private": True},
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["export_id"] == export_id
        assert body["repo_id"] == "my-org/my-dataset"
        assert body["status"] == "pending"

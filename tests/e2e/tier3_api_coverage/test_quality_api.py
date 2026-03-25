"""Tier 3 — API Coverage: Quality (T3-12).

Tests:
    T3-12: Dashboard + agreement + drift endpoints
"""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SHARED_WORKSPACE

BASE = "/api/v1"


async def _setup(client: InstrumentedClient) -> str:
    rp = await client.post(
        f"{BASE}/reviewer-profiles",
        json={
            "display_name": "QA Reviewer",
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
        json={"path": "/tmp/ws-quality", "workspace_name": "Quality WS"},
    )
    assert ws.status_code == 201
    return ws.json()["workspace_id"]


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier3
async def test_quality_dashboard_agreement_drift(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T3-12: Quality dashboard, agreement metrics, and drift report."""

    workspace_id = await _setup(client)

    with checkpoint(ctx, "quality_dashboard"):
        resp = await client.get(
            f"{BASE}/quality/dashboard",
            params={"workspace_id": workspace_id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["workspace_id"] == workspace_id
        assert "overall_agreement" in body
        assert "readiness_gates" in body
        assert "recent_quality_trend" in body

    with checkpoint(ctx, "quality_dashboard_with_filters"):
        resp = await client.get(
            f"{BASE}/quality/dashboard",
            params={
                "workspace_id": workspace_id,
                "dataset_id": "00000000-0000-0000-0000-000000000001",
                "task_schema_id": "00000000-0000-0000-0000-000000000002",
            },
        )
        assert resp.status_code == 200, resp.text

    with checkpoint(ctx, "agreement_metrics"):
        resp = await client.get(
            f"{BASE}/quality/agreement",
            params={"workspace_id": workspace_id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "overall" in body
        assert "cohens_kappa" in body["overall"]
        assert "per_field" in body
        assert "per_reviewer" in body
        assert "confusion_matrices" in body

    with checkpoint(ctx, "agreement_metrics_with_filters"):
        resp = await client.get(
            f"{BASE}/quality/agreement",
            params={
                "workspace_id": workspace_id,
                "dataset_id": "00000000-0000-0000-0000-000000000001",
                "task_schema_id": "00000000-0000-0000-0000-000000000002",
            },
        )
        assert resp.status_code == 200, resp.text

    with checkpoint(ctx, "drift_report"):
        resp = await client.get(
            f"{BASE}/quality/drift",
            params={"workspace_id": workspace_id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "indicators" in body
        assert "last_analyzed_at" in body

    with checkpoint(ctx, "drift_report_filtered_by_dataset"):
        resp = await client.get(
            f"{BASE}/quality/drift",
            params={
                "workspace_id": workspace_id,
                "dataset_id": "00000000-0000-0000-0000-000000000001",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["dataset_id"] == "00000000-0000-0000-0000-000000000001"

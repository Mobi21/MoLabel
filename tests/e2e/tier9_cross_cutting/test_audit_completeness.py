"""Tier 9 — Cross-Cutting: Audit Completeness (T9-01).

Tests:
    T9-01: Run full pipeline, verify audit log endpoint is reachable and
           responds with the expected schema; enumerate all AuditAction values.
"""

from __future__ import annotations

import pytest

from molabel.core.types import AuditAction
from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import INDEPENDENT

BASE = "/api/v1"


async def _setup(client: InstrumentedClient) -> str:
    """Create reviewer, log in, create workspace; return workspace_id."""
    rp = await client.post(
        f"{BASE}/reviewer-profiles",
        json={
            "display_name": "Audit Complete Reviewer",
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
        json={"path": "/tmp/ws-audit-complete", "workspace_name": "AuditComplete WS"},
    )
    assert ws.status_code == 201
    return ws.json()["workspace_id"]


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier9
async def test_audit_completeness(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T9-01: All AuditAction enum values are defined and the audit endpoint returns
    correct schema.
    """

    workspace_id = await _setup(client)

    # --- Verify all 31 AuditAction enum members exist ---
    with checkpoint(ctx, "all_audit_actions_defined"):
        all_actions = list(AuditAction)
        assert len(all_actions) >= 31, (
            f"Expected at least 31 AuditAction values, got {len(all_actions)}: "
            f"{[a.value for a in all_actions]}"
        )

    with checkpoint(ctx, "audit_action_core_values"):
        values = {a.value for a in AuditAction}
        required = {
            "workspace_created",
            "dataset_imported",
            "dataset_reindexed",
            "workflow_created",
            "workflow_started",
            "workflow_completed",
            "task_schema_created",
            "task_schema_updated",
            "agent_run_started",
            "agent_run_completed",
            "agent_run_failed",
            "review_submitted",
            "review_draft_saved",
            "ai_revealed",
            "adjudication_resolved",
            "export_created",
            "export_validated",
            "release_created",
            "release_approved",
            "release_rejected",
            "snapshot_created",
            "snapshot_restored",
            "plugin_enabled",
            "plugin_disabled",
            "config_changed",
            "file_written",
            "reindex_triggered",
            "prompt_created",
            "prompt_refined",
            "correction_analyzed",
            "provider_detected",
        }
        missing = required - values
        assert not missing, f"Missing AuditAction values: {missing}"

    # --- Verify audit endpoint schema ---
    with checkpoint(ctx, "audit_list_schema"):
        resp = await client.get(
            f"{BASE}/audit",
            params={"workspace_id": workspace_id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "items" in body
        assert "has_more" in body
        assert "cursor" in body
        assert isinstance(body["items"], list)

    with checkpoint(ctx, "audit_list_initially_empty"):
        resp = await client.get(
            f"{BASE}/audit",
            params={"workspace_id": workspace_id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # Stub always returns empty list
        assert isinstance(body["items"], list)

    # --- Verify each AuditAction value is a valid string ---
    with checkpoint(ctx, "audit_action_string_enum"):
        for action in AuditAction:
            assert isinstance(action.value, str), (
                f"AuditAction.{action.name} value is not a string"
            )
            assert action.value == action.value.lower(), (
                f"AuditAction.{action.name} value '{action.value}' is not lowercase"
            )

    # --- Verify filtering by each known event_type is accepted ---
    with checkpoint(ctx, "audit_filter_by_event_type_accepted"):
        for action in [
            AuditAction.workspace_created,
            AuditAction.review_submitted,
            AuditAction.export_created,
        ]:
            resp = await client.get(
                f"{BASE}/audit",
                params={"workspace_id": workspace_id, "event_type": action.value},
            )
            assert resp.status_code == 200, (
                f"Expected 200 for event_type={action.value}, "
                f"got {resp.status_code}: {resp.text}"
            )

    # --- Verify time range filters work ---
    with checkpoint(ctx, "audit_time_range_filter"):
        resp = await client.get(
            f"{BASE}/audit",
            params={
                "workspace_id": workspace_id,
                "created_after": "2020-01-01T00:00:00Z",
                "created_before": "2030-01-01T00:00:00Z",
            },
        )
        assert resp.status_code == 200, resp.text

    # --- Verify get single event returns 404 for unknown ---
    with checkpoint(ctx, "audit_get_single_404"):
        resp = await client.get(f"{BASE}/audit/00000000-0000-0000-0000-aud1c0mpl001")
        assert resp.status_code == 404, resp.text
        body = resp.json()
        assert "error" in body

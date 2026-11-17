"""Tier 3 — API Coverage: Adjudication (T3-11).

Tests:
    T3-11: A review queue's disagreements answer 404 for an unknown queue.
    ``tests/integration/test_api_review_adjudication.py`` covers detection
    and resolution on a reviewed queue.
"""

from __future__ import annotations

import uuid

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SHARED_WORKSPACE

BASE = "/api/v1"


async def _setup(client: InstrumentedClient) -> None:
    rp = await client.post(
        f"{BASE}/reviewer-profiles",
        json={
            "display_name": "Adj Reviewer",
            "workspace_id": "00000000-0000-0000-0000-000000000001",
        },
    )
    assert rp.status_code == 201
    reviewer_id = rp.json()["id"]
    login = await client.post(f"{BASE}/sessions", json={"reviewer_id": reviewer_id})
    assert login.status_code == 200
    client._session_cookie = login.cookies.get("molabel_session")


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier3
async def test_adjudication_of_an_unknown_queue_is_not_found(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T3-11: List, show, and resolve answer 404 for an unknown queue."""

    await _setup(client)
    base = f"{BASE}/adjudication/queues/{uuid.uuid4()}/disagreements"
    record_id = str(uuid.uuid4())

    with checkpoint(ctx, "list_disagreements_404"):
        resp = await client.get(base)
        assert resp.status_code == 404, resp.text

    with checkpoint(ctx, "show_disagreement_404"):
        resp = await client.get(f"{base}/{record_id}")
        assert resp.status_code == 404, resp.text

    with checkpoint(ctx, "resolve_disagreement_404"):
        resp = await client.post(
            f"{base}/{record_id}/resolve",
            json={
                "resolved_labels": {"sentiment": "positive"},
                "review_event_ids": [str(uuid.uuid4())],
            },
        )
        assert resp.status_code == 404, resp.text

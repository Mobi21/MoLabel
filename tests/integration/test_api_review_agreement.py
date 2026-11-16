"""Agreement measured from a queue's review events."""

from __future__ import annotations

import pytest
import pytest_asyncio

from tests.integration.review_flow import (
    NO_PAIRS,
    _as,
    _review_both,
    _start_review,
    review_app,
    review_client,
)


@pytest.fixture()
def app(tmp_path):
    return review_app(tmp_path)


@pytest_asyncio.fixture()
async def client(app):
    async with review_client(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Agreement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agreement_rates_each_reviewer_and_skips_fields_without_pairs(
    client, app, tmp_path
):
    workspace_id, tokens, queue = await _start_review(client, app, tmp_path)
    await _review_both(client, queue["queue_id"], tokens)

    report = await client.get(
        "/api/v1/quality/agreement",
        params={"workspace_id": workspace_id, "queue_id": queue["queue_id"]},
        headers=_as(tokens[0]),
    )
    assert report.status_code == 200, report.text
    body = report.json()
    assert (body["record_count"], body["reviewer_count"]) == (6, 2)

    # Two reviewers per record: pos 4, neg 5, neu 3 of n = 12, one split pair
    # (r3). D_o = 2/12, D_e = (144 - 50) / 132, alpha = 1 - D_o / D_e = 72/94.
    inter = body["inter_annotator"]
    assert inter["fields"]["sentiment"]["krippendorff_alpha"] == pytest.approx(72 / 94)
    assert inter["pooled"]["krippendorff_alpha"] == pytest.approx(72 / 94)
    assert inter["skipped_fields"] == {"note": NO_PAIRS}

    # Twelve human-agent pairs, r3's first-reviewer pair split: pos 8, neg 9,
    # neu 7 of n = 24, D_o = 2/24, D_e = (576 - 194) / 552, alpha = 336/382.
    human_agent = body["human_agent"]
    assert human_agent["fields"]["sentiment"]["percent_agreement"] == pytest.approx(
        11 / 12
    )
    assert human_agent["fields"]["sentiment"]["krippendorff_alpha"] == pytest.approx(
        336 / 382
    )
    assert human_agent["skipped_fields"] == {"note": NO_PAIRS}

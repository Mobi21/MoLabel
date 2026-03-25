"""All 8 AgentRole values test (T5-10).

Exercises all AgentRole enum values through the agent-runs API:
proposer, critic, normalizer, disagreement_flagger, deduper,
rubric_judge, edge_case_miner, export_prep.
"""

from __future__ import annotations

import pytest

from molabel.core.types import AgentRole
from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SHARED_WORKSPACE

ALL_AGENT_ROLES = [
    AgentRole.proposer,
    AgentRole.critic,
    AgentRole.normalizer,
    AgentRole.disagreement_flagger,
    AgentRole.deduper,
    AgentRole.rubric_judge,
    AgentRole.edge_case_miner,
    AgentRole.export_prep,
]


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier5
async def test_all_eight_agent_roles(
    ctx: TestContext,
    client: InstrumentedClient,
) -> None:
    """T5-10: All 8 AgentRole enum values accepted by the agent-runs API."""
    with checkpoint(ctx, "session_setup"):
        await client.login("reviewer-t5-10")

    with checkpoint(ctx, "verify_agent_role_enum_coverage"):
        expected_roles = {
            "proposer",
            "critic",
            "normalizer",
            "disagreement_flagger",
            "deduper",
            "rubric_judge",
            "edge_case_miner",
            "export_prep",
        }
        actual_roles = {r.value for r in AgentRole}
        assert expected_roles == actual_roles, (
            f"AgentRole enum mismatch. Expected {expected_roles}, got {actual_roles}"
        )

    role_run_ids: dict[str, str] = {}

    for role in ALL_AGENT_ROLES:
        with checkpoint(ctx, f"start_agent_run_role_{role.value}"):
            run_resp = await client.post(
                "/agent-runs",
                json={
                    "workspace_id": "00000000-0000-0000-0000-000000000001",
                    "dataset_id": "00000000-0000-0000-0000-000000000002",
                    "agent_role": role.value,
                    "task_schema_id": "00000000-0000-0000-0000-000000000003",
                    "model_profile_id": f"profile-for-{role.value}",
                    "prompt_version": "v1",
                },
            )
            assert run_resp.status_code == 202, (
                f"Expected 202 for agent_role={role.value}, "
                f"got {run_resp.status_code}: {run_resp.text}"
            )

            run_body = run_resp.json()
            assert run_body["agent_role"] == role.value, (
                f"Expected agent_role={role.value} in response, "
                f"got {run_body['agent_role']}"
            )
            assert run_body["status"] == "pending"
            assert "agent_run_id" in run_body

            role_run_ids[role.value] = run_body["agent_run_id"]

    with checkpoint(ctx, "all_roles_created_successfully"):
        assert len(role_run_ids) == len(ALL_AGENT_ROLES)
        for role in ALL_AGENT_ROLES:
            assert role.value in role_run_ids
            assert role_run_ids[role.value] != ""

    with checkpoint(ctx, "list_agent_runs_includes_all_roles"):
        list_resp = await client.get(
            "/agent-runs",
            params={"workspace_id": "00000000-0000-0000-0000-000000000001"},
        )
        assert list_resp.status_code == 200
        list_body = list_resp.json()
        assert "items" in list_body

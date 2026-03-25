"""Tier 9 — Cross-Cutting: Executor Registry (T9-11).

Tests:
    T9-11: create_default_registry() has executors for all 21 WorkflowStepType
           values; verify registration, has_executor, registered_types, and
           category mapping coverage.
"""

from __future__ import annotations

import pytest

from molabel.core.types import WorkflowStepType
from molabel.core.workflow.engine import create_default_registry
from molabel.core.workflow.registry import STEP_TYPE_CATEGORIES, StepExecutorRegistry
from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import INDEPENDENT


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier9
async def test_executor_registry(
    client: InstrumentedClient,
    ctx: TestContext,
) -> None:
    """T9-11: create_default_registry() provides executors for all 21 step types."""

    with checkpoint(ctx, "create_default_registry_returns_registry"):
        registry = create_default_registry()
        assert isinstance(registry, StepExecutorRegistry)

    with checkpoint(ctx, "all_step_types_have_executors"):
        registry = create_default_registry()
        all_step_types = list(WorkflowStepType)
        missing = []
        for step_type in all_step_types:
            if not registry.has_executor(step_type.value):
                missing.append(step_type.value)
        assert not missing, (
            f"create_default_registry() is missing executors for: {missing}"
        )

    with checkpoint(ctx, "registered_types_count_matches_enum"):
        registry = create_default_registry()
        registered = registry.registered_types()
        enum_values = sorted(st.value for st in WorkflowStepType)
        assert registered == enum_values, (
            f"registered_types() doesn't match WorkflowStepType enum.\n"
            f"Only in registry: {set(registered) - set(enum_values)}\n"
            f"Only in enum: {set(enum_values) - set(registered)}"
        )

    with checkpoint(ctx, "step_type_categories_covers_all_types"):
        enum_values = {st.value for st in WorkflowStepType}
        category_keys = set(STEP_TYPE_CATEGORIES.keys())
        missing = enum_values - category_keys
        assert not missing, f"STEP_TYPE_CATEGORIES is missing entries for: {missing}"

    with checkpoint(ctx, "registry_category_lookup_works"):
        registry = create_default_registry()
        for step_type in WorkflowStepType:
            cat = registry.get_category(step_type.value)
            assert cat is not None, f"get_category('{step_type.value}') returned None"

    with checkpoint(ctx, "blocking_step_types_identified"):
        registry = create_default_registry()
        blocking_types = [
            WorkflowStepType.human_review,
            WorkflowStepType.human_triage,
            WorkflowStepType.human_calibration,
            WorkflowStepType.human_adjudication,
            WorkflowStepType.gate,
        ]
        for st in blocking_types:
            assert registry.is_blocking(st.value), (
                f"Expected '{st.value}' to be a blocking step type"
            )

    with checkpoint(ctx, "non_blocking_step_types_identified"):
        registry = create_default_registry()
        non_blocking_types = [
            WorkflowStepType.data_ingest,
            WorkflowStepType.agent_run,
            WorkflowStepType.export,
        ]
        for st in non_blocking_types:
            assert not registry.is_blocking(st.value), (
                f"Expected '{st.value}' to NOT be a blocking step type"
            )

    with checkpoint(ctx, "has_timeout_for_automated_steps"):
        registry = create_default_registry()
        # Automated (non-blocking) steps should have timeouts
        assert registry.has_timeout(WorkflowStepType.data_ingest.value)
        assert registry.has_timeout(WorkflowStepType.agent_run.value)

    with checkpoint(ctx, "no_timeout_for_blocking_steps"):
        registry = create_default_registry()
        # Blocking steps should NOT have automatic timeouts
        assert not registry.has_timeout(WorkflowStepType.human_review.value)
        assert not registry.has_timeout(WorkflowStepType.gate.value)

    with checkpoint(ctx, "unknown_step_type_raises_key_error"):
        registry = create_default_registry()
        with pytest.raises(KeyError, match="not_a_step_type"):
            registry.create("not_a_step_type")

    with checkpoint(ctx, "data_category_steps_correct"):
        registry = create_default_registry()
        from molabel.core.types import WorkflowStepCategory

        data_steps = [
            WorkflowStepType.data_ingest,
            WorkflowStepType.data_normalize,
            WorkflowStepType.data_filter,
            WorkflowStepType.data_sample,
            WorkflowStepType.data_deduplicate,
        ]
        for st in data_steps:
            cat = registry.get_category(st.value)
            assert cat == WorkflowStepCategory.data, (
                f"Expected '{st.value}' to have category 'data', got '{cat}'"
            )

    with checkpoint(ctx, "control_category_steps_correct"):
        registry = create_default_registry()
        from molabel.core.types import WorkflowStepCategory

        control_steps = [
            WorkflowStepType.loop,
            WorkflowStepType.conditional,
            WorkflowStepType.parallel,
            WorkflowStepType.gate,
        ]
        for st in control_steps:
            cat = registry.get_category(st.value)
            assert cat == WorkflowStepCategory.control, (
                f"Expected '{st.value}' to have category 'control', got '{cat}'"
            )

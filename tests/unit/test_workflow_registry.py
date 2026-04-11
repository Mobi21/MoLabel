"""Tests for the step executor registry (WF-003)."""

from __future__ import annotations

import pytest

from molabel.core.types import WorkflowStepCategory
from molabel.core.workflow.engine import create_default_registry
from molabel.core.workflow.registry import (
    BLOCKING_STEP_TYPES,
    STEP_TYPE_CATEGORIES,
    StepExecutorRegistry,
)


class TestStepExecutorRegistry:
    """Tests for registry registration, lookup, and metadata."""

    def test_default_registry_has_all_types(self) -> None:
        registry = create_default_registry()
        expected_types = [
            "data_ingest",
            "data_normalize",
            "data_filter",
            "data_sample",
            "data_deduplicate",
            "agent_run",
            "agent_compare",
            "human_review",
            "human_triage",
            "human_calibration",
            "human_adjudication",
            "quality_check",
            "agreement_analysis",
            "drift_detection",
            "export",
            "snapshot",
            "release_validation",
            "loop",
            "conditional",
            "parallel",
            "gate",
        ]
        for t in expected_types:
            assert registry.has_executor(t), f"Missing executor for '{t}'"

    def test_create_executor(self) -> None:
        registry = create_default_registry()
        executor = registry.create("data_ingest")
        assert executor is not None

    def test_unknown_type_raises(self) -> None:
        registry = StepExecutorRegistry()
        with pytest.raises(KeyError, match="No executor"):
            registry.create("nonexistent")

    def test_registered_types(self) -> None:
        registry = create_default_registry()
        types = registry.registered_types()
        assert len(types) == 21
        assert "data_ingest" in types
        assert "gate" in types
        assert "agent_labeling" not in types

    def test_step_type_categories(self) -> None:
        assert STEP_TYPE_CATEGORIES["data_ingest"] == WorkflowStepCategory.data
        assert STEP_TYPE_CATEGORIES["agent_run"] == WorkflowStepCategory.agent
        assert STEP_TYPE_CATEGORIES["human_review"] == WorkflowStepCategory.human
        assert STEP_TYPE_CATEGORIES["quality_check"] == WorkflowStepCategory.quality
        assert STEP_TYPE_CATEGORIES["export"] == WorkflowStepCategory.output
        assert STEP_TYPE_CATEGORIES["loop"] == WorkflowStepCategory.control

    def test_get_category(self) -> None:
        registry = create_default_registry()
        assert registry.get_category("data_ingest") == WorkflowStepCategory.data
        assert registry.get_category("nonexistent") is None

    def test_blocking_step_types(self) -> None:
        assert "human_review" in BLOCKING_STEP_TYPES
        assert "human_triage" in BLOCKING_STEP_TYPES
        assert "gate" in BLOCKING_STEP_TYPES
        assert "data_ingest" not in BLOCKING_STEP_TYPES

    def test_is_blocking(self) -> None:
        registry = create_default_registry()
        assert registry.is_blocking("human_review") is True
        assert registry.is_blocking("data_ingest") is False

    def test_has_timeout(self) -> None:
        registry = create_default_registry()
        assert registry.has_timeout("data_ingest") is True
        assert registry.has_timeout("human_review") is False
        assert registry.has_timeout("gate") is False

    def test_all_step_types_have_categories(self) -> None:
        registry = create_default_registry()
        for step_type in registry.registered_types():
            cat = registry.get_category(step_type)
            assert cat is not None, f"Step type '{step_type}' has no category"

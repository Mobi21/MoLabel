"""Tests for built-in workflow templates (WF-046 through WF-051)."""

from __future__ import annotations

import pytest

from molabel.core.workflow.parser import parse_workflow_yaml
from molabel.core.workflow.templates import (
    get_template_path,
    get_template_yaml,
    list_templates,
)


class TestTemplateRegistry:
    """Tests for the template listing and loading functions."""

    def test_list_templates_returns_ten(self) -> None:
        templates = list_templates()
        assert len(templates) == 10

    def test_all_templates_have_required_keys(self) -> None:
        for t in list_templates():
            assert "id" in t
            assert "name" in t
            assert "description" in t
            assert "file" in t
            assert "version" in t
            assert "task_family" in t
            assert "capabilities" in t
            assert "validated_by_benchmarks" in t

    def test_get_template_path_exists(self) -> None:
        for t in list_templates():
            path = get_template_path(t["id"])
            assert path.exists(), f"Template file missing: {path}"

    def test_get_template_yaml_returns_content(self) -> None:
        yaml_str = get_template_yaml("quick_agentic_label")
        assert "name:" in yaml_str
        assert "steps:" in yaml_str

    def test_unknown_template_raises(self) -> None:
        with pytest.raises(KeyError, match="Unknown template"):
            get_template_path("nonexistent")


class TestTemplateParsing:
    """Tests that all templates parse without errors."""

    @pytest.mark.parametrize(
        "template_id",
        [t["id"] for t in list_templates()],
    )
    def test_template_parses(self, template_id: str) -> None:
        yaml_str = get_template_yaml(template_id)
        wf = parse_workflow_yaml(yaml_str, from_string=True)
        assert wf.name
        assert wf.version >= 1
        assert len(wf.steps) >= 2


class TestSpecificTemplates:
    """Tests for specific template structure."""

    def test_quick_agentic_label(self) -> None:
        wf = parse_workflow_yaml(
            get_template_yaml("quick_agentic_label"), from_string=True
        )
        assert wf.name == "Quick Agentic Label"
        step_types = [s.type for s in wf.steps]
        assert "data_ingest" in step_types
        assert "agent_run" in step_types
        assert "export" in step_types

    def test_human_in_the_loop(self) -> None:
        wf = parse_workflow_yaml(
            get_template_yaml("human_in_the_loop"), from_string=True
        )
        assert wf.name == "Human-in-the-Loop Review"
        step_types = [s.type for s in wf.steps]
        assert "human_review" in step_types
        assert "loop" in step_types
        assert "quality_check" in step_types

    def test_full_quality_pipeline(self) -> None:
        wf = parse_workflow_yaml(
            get_template_yaml("full_quality_pipeline"), from_string=True
        )
        step_types = [s.type for s in wf.steps]
        assert "human_calibration" in step_types
        assert "agreement_analysis" in step_types
        assert "human_adjudication" in step_types
        assert "release_validation" in step_types

    def test_benchmark_authority(self) -> None:
        wf = parse_workflow_yaml(
            get_template_yaml("benchmark_authority"), from_string=True
        )
        step_types = [s.type for s in wf.steps]
        assert "snapshot" in step_types
        assert "gate" in step_types

    def test_agent_comparison(self) -> None:
        wf = parse_workflow_yaml(
            get_template_yaml("agent_comparison"), from_string=True
        )
        step_types = [s.type for s in wf.steps]
        assert "agent_compare" in step_types

    def test_iterative_refinement(self) -> None:
        wf = parse_workflow_yaml(
            get_template_yaml("iterative_refinement"), from_string=True
        )
        step_types = [s.type for s in wf.steps]
        assert "loop" in step_types
        assert "data_sample" in step_types

    def test_grounded_rationale_moderation(self) -> None:
        wf = parse_workflow_yaml(
            get_template_yaml("grounded_rationale_moderation"), from_string=True
        )
        step_types = [s.type for s in wf.steps]
        assert "agent_run" in step_types
        assert "human_review" in step_types
        assert "human_adjudication" in step_types

    def test_psychology_survey_codebook(self) -> None:
        wf = parse_workflow_yaml(
            get_template_yaml("psychology_survey_codebook"), from_string=True
        )
        step_types = [s.type for s in wf.steps]
        metadata = wf.metadata["metadata"]
        assert metadata["domain"] == "psychology_research"
        assert metadata["canonical_model"] == "MiniMax-M2.7-highspeed"
        assert "human_calibration" in step_types
        assert "agent_run" in step_types
        assert "agreement_analysis" in step_types
        assert "human_adjudication" in step_types
        assert "release_validation" in step_types

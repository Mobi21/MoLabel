"""Built-in workflow templates (WF-046 through WF-051).

Provides 6 YAML template files and a loader function for accessing them.
"""

from __future__ import annotations

from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent


def list_templates() -> list[dict[str, str]]:
    """Return metadata for all built-in workflow templates."""
    return [
        {
            "id": "quick_agentic_label",
            "name": "Quick Agentic Label",
            "description": (
                "Ingest, agent run, spot-check sample, export. "
                "Minimal human involvement."
            ),
            "file": "quick_agentic_label.yaml",
        },
        {
            "id": "human_in_the_loop",
            "name": "Human-in-the-Loop Review",
            "description": (
                "Ingest, agent run, human review, quality check, "
                "refinement loop, export."
            ),
            "file": "human_in_the_loop.yaml",
        },
        {
            "id": "full_quality_pipeline",
            "name": "Full Quality Pipeline",
            "description": (
                "Ingest, calibration, agent run, human review, "
                "agreement analysis, adjudication, quality check, "
                "export, release validation."
            ),
            "file": "full_quality_pipeline.yaml",
        },
        {
            "id": "benchmark_authority",
            "name": "Benchmark Authority",
            "description": (
                "Ingest, multi-round expert review, adjudication, "
                "agreement analysis, snapshot as ground truth."
            ),
            "file": "benchmark_authority.yaml",
        },
        {
            "id": "agent_comparison",
            "name": "Agent Comparison",
            "description": (
                "Ingest, parallel agent runs (multiple models), "
                "side-by-side human review, comparison analytics, export."
            ),
            "file": "agent_comparison.yaml",
        },
        {
            "id": "iterative_refinement",
            "name": "Iterative Refinement",
            "description": (
                "Ingest, agent run, low-confidence review, prompt "
                "refinement, loop until quality target, export."
            ),
            "file": "iterative_refinement.yaml",
        },
    ]


def get_template_path(template_id: str) -> Path:
    """Return the absolute path to a template YAML file.

    Raises KeyError if the template ID is not found.
    """
    for t in list_templates():
        if t["id"] == template_id:
            return TEMPLATES_DIR / t["file"]
    raise KeyError(f"Unknown template: {template_id}")


def get_template_yaml(template_id: str) -> str:
    """Return the YAML content of a built-in template.

    Raises KeyError if the template ID is not found.
    """
    path = get_template_path(template_id)
    return path.read_text(encoding="utf-8")

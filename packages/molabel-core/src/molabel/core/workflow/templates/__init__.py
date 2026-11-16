"""Built-in workflow templates (WF-046 through WF-051).

Provides built-in YAML template files and loader functions for CLI/product use.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

TEMPLATES_DIR = Path(__file__).parent


def list_templates() -> list[dict[str, Any]]:
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
            "version": "1.0.0",
            "task_family": "general_labeling",
            "capabilities": ["agent_labeling", "spot_check", "export"],
            "validated_by_benchmarks": [],
        },
        {
            "id": "human_in_the_loop",
            "name": "Human-in-the-Loop Review",
            "description": (
                "Ingest, agent run, human review, quality check, "
                "refinement loop, export."
            ),
            "file": "human_in_the_loop.yaml",
            "version": "1.0.0",
            "task_family": "general_review",
            "capabilities": ["agent_labeling", "human_review", "quality_check"],
            "validated_by_benchmarks": [],
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
            "version": "1.0.0",
            "task_family": "general_quality",
            "capabilities": [
                "human_calibration",
                "agreement_analysis",
                "human_adjudication",
                "release_validation",
            ],
            "validated_by_benchmarks": [],
        },
        {
            "id": "benchmark_authority",
            "name": "Benchmark Authority",
            "description": (
                "Ingest, multi-round expert review, adjudication, "
                "agreement analysis, snapshot as ground truth."
            ),
            "file": "benchmark_authority.yaml",
            "version": "1.0.0",
            "task_family": "benchmark_authoring",
            "capabilities": ["human_review", "adjudication", "snapshot"],
            "validated_by_benchmarks": [],
        },
        {
            "id": "agent_comparison",
            "name": "Agent Comparison",
            "description": (
                "Ingest, parallel agent runs (multiple models), "
                "side-by-side human review, comparison analytics, export."
            ),
            "file": "agent_comparison.yaml",
            "version": "1.0.0",
            "task_family": "comparison",
            "capabilities": ["agent_compare", "human_review", "analytics"],
            "validated_by_benchmarks": [],
        },
        {
            "id": "iterative_refinement",
            "name": "Iterative Refinement",
            "description": (
                "Ingest, agent run, low-confidence review, prompt "
                "refinement, loop until quality target, export."
            ),
            "file": "iterative_refinement.yaml",
            "version": "1.0.0",
            "task_family": "prompt_refinement",
            "capabilities": ["agent_labeling", "low_confidence_review", "loop"],
            "validated_by_benchmarks": [],
        },
        {
            "id": "grounded_classification_review",
            "name": "Grounded Classification Review",
            "description": (
                "Grounded single-label or multi-label classification with "
                "explicit proposer, all-record review, and benchmark artifacts."
            ),
            "file": "grounded_classification_review.yaml",
            "version": "1.0.0",
            "task_family": "grounded_classification",
            "capabilities": [
                "source_record_ids",
                "agent_labeling",
                "human_review",
                "benchmark_artifacts",
            ],
            "validated_by_benchmarks": [
                "clinc150",
                "banking77",
                "goemotions",
            ],
        },
        {
            "id": "grounded_evidence_verification",
            "name": "Grounded Evidence Verification",
            "description": (
                "Verification workflow that preserves stable evidence atom IDs "
                "through proposer and review."
            ),
            "file": "grounded_evidence_verification.yaml",
            "version": "1.0.0",
            "task_family": "grounded_evidence",
            "capabilities": [
                "grouped_evidence_atoms",
                "source_record_ids",
                "human_review",
                "benchmark_artifacts",
            ],
            "validated_by_benchmarks": ["feverous", "scifact"],
        },
        {
            "id": "grounded_rationale_moderation",
            "name": "Grounded Rationale Moderation",
            "description": (
                "Moderation workflow with explicit rationale-mask preservation "
                "and review breakpoint."
            ),
            "file": "grounded_rationale_moderation.yaml",
            "version": "1.0.0",
            "task_family": "grounded_rationale",
            "capabilities": [
                "rationale_token_mask",
                "source_record_ids",
                "human_review",
                "benchmark_artifacts",
            ],
            "validated_by_benchmarks": ["hatexplain"],
        },
        {
            "id": "psychology_survey_codebook",
            "name": "Psychology Survey Codebook",
            "description": (
                "Psychology and qualitative research workflow with codebook "
                "calibration, MiniMax-assisted coding, evidence spans, "
                "agreement analysis, adjudication, export, and release proof."
            ),
            "file": "psychology_survey_codebook.yaml",
            "version": "1.0.0",
            "task_family": "psychology_research",
            "capabilities": [
                "codebook_management",
                "pii_redaction",
                "agent_labeling",
                "human_calibration",
                "human_review",
                "agreement_analysis",
                "human_adjudication",
                "release_validation",
            ],
            "validated_by_benchmarks": ["psychology-survey-codebook"],
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


TASK_SCHEMA_STEP_TYPES = frozenset(
    {"agent_run", "agent_compare", "human_review", "human_calibration"}
)


def _steps(definition: dict[str, Any]) -> list[dict[str, Any]]:
    steps = definition.get("steps")
    return steps if isinstance(steps, list) else []


def _config(step: dict[str, Any]) -> dict[str, Any]:
    config = step.get("config")
    return config if isinstance(config, dict) else {}


def template_needs_dataset(definition: dict[str, Any]) -> bool:
    """Whether a data_ingest step has neither a source file nor a dataset."""
    return any(
        step.get("type") == "data_ingest"
        and not _config(step).get("source")
        and not _config(step).get("dataset_id")
        for step in _steps(definition)
    )


def template_needs_task_schema(definition: dict[str, Any]) -> bool:
    """Whether a step that labels or reviews records has no task schema."""
    return any(
        step.get("type") in TASK_SCHEMA_STEP_TYPES
        and not _config(step).get("task_schema_id")
        for step in _steps(definition)
    )


MODEL_CONFIG_KEYS = frozenset(
    {
        "model",
        "model_profile_id",
        "provider_type",
        "provider_name",
        "base_url",
        "auth_ref",
    }
)


AGENT_MODEL_STEP_TYPES = frozenset({"agent_run", "agent_compare"})


def template_has_agent_step(definition: dict[str, Any]) -> bool:
    """Whether a template has an agent step whose model can be bound."""
    return any(
        step.get("type") in AGENT_MODEL_STEP_TYPES for step in _steps(definition)
    )


def template_unset_model_steps(definition: dict[str, Any]) -> list[str]:
    """IDs of the agent_compare steps that leave a model unset, as null."""
    return [
        str(step.get("id"))
        for step in _steps(definition)
        if step.get("type") == "agent_compare"
        and None in (_config(step).get("models") or [])
    ]


def _without_model_config(config: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in config.items() if key not in MODEL_CONFIG_KEYS}


def _bind_compared_models(
    config: dict[str, Any], agent_model: dict[str, str]
) -> dict[str, Any]:
    models = config.get("models") or []
    if "provider_type" in agent_model:
        return {
            **_without_model_config(config),
            "models": [agent_model["model"]] * len(models),
            "provider_type": agent_model["provider_type"],
        }
    return {
        **config,
        "models": [
            agent_model["model"] if model is None else model for model in models
        ],
    }


def bind_template_inputs(
    definition: dict[str, Any],
    *,
    dataset_id: str | None,
    task_schema_id: str | None,
    agent_model: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Return a copy of a template definition bound to a dataset and schema.

    A bound dataset replaces any ingest source file. A bound task schema
    applies to every labeling, review, and normalize step. A bound agent
    model replaces the model and provider settings of every agent_run step.
    In an agent_compare step it fills the models the template leaves unset,
    or, when it names a provider_type, runs every compared model on it.
    """
    bound_steps: list[dict[str, Any]] = []
    for step in _steps(definition):
        config = dict(_config(step))
        step_type = step.get("type")
        if agent_model and step_type == "agent_run":
            config = {**_without_model_config(config), **agent_model}
        if agent_model and step_type == "agent_compare":
            config = _bind_compared_models(config, agent_model)
        if dataset_id and step_type == "data_ingest":
            config.pop("source", None)
            config["dataset_id"] = dataset_id
        if task_schema_id and step_type in TASK_SCHEMA_STEP_TYPES:
            config["task_schema_id"] = task_schema_id
        if task_schema_id and step_type == "data_normalize":
            config["schema_ref"] = task_schema_id
        bound_steps.append({**step, "config": config})
    return {**definition, "steps": bound_steps}

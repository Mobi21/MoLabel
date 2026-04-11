"""Shared contracts and scoring helpers for grounded benchmark fixtures.

Grounded benchmarks now prefer an authority-pack-first layout rooted at
``authority/`` while still supporting legacy workspace-first fixtures during
the migration. This module loads both layouts and provides reusable helpers for:

* paper-direct evaluation,
* MoLabel-operated evaluation,
* workflow and operator comparisons,
* and signed "tax" calculations between those layers.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator

from molabel.core.quality.grounded_benchmark_primitives import (
    build_classification_diagnostics,
    ingest_qrels,
    normalize_answer_text,
    normalize_classification_artifact,
    normalize_evidence_annotation,
    normalize_label_set_artifact,
    normalize_qa_with_evidence_artifact,
    normalize_ranking_artifact,
    score_anls,
    score_grounded_generation,
    score_grouped_evidence,
    score_multilabel_micro_f1,
    score_qa_with_evidence,
    score_ranking,
    score_span_exact_match,
    score_span_overlap_f1,
    sweep_label_thresholds,
    threshold_label_scores,
    validate_evidence_annotation,
    validate_grounded_ranking_artifact,
    validate_label_set_artifact,
    validate_span_annotation,
)
from molabel.core.utils.canonical import canonical_label_value

MetricType = Literal[
    "accuracy",
    "abstain_precision",
    "abstain_recall",
    "answer_exact_match",
    "answer_token_f1",
    "anls",
    "binary_recall",
    "evidence_group_exact_match",
    "evidence_group_f1",
    "evidence_group_precision",
    "evidence_group_recall",
    "feverous_score",
    "grounded_generation_score",
    "macro_f1",
    "map",
    "micro_f1",
    "mrr",
    "ndcg_at_k",
    "joint_answer_support",
    "joint_evidence_decision",
    "precision_at_k",
    "recall_at_k",
    "exact_match",
    "jaccard",
    "set_precision",
    "set_recall",
    "set_f1",
    "source_coverage",
    "span_exact_match",
    "span_overlap_f1",
    "supporting_fact_exact_match",
    "supporting_fact_f1",
    "token_mask_f1",
    "unsupported_content_rate",
]

BenchmarkMode = Literal["model", "workflow", "operator"]
BenchmarkStage = Literal[
    "paper_model",
    "molabel_model",
    "workflow_autorun",
    "workflow_reviewed",
    "operator_reviewed",
]
ScoringVariant = Literal["paper_direct", "molabel_operated"]


class GroundedBenchmarkProfile(BaseModel):
    """A named grounded benchmark profile."""

    profile_id: Literal["canonical", "operator-primary", "smoke"]
    split_id: str | None = None
    description: str | None = None
    notes: list[str] = Field(default_factory=list)


class GroundedAuthorityPackManifest(BaseModel):
    """Canonical pack manifest for grounded benchmarks."""

    benchmark_id: str
    layout: Literal["authority"] = "authority"
    benchmark_profiles: list[GroundedBenchmarkProfile] = Field(default_factory=list)
    canonical_profile_id: str = "canonical"
    operator_primary_profile_id: str = "operator-primary"
    smoke_profile_id: str = "smoke"
    paper_path: str = "paper.yaml"
    scenario_path: str = "scenario.yaml"
    label_map_path: str = "label-map.yaml"
    metrics_path: str = "metrics.yaml"
    baselines_path: str = "baselines.yaml"
    operator_path: str | None = None
    source_path: str | None = None
    source_manifest_paths: list[str] = Field(default_factory=list)
    reference_workspace_path: str | None = None
    raw_paths: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @field_validator("benchmark_profiles", mode="before")
    @classmethod
    def _coerce_benchmark_profiles(cls, value: Any) -> list[GroundedBenchmarkProfile]:
        return _coerce_benchmark_profiles(value)


class GroundedAuthorityValidationIssue(BaseModel):
    """A validation issue for an authority pack."""

    path: str
    message: str
    severity: Literal["error", "warning"] = "error"


class GroundedAuthorityValidationResult(BaseModel):
    """Validation result for a grounded authority pack."""

    benchmark_id: str
    is_valid: bool
    issues: list[GroundedAuthorityValidationIssue] = Field(default_factory=list)
    profiles: list[GroundedBenchmarkProfile] = Field(default_factory=list)


class GroundedAuthorityPack(BaseModel):
    """Canonical authority pack for a grounded benchmark."""

    manifest: GroundedAuthorityPackManifest
    paper: GroundedPaperMetadata
    scenario: GroundedBenchmarkScenario
    label_map: GroundedLabelMap
    metrics: GroundedMetricsConfig
    baselines: GroundedBaselines
    operator: GroundedOperatorSpec | None = None
    profiles: list[GroundedBenchmarkProfile] = Field(default_factory=list)
    source_root: Path | None = None
    raw_paths: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @field_validator("profiles", mode="before")
    @classmethod
    def _coerce_profiles(cls, value: Any) -> list[GroundedBenchmarkProfile]:
        return _coerce_benchmark_profiles(value)


class GroundedModelProfile(BaseModel):
    """Default live model profile for a grounded benchmark."""

    provider_type: str
    provider_name: str
    model_identifier: str
    sdk_stack: str
    agent_role: str | None = None


class GroundedBenchmarkScenario(BaseModel):
    """Top-level machine contract for a grounded benchmark fixture."""

    benchmark_id: str
    track: Literal["grounded"] = "grounded"
    name: str
    description: str
    raw_format: str
    source_path: str
    loader_plugin: str
    record_id_field: str | None = None
    record_id_from: str | None = None
    task_schema_path: str | None = None
    workflow_path: str | None = None
    paper_metadata_path: str
    label_map_path: str
    metrics_path: str
    baselines_path: str
    operator_path: str | None = None
    gold_labels_path: str
    paper_gold_path: str | None = None
    molabel_gold_path: str | None = None
    split_paths: list[str] = Field(default_factory=list)
    human_label_paths: list[str] = Field(default_factory=list)
    review_paths: list[str] = Field(default_factory=list)
    benchmark_profiles: list[GroundedBenchmarkProfile] = Field(default_factory=list)
    evaluation_modes: list[BenchmarkMode] = Field(
        default_factory=lambda: ["model", "workflow", "operator"]
    )
    scoring_variants: list[ScoringVariant] = Field(
        default_factory=lambda: ["paper_direct", "molabel_operated"]
    )
    evaluation_fields: list[str] = Field(default_factory=list)
    subset_policy: dict[str, Any] = Field(default_factory=dict)
    default_model_profile: GroundedModelProfile
    requires_dataset_download: bool = False
    redistribution_notes: list[str] = Field(default_factory=list)
    authority_pack_path: str | None = None

    @field_validator("benchmark_profiles", mode="before")
    @classmethod
    def _coerce_benchmark_profiles(cls, value: Any) -> list[GroundedBenchmarkProfile]:
        return _coerce_benchmark_profiles(value)


class GroundedPaperMetadata(BaseModel):
    """Paper, dataset, and licensing facts for a grounded benchmark."""

    benchmark_id: str
    paper_title: str
    paper_url: str
    citation: str
    publication_year: int
    dataset_name: str
    dataset_url: str
    source_repository_url: str | None = None
    dataset_license: str
    repository_license: str | None = None
    redistribution_status: Literal[
        "allowed",
        "subset_allowed",
        "review_required",
        "blocked",
    ]
    task_summary: str
    original_task_definition: str
    original_metrics: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class GroundedLabelMapField(BaseModel):
    """Mapping from dataset-native fields/labels into MoLabel fields."""

    dataset_field: str
    target_field: str
    mapping: dict[str, Any] = Field(default_factory=dict)
    lossy: bool = False
    notes: str | None = None


class GroundedLabelMap(BaseModel):
    """Explicit paper-to-MoLabel label mapping."""

    benchmark_id: str
    record_id_field: str
    dataset_label_fields: list[str] = Field(default_factory=list)
    target_label_fields: list[str] = Field(default_factory=list)
    field_mappings: list[GroundedLabelMapField] = Field(default_factory=list)


class GroundedMetricDefinition(BaseModel):
    """A score computed for one or more fields in a mode/variant combination."""

    metric_id: str
    name: str
    metric_type: MetricType
    modes: list[BenchmarkMode]
    variants: list[ScoringVariant]
    stages: list[BenchmarkStage] = Field(default_factory=list)
    fields: list[str] = Field(default_factory=list)
    weight: float = 1.0
    higher_is_better: bool = True
    positive_value: Any | None = None
    metric_options: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None


class GroundedTaxDefinition(BaseModel):
    """Signed delta between two scored layers."""

    tax_id: str
    name: str
    minuend_mode: BenchmarkMode | None = None
    minuend_variant: ScoringVariant
    subtrahend_mode: BenchmarkMode | None = None
    subtrahend_variant: ScoringVariant
    minuend_stage: BenchmarkStage | None = None
    subtrahend_stage: BenchmarkStage | None = None
    notes: str | None = None


class GroundedMetricsConfig(BaseModel):
    """Scoring contract for grounded benchmarks."""

    benchmark_id: str
    aggregation: Literal["weighted_mean"] = "weighted_mean"
    primary_metric_id: str | None = None
    metrics: list[GroundedMetricDefinition] = Field(default_factory=list)
    tax_definitions: list[GroundedTaxDefinition] = Field(default_factory=list)


class GroundedBaselineEntry(BaseModel):
    """Paper or local baseline for comparison."""

    baseline_id: str
    name: str
    source: Literal["paper", "shared_task", "molabel_local"]
    mode: BenchmarkMode
    variant: ScoringVariant
    stage: BenchmarkStage | None = None
    split_id: str
    metrics: dict[str, float] = Field(default_factory=dict)
    notes: str | None = None


def _coerce_benchmark_profiles(
    value: Any,
) -> list[GroundedBenchmarkProfile]:
    if value is None:
        return []
    profiles: list[GroundedBenchmarkProfile] = []
    for entry in value:
        if isinstance(entry, GroundedBenchmarkProfile):
            profiles.append(entry)
        elif isinstance(entry, str):
            profiles.append(GroundedBenchmarkProfile(profile_id=entry))
        elif isinstance(entry, dict):
            profiles.append(GroundedBenchmarkProfile.model_validate(entry))
        else:
            raise TypeError(
                "Benchmark profiles must be strings or benchmark profile mappings"
            )
    return profiles


class GroundedBaselines(BaseModel):
    """Baseline registry for a benchmark."""

    benchmark_id: str
    baselines: list[GroundedBaselineEntry] = Field(default_factory=list)


class GroundedOperatorCheck(BaseModel):
    """A required or optional operator-quality check."""

    check_id: str
    phase: str
    description: str
    weight: float = 1.0
    required: bool = True


class GroundedOperatorSpec(BaseModel):
    """Operator-quality contract for Codex or another external agent."""

    benchmark_id: str
    goal: str
    current_labeling_engine: str = "MiniMax 2.7"
    aggregation: Literal["weighted_mean"] = "weighted_mean"
    label_quality_weight: float = 0.7
    checklist_weight: float = 0.3
    blocking_check_ids: list[str] = Field(default_factory=list)
    checks: list[GroundedOperatorCheck] = Field(default_factory=list)


class GroundedOperatorObservation(BaseModel):
    """Observed outcome for one operator-quality check."""

    check_id: str
    passed: bool
    details: dict[str, Any] = Field(default_factory=dict)


class GroundedMetricResult(BaseModel):
    """A computed metric value."""

    metric_id: str
    name: str
    metric_type: MetricType
    value: float
    weight: float = 1.0
    fields: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class GroundedOperatorTruthfulnessCheck(BaseModel):
    """A check that operator-authored artifacts match persisted state."""

    check_id: str
    passed: bool
    details: dict[str, Any] = Field(default_factory=dict)


class GroundedOperatorRecordDelta(BaseModel):
    """Per-record proposal-versus-review diagnostic row."""

    record_id: str
    proposal_matches_gold: bool
    review_matches_gold: bool
    proposal_matches_review: bool
    status: Literal["unchanged", "corrected", "regressed", "changed"]
    gold_labels: dict[str, Any] = Field(default_factory=dict)
    proposal_labels: dict[str, Any] = Field(default_factory=dict)
    review_labels: dict[str, Any] = Field(default_factory=dict)


class GroundedOperatorDiagnostics(BaseModel):
    """Operator-quality diagnostics emitted alongside the benchmark summary."""

    record_count: int
    proposal_exact_match_count: int
    proposal_exact_match_rate: float
    review_exact_match_count: int
    review_exact_match_rate: float
    changed_count: int
    unchanged_count: int
    corrected_count: int
    regressed_count: int
    preserved_correct_count: int
    preserved_wrong_count: int
    changed_wrong_to_wrong_count: int
    proposal_to_review_delta: float
    operator_lift_count: int
    operator_lift_rate: float
    preserve_correct_rate: float
    regression_rate: float
    review_event_count: int
    final_decision_count: int
    multi_event_record_count: int
    accept_ai_count: int
    edit_ai_count: int
    correct_count: int
    reject_ai_count: int
    skip_count: int
    accept_ai_rate: float
    edit_ai_rate: float
    correct_rate: float
    reject_ai_rate: float
    skip_rate: float
    shell_command_count: int
    non_cli_surface_command_count: int
    hidden_benchmark_path_command_count: int
    truth_probe_command_count: int
    proposal_field_accuracy: dict[str, float] = Field(default_factory=dict)
    review_field_accuracy: dict[str, float] = Field(default_factory=dict)
    coverage: dict[str, Any] = Field(default_factory=dict)
    proposal_stage: dict[str, Any] = Field(default_factory=dict)
    review_stage: dict[str, Any] = Field(default_factory=dict)
    decision_quality: dict[str, Any] = Field(default_factory=dict)
    hard_case_breakdown: dict[str, Any] = Field(default_factory=dict)
    confidence_diagnostics: dict[str, Any] = Field(default_factory=dict)
    audit_summary: dict[str, Any] = Field(default_factory=dict)
    record_deltas: list[GroundedOperatorRecordDelta] = Field(default_factory=list)
    command_audit: dict[str, list[str]] = Field(default_factory=dict)
    truthfulness_checks: list[GroundedOperatorTruthfulnessCheck] = Field(
        default_factory=list
    )
    artifact_truthfulness: dict[str, Any] = Field(default_factory=dict)
    truthfulness_ok: bool = True


class GroundedTaxResult(BaseModel):
    """Computed tax result for a scored layer transition."""

    tax_id: str
    name: str
    value: float
    minuend_mode: BenchmarkMode
    minuend_variant: ScoringVariant
    subtrahend_mode: BenchmarkMode
    subtrahend_variant: ScoringVariant
    minuend_stage: BenchmarkStage | None = None
    subtrahend_stage: BenchmarkStage | None = None
    metric_deltas: dict[str, float] = Field(default_factory=dict)


class GroundedStageStabilitySummary(BaseModel):
    """Repeated-run stability summary for one stage/mode/variant."""

    stage: BenchmarkStage | None = None
    mode: BenchmarkMode
    variant: ScoringVariant
    run_count: int
    run_ids: list[str] = Field(default_factory=list)
    overall_mean: float
    overall_min: float
    overall_max: float
    overall_stddev: float
    overall_span: float
    metric_means: dict[str, float] = Field(default_factory=dict)
    metric_stddevs: dict[str, float] = Field(default_factory=dict)
    metric_spans: dict[str, float] = Field(default_factory=dict)


class GroundedRunSummary(BaseModel):
    """Serializable summary for a benchmark run."""

    benchmark_id: str
    run_id: str
    stage: BenchmarkStage | None = None
    mode: BenchmarkMode
    variant: ScoringVariant
    record_count: int
    overall_score: float
    primary_metric_id: str | None = None
    metrics: list[GroundedMetricResult] = Field(default_factory=list)
    tax_breakdown: list[GroundedTaxResult] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    summary_version: int = 4


@dataclass(frozen=True)
class GroundedBenchmarkBundle:
    """Loaded grounded benchmark fixture."""

    workspace_root: Path
    authority: GroundedAuthorityPack | None
    scenario: GroundedBenchmarkScenario
    paper: GroundedPaperMetadata
    label_map: GroundedLabelMap
    metrics: GroundedMetricsConfig
    baselines: GroundedBaselines
    operator: GroundedOperatorSpec | None = None


def _load_yaml_model(path: Path, model_class: type[BaseModel]) -> BaseModel:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if payload is None:
        payload = {}
    return model_class.model_validate(payload)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load a JSONL file."""
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def _authority_root_for(workspace_root: Path) -> Path | None:
    """Resolve the canonical authority-pack root, if present."""
    candidates = [
        workspace_root / "authority",
        workspace_root / "workbench" / "benchmarks" / "authority",
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def _default_profiles_from_scenario(
    scenario: GroundedBenchmarkScenario,
) -> list[GroundedBenchmarkProfile]:
    """Synthesize the standard benchmark profiles when the pack omits them."""
    profiles = list(scenario.benchmark_profiles)
    if profiles:
        return profiles
    return [
        GroundedBenchmarkProfile(
            profile_id="canonical",
            split_id=_primary_split_id(scenario),
            description=f"Canonical evaluation for {scenario.benchmark_id}.",
        ),
        GroundedBenchmarkProfile(
            profile_id="operator-primary",
            split_id=_primary_split_id(scenario),
            description=f"Operator-primary slice for {scenario.benchmark_id}.",
        ),
        GroundedBenchmarkProfile(
            profile_id="smoke",
            split_id=_primary_split_id(scenario),
            description=f"Smoke regression slice for {scenario.benchmark_id}.",
        ),
    ]


def _primary_split_id(scenario: GroundedBenchmarkScenario) -> str | None:
    """Choose a representative split id for default profiles."""
    if scenario.split_paths:
        first_split = Path(scenario.split_paths[0]).stem
        if first_split:
            return first_split
    return None


def _load_authority_manifest(path: Path) -> GroundedAuthorityPackManifest | None:
    if not path.exists():
        return None
    return _load_yaml_model(path, GroundedAuthorityPackManifest)


def _load_authority_pack_from_manifest(
    authority_root: Path,
    manifest: GroundedAuthorityPackManifest,
) -> GroundedAuthorityPack:
    workspace_root = authority_root.parent
    scenario = _load_yaml_model(
        authority_root / manifest.scenario_path, GroundedBenchmarkScenario
    )
    paper = _load_yaml_model(
        workspace_root / scenario.paper_metadata_path, GroundedPaperMetadata
    )
    label_map = _load_yaml_model(
        workspace_root / scenario.label_map_path, GroundedLabelMap
    )
    metrics = _load_yaml_model(
        workspace_root / scenario.metrics_path, GroundedMetricsConfig
    )
    baselines = _load_yaml_model(
        workspace_root / scenario.baselines_path, GroundedBaselines
    )
    operator = None
    operator_path = manifest.operator_path or scenario.operator_path
    if operator_path:
        operator = _load_yaml_model(
            workspace_root / operator_path, GroundedOperatorSpec
        )

    profiles = (
        list(scenario.benchmark_profiles)
        or list(manifest.benchmark_profiles)
        or [
            GroundedBenchmarkProfile(profile_id=manifest.canonical_profile_id),
            GroundedBenchmarkProfile(profile_id=manifest.operator_primary_profile_id),
            GroundedBenchmarkProfile(profile_id=manifest.smoke_profile_id),
        ]
    )

    return GroundedAuthorityPack(
        manifest=manifest,
        paper=paper,
        scenario=scenario,
        label_map=label_map,
        metrics=metrics,
        baselines=baselines,
        operator=operator,
        profiles=profiles,
        source_root=authority_root,
        raw_paths=list(manifest.raw_paths),
        notes=list(manifest.notes),
    )


def validate_grounded_authority_pack(
    authority_pack: GroundedAuthorityPack,
) -> GroundedAuthorityValidationResult:
    """Validate a grounded authority pack and collect any issues."""
    issues: list[GroundedAuthorityValidationIssue] = []
    manifest = authority_pack.manifest
    authority_root = authority_pack.source_root
    benchmark_id = manifest.benchmark_id

    for label, model in [
        ("paper", authority_pack.paper),
        ("scenario", authority_pack.scenario),
        ("label-map", authority_pack.label_map),
        ("metrics", authority_pack.metrics),
        ("baselines", authority_pack.baselines),
    ]:
        if getattr(model, "benchmark_id", benchmark_id) != benchmark_id:
            issues.append(
                GroundedAuthorityValidationIssue(
                    path=label,
                    message=f"{label} benchmark_id must match {benchmark_id}",
                )
            )
    if (
        authority_pack.operator is not None
        and authority_pack.operator.benchmark_id != benchmark_id
    ):
        issues.append(
            GroundedAuthorityValidationIssue(
                path="operator",
                message=f"operator benchmark_id must match {benchmark_id}",
            )
        )

    if manifest.canonical_profile_id == manifest.operator_primary_profile_id:
        issues.append(
            GroundedAuthorityValidationIssue(
                path="manifest",
                message="canonical and operator-primary profiles must differ",
            )
        )
    if manifest.canonical_profile_id == manifest.smoke_profile_id:
        issues.append(
            GroundedAuthorityValidationIssue(
                path="manifest",
                message="canonical and smoke profiles must differ",
            )
        )
    if manifest.operator_primary_profile_id == manifest.smoke_profile_id:
        issues.append(
            GroundedAuthorityValidationIssue(
                path="manifest",
                message="operator-primary and smoke profiles must differ",
            )
        )

    if authority_root is not None:
        for relative_path, label in [
            (manifest.paper_path, "paper"),
            (manifest.scenario_path, "scenario"),
            (manifest.label_map_path, "label-map"),
            (manifest.metrics_path, "metrics"),
            (manifest.baselines_path, "baselines"),
        ]:
            resolved = authority_root / relative_path
            if not resolved.exists():
                issues.append(
                    GroundedAuthorityValidationIssue(
                        path=str(resolved),
                        message=f"Missing required {label} file",
                    )
                )
        if (
            manifest.operator_path is not None
            and not (authority_root / manifest.operator_path).exists()
        ):
            issues.append(
                GroundedAuthorityValidationIssue(
                    path=str(authority_root / manifest.operator_path),
                    message="Missing operator file",
                )
            )
        for raw_path in manifest.raw_paths:
            if raw_path and not (authority_root / raw_path).exists():
                issues.append(
                    GroundedAuthorityValidationIssue(
                        path=str(authority_root / raw_path),
                        message="Missing raw source file",
                    )
                )
        workspace_root = authority_root.parent
        for relative_path, label in [
            (authority_pack.scenario.paper_metadata_path, "paper metadata"),
            (authority_pack.scenario.label_map_path, "label map"),
            (authority_pack.scenario.metrics_path, "metrics"),
            (authority_pack.scenario.baselines_path, "baselines"),
            (authority_pack.scenario.task_schema_path, "task schema"),
            (authority_pack.scenario.workflow_path, "workflow"),
            (authority_pack.scenario.operator_path, "operator"),
            (authority_pack.scenario.gold_labels_path, "gold labels"),
            (authority_pack.scenario.paper_gold_path, "paper gold"),
            (authority_pack.scenario.molabel_gold_path, "molabel gold"),
        ]:
            if relative_path and not (workspace_root / relative_path).exists():
                issues.append(
                    GroundedAuthorityValidationIssue(
                        path=str(workspace_root / relative_path),
                        message=f"Missing scenario {label} file",
                    )
                )
        for relative_path in (
            *authority_pack.scenario.split_paths,
            *authority_pack.scenario.human_label_paths,
            *authority_pack.scenario.review_paths,
        ):
            if relative_path and not (workspace_root / relative_path).exists():
                issues.append(
                    GroundedAuthorityValidationIssue(
                        path=str(workspace_root / relative_path),
                        message="Missing scenario artifact file",
                    )
                )

    if not authority_pack.profiles:
        issues.append(
            GroundedAuthorityValidationIssue(
                path="profiles",
                message="Authority pack should declare benchmark profiles",
            )
        )
    else:
        profile_ids = [profile.profile_id for profile in authority_pack.profiles]
        if len(profile_ids) != len(set(profile_ids)):
            issues.append(
                GroundedAuthorityValidationIssue(
                    path="profiles",
                    message="Authority pack profile ids must be unique",
                )
            )
        for required_profile in [
            manifest.canonical_profile_id,
            manifest.operator_primary_profile_id,
            manifest.smoke_profile_id,
        ]:
            if required_profile not in profile_ids:
                issues.append(
                    GroundedAuthorityValidationIssue(
                        path="profiles",
                        message=f"Missing required profile: {required_profile}",
                    )
                )

    return GroundedAuthorityValidationResult(
        benchmark_id=manifest.benchmark_id,
        is_valid=not any(issue.severity == "error" for issue in issues),
        issues=issues,
        profiles=list(authority_pack.profiles),
    )


def load_grounded_authority_pack(workspace_root: Path) -> GroundedAuthorityPack:
    """Load a canonical authority pack if available, or synthesize one."""
    authority_root = _authority_root_for(workspace_root)
    if authority_root is not None:
        manifest = _load_authority_manifest(authority_root / "manifest.yaml")
        if manifest is None:
            manifest = GroundedAuthorityPackManifest(
                benchmark_id=authority_root.parent.name,
            )
        return _load_authority_pack_from_manifest(authority_root, manifest)

    scenario = _load_yaml_model(
        workspace_root / "workbench" / "benchmarks" / "scenario.yaml",
        GroundedBenchmarkScenario,
    )
    paper = _load_yaml_model(
        workspace_root / scenario.paper_metadata_path,
        GroundedPaperMetadata,
    )
    label_map = _load_yaml_model(
        workspace_root / scenario.label_map_path,
        GroundedLabelMap,
    )
    metrics = _load_yaml_model(
        workspace_root / scenario.metrics_path,
        GroundedMetricsConfig,
    )
    baselines = _load_yaml_model(
        workspace_root / scenario.baselines_path,
        GroundedBaselines,
    )
    operator = None
    if scenario.operator_path:
        operator = _load_yaml_model(
            workspace_root / scenario.operator_path,
            GroundedOperatorSpec,
        )

    manifest = GroundedAuthorityPackManifest(
        benchmark_id=scenario.benchmark_id,
        layout="authority",
        benchmark_profiles=list(scenario.benchmark_profiles),
        source_path=str(workspace_root / "workbench" / "benchmarks"),
        reference_workspace_path=str(workspace_root),
        notes=list(scenario.redistribution_notes),
    )
    profiles = _default_profiles_from_scenario(scenario)
    return GroundedAuthorityPack(
        manifest=manifest,
        paper=paper,
        scenario=scenario,
        label_map=label_map,
        metrics=metrics,
        baselines=baselines,
        operator=operator,
        profiles=profiles,
        source_root=workspace_root,
        raw_paths=list(scenario.split_paths),
        notes=list(scenario.redistribution_notes),
    )


def write_run_outputs(
    summary: GroundedRunSummary,
    report_markdown: str,
    runs_root: Path,
    *,
    evidence: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    """Write a summary JSON and Markdown report for a run."""
    run_dir = runs_root / summary.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    summary_path = run_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )

    report_path = run_dir / "report.md"
    report_path.write_text(report_markdown, encoding="utf-8")

    if evidence:
        evidence_dir = run_dir / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        manifest_entries: list[dict[str, Any]] = []

        def _write_evidence_node(
            relative_path: str,
            payload: Any,
            *,
            content_type: str,
        ) -> None:
            target = evidence_dir / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            if content_type == "json":
                target.write_text(
                    json.dumps(payload, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
            elif content_type == "jsonl":
                rows = payload if isinstance(payload, list) else []
                target.write_text(
                    "\n".join(json.dumps(row, sort_keys=True) for row in rows)
                    + ("\n" if rows else ""),
                    encoding="utf-8",
                )
            elif content_type == "text":
                target.write_text(str(payload), encoding="utf-8")
            else:
                raise ValueError(f"Unsupported evidence content type: {content_type}")
            manifest_entries.append(
                {
                    "path": str(Path("evidence") / relative_path),
                    "content_type": content_type,
                }
            )

        for relative_path, payload in sorted(evidence.items()):
            if isinstance(payload, str):
                content_type = "text"
            elif relative_path.endswith(".jsonl"):
                content_type = "jsonl"
            else:
                content_type = "json"
            _write_evidence_node(relative_path, payload, content_type=content_type)

        manifest_path = run_dir / "evidence_manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "benchmark_id": summary.benchmark_id,
                    "run_id": summary.run_id,
                    "summary_version": summary.summary_version,
                    "artifacts": [
                        {
                            "path": "summary.json",
                            "content_type": "json",
                        },
                        {
                            "path": "report.md",
                            "content_type": "text/markdown",
                        },
                        *manifest_entries,
                    ],
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    return summary_path, report_path


def load_grounded_benchmark(workspace_root: Path) -> GroundedBenchmarkBundle:
    """Load a grounded benchmark workspace fixture or authority pack."""
    authority = load_grounded_authority_pack(workspace_root)
    return GroundedBenchmarkBundle(
        workspace_root=workspace_root,
        authority=authority,
        scenario=authority.scenario,
        paper=authority.paper,
        label_map=authority.label_map,
        metrics=authority.metrics,
        baselines=authority.baselines,
        operator=authority.operator,
    )


def _record_labels(
    rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {str(row["record_id"]): dict(row["labels"]) for row in rows}


def _default_stage_for_mode(
    mode: BenchmarkMode,
    variant: ScoringVariant,
) -> BenchmarkStage:
    if mode == "model" and variant == "paper_direct":
        return "paper_model"
    if mode == "model" and variant == "molabel_operated":
        return "molabel_model"
    if mode == "workflow":
        return "workflow_reviewed"
    return "operator_reviewed"


def _stage_matches_metric(
    metric: GroundedMetricDefinition,
    stage: BenchmarkStage | None,
    mode: BenchmarkMode,
    variant: ScoringVariant,
) -> bool:
    if metric.stages:
        if stage is None:
            return False
        return stage in metric.stages
    return mode in metric.modes and variant in metric.variants


def _tax_matches_summary(
    tax: GroundedTaxDefinition,
    summary: GroundedRunSummary,
) -> bool:
    if tax.minuend_stage is not None or tax.subtrahend_stage is not None:
        return (
            tax.minuend_stage == summary.stage
            and tax.minuend_variant == summary.variant
        ) or (
            tax.subtrahend_stage == summary.stage
            and tax.subtrahend_variant == summary.variant
        )
    return tax.minuend_mode == summary.mode and tax.minuend_variant == summary.variant


def _mode_for_stage(stage: BenchmarkStage) -> BenchmarkMode:
    if stage in {"paper_model", "molabel_model"}:
        return "model"
    if stage == "workflow_autorun" or stage == "workflow_reviewed":
        return "workflow"
    return "operator"


def _resolve_fields(
    metric: GroundedMetricDefinition,
    fallback_fields: list[str],
) -> list[str]:
    return metric.fields or fallback_fields


def _value_matches(expected: Any, actual: Any) -> bool:
    if isinstance(expected, (list, dict)):
        return canonical_label_value(expected) == canonical_label_value(actual)
    if isinstance(expected, bool):
        return actual is expected
    if isinstance(expected, (int, float)):
        return isinstance(actual, (int, float)) and (
            abs(float(expected) - float(actual)) < 0.01
        )
    return str(expected) == str(actual)


def _safe_ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _record_exact_match(
    gold_labels: dict[str, Any],
    predicted_labels: dict[str, Any],
) -> bool:
    return canonical_label_value(gold_labels) == canonical_label_value(predicted_labels)


def _select_label_fields(
    labels: dict[str, Any],
    evaluation_fields: list[str] | None,
) -> dict[str, Any]:
    if not evaluation_fields:
        return dict(labels)
    return {field: labels.get(field) for field in evaluation_fields}


def _index_label_rows(
    rows: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], Counter[str]]:
    by_record: dict[str, dict[str, Any]] = {}
    counts: Counter[str] = Counter()
    for row in rows:
        record_id = str(row["record_id"])
        counts[record_id] += 1
        by_record[record_id] = dict(row.get("labels") or {})
    return by_record, counts


def _scalar_confusion_key(value: Any) -> str:
    canonical = canonical_label_value(value)
    if canonical is None:
        return "<missing>"
    if canonical == "__null__":
        return "<missing>"
    return str(canonical)


def _metric_fields_for_stage(
    bundle: GroundedBenchmarkBundle,
    stage: BenchmarkStage,
    mode: BenchmarkMode,
    variant: ScoringVariant,
) -> list[str]:
    fields: set[str] = set(bundle.scenario.evaluation_fields)
    for metric in bundle.metrics.metrics:
        if not _stage_matches_metric(metric, stage, mode, variant):
            continue
        fields.update(_resolve_fields(metric, bundle.scenario.evaluation_fields))
    return sorted(field for field in fields if field)


def _build_coverage_diagnostics(
    *,
    gold_rows: list[dict[str, Any]],
    prediction_rows: list[dict[str, Any]],
    prediction_counts: Counter[str],
) -> dict[str, Any]:
    gold_ids = [str(row["record_id"]) for row in gold_rows]
    prediction_ids = [str(row["record_id"]) for row in prediction_rows]
    gold_set = set(gold_ids)
    prediction_set = set(prediction_ids)
    duplicate_ids = sorted(
        record_id for record_id, count in prediction_counts.items() if count > 1
    )
    duplicate_instances = sum(
        count - 1 for count in prediction_counts.values() if count > 1
    )
    missing_ids = sorted(gold_set - prediction_set)
    extra_ids = sorted(prediction_set - gold_set)
    return {
        "gold_record_count": len(gold_rows),
        "prediction_row_count": len(prediction_rows),
        "unique_prediction_record_count": len(prediction_set),
        "coverage_rate": _safe_ratio(len(prediction_set & gold_set), len(gold_set)),
        "missing_prediction_count": len(missing_ids),
        "extra_prediction_count": len(extra_ids),
        "duplicate_prediction_count": duplicate_instances,
        "duplicate_prediction_ids": duplicate_ids,
        "missing_prediction_ids": missing_ids,
        "extra_prediction_ids": extra_ids,
    }


def _build_field_accuracy(
    *,
    fields: list[str],
    gold: dict[str, dict[str, Any]],
    predictions: dict[str, dict[str, Any]],
    record_ids: list[str],
) -> dict[str, dict[str, Any]]:
    accuracy: dict[str, dict[str, Any]] = {}
    for field in fields:
        matched = 0
        total = 0
        for record_id in record_ids:
            gold_value = gold.get(record_id, {}).get(field)
            predicted_value = predictions.get(record_id, {}).get(field)
            total += 1
            if _value_matches(gold_value, predicted_value):
                matched += 1
        accuracy[field] = {
            "matched": matched,
            "total": total,
            "accuracy": _safe_ratio(matched, total),
        }
    return accuracy


def _build_confusion_matrices(
    *,
    fields: list[str],
    gold: dict[str, dict[str, Any]],
    predictions: dict[str, dict[str, Any]],
    record_ids: list[str],
) -> dict[str, Any]:
    confusion: dict[str, Any] = {}
    for field in fields:
        values = {
            _scalar_confusion_key(gold.get(record_id, {}).get(field))
            for record_id in record_ids
        }
        values.update(
            _scalar_confusion_key(predictions.get(record_id, {}).get(field))
            for record_id in record_ids
        )
        counts: Counter[tuple[str, str]] = Counter()
        top_confusions: list[dict[str, Any]] = []
        for record_id in record_ids:
            gold_value = _scalar_confusion_key(gold.get(record_id, {}).get(field))
            predicted_value = _scalar_confusion_key(
                predictions.get(record_id, {}).get(field)
            )
            counts[(gold_value, predicted_value)] += 1
        for (gold_value, predicted_value), count in counts.most_common():
            if gold_value == predicted_value:
                continue
            top_confusions.append(
                {"gold": gold_value, "predicted": predicted_value, "count": count}
            )
        confusion[field] = {
            "labels": sorted(values),
            "matrix": [
                {"gold": gold_value, "predicted": predicted_value, "count": count}
                for (gold_value, predicted_value), count in sorted(counts.items())
            ],
            "top_confusions": top_confusions[:10],
        }
    return confusion


def _subset_summary(
    *,
    subset_ids: list[str],
    fields: list[str],
    gold: dict[str, dict[str, Any]],
    predictions: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if not subset_ids:
        return {
            "count": 0,
            "exact_match_count": 0,
            "exact_match_rate": 0.0,
            "field_accuracy": {},
        }
    exact_match_count = sum(
        1
        for record_id in subset_ids
        if _record_exact_match(
            _select_label_fields(gold.get(record_id, {}), fields),
            _select_label_fields(predictions.get(record_id, {}), fields),
        )
    )
    return {
        "count": len(subset_ids),
        "exact_match_count": exact_match_count,
        "exact_match_rate": _safe_ratio(exact_match_count, len(subset_ids)),
        "field_accuracy": _build_field_accuracy(
            fields=fields,
            gold=gold,
            predictions=predictions,
            record_ids=subset_ids,
        ),
    }


def _build_subset_breakdowns(
    *,
    gold_rows: list[dict[str, Any]],
    gold: dict[str, dict[str, Any]],
    predictions: dict[str, dict[str, Any]],
    fields: list[str],
    context_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    subsets: dict[str, dict[str, Any]] = {}
    record_ids = [str(row["record_id"]) for row in gold_rows]

    for field in fields:
        by_value: dict[str, list[str]] = defaultdict(list)
        for record_id in record_ids:
            key = _scalar_confusion_key(gold.get(record_id, {}).get(field))
            by_value[key].append(record_id)
        subsets[f"gold.{field}"] = {
            value: _subset_summary(
                subset_ids=sorted(ids),
                fields=fields,
                gold=gold,
                predictions=predictions,
            )
            for value, ids in sorted(by_value.items())
        }

    if context_rows:
        context_map = {
            str(row["record_id"]): row
            for row in context_rows
            if row.get("record_id") is not None
        }
        for context_field in ("source_split",):
            by_value: dict[str, list[str]] = defaultdict(list)
            for record_id in record_ids:
                raw_value = context_map.get(record_id, {}).get(context_field)
                if raw_value is None:
                    continue
                by_value[str(raw_value)].append(record_id)
            if by_value:
                subsets[f"context.{context_field}"] = {
                    value: _subset_summary(
                        subset_ids=sorted(ids),
                        fields=fields,
                        gold=gold,
                        predictions=predictions,
                    )
                    for value, ids in sorted(by_value.items())
                }

    return subsets


def _build_stage_diagnostics(
    *,
    gold_rows: list[dict[str, Any]],
    prediction_rows: list[dict[str, Any]],
    fields: list[str],
    context_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    gold, _ = _index_label_rows(gold_rows)
    predictions, prediction_counts = _index_label_rows(prediction_rows)
    record_ids = sorted(gold)
    exact_match_count = sum(
        1
        for record_id in record_ids
        if _record_exact_match(
            _select_label_fields(gold.get(record_id, {}), fields),
            _select_label_fields(predictions.get(record_id, {}), fields),
        )
    )
    field_accuracy = _build_field_accuracy(
        fields=fields,
        gold=gold,
        predictions=predictions,
        record_ids=record_ids,
    )
    return {
        "coverage": _build_coverage_diagnostics(
            gold_rows=gold_rows,
            prediction_rows=prediction_rows,
            prediction_counts=prediction_counts,
        ),
        "exact_match_count": exact_match_count,
        "exact_match_rate": _safe_ratio(exact_match_count, len(record_ids)),
        "field_accuracy": field_accuracy,
        "confusion": _build_confusion_matrices(
            fields=fields,
            gold=gold,
            predictions=predictions,
            record_ids=record_ids,
        ),
        "subset_breakdowns": _build_subset_breakdowns(
            gold_rows=gold_rows,
            gold=gold,
            predictions=predictions,
            fields=fields,
            context_rows=context_rows,
        ),
    }


def _metric_map(summary: GroundedRunSummary) -> dict[str, float]:
    return {metric.metric_id: metric.value for metric in summary.metrics}


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _stddev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = _mean(values)
    variance = sum((value - avg) ** 2 for value in values) / len(values)
    return math.sqrt(variance)


def _extract_confidence(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
    elif isinstance(value, str):
        text = value.strip().rstrip("%")
        if not text:
            return None
        try:
            numeric = float(text)
        except ValueError:
            return None
        if value.strip().endswith("%"):
            numeric = numeric / 100.0
    else:
        return None
    if numeric > 1.0 and numeric <= 100.0:
        numeric = numeric / 100.0
    if 0.0 <= numeric <= 1.0:
        return numeric
    return None


def _proposal_confidence_for_row(row: dict[str, Any]) -> float | None:
    labels = row.get("labels") or {}
    raw_response = row.get("raw_response") or {}
    candidate_keys = (
        "confidence",
        "score",
        "probability",
        "intent_confidence",
    )
    for container in (raw_response, labels):
        if not isinstance(container, dict):
            continue
        for key in candidate_keys:
            confidence = _extract_confidence(container.get(key))
            if confidence is not None:
                return confidence
    return None


def _score_accuracy(
    predictions: dict[str, dict[str, Any]],
    gold: dict[str, dict[str, Any]],
    fields: list[str],
) -> GroundedMetricResult:
    matches = 0
    total = 0
    for record_id, gold_labels in gold.items():
        predicted = predictions.get(record_id, {})
        for field in fields:
            total += 1
            if _value_matches(gold_labels.get(field), predicted.get(field)):
                matches += 1
    return GroundedMetricResult(
        metric_id="",
        name="",
        metric_type="accuracy",
        value=_safe_ratio(matches, total),
        fields=fields,
        details={"matched_fields": matches, "total_fields": total},
    )


def _score_exact_match(
    predictions: dict[str, dict[str, Any]],
    gold: dict[str, dict[str, Any]],
    fields: list[str],
) -> GroundedMetricResult:
    matches = 0
    total = len(gold)
    for record_id, gold_labels in gold.items():
        predicted = predictions.get(record_id, {})
        if all(
            _value_matches(gold_labels.get(field), predicted.get(field))
            for field in fields
        ):
            matches += 1
    return GroundedMetricResult(
        metric_id="",
        name="",
        metric_type="exact_match",
        value=_safe_ratio(matches, total),
        fields=fields,
        details={"matched_records": matches, "total_records": total},
    )


def _score_macro_f1(
    predictions: dict[str, dict[str, Any]],
    gold: dict[str, dict[str, Any]],
    field: str,
) -> GroundedMetricResult:
    labels = {canonical_label_value(labels.get(field)) for labels in gold.values()}
    labels.update(
        canonical_label_value(labels.get(field))
        for labels in predictions.values()
        if field in labels
    )
    label_scores: dict[str, float] = {}
    for label in sorted(labels):
        tp = 0
        fp = 0
        fn = 0
        for record_id, gold_labels in gold.items():
            gold_value = canonical_label_value(gold_labels.get(field))
            pred_value = canonical_label_value(
                predictions.get(record_id, {}).get(field)
            )
            if pred_value == label and gold_value == label:
                tp += 1
            elif pred_value == label and gold_value != label:
                fp += 1
            elif pred_value != label and gold_value == label:
                fn += 1
        precision = _safe_ratio(tp, tp + fp)
        recall = _safe_ratio(tp, tp + fn)
        label_scores[label] = _safe_ratio(2 * precision * recall, precision + recall)

    macro_f1 = _safe_ratio(sum(label_scores.values()), len(label_scores))
    return GroundedMetricResult(
        metric_id="",
        name="",
        metric_type="macro_f1",
        value=macro_f1,
        fields=[field],
        details={"per_label_f1": label_scores},
    )


def _score_binary_recall(
    predictions: dict[str, dict[str, Any]],
    gold: dict[str, dict[str, Any]],
    field: str,
    positive_value: Any,
) -> GroundedMetricResult:
    true_positive = 0
    false_negative = 0

    for record_id, gold_labels in gold.items():
        gold_value = gold_labels.get(field)
        predicted_value = predictions.get(record_id, {}).get(field)
        if _value_matches(gold_value, positive_value):
            if _value_matches(predicted_value, positive_value):
                true_positive += 1
            else:
                false_negative += 1

    recall = _safe_ratio(true_positive, true_positive + false_negative)
    return GroundedMetricResult(
        metric_id="",
        name="",
        metric_type="binary_recall",
        value=recall,
        fields=[field],
        details={
            "true_positive": true_positive,
            "false_negative": false_negative,
            "positive_value": positive_value,
        },
    )


def _coerce_set(value: Any) -> set[str]:
    artifact = normalize_label_set_artifact(value)
    return set(artifact.labels)


def _score_abstain_metric(
    predictions: dict[str, dict[str, Any]],
    gold: dict[str, dict[str, Any]],
    field: str,
    *,
    metric_type: Literal["abstain_precision", "abstain_recall"],
    metric_options: dict[str, Any],
) -> GroundedMetricResult:
    abstain_values = metric_options.get("abstain_values") or []
    confidence_field = str(metric_options.get("confidence_field", "confidence"))
    abstain_field = metric_options.get("abstain_field")
    review_route_field = metric_options.get("review_route_field")
    gold_abstain_field = metric_options.get("abstain_gold_field")

    true_positive = 0
    predicted_positive = 0
    gold_positive = 0
    for record_id, gold_labels in gold.items():
        prediction_artifact = normalize_classification_artifact(
            predictions.get(record_id, {}),
            label_field=field,
            confidence_field=confidence_field,
            abstain_field=(None if abstain_field is None else str(abstain_field)),
            review_route_field=(
                None if review_route_field is None else str(review_route_field)
            ),
            abstain_values=abstain_values,
        )
        gold_should_abstain = (
            bool(gold_labels.get(gold_abstain_field)) if gold_abstain_field else False
        )
        gold_positive += int(gold_should_abstain)
        predicted_positive += int(prediction_artifact.abstained)
        true_positive += int(gold_should_abstain and prediction_artifact.abstained)
    value = (
        _safe_ratio(true_positive, predicted_positive)
        if metric_type == "abstain_precision"
        else _safe_ratio(true_positive, gold_positive)
    )
    return GroundedMetricResult(
        metric_id="",
        name="",
        metric_type=metric_type,
        value=value,
        fields=[field],
        details={
            "true_positive": true_positive,
            "predicted_positive": predicted_positive,
            "gold_positive": gold_positive,
        },
    )


def _score_micro_f1_metric(
    predictions: dict[str, dict[str, Any]],
    gold: dict[str, dict[str, Any]],
    field: str,
    *,
    metric_options: dict[str, Any],
) -> GroundedMetricResult:
    hierarchy = {
        str(child): [str(parent) for parent in parents]
        for child, parents in dict(metric_options.get("hierarchy", {}) or {}).items()
    }
    thresholds = [
        float(value)
        for value in metric_options.get("thresholds", [])
        if isinstance(value, (int, float))
    ]
    threshold = float(metric_options.get("threshold", 0.5))
    predicted_artifacts = {
        record_id: normalize_label_set_artifact(labels.get(field))
        for record_id, labels in predictions.items()
    }
    gold_artifacts = {
        record_id: normalize_label_set_artifact(labels.get(field))
        for record_id, labels in gold.items()
    }
    if any(artifact.scores for artifact in predicted_artifacts.values()):
        for artifact in predicted_artifacts.values():
            if artifact.scores:
                artifact.labels = threshold_label_scores(
                    artifact.scores,
                    threshold=threshold,
                    hierarchy=hierarchy or None,
                )
    score = score_multilabel_micro_f1(
        predictions=predicted_artifacts,
        gold=gold_artifacts,
    )
    details = dict(score["details"])
    if thresholds:
        details["threshold_sweep"] = sweep_label_thresholds(
            gold_artifacts=gold_artifacts,
            predicted_artifacts=predicted_artifacts,
            thresholds=thresholds,
            hierarchy=hierarchy or None,
        )
        if details["threshold_sweep"]:
            best = max(details["threshold_sweep"], key=lambda item: item["micro_f1"])
            details["best_threshold"] = best["threshold"]
            details["best_threshold_micro_f1"] = best["micro_f1"]
    if metric_options.get("vocabulary") or hierarchy:
        validations = [
            validate_label_set_artifact(
                artifact,
                vocabulary=metric_options.get("vocabulary"),
                hierarchy=hierarchy or None,
            ).model_dump(mode="json")
            for artifact in predicted_artifacts.values()
        ]
        details["validation"] = {
            "issue_count": sum(len(result["issues"]) for result in validations),
            "results": validations,
        }
    return GroundedMetricResult(
        metric_id="",
        name="",
        metric_type="micro_f1",
        value=float(score["value"]),
        fields=[field],
        details=details,
    )


def _score_evidence_metric(
    predictions: dict[str, dict[str, Any]],
    gold: dict[str, dict[str, Any]],
    fields: list[str],
    *,
    metric_type: Literal[
        "evidence_group_precision",
        "evidence_group_recall",
        "evidence_group_f1",
        "evidence_group_exact_match",
        "joint_evidence_decision",
    ],
    metric_options: dict[str, Any],
) -> GroundedMetricResult:
    evidence_field = fields[0]
    decision_field = (
        fields[1]
        if len(fields) > 1
        else str(metric_options.get("decision_field", "decision"))
    )
    per_record: dict[str, Any] = {}
    total = 0.0
    for record_id, gold_labels in gold.items():
        prediction_annotation = normalize_evidence_annotation(
            predictions.get(record_id, {}).get(evidence_field)
            or {
                "decision": predictions.get(record_id, {}).get(decision_field),
                "evidence_groups": predictions.get(record_id, {}).get(evidence_field),
            }
        )
        gold_annotation = normalize_evidence_annotation(
            gold_labels.get(evidence_field)
            or {
                "decision": gold_labels.get(decision_field),
                "evidence_groups": gold_labels.get(evidence_field),
            }
        )
        if prediction_annotation.decision is None:
            prediction_annotation.decision = (
                None
                if predictions.get(record_id, {}).get(decision_field) is None
                else str(predictions.get(record_id, {}).get(decision_field))
            )
        if gold_annotation.decision is None:
            gold_annotation.decision = (
                None
                if gold_labels.get(decision_field) is None
                else str(gold_labels.get(decision_field))
            )
        evidence_score = score_grouped_evidence(
            prediction=prediction_annotation,
            gold=gold_annotation,
        )
        if metric_type == "evidence_group_precision":
            record_value = evidence_score["precision"]
        elif metric_type == "evidence_group_recall":
            record_value = evidence_score["recall"]
        elif metric_type == "evidence_group_f1":
            record_value = evidence_score["f1"]
        elif metric_type == "evidence_group_exact_match":
            record_value = evidence_score["exact_match"]
        else:
            decision_ok = float(
                normalize_answer_text(prediction_annotation.decision)
                == normalize_answer_text(gold_annotation.decision)
            )
            record_value = decision_ok * evidence_score["completeness"]
            evidence_score["decision_exact_match"] = decision_ok
        per_record[record_id] = {
            **evidence_score,
            "validation": validate_evidence_annotation(
                prediction_annotation
            ).model_dump(mode="json"),
        }
        total += record_value
    return GroundedMetricResult(
        metric_id="",
        name="",
        metric_type=metric_type,
        value=_safe_ratio(total, len(gold)),
        fields=fields,
        details={"per_record": per_record},
    )


def _score_qa_metric(
    predictions: dict[str, dict[str, Any]],
    gold: dict[str, dict[str, Any]],
    field: str,
    *,
    metric_type: Literal[
        "answer_exact_match",
        "answer_token_f1",
        "supporting_fact_exact_match",
        "supporting_fact_f1",
        "joint_answer_support",
        "anls",
    ],
    metric_options: dict[str, Any],
) -> GroundedMetricResult:
    per_record: dict[str, Any] = {}
    total = 0.0
    joint_mode = str(metric_options.get("joint_mode", "f1"))
    for record_id, gold_labels in gold.items():
        predicted_value = predictions.get(record_id, {}).get(field)
        gold_value = gold_labels.get(field)
        qa_score = score_qa_with_evidence(predicted_value, gold_value)
        if metric_type == "answer_exact_match":
            record_value = qa_score["answer_exact_match"]
        elif metric_type == "answer_token_f1":
            record_value = qa_score["answer_token_f1"]
        elif metric_type == "supporting_fact_exact_match":
            record_value = qa_score["supporting_fact_exact_match"]
        elif metric_type == "supporting_fact_f1":
            record_value = qa_score["supporting_fact_f1"]
        elif metric_type == "anls":
            predicted_artifact = normalize_qa_with_evidence_artifact(predicted_value)
            gold_artifact = normalize_qa_with_evidence_artifact(gold_value)
            answers = gold_artifact.acceptable_answers or [gold_artifact.answer or ""]
            record_value = max(
                score_anls(predicted_artifact.answer or "", answer)
                for answer in answers
            )
        else:
            record_value = (
                qa_score["joint_exact_match"]
                if joint_mode == "exact"
                else qa_score["joint_f1"]
            )
        per_record[record_id] = qa_score
        total += record_value
    return GroundedMetricResult(
        metric_id="",
        name="",
        metric_type=metric_type,
        value=_safe_ratio(total, len(gold)),
        fields=[field],
        details={"per_record": per_record, "joint_mode": joint_mode},
    )


def _score_ranking_metric(
    predictions: dict[str, dict[str, Any]],
    gold: dict[str, dict[str, Any]],
    field: str,
    *,
    metric_type: Literal["mrr", "ndcg_at_k", "recall_at_k", "precision_at_k", "map"],
    metric_options: dict[str, Any],
) -> GroundedMetricResult:
    qrels_field = str(metric_options.get("qrels_field", "qrels"))
    cutoff = metric_options.get("k")
    cutoff_value = int(cutoff) if cutoff is not None else None
    per_record: dict[str, Any] = {}
    total = 0.0
    validation_results: dict[str, Any] = {}
    missing_qrels_count = 0
    for record_id, gold_labels in gold.items():
        prediction_artifact = normalize_ranking_artifact(
            predictions.get(record_id, {}).get(field)
        )
        qrels = ingest_qrels(gold_labels.get(qrels_field, gold_labels.get(field)))
        if not qrels.qrels:
            missing_qrels_count += 1
            per_record[record_id] = {"value": 0.0, "missing_qrels": True}
            validation_results[record_id] = validate_grounded_ranking_artifact(
                prediction_artifact,
                fixed_depth=metric_options.get("fixed_depth"),
                require_corpus_metadata=bool(
                    metric_options.get("require_corpus_metadata")
                ),
            ).model_dump(mode="json")
            continue
        record_score = score_ranking(
            prediction=prediction_artifact,
            qrels=qrels,
            metric_type=metric_type,
            k=cutoff_value,
        )
        validation_results[record_id] = validate_grounded_ranking_artifact(
            prediction_artifact,
            fixed_depth=metric_options.get("fixed_depth"),
            require_corpus_metadata=bool(metric_options.get("require_corpus_metadata")),
        ).model_dump(mode="json")
        per_record[record_id] = record_score
        total += float(record_score["value"])
    return GroundedMetricResult(
        metric_id="",
        name="",
        metric_type=metric_type,
        value=_safe_ratio(total, len(gold)),
        fields=[field],
        details={
            "per_record": per_record,
            "validation": validation_results,
            "missing_qrels_count": missing_qrels_count,
            "cutoff": cutoff_value,
        },
    )


def _score_span_metric(
    predictions: dict[str, dict[str, Any]],
    gold: dict[str, dict[str, Any]],
    field: str,
    *,
    metric_type: Literal["span_exact_match", "span_overlap_f1"],
) -> GroundedMetricResult:
    per_record: dict[str, Any] = {}
    total = 0.0
    for record_id, gold_labels in gold.items():
        predicted_value = predictions.get(record_id, {}).get(field)
        gold_value = gold_labels.get(field)
        validation = validate_span_annotation(predicted_value).model_dump(mode="json")
        record_value = (
            score_span_exact_match(predicted_value, gold_value)
            if metric_type == "span_exact_match"
            else score_span_overlap_f1(predicted_value, gold_value)
        )
        per_record[record_id] = {"value": record_value, "validation": validation}
        total += record_value
    return GroundedMetricResult(
        metric_id="",
        name="",
        metric_type=metric_type,
        value=_safe_ratio(total, len(gold)),
        fields=[field],
        details={"per_record": per_record},
    )


def _score_grounded_generation_metric(
    predictions: dict[str, dict[str, Any]],
    gold: dict[str, dict[str, Any]],
    field: str,
    *,
    metric_type: Literal[
        "source_coverage",
        "unsupported_content_rate",
        "grounded_generation_score",
    ],
    metric_options: dict[str, Any],
) -> GroundedMetricResult:
    required_fields = metric_options.get("required_fields") or []
    per_record: dict[str, Any] = {}
    total = 0.0
    for record_id, gold_labels in gold.items():
        generation_score = score_grounded_generation(
            predictions.get(record_id, {}).get(field),
            gold_labels.get(field),
            required_fields=required_fields,
        )
        record_value = (
            generation_score["source_coverage"]
            if metric_type == "source_coverage"
            else generation_score["unsupported_content_rate"]
            if metric_type == "unsupported_content_rate"
            else generation_score["grounded_generation_score"]
        )
        per_record[record_id] = generation_score
        total += record_value
    return GroundedMetricResult(
        metric_id="",
        name="",
        metric_type=metric_type,
        value=_safe_ratio(total, len(gold)),
        fields=[field],
        details={"per_record": per_record},
    )


def _score_set_metric(
    predictions: dict[str, dict[str, Any]],
    gold: dict[str, dict[str, Any]],
    field: str,
    metric_type: Literal["set_precision", "set_recall", "set_f1"],
) -> GroundedMetricResult:
    overlap_total = 0
    predicted_total = 0
    gold_total = 0
    parser_failure_count = 0
    valid_empty_count = 0

    for record_id, gold_labels in gold.items():
        gold_artifact = normalize_label_set_artifact(gold_labels.get(field))
        predicted_artifact = normalize_label_set_artifact(
            predictions.get(record_id, {}).get(field)
        )
        gold_set = set(gold_artifact.labels)
        predicted_set = set(predicted_artifact.labels)
        overlap_total += len(gold_set & predicted_set)
        predicted_total += len(predicted_set)
        gold_total += len(gold_set)
        if predicted_artifact.parser_failed:
            parser_failure_count += 1
        elif not predicted_set:
            valid_empty_count += 1

    precision = _safe_ratio(overlap_total, predicted_total)
    recall = _safe_ratio(overlap_total, gold_total)
    if metric_type == "set_precision":
        value = precision
    elif metric_type == "set_recall":
        value = recall
    else:
        value = _safe_ratio(2 * precision * recall, precision + recall)

    return GroundedMetricResult(
        metric_id="",
        name="",
        metric_type=metric_type,
        value=value,
        fields=[field],
        details={
            "overlap_total": overlap_total,
            "predicted_total": predicted_total,
            "gold_total": gold_total,
            "precision": precision,
            "recall": recall,
            "parser_failure_count": parser_failure_count,
            "valid_empty_count": valid_empty_count,
        },
    )


def _score_jaccard(
    predictions: dict[str, dict[str, Any]],
    gold: dict[str, dict[str, Any]],
    field: str,
) -> GroundedMetricResult:
    total = 0.0
    count = 0
    per_record: dict[str, float] = {}
    parser_failure_count = 0
    valid_empty_count = 0

    for record_id, gold_labels in gold.items():
        gold_artifact = normalize_label_set_artifact(gold_labels.get(field))
        predicted_artifact = normalize_label_set_artifact(
            predictions.get(record_id, {}).get(field)
        )
        gold_set = set(gold_artifact.labels)
        predicted_set = set(predicted_artifact.labels)
        union = gold_set | predicted_set
        score = _safe_ratio(len(gold_set & predicted_set), len(union))
        per_record[record_id] = score
        total += score
        count += 1
        if predicted_artifact.parser_failed:
            parser_failure_count += 1
        elif not predicted_set:
            valid_empty_count += 1

    return GroundedMetricResult(
        metric_id="",
        name="",
        metric_type="jaccard",
        value=_safe_ratio(total, count),
        fields=[field],
        details={
            "per_record": per_record,
            "parser_failure_count": parser_failure_count,
            "valid_empty_count": valid_empty_count,
        },
    )


def _mask_positions(value: Any) -> set[int]:
    if value is None:
        return set()
    if isinstance(value, list):
        if all(isinstance(item, bool) or item in {0, 1} for item in value):
            return {index for index, item in enumerate(value) if bool(item)}
        return {int(item) for item in value}
    return {int(value)}


def _score_token_mask_f1(
    predictions: dict[str, dict[str, Any]],
    gold: dict[str, dict[str, Any]],
    field: str,
) -> GroundedMetricResult:
    total = 0.0
    count = 0
    per_record: dict[str, float] = {}

    for record_id, gold_labels in gold.items():
        gold_positions = _mask_positions(gold_labels.get(field))
        predicted_positions = _mask_positions(predictions.get(record_id, {}).get(field))
        overlap = len(gold_positions & predicted_positions)
        precision = _safe_ratio(overlap, len(predicted_positions))
        recall = _safe_ratio(overlap, len(gold_positions))
        score = _safe_ratio(2 * precision * recall, precision + recall)
        per_record[record_id] = score
        total += score
        count += 1

    return GroundedMetricResult(
        metric_id="",
        name="",
        metric_type="token_mask_f1",
        value=_safe_ratio(total, count),
        fields=[field],
        details={"per_record": per_record},
    )


def _normalize_feverous_verdict(value: Any) -> str:
    """Normalize verification verdicts into the canonical supports/refutes/nei set.

    Accepts the FEVER/FEVEROUS-native vocabulary plus a small set of aliases
    used by sibling verification benchmarks (e.g. SciFact uses
    SUPPORT/CONTRADICT/NOT_ENOUGH_INFO, which are semantically identical).
    Unknown values are returned unchanged (lowercased) so malformed outputs
    remain visibly wrong during scoring.
    """
    normalized = str(value).strip().lower()
    aliases = {
        "supports": "supports",
        "supported": "supports",
        "support": "supports",
        "refutes": "refutes",
        "refuted": "refutes",
        "refute": "refutes",
        "contradict": "refutes",
        "contradicts": "refutes",
        "contradicted": "refutes",
        "nei": "nei",
        "not enough info": "nei",
        "not_enough_info": "nei",
        "notenoughinfo": "nei",
    }
    return aliases.get(normalized, normalized)


def _truncate_feverous_predictions(predicted_atoms: list[str]) -> list[str]:
    """Apply the official FEVEROUS prediction truncation heuristics."""
    sentence_atoms = [atom for atom in predicted_atoms if "_sentence_" in atom]
    cell_atoms = [atom for atom in predicted_atoms if "_cell_" in atom]
    other_atoms = [
        atom
        for atom in predicted_atoms
        if "_sentence_" not in atom and "_cell_" not in atom
    ]
    truncated = sentence_atoms[:5] + cell_atoms[:25] + other_atoms
    return list(dict.fromkeys(truncated))


def _score_feverous_paper_direct(
    gold_rows: list[dict[str, Any]],
    predictions: dict[str, dict[str, Any]],
) -> GroundedMetricResult:
    matches = 0
    total = len(gold_rows)
    per_record: dict[str, bool] = {}

    for row in gold_rows:
        record_id = str(row["record_id"])
        labels = row["labels"]
        gold_verdict = _normalize_feverous_verdict(labels["paper_label"])
        gold_sets = labels["paper_evidence_sets"]
        predicted = predictions.get(record_id, {})
        predicted_verdict = _normalize_feverous_verdict(predicted.get("verdict", ""))
        predicted_atoms = set(
            _truncate_feverous_predictions(
                [str(item) for item in predicted.get("evidence_atoms", [])]
            )
        )

        verdict_ok = predicted_verdict == gold_verdict
        evidence_ok = gold_verdict == "nei" or any(
            set(str(item) for item in gold_set).issubset(predicted_atoms)
            for gold_set in gold_sets
        )
        record_ok = verdict_ok and evidence_ok
        per_record[record_id] = record_ok
        matches += int(record_ok)

    return GroundedMetricResult(
        metric_id="",
        name="",
        metric_type="feverous_score",
        value=_safe_ratio(matches, total),
        fields=["verdict", "evidence_sets"],
        details={
            "matched_records": matches,
            "total_records": total,
            "per_record": per_record,
        },
    )


def _metric_family_summaries(
    metric_results: list[GroundedMetricResult],
) -> dict[str, dict[str, float]]:
    """Group metrics into reusable report sections."""

    grouped: dict[str, dict[str, float]] = {
        "classification": {},
        "evidence": {},
        "qa_with_evidence": {},
        "retrieval": {},
        "spans": {},
        "grounded_generation": {},
        "document_grounding": {},
    }
    for metric in metric_results:
        if metric.metric_type in {
            "abstain_precision",
            "abstain_recall",
            "accuracy",
            "binary_recall",
            "macro_f1",
            "micro_f1",
        }:
            grouped["classification"][metric.metric_id] = metric.value
        elif metric.metric_type in {
            "evidence_group_precision",
            "evidence_group_recall",
            "evidence_group_f1",
            "evidence_group_exact_match",
            "joint_evidence_decision",
            "feverous_score",
        }:
            grouped["evidence"][metric.metric_id] = metric.value
        elif metric.metric_type in {
            "answer_exact_match",
            "answer_token_f1",
            "supporting_fact_exact_match",
            "supporting_fact_f1",
            "joint_answer_support",
        }:
            grouped["qa_with_evidence"][metric.metric_id] = metric.value
        elif metric.metric_type in {
            "mrr",
            "ndcg_at_k",
            "recall_at_k",
            "precision_at_k",
            "map",
        }:
            grouped["retrieval"][metric.metric_id] = metric.value
        elif metric.metric_type in {"span_exact_match", "span_overlap_f1"}:
            grouped["spans"][metric.metric_id] = metric.value
        elif metric.metric_type in {
            "source_coverage",
            "unsupported_content_rate",
            "grounded_generation_score",
        }:
            grouped["grounded_generation"][metric.metric_id] = metric.value
        elif metric.metric_type == "anls":
            grouped["document_grounding"][metric.metric_id] = metric.value
    return {key: value for key, value in grouped.items() if value}


def _classification_metric_options(
    metrics: list[GroundedMetricDefinition],
) -> dict[str, Any] | None:
    for metric in metrics:
        options = dict(metric.metric_options or {})
        config = options.get("classification_diagnostics")
        if isinstance(config, dict):
            return dict(config)
    return None


def score_grounded_stage(
    *,
    bundle: GroundedBenchmarkBundle,
    predictions: list[dict[str, Any]],
    gold_rows: list[dict[str, Any]],
    run_id: str,
    stage: BenchmarkStage,
    variant: ScoringVariant,
    mode: BenchmarkMode | None = None,
    context_rows: list[dict[str, Any]] | None = None,
) -> GroundedRunSummary:
    """Score predictions against a grounded benchmark's configured metrics."""
    score_mode = mode or _mode_for_stage(stage)
    gold = _record_labels(gold_rows)
    predicted, _ = _index_label_rows(predictions)

    metric_results: list[GroundedMetricResult] = []
    weighted_total = 0.0
    weight_sum = 0.0

    for metric in bundle.metrics.metrics:
        if not _stage_matches_metric(metric, stage, score_mode, variant):
            continue

        fields = _resolve_fields(metric, bundle.scenario.evaluation_fields)
        if metric.metric_type == "accuracy":
            result = _score_accuracy(predicted, gold, fields)
        elif metric.metric_type in {"abstain_precision", "abstain_recall"}:
            if len(fields) != 1:
                raise ValueError(
                    f"{metric.metric_type} metrics must declare exactly one field"
                )
            result = _score_abstain_metric(
                predicted,
                gold,
                fields[0],
                metric_type=metric.metric_type,
                metric_options=metric.metric_options,
            )
        elif metric.metric_type == "binary_recall":
            if len(fields) != 1:
                raise ValueError("binary_recall metrics must declare exactly one field")
            result = _score_binary_recall(
                predicted,
                gold,
                fields[0],
                metric.positive_value,
            )
        elif metric.metric_type == "exact_match":
            result = _score_exact_match(predicted, gold, fields)
        elif metric.metric_type == "macro_f1":
            if len(fields) != 1:
                raise ValueError("macro_f1 metrics must declare exactly one field")
            result = _score_macro_f1(predicted, gold, fields[0])
        elif metric.metric_type == "micro_f1":
            if len(fields) != 1:
                raise ValueError("micro_f1 metrics must declare exactly one field")
            result = _score_micro_f1_metric(
                predicted,
                gold,
                fields[0],
                metric_options=metric.metric_options,
            )
        elif metric.metric_type == "feverous_score":
            result = _score_feverous_paper_direct(gold_rows, predicted)
        elif metric.metric_type == "jaccard":
            if len(fields) != 1:
                raise ValueError("jaccard metrics must declare exactly one field")
            result = _score_jaccard(predicted, gold, fields[0])
        elif metric.metric_type in {"set_precision", "set_recall", "set_f1"}:
            if len(fields) != 1:
                raise ValueError("set metrics must declare exactly one field")
            result = _score_set_metric(predicted, gold, fields[0], metric.metric_type)
        elif metric.metric_type == "token_mask_f1":
            if len(fields) != 1:
                raise ValueError("token_mask_f1 metrics must declare exactly one field")
            result = _score_token_mask_f1(predicted, gold, fields[0])
        elif metric.metric_type in {
            "evidence_group_precision",
            "evidence_group_recall",
            "evidence_group_f1",
            "evidence_group_exact_match",
            "joint_evidence_decision",
        }:
            result = _score_evidence_metric(
                predicted,
                gold,
                fields,
                metric_type=metric.metric_type,
                metric_options=metric.metric_options,
            )
        elif metric.metric_type in {
            "answer_exact_match",
            "answer_token_f1",
            "supporting_fact_exact_match",
            "supporting_fact_f1",
            "joint_answer_support",
            "anls",
        }:
            if len(fields) != 1:
                raise ValueError(
                    f"{metric.metric_type} metrics must declare exactly one field"
                )
            result = _score_qa_metric(
                predicted,
                gold,
                fields[0],
                metric_type=metric.metric_type,
                metric_options=metric.metric_options,
            )
        elif metric.metric_type in {
            "mrr",
            "ndcg_at_k",
            "recall_at_k",
            "precision_at_k",
            "map",
        }:
            if len(fields) != 1:
                raise ValueError(
                    f"{metric.metric_type} metrics must declare exactly one field"
                )
            result = _score_ranking_metric(
                predicted,
                gold,
                fields[0],
                metric_type=metric.metric_type,
                metric_options=metric.metric_options,
            )
        elif metric.metric_type in {"span_exact_match", "span_overlap_f1"}:
            if len(fields) != 1:
                raise ValueError(
                    f"{metric.metric_type} metrics must declare exactly one field"
                )
            result = _score_span_metric(
                predicted,
                gold,
                fields[0],
                metric_type=metric.metric_type,
            )
        elif metric.metric_type in {
            "source_coverage",
            "unsupported_content_rate",
            "grounded_generation_score",
        }:
            if len(fields) != 1:
                raise ValueError(
                    f"{metric.metric_type} metrics must declare exactly one field"
                )
            result = _score_grounded_generation_metric(
                predicted,
                gold,
                fields[0],
                metric_type=metric.metric_type,
                metric_options=metric.metric_options,
            )
        else:
            raise ValueError(f"Unsupported grounded metric type: {metric.metric_type}")

        metric_results.append(
            result.model_copy(
                update={
                    "metric_id": metric.metric_id,
                    "name": metric.name,
                    "weight": metric.weight,
                }
            )
        )
        weighted_total += result.value * metric.weight
        weight_sum += metric.weight

    overall_score = _safe_ratio(weighted_total, weight_sum)
    diagnostic_fields = _metric_fields_for_stage(bundle, stage, score_mode, variant)
    diagnostics = _build_stage_diagnostics(
        gold_rows=gold_rows,
        prediction_rows=predictions,
        fields=diagnostic_fields,
        context_rows=context_rows,
    )
    classification_options = _classification_metric_options(bundle.metrics.metrics)
    if classification_options:
        label_field = str(
            classification_options.get(
                "label_field",
                diagnostic_fields[0]
                if diagnostic_fields
                else bundle.scenario.evaluation_fields[0],
            )
        )
        diagnostics["classification_routing"] = build_classification_diagnostics(
            predictions=predicted,
            gold=gold,
            label_field=label_field,
            confidence_field=str(
                classification_options.get("confidence_field", "confidence")
            ),
            abstain_field=classification_options.get("abstain_field"),
            review_route_field=classification_options.get("review_route_field"),
            review_required_field=classification_options.get("review_required_field"),
            abstain_gold_field=classification_options.get("abstain_gold_field"),
            abstain_values=classification_options.get("abstain_values"),
            low_confidence_threshold=float(
                classification_options.get("low_confidence_threshold", 0.5)
            ),
            calibration_bin_count=int(
                classification_options.get("calibration_bin_count", 5)
            ),
        )
    diagnostics["metric_family_summaries"] = _metric_family_summaries(metric_results)
    notes: list[str] = []
    coverage = diagnostics["coverage"]
    if coverage["missing_prediction_count"] or coverage["extra_prediction_count"]:
        notes.append(
            "Coverage integrity warning: "
            f"missing={coverage['missing_prediction_count']}, "
            f"extra={coverage['extra_prediction_count']}."
        )
    if coverage["duplicate_prediction_count"]:
        notes.append(
            "Coverage integrity warning: "
            f"{coverage['duplicate_prediction_count']} duplicate prediction row(s)."
        )
    return GroundedRunSummary(
        benchmark_id=bundle.scenario.benchmark_id,
        run_id=run_id,
        stage=stage,
        mode=score_mode,
        variant=variant,
        record_count=len(gold_rows),
        overall_score=overall_score,
        primary_metric_id=bundle.metrics.primary_metric_id,
        metrics=metric_results,
        diagnostics=diagnostics,
        notes=notes,
    )


def score_grounded_predictions(
    *,
    bundle: GroundedBenchmarkBundle,
    predictions: list[dict[str, Any]],
    gold_rows: list[dict[str, Any]],
    run_id: str,
    mode: BenchmarkMode,
    variant: ScoringVariant,
) -> GroundedRunSummary:
    """Backward-compatible grounded scorer."""
    return score_grounded_stage(
        bundle=bundle,
        predictions=predictions,
        gold_rows=gold_rows,
        run_id=run_id,
        stage=_default_stage_for_mode(mode, variant),
        mode=mode,
        variant=variant,
    )


def compute_stage_deltas(
    summaries: list[GroundedRunSummary],
    metrics_config: GroundedMetricsConfig,
) -> list[GroundedTaxResult]:
    """Compute signed benchmark deltas using stage-aware semantics."""
    by_stage = {
        (summary.stage, summary.variant): summary
        for summary in summaries
        if summary.stage is not None
    }
    by_legacy = {(summary.mode, summary.variant): summary for summary in summaries}
    results: list[GroundedTaxResult] = []

    for tax in metrics_config.tax_definitions:
        minuend = None
        subtrahend = None
        if tax.minuend_stage is not None and tax.subtrahend_stage is not None:
            minuend = by_stage.get((tax.minuend_stage, tax.minuend_variant))
            subtrahend = by_stage.get((tax.subtrahend_stage, tax.subtrahend_variant))
        if minuend is None or subtrahend is None:
            minuend = by_legacy.get((tax.minuend_mode, tax.minuend_variant))
            subtrahend = by_legacy.get((tax.subtrahend_mode, tax.subtrahend_variant))
        if minuend is None or subtrahend is None:
            continue
        minuend_metrics = _metric_map(minuend)
        subtrahend_metrics = _metric_map(subtrahend)
        metric_deltas = {
            metric_id: minuend_metrics[metric_id] - subtrahend_metrics[metric_id]
            for metric_id in sorted(set(minuend_metrics) & set(subtrahend_metrics))
        }
        results.append(
            GroundedTaxResult(
                tax_id=tax.tax_id,
                name=tax.name,
                value=minuend.overall_score - subtrahend.overall_score,
                minuend_mode=minuend.mode,
                minuend_variant=minuend.variant,
                subtrahend_mode=subtrahend.mode,
                subtrahend_variant=subtrahend.variant,
                minuend_stage=minuend.stage,
                subtrahend_stage=subtrahend.stage,
                metric_deltas=metric_deltas,
            )
        )

    return results


def compute_tax_breakdown(
    summaries: list[GroundedRunSummary],
    metrics_config: GroundedMetricsConfig,
) -> list[GroundedTaxResult]:
    """Backward-compatible tax delta calculation."""
    return compute_stage_deltas(summaries, metrics_config)


def compute_stage_stability(
    summaries: list[GroundedRunSummary],
) -> list[GroundedStageStabilitySummary]:
    """Summarize repeated-run variance for comparable grounded stages."""
    grouped: dict[
        tuple[BenchmarkStage | None, BenchmarkMode, ScoringVariant],
        list[GroundedRunSummary],
    ] = defaultdict(list)
    for summary in summaries:
        grouped[(summary.stage, summary.mode, summary.variant)].append(summary)

    stability_summaries: list[GroundedStageStabilitySummary] = []
    for (stage, mode, variant), grouped_summaries in sorted(
        grouped.items(),
        key=lambda item: (
            str(item[0][0] or ""),
            item[0][1],
            item[0][2],
        ),
    ):
        if len(grouped_summaries) < 2:
            continue
        overall_values = [summary.overall_score for summary in grouped_summaries]
        metric_values: dict[str, list[float]] = defaultdict(list)
        for summary in grouped_summaries:
            for metric in summary.metrics:
                metric_values[metric.metric_id].append(metric.value)
        stability_summaries.append(
            GroundedStageStabilitySummary(
                stage=stage,
                mode=mode,
                variant=variant,
                run_count=len(grouped_summaries),
                run_ids=[summary.run_id for summary in grouped_summaries],
                overall_mean=_mean(overall_values),
                overall_min=min(overall_values),
                overall_max=max(overall_values),
                overall_stddev=_stddev(overall_values),
                overall_span=max(overall_values) - min(overall_values),
                metric_means={
                    metric_id: _mean(values)
                    for metric_id, values in sorted(metric_values.items())
                },
                metric_stddevs={
                    metric_id: _stddev(values)
                    for metric_id, values in sorted(metric_values.items())
                },
                metric_spans={
                    metric_id: max(values) - min(values)
                    for metric_id, values in sorted(metric_values.items())
                },
            )
        )

    return stability_summaries


def _final_review_events_by_record(
    review_events: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], Counter[str]]:
    final_events: dict[str, dict[str, Any]] = {}
    counts: Counter[str] = Counter()
    for event in review_events:
        record_id = str(event.get("record_id", "")).strip()
        if not record_id:
            continue
        counts[record_id] += 1
        final_events[record_id] = event
    return final_events, counts


def _normalize_review_decision(decision: Any) -> str:
    """Normalize persisted review decision variants into stable benchmark buckets."""

    normalized = str(decision or "").strip().lower()
    if not normalized:
        return "<missing>"
    aliases = {
        "accept": "accept_ai",
        "accept_ai": "accept_ai",
        "edit": "edit_ai",
        "edit_ai": "edit_ai",
        "correct": "correct",
        "reject": "reject_ai",
        "reject_ai": "reject_ai",
        "skip": "skip",
    }
    return aliases.get(normalized, normalized)


def _subset_record_delta_summary(
    *,
    subset_ids: list[str],
    delta_by_record: dict[str, GroundedOperatorRecordDelta],
    final_decisions: dict[str, str],
) -> dict[str, Any]:
    if not subset_ids:
        return {
            "count": 0,
            "proposal_exact_match_rate": 0.0,
            "review_exact_match_rate": 0.0,
            "corrected_count": 0,
            "regressed_count": 0,
            "decision_counts": {},
        }
    deltas = [delta_by_record[record_id] for record_id in subset_ids]
    decision_counts = Counter(
        final_decisions.get(record_id, "<missing>") for record_id in subset_ids
    )
    proposal_correct = sum(int(delta.proposal_matches_gold) for delta in deltas)
    review_correct = sum(int(delta.review_matches_gold) for delta in deltas)
    corrected = sum(int(delta.status == "corrected") for delta in deltas)
    regressed = sum(int(delta.status == "regressed") for delta in deltas)
    return {
        "count": len(subset_ids),
        "proposal_exact_match_rate": _safe_ratio(proposal_correct, len(subset_ids)),
        "review_exact_match_rate": _safe_ratio(review_correct, len(subset_ids)),
        "corrected_count": corrected,
        "regressed_count": regressed,
        "decision_counts": dict(sorted(decision_counts.items())),
    }


def _decision_quality_summary(
    *,
    record_ids: list[str],
    delta_by_record: dict[str, GroundedOperatorRecordDelta],
    final_decisions: dict[str, str],
    raw_final_decisions: dict[str, str] | None = None,
) -> dict[str, Any]:
    by_decision: dict[str, dict[str, Any]] = {}
    decision_ids: dict[str, list[str]] = defaultdict(list)
    for record_id in record_ids:
        decision = final_decisions.get(record_id, "<missing>")
        decision_ids[decision].append(record_id)

    for decision, ids in sorted(decision_ids.items()):
        deltas = [delta_by_record[record_id] for record_id in ids]
        changed_count = sum(int(not delta.proposal_matches_review) for delta in deltas)
        corrected_count = sum(int(delta.status == "corrected") for delta in deltas)
        regressed_count = sum(int(delta.status == "regressed") for delta in deltas)
        preserved_correct_count = sum(
            int(delta.proposal_matches_gold and delta.proposal_matches_review)
            for delta in deltas
        )
        preserved_wrong_count = sum(
            int((not delta.proposal_matches_gold) and delta.proposal_matches_review)
            for delta in deltas
        )
        review_correct_count = sum(int(delta.review_matches_gold) for delta in deltas)
        proposal_correct_count = sum(
            int(delta.proposal_matches_gold) for delta in deltas
        )
        decision_label_mismatch_count = 0
        if decision == "accept_ai":
            decision_label_mismatch_count = changed_count
        elif decision == "edit_ai":
            decision_label_mismatch_count = len(ids) - changed_count
        by_decision[decision] = {
            "count": len(ids),
            "review_correct_count": review_correct_count,
            "review_correct_rate": _safe_ratio(review_correct_count, len(ids)),
            "proposal_correct_count": proposal_correct_count,
            "proposal_correct_rate": _safe_ratio(proposal_correct_count, len(ids)),
            "changed_count": changed_count,
            "corrected_count": corrected_count,
            "regressed_count": regressed_count,
            "preserved_correct_count": preserved_correct_count,
            "preserved_wrong_count": preserved_wrong_count,
            "decision_label_mismatch_count": decision_label_mismatch_count,
        }

    return {
        "final_decision_count": len(record_ids),
        "missing_decision_count": len(decision_ids.get("<missing>", [])),
        "raw_decision_counts": dict(
            sorted(Counter((raw_final_decisions or {}).values()).items())
        ),
        "by_decision": by_decision,
    }


def _benchmark_case_sets(
    *,
    gold: dict[str, dict[str, Any]],
    benchmark_human_rows: list[dict[str, Any]],
    benchmark_review_rows: list[dict[str, Any]],
) -> tuple[set[str], set[str]]:
    intentionally_wrong_ids: set[str] = set()
    disagreement_ids: set[str] = set()
    for row in [*benchmark_human_rows, *benchmark_review_rows]:
        record_id = str(row.get("record_id", "")).strip()
        if not record_id:
            continue
        if row.get("is_intentionally_wrong"):
            intentionally_wrong_ids.add(record_id)
        labels = dict(row.get("labels") or {})
        if labels and not _record_exact_match(gold.get(record_id, {}), labels):
            disagreement_ids.add(record_id)
    return intentionally_wrong_ids, disagreement_ids


def _confidence_diagnostics(
    *,
    proposal_rows: list[dict[str, Any]],
    delta_by_record: dict[str, GroundedOperatorRecordDelta],
) -> dict[str, Any]:
    confidence_by_record: dict[str, float] = {}
    for row in proposal_rows:
        record_id = str(row.get("record_id", "")).strip()
        if not record_id:
            continue
        confidence = _proposal_confidence_for_row(row)
        if confidence is not None:
            confidence_by_record[record_id] = confidence

    if not confidence_by_record:
        return {"available": False, "count": 0, "missing_count": len(delta_by_record)}

    correct_values: list[float] = []
    incorrect_values: list[float] = []
    low_confidence_ids: list[str] = []
    high_confidence_ids: list[str] = []
    bin_ranges = [
        (0.0, 0.2),
        (0.2, 0.4),
        (0.4, 0.6),
        (0.6, 0.8),
        (0.8, 1.01),
    ]
    calibration_bins: list[dict[str, Any]] = []

    for record_id, confidence in confidence_by_record.items():
        delta = delta_by_record.get(record_id)
        if delta is None:
            continue
        if delta.proposal_matches_gold:
            correct_values.append(confidence)
        else:
            incorrect_values.append(confidence)
        if confidence <= 0.5:
            low_confidence_ids.append(record_id)
        if confidence >= 0.8:
            high_confidence_ids.append(record_id)

    for start, end in bin_ranges:
        ids = [
            record_id
            for record_id, confidence in confidence_by_record.items()
            if start <= confidence < end
        ]
        if not ids:
            continue
        confidences = [confidence_by_record[record_id] for record_id in ids]
        deltas = [
            delta_by_record[record_id]
            for record_id in ids
            if record_id in delta_by_record
        ]
        proposal_accuracy = _safe_ratio(
            sum(int(delta.proposal_matches_gold) for delta in deltas),
            len(deltas),
        )
        review_accuracy = _safe_ratio(
            sum(int(delta.review_matches_gold) for delta in deltas),
            len(deltas),
        )
        review_change_rate = _safe_ratio(
            sum(int(not delta.proposal_matches_review) for delta in deltas),
            len(deltas),
        )
        calibration_bins.append(
            {
                "start": start,
                "end": min(end, 1.0),
                "count": len(ids),
                "mean_confidence": _mean(confidences),
                "proposal_accuracy": proposal_accuracy,
                "review_accuracy": review_accuracy,
                "review_change_rate": review_change_rate,
            }
        )

    low_change_rate = _safe_ratio(
        sum(
            int(not delta_by_record[record_id].proposal_matches_review)
            for record_id in low_confidence_ids
            if record_id in delta_by_record
        ),
        len(low_confidence_ids),
    )
    high_change_rate = _safe_ratio(
        sum(
            int(not delta_by_record[record_id].proposal_matches_review)
            for record_id in high_confidence_ids
            if record_id in delta_by_record
        ),
        len(high_confidence_ids),
    )

    return {
        "available": True,
        "count": len(confidence_by_record),
        "missing_count": max(len(delta_by_record) - len(confidence_by_record), 0),
        "mean_confidence": _mean(list(confidence_by_record.values())),
        "mean_confidence_correct": _mean(correct_values),
        "mean_confidence_incorrect": _mean(incorrect_values),
        "low_confidence_threshold": 0.5,
        "high_confidence_threshold": 0.8,
        "low_confidence_count": len(low_confidence_ids),
        "high_confidence_count": len(high_confidence_ids),
        "low_confidence_review_change_rate": low_change_rate,
        "high_confidence_review_change_rate": high_change_rate,
        "attention_alignment_gap": low_change_rate - high_change_rate,
        "calibration_bins": calibration_bins,
    }


def _summarize_audit(
    *,
    shell_audit: dict[str, Any],
    final_decision_count: int,
    revealed_record_count: int,
) -> dict[str, Any]:
    shell_commands = list(shell_audit.get("shell_commands", []))
    non_cli_surface_commands = list(shell_audit.get("non_cli_surface_commands", []))
    hidden_benchmark_path_commands = list(
        shell_audit.get("hidden_benchmark_path_commands", [])
    )
    truth_probe_commands = list(shell_audit.get("truth_probe_commands", []))
    queue_claim_commands = list(shell_audit.get("queue_claim_commands", []))
    reveal_ai_commands = list(shell_audit.get("reveal_ai_commands", []))
    status_poll_commands = list(shell_audit.get("status_poll_commands", []))
    repeated_poll_commands = list(shell_audit.get("repeated_poll_commands", []))
    duplicate_shell_commands = list(shell_audit.get("duplicate_shell_commands", []))
    redundant_read_commands = list(shell_audit.get("redundant_read_commands", []))
    unnecessary_queue_claim_count = max(
        len(queue_claim_commands) - final_decision_count,
        0,
    )
    unnecessary_reveal_ai_command_count = max(
        len(reveal_ai_commands) - revealed_record_count,
        0,
    )
    avoidable_command_count = (
        unnecessary_queue_claim_count
        + unnecessary_reveal_ai_command_count
        + len(repeated_poll_commands)
        + len(redundant_read_commands)
    )
    return {
        "shell_command_count": len(shell_commands),
        "queue_claim_count": len(queue_claim_commands),
        "unnecessary_queue_claim_count": unnecessary_queue_claim_count,
        "reveal_ai_command_count": len(reveal_ai_commands),
        "unnecessary_reveal_ai_command_count": unnecessary_reveal_ai_command_count,
        "status_poll_command_count": len(status_poll_commands),
        "repeated_poll_command_count": len(repeated_poll_commands),
        "duplicate_shell_command_count": len(duplicate_shell_commands),
        "redundant_read_command_count": len(redundant_read_commands),
        "non_cli_surface_command_count": len(non_cli_surface_commands),
        "hidden_benchmark_path_command_count": len(hidden_benchmark_path_commands),
        "truth_probe_command_count": len(truth_probe_commands),
        "avoidable_command_count": avoidable_command_count,
    }


def build_operator_diagnostics(
    *,
    gold_rows: list[dict[str, Any]],
    proposal_rows: list[dict[str, Any]],
    review_rows: list[dict[str, Any]],
    evaluation_fields: list[str] | None = None,
    review_events: list[dict[str, Any]] | None = None,
    shell_audit: dict[str, Any] | None = None,
    report_text: str | None = None,
    summary_payload: dict[str, Any] | None = None,
    source_rows: list[dict[str, Any]] | None = None,
    benchmark_human_rows: list[dict[str, Any]] | None = None,
    benchmark_review_rows: list[dict[str, Any]] | None = None,
    expected_benchmark_id: str | None = None,
) -> GroundedOperatorDiagnostics:
    """Build operator-centric diagnostics for the grounded benchmark."""

    gold = _record_labels(gold_rows)
    proposals = _record_labels(proposal_rows)
    reviews = _record_labels(review_rows)
    record_ids = sorted(gold)
    fields_to_score = evaluation_fields or sorted(
        {field for labels in gold.values() for field in labels}
    )

    proposal_stage = _build_stage_diagnostics(
        gold_rows=gold_rows,
        prediction_rows=proposal_rows,
        fields=fields_to_score,
        context_rows=source_rows,
    )
    review_stage = _build_stage_diagnostics(
        gold_rows=gold_rows,
        prediction_rows=review_rows,
        fields=fields_to_score,
        context_rows=source_rows,
    )

    record_deltas: list[GroundedOperatorRecordDelta] = []
    proposal_exact_match_count = 0
    review_exact_match_count = 0
    changed_count = 0
    unchanged_count = 0
    corrected_count = 0
    regressed_count = 0

    for record_id in record_ids:
        gold_labels = dict(gold.get(record_id, {}))
        proposal_labels = dict(proposals.get(record_id, {}))
        review_labels = dict(reviews.get(record_id, {}))
        gold_view = _select_label_fields(gold_labels, evaluation_fields)
        proposal_view = _select_label_fields(proposal_labels, evaluation_fields)
        review_view = _select_label_fields(review_labels, evaluation_fields)
        proposal_matches_gold = _record_exact_match(gold_view, proposal_view)
        review_matches_gold = _record_exact_match(gold_view, review_view)
        proposal_matches_review = _record_exact_match(proposal_view, review_view)

        if proposal_matches_gold:
            proposal_exact_match_count += 1
        if review_matches_gold:
            review_exact_match_count += 1
        if proposal_matches_review:
            unchanged_count += 1
            status = "unchanged"
        else:
            changed_count += 1
            if not proposal_matches_gold and review_matches_gold:
                corrected_count += 1
                status = "corrected"
            elif proposal_matches_gold and not review_matches_gold:
                regressed_count += 1
                status = "regressed"
            else:
                status = "changed"

        record_deltas.append(
            GroundedOperatorRecordDelta(
                record_id=record_id,
                proposal_matches_gold=proposal_matches_gold,
                review_matches_gold=review_matches_gold,
                proposal_matches_review=proposal_matches_review,
                status=status,
                gold_labels=gold_labels,
                proposal_labels=proposal_labels,
                review_labels=review_labels,
            )
        )

    delta_by_record = {delta.record_id: delta for delta in record_deltas}
    final_events, final_event_counts = _final_review_events_by_record(
        review_events or []
    )
    raw_final_decisions = {
        record_id: str(event.get("decision") or "").strip().lower() or "<missing>"
        for record_id, event in final_events.items()
    }
    final_decisions = {
        record_id: _normalize_review_decision(event.get("decision"))
        for record_id, event in final_events.items()
    }
    decision_counts = Counter(
        final_decisions.get(record_id, "<missing>") for record_id in record_ids
    )
    review_event_count = sum(final_event_counts.values())
    final_decision_count = len(final_events)
    accept_ai_count = int(decision_counts.get("accept_ai", 0))
    edit_ai_count = int(decision_counts.get("edit_ai", 0))
    correct_count = int(decision_counts.get("correct", 0))
    reject_ai_count = int(decision_counts.get("reject_ai", 0))
    skip_count = int(decision_counts.get("skip", 0))
    multi_event_record_count = sum(
        1 for count in final_event_counts.values() if count > 1
    )

    shell_audit = shell_audit or {}
    non_cli_surface_commands = list(shell_audit.get("non_cli_surface_commands", []))
    hidden_benchmark_path_commands = list(
        shell_audit.get("hidden_benchmark_path_commands", [])
    )
    truth_probe_commands = list(shell_audit.get("truth_probe_commands", []))

    truthfulness_checks: list[GroundedOperatorTruthfulnessCheck] = []
    report_lower = (report_text or "").lower()

    if re.search(r"accepted all(?: \d+)? ai proposals", report_lower):
        truthfulness_checks.append(
            GroundedOperatorTruthfulnessCheck(
                check_id="report_accept_all_ai_claim",
                passed=accept_ai_count == len(record_ids) and len(record_ids) > 0,
                details={
                    "claim_detected": True,
                    "accept_ai_count": accept_ai_count,
                    "record_count": len(record_ids),
                },
            )
        )

    count_patterns: dict[str, tuple[str, int]] = {
        "report_review_submission_count": (
            r"review submissions persisted:\s*`?(\d+)`?",
            len(review_rows),
        ),
        "report_agent_output_count": (
            r"agent outputs(?: persisted)?:\s*`?(\d+)`?",
            len(proposal_rows),
        ),
        "report_non_cli_surface_command_count": (
            r"non-cli surface commands:\s*`?(\d+)`?",
            len(non_cli_surface_commands),
        ),
        "report_hidden_benchmark_path_command_count": (
            r"hidden benchmark path commands:\s*`?(\d+)`?",
            len(hidden_benchmark_path_commands),
        ),
        "report_truth_probe_command_count": (
            r"truth probe commands:\s*`?(\d+)`?",
            len(truth_probe_commands),
        ),
    }
    for check_id, (pattern, expected_value) in count_patterns.items():
        match = re.search(pattern, report_lower)
        if match is None:
            continue
        claimed_value = int(match.group(1))
        truthfulness_checks.append(
            GroundedOperatorTruthfulnessCheck(
                check_id=check_id,
                passed=claimed_value == expected_value,
                details={
                    "claim_detected": True,
                    "claimed": claimed_value,
                    "expected": expected_value,
                },
            )
        )

    if summary_payload:
        summary_checks: dict[str, tuple[str, Any]] = {
            "summary_record_count": ("record_count", len(gold_rows)),
            "summary_submitted_count": ("submitted_count", len(review_rows)),
            "summary_agent_output_count": ("agent_output_count", len(proposal_rows)),
            "summary_proposal_coverage": ("proposal_coverage", len(proposal_rows)),
            "summary_proposal_success": ("proposal_success", len(proposal_rows)),
            "summary_proposal_failures": (
                "proposal_failures",
                max(len(gold_rows) - len(proposal_rows), 0),
            ),
            "summary_accept_ai_rate": (
                "accept_ai_rate",
                _safe_ratio(accept_ai_count, final_decision_count),
            ),
            "summary_hidden_benchmark_path_command_count": (
                "hidden_benchmark_path_command_count",
                len(hidden_benchmark_path_commands),
            ),
            "summary_truth_probe_command_count": (
                "truth_probe_command_count",
                len(truth_probe_commands),
            ),
        }
        if expected_benchmark_id is not None:
            summary_checks["summary_benchmark_id"] = (
                "benchmark_id",
                expected_benchmark_id,
            )
        for check_id, (field_name, expected_value) in summary_checks.items():
            if field_name not in summary_payload:
                continue
            truthfulness_checks.append(
                GroundedOperatorTruthfulnessCheck(
                    check_id=check_id,
                    passed=summary_payload.get(field_name) == expected_value,
                    details={
                        "field": field_name,
                        "claimed": summary_payload.get(field_name),
                        "expected": expected_value,
                    },
                )
            )

    truthfulness_ok = all(check.passed for check in truthfulness_checks)

    proposal_exact_match_rate = _safe_ratio(proposal_exact_match_count, len(record_ids))
    review_exact_match_rate = _safe_ratio(review_exact_match_count, len(record_ids))
    proposal_to_review_delta = review_exact_match_rate - proposal_exact_match_rate
    preserved_correct_count = sum(
        int(delta.proposal_matches_gold and delta.proposal_matches_review)
        for delta in record_deltas
    )
    preserved_wrong_count = sum(
        int((not delta.proposal_matches_gold) and delta.proposal_matches_review)
        for delta in record_deltas
    )
    changed_wrong_to_wrong_count = sum(
        int(
            (not delta.proposal_matches_gold)
            and (not delta.review_matches_gold)
            and (not delta.proposal_matches_review)
        )
        for delta in record_deltas
    )

    coverage = {
        "proposal": proposal_stage["coverage"],
        "review": review_stage["coverage"],
    }

    decision_quality = _decision_quality_summary(
        record_ids=record_ids,
        delta_by_record=delta_by_record,
        final_decisions=final_decisions,
        raw_final_decisions=raw_final_decisions,
    )
    benchmark_human_rows = benchmark_human_rows or []
    benchmark_review_rows = benchmark_review_rows or []
    intentionally_wrong_ids, disagreement_ids = _benchmark_case_sets(
        gold=gold,
        benchmark_human_rows=benchmark_human_rows,
        benchmark_review_rows=benchmark_review_rows,
    )
    confidence_diagnostics = _confidence_diagnostics(
        proposal_rows=proposal_rows,
        delta_by_record=delta_by_record,
    )
    low_confidence_ids: list[str] = []
    if confidence_diagnostics.get("available"):
        threshold = float(confidence_diagnostics["low_confidence_threshold"])
        low_confidence_ids = [
            str(row["record_id"])
            for row in proposal_rows
            if (_proposal_confidence_for_row(row) or 2.0) <= threshold
        ]
    hard_case_breakdown = {
        "proposal_wrong": _subset_record_delta_summary(
            subset_ids=sorted(
                record_id
                for record_id, delta in delta_by_record.items()
                if not delta.proposal_matches_gold
            ),
            delta_by_record=delta_by_record,
            final_decisions=final_decisions,
        ),
        "low_confidence": _subset_record_delta_summary(
            subset_ids=sorted(low_confidence_ids),
            delta_by_record=delta_by_record,
            final_decisions=final_decisions,
        ),
        "benchmark_disagreement": _subset_record_delta_summary(
            subset_ids=sorted(disagreement_ids),
            delta_by_record=delta_by_record,
            final_decisions=final_decisions,
        ),
        "benchmark_intentionally_wrong": _subset_record_delta_summary(
            subset_ids=sorted(intentionally_wrong_ids),
            delta_by_record=delta_by_record,
            final_decisions=final_decisions,
        ),
        "out_of_scope": _subset_record_delta_summary(
            subset_ids=sorted(
                record_id
                for record_id, labels in gold.items()
                if bool(labels.get("is_out_of_scope"))
            ),
            delta_by_record=delta_by_record,
            final_decisions=final_decisions,
        ),
    }
    audit_summary = _summarize_audit(
        shell_audit=shell_audit,
        final_decision_count=final_decision_count,
        revealed_record_count=sum(
            int(bool(final_events.get(record_id, {}).get("ai_was_revealed")))
            for record_id in record_ids
        ),
    )
    artifact_truthfulness = {
        "failed_count": sum(int(not check.passed) for check in truthfulness_checks),
        "failed_check_ids": [
            check.check_id for check in truthfulness_checks if not check.passed
        ],
        "check_count": len(truthfulness_checks),
        "truthfulness_ok": truthfulness_ok,
    }

    return GroundedOperatorDiagnostics(
        record_count=len(record_ids),
        proposal_exact_match_count=proposal_exact_match_count,
        proposal_exact_match_rate=proposal_exact_match_rate,
        review_exact_match_count=review_exact_match_count,
        review_exact_match_rate=review_exact_match_rate,
        changed_count=changed_count,
        unchanged_count=unchanged_count,
        corrected_count=corrected_count,
        regressed_count=regressed_count,
        preserved_correct_count=preserved_correct_count,
        preserved_wrong_count=preserved_wrong_count,
        changed_wrong_to_wrong_count=changed_wrong_to_wrong_count,
        proposal_to_review_delta=proposal_to_review_delta,
        operator_lift_count=corrected_count - regressed_count,
        operator_lift_rate=_safe_ratio(
            corrected_count - regressed_count, len(record_ids)
        ),
        preserve_correct_rate=_safe_ratio(preserved_correct_count, len(record_ids)),
        regression_rate=_safe_ratio(regressed_count, len(record_ids)),
        review_event_count=review_event_count,
        final_decision_count=final_decision_count,
        multi_event_record_count=multi_event_record_count,
        accept_ai_count=accept_ai_count,
        edit_ai_count=edit_ai_count,
        correct_count=correct_count,
        reject_ai_count=reject_ai_count,
        skip_count=skip_count,
        accept_ai_rate=_safe_ratio(accept_ai_count, len(record_ids)),
        edit_ai_rate=_safe_ratio(edit_ai_count, len(record_ids)),
        correct_rate=_safe_ratio(correct_count, len(record_ids)),
        reject_ai_rate=_safe_ratio(reject_ai_count, len(record_ids)),
        skip_rate=_safe_ratio(skip_count, len(record_ids)),
        shell_command_count=audit_summary["shell_command_count"],
        non_cli_surface_command_count=len(non_cli_surface_commands),
        hidden_benchmark_path_command_count=len(hidden_benchmark_path_commands),
        truth_probe_command_count=len(truth_probe_commands),
        proposal_field_accuracy={
            field: details["accuracy"]
            for field, details in proposal_stage["field_accuracy"].items()
        },
        review_field_accuracy={
            field: details["accuracy"]
            for field, details in review_stage["field_accuracy"].items()
        },
        coverage=coverage,
        proposal_stage=proposal_stage,
        review_stage=review_stage,
        decision_quality=decision_quality,
        hard_case_breakdown=hard_case_breakdown,
        confidence_diagnostics=confidence_diagnostics,
        audit_summary=audit_summary,
        record_deltas=record_deltas,
        command_audit={
            key: value for key, value in shell_audit.items() if isinstance(value, list)
        },
        truthfulness_checks=truthfulness_checks,
        artifact_truthfulness=artifact_truthfulness,
        truthfulness_ok=truthfulness_ok,
    )


def score_operator_observations(
    spec: GroundedOperatorSpec,
    observations: list[GroundedOperatorObservation],
    *,
    metric_id: str = "operator_checklist",
    metric_name: str = "Operator Checklist Score",
) -> GroundedMetricResult:
    """Score Codex-as-operator quality from explicit checklist observations."""
    observed_by_id = {observation.check_id: observation for observation in observations}
    passed_weight = 0.0
    total_weight = 0.0
    missing_required: list[str] = []
    per_check: dict[str, bool] = {}

    for check in spec.checks:
        total_weight += check.weight
        observation = observed_by_id.get(check.check_id)
        if observation is None:
            per_check[check.check_id] = False
            if check.required:
                missing_required.append(check.check_id)
            continue
        per_check[check.check_id] = observation.passed
        if observation.passed:
            passed_weight += check.weight

    return GroundedMetricResult(
        metric_id=metric_id,
        name=metric_name,
        metric_type="accuracy",
        value=_safe_ratio(passed_weight, total_weight),
        fields=["operator_checks"],
        details={
            "passed_weight": passed_weight,
            "total_weight": total_weight,
            "missing_required": missing_required,
            "per_check": per_check,
        },
    )


def summarize_operator_run(
    *,
    bundle: GroundedBenchmarkBundle,
    label_summary: GroundedRunSummary,
    observations: list[GroundedOperatorObservation],
    run_id: str | None = None,
) -> GroundedRunSummary:
    """Combine operator label quality and operator checklist quality."""
    if bundle.operator is None:
        raise ValueError("Grounded benchmark is missing operator specification")
    if label_summary.mode != "operator":
        raise ValueError("Operator summary requires an operator-mode label summary")

    checklist_metric = score_operator_observations(bundle.operator, observations)
    combined_score = (
        label_summary.overall_score * bundle.operator.label_quality_weight
        + checklist_metric.value * bundle.operator.checklist_weight
    ) / (bundle.operator.label_quality_weight + bundle.operator.checklist_weight)

    per_check = checklist_metric.details.get("per_check", {})
    blocking_failures = [
        check_id
        for check_id in bundle.operator.blocking_check_ids
        if per_check.get(check_id) is not True
    ]
    if blocking_failures:
        combined_score = min(combined_score, checklist_metric.value)

    notes = list(label_summary.notes)
    notes.append(
        "Operator score combines MoLabel-operated label quality and explicit "
        "Codex-as-operator checklist quality."
    )
    notes.append(
        "Operator weighting: "
        f"label={bundle.operator.label_quality_weight:.2f}, "
        f"checklist={bundle.operator.checklist_weight:.2f}."
    )
    if blocking_failures:
        notes.append(
            "Blocking operator checks failed: " + ", ".join(sorted(blocking_failures))
        )

    return label_summary.model_copy(
        update={
            "run_id": run_id or label_summary.run_id,
            "stage": label_summary.stage or "operator_reviewed",
            "overall_score": combined_score,
            "metrics": [*label_summary.metrics, checklist_metric],
            "notes": notes,
        }
    )


def _render_diagnostics_lines(diagnostics: dict[str, Any]) -> list[str]:
    """Render structured diagnostics into Markdown report lines."""
    if not diagnostics:
        return []

    lines: list[str] = ["", "## Diagnostics"]
    scalar_keys = [
        "record_count",
        "proposal_exact_match_count",
        "proposal_exact_match_rate",
        "review_exact_match_count",
        "review_exact_match_rate",
        "changed_count",
        "unchanged_count",
        "corrected_count",
        "regressed_count",
        "preserved_correct_count",
        "preserved_wrong_count",
        "changed_wrong_to_wrong_count",
        "proposal_to_review_delta",
        "operator_lift_count",
        "operator_lift_rate",
        "preserve_correct_rate",
        "regression_rate",
        "review_event_count",
        "final_decision_count",
        "multi_event_record_count",
        "accept_ai_count",
        "edit_ai_count",
        "correct_count",
        "reject_ai_count",
        "skip_count",
        "accept_ai_rate",
        "edit_ai_rate",
        "correct_rate",
        "reject_ai_rate",
        "skip_rate",
        "shell_command_count",
        "non_cli_surface_command_count",
        "hidden_benchmark_path_command_count",
        "truth_probe_command_count",
        "truthfulness_ok",
    ]
    for key in scalar_keys:
        if key not in diagnostics:
            continue
        value = diagnostics[key]
        rendered = f"{value:.4f}" if isinstance(value, float) else str(value)
        lines.append(f"- `{key}`: `{rendered}`")

    coverage = diagnostics.get("coverage")
    if isinstance(coverage, dict) and coverage:
        lines.append("- `coverage`:")
        if "proposal" in coverage or "review" in coverage:
            for name in ("proposal", "review"):
                info = coverage.get(name)
                if not isinstance(info, dict):
                    continue
                lines.append(
                    "  - "
                    f"`{name}`: coverage=`{info.get('coverage_rate', 0.0):.4f}`, "
                    f"missing=`{info.get('missing_prediction_count', 0)}`, "
                    f"extra=`{info.get('extra_prediction_count', 0)}`, "
                    f"duplicates=`{info.get('duplicate_prediction_count', 0)}`"
                )
        else:
            lines.append(
                "  - "
                f"coverage=`{coverage.get('coverage_rate', 0.0):.4f}`, "
                f"missing=`{coverage.get('missing_prediction_count', 0)}`, "
                f"extra=`{coverage.get('extra_prediction_count', 0)}`, "
                f"duplicates=`{coverage.get('duplicate_prediction_count', 0)}`"
            )

    for key in ("proposal_field_accuracy", "review_field_accuracy"):
        field_accuracy = diagnostics.get(key)
        if isinstance(field_accuracy, dict) and field_accuracy:
            lines.append(f"- `{key}`:")
            for field, value in sorted(field_accuracy.items()):
                rendered = value
                if isinstance(rendered, dict):
                    rendered = rendered.get("accuracy", 0.0)
                lines.append(f"  - `{field}`: `{float(rendered):.4f}`")

    for key in ("field_accuracy",):
        field_accuracy = diagnostics.get(key)
        if isinstance(field_accuracy, dict) and field_accuracy:
            lines.append(f"- `{key}`:")
            for field, value in sorted(field_accuracy.items()):
                if not isinstance(value, dict):
                    continue
                lines.append(
                    f"  - `{field}`: `{value.get('accuracy', 0.0):.4f}` "
                    f"({value.get('matched', 0)}/{value.get('total', 0)})"
                )

    confusion = diagnostics.get("confusion")
    if isinstance(confusion, dict) and confusion:
        lines.append("- `confusion`:")
        for field, details in sorted(confusion.items()):
            if not isinstance(details, dict):
                continue
            top_confusions = details.get("top_confusions", [])
            if not top_confusions:
                lines.append(f"  - `{field}`: no confusions")
                continue
            rendered = ", ".join(
                f"{item.get('gold')} -> {item.get('predicted')} ({item.get('count')})"
                for item in top_confusions[:3]
                if isinstance(item, dict)
            )
            lines.append(f"  - `{field}`: {rendered}")

    subset_breakdowns = diagnostics.get("subset_breakdowns")
    if isinstance(subset_breakdowns, dict) and subset_breakdowns:
        lines.append("- `subset_breakdowns`:")
        for subset_name, subset_values in sorted(subset_breakdowns.items()):
            if not isinstance(subset_values, dict):
                continue
            lines.append(f"  - `{subset_name}`: `{len(subset_values)}` subset value(s)")

    decision_quality = diagnostics.get("decision_quality")
    if isinstance(decision_quality, dict) and decision_quality:
        lines.append("- `decision_quality`:")
        for decision, details in sorted(
            decision_quality.get("by_decision", {}).items()
        ):
            if not isinstance(details, dict):
                continue
            lines.append(
                "  - "
                f"`{decision}`: count=`{details.get('count', 0)}`, "
                f"review_correct_rate=`{details.get('review_correct_rate', 0.0):.4f}`, "
                f"corrected=`{details.get('corrected_count', 0)}`, "
                f"regressed=`{details.get('regressed_count', 0)}`"
            )

    hard_case_breakdown = diagnostics.get("hard_case_breakdown")
    if isinstance(hard_case_breakdown, dict) and hard_case_breakdown:
        lines.append("- `hard_case_breakdown`:")
        for subset_name, details in sorted(hard_case_breakdown.items()):
            if not isinstance(details, dict):
                continue
            lines.append(
                "  - "
                f"`{subset_name}`: count=`{details.get('count', 0)}`, "
                "proposal_exact_match_rate="
                f"`{details.get('proposal_exact_match_rate', 0.0):.4f}`, "
                "review_exact_match_rate="
                f"`{details.get('review_exact_match_rate', 0.0):.4f}`"
            )

    confidence_diagnostics = diagnostics.get("confidence_diagnostics")
    if isinstance(confidence_diagnostics, dict) and confidence_diagnostics:
        available = bool(confidence_diagnostics.get("available"))
        lines.append(
            f"- `confidence_diagnostics`: available=`{available}`, "
            f"count=`{confidence_diagnostics.get('count', 0)}`"
        )
        if available:
            lines.append(
                "  - "
                "mean_correct="
                f"`{confidence_diagnostics.get('mean_confidence_correct', 0.0):.4f}`, "
                "mean_incorrect="
                f"`{confidence_diagnostics.get('mean_confidence_incorrect', 0.0):.4f}`,"
                " "
                "attention_alignment_gap="
                f"`{confidence_diagnostics.get('attention_alignment_gap', 0.0):.4f}`"
            )

    classification_routing = diagnostics.get("classification_routing")
    if isinstance(classification_routing, dict) and classification_routing:
        lines.append("- `classification_routing`:")
        for key in (
            "coverage_rate",
            "answered_accuracy",
            "abstain_rate",
            "abstain_precision",
            "abstain_recall",
            "expected_calibration_error",
            "review_routing_precision",
            "review_routing_recall",
            "incorrect_capture_recall",
        ):
            if key in classification_routing:
                lines.append(f"  - `{key}`: `{float(classification_routing[key]):.4f}`")
        if classification_routing.get("selective_curve"):
            selective_curve_points = len(classification_routing["selective_curve"])
            lines.append(f"  - `selective_curve_points`: `{selective_curve_points}`")

    metric_family_summaries = diagnostics.get("metric_family_summaries")
    if isinstance(metric_family_summaries, dict) and metric_family_summaries:
        lines.append("- `metric_family_summaries`:")
        for family, metrics in sorted(metric_family_summaries.items()):
            if not isinstance(metrics, dict):
                continue
            rendered = ", ".join(
                f"{metric_id}={value:.4f}"
                for metric_id, value in sorted(metrics.items())
            )
            lines.append(f"  - `{family}`: {rendered}")

    audit_summary = diagnostics.get("audit_summary")
    if isinstance(audit_summary, dict) and audit_summary:
        lines.append("- `audit_summary`:")
        for key in (
            "queue_claim_count",
            "unnecessary_queue_claim_count",
            "reveal_ai_command_count",
            "unnecessary_reveal_ai_command_count",
            "status_poll_command_count",
            "repeated_poll_command_count",
            "duplicate_shell_command_count",
            "redundant_read_command_count",
            "avoidable_command_count",
        ):
            if key in audit_summary:
                lines.append(f"  - `{key}`: `{audit_summary[key]}`")

    record_deltas = diagnostics.get("record_deltas", [])
    if isinstance(record_deltas, list) and record_deltas:
        lines.append(f"- `record_deltas`: `{len(record_deltas)}` records")

    command_audit = diagnostics.get("command_audit", {})
    if isinstance(command_audit, dict) and command_audit:
        lines.append("- `command_audit`:")
        for key in (
            "non_cli_surface_commands",
            "hidden_benchmark_path_commands",
            "truth_probe_commands",
        ):
            commands = command_audit.get(key, [])
            lines.append(f"  - `{key}`: `{len(commands)}`")

    artifact_truthfulness = diagnostics.get("artifact_truthfulness", {})
    if isinstance(artifact_truthfulness, dict) and artifact_truthfulness:
        lines.append(
            "- `artifact_truthfulness`: "
            f"checks=`{artifact_truthfulness.get('check_count', 0)}`, "
            f"failed=`{artifact_truthfulness.get('failed_count', 0)}`"
        )

    truthfulness_checks = diagnostics.get("truthfulness_checks", [])
    if isinstance(truthfulness_checks, list) and truthfulness_checks:
        lines.append("- `truthfulness_checks`:")
        for check in truthfulness_checks:
            if not isinstance(check, dict):
                continue
            status = "pass" if check.get("passed") else "fail"
            lines.append(f"  - `{check.get('check_id', 'unknown')}`: `{status}`")

    return lines


def render_grounded_stage_report(
    *,
    bundle: GroundedBenchmarkBundle,
    summaries: list[GroundedRunSummary],
    tax_breakdown: list[GroundedTaxResult] | None = None,
) -> str:
    """Render a stage-aware grounded benchmark report."""
    stability_summaries = compute_stage_stability(summaries)
    summary_lines = [
        f"# {bundle.scenario.name} Benchmark Report",
        "",
        f"- Benchmark ID: `{bundle.scenario.benchmark_id}`",
        f"- Paper: [{bundle.paper.paper_title}]({bundle.paper.paper_url})",
        f"- Dataset: [{bundle.paper.dataset_name}]({bundle.paper.dataset_url})",
    ]

    if summaries:
        summary_lines.extend(["", "## Stages"])
        for summary in summaries:
            stage = summary.stage or _default_stage_for_mode(
                summary.mode, summary.variant
            )
            summary_lines.append(
                f"- `{summary.run_id}`: `{stage}` / "
                f"`{summary.mode}` / `{summary.variant}` = "
                f"`{summary.overall_score:.4f}` ({summary.record_count} records)"
            )
            for metric in summary.metrics:
                fields = ", ".join(metric.fields) if metric.fields else "n/a"
                summary_lines.append(
                    f"  - `{metric.metric_id}` "
                    f"({metric.metric_type}, fields: {fields}) "
                    f"= `{metric.value:.4f}`"
                )
            operator_metric = next(
                (
                    metric
                    for metric in summary.metrics
                    if metric.metric_id == "operator_checklist"
                ),
                None,
            )
            if operator_metric is not None:
                for check_id, passed in sorted(
                    operator_metric.details.get("per_check", {}).items()
                ):
                    status = "pass" if passed else "fail"
                    summary_lines.append(f"  - `{check_id}`: `{status}`")
            summary_lines.extend(_render_diagnostics_lines(summary.diagnostics))

    if tax_breakdown:
        summary_lines.extend(["", "## Tax Breakdown"])
        for tax in tax_breakdown:
            stage_label = ""
            if tax.minuend_stage is not None or tax.subtrahend_stage is not None:
                stage_label = (
                    f" (`{tax.minuend_stage or tax.minuend_mode}` -> "
                    f"`{tax.subtrahend_stage or tax.subtrahend_mode}`)"
                )
            summary_lines.append(f"- `{tax.tax_id}`{stage_label} = `{tax.value:+.4f}`")
            if tax.metric_deltas:
                rendered_metric_deltas = ", ".join(
                    f"{metric_id}={value:+.4f}"
                    for metric_id, value in sorted(tax.metric_deltas.items())
                )
                summary_lines.append(f"  - metric deltas: {rendered_metric_deltas}")

    if stability_summaries:
        summary_lines.extend(["", "## Stability"])
        for stability in stability_summaries:
            stage = stability.stage or _default_stage_for_mode(
                stability.mode, stability.variant
            )
            summary_lines.append(
                f"- `{stage}` / `{stability.mode}` / `{stability.variant}`: "
                f"runs=`{stability.run_count}`, "
                f"mean=`{stability.overall_mean:.4f}`, "
                f"std=`{stability.overall_stddev:.4f}`, "
                f"span=`{stability.overall_span:.4f}`"
            )
            if stability.metric_spans:
                rendered_metric_spans = ", ".join(
                    f"{metric_id}={value:.4f}"
                    for metric_id, value in sorted(stability.metric_spans.items())
                )
                summary_lines.append(f"  - metric spans: {rendered_metric_spans}")

    combined_notes: list[str] = []
    for summary in summaries:
        combined_notes.extend(summary.notes)
    if combined_notes:
        summary_lines.extend(["", "## Notes"])
        for note in combined_notes:
            summary_lines.append(f"- {note}")

    return "\n".join(summary_lines) + "\n"


def render_grounded_report(
    *,
    bundle: GroundedBenchmarkBundle,
    summary: GroundedRunSummary,
) -> str:
    """Render a concise Markdown benchmark report."""
    return render_grounded_stage_report(
        bundle=bundle,
        summaries=[summary],
        tax_breakdown=summary.tax_breakdown,
    )

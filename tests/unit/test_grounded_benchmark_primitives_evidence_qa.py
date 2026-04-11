from __future__ import annotations

from pathlib import Path

import pytest

from molabel.core.quality.grounded_benchmark_primitives import (
    answer_exact_match,
    answer_token_f1,
    normalize_evidence_annotation,
    score_grouped_evidence,
    score_qa_with_evidence,
    supporting_fact_exact_match,
    supporting_fact_f1,
    validate_evidence_annotation,
)
from molabel.core.quality.grounded_benchmarks import (
    GroundedAuthorityPack,
    GroundedAuthorityPackManifest,
    GroundedBaselines,
    GroundedBenchmarkBundle,
    GroundedBenchmarkScenario,
    GroundedLabelMap,
    GroundedMetricDefinition,
    GroundedMetricsConfig,
    GroundedPaperMetadata,
    score_grounded_stage,
)


def _bundle_for_metrics(
    tmp_path: Path,
    metrics: list[GroundedMetricDefinition],
    *,
    evaluation_fields: list[str],
) -> GroundedBenchmarkBundle:
    scenario = GroundedBenchmarkScenario(
        benchmark_id="framework-demo",
        name="Framework Demo",
        description="Evidence and QA primitive coverage.",
        raw_format="jsonl",
        source_path="data/raw/demo.jsonl",
        loader_plugin="molabel.loaders.jsonl",
        record_id_field="record_id",
        task_schema_path="workbench/config/task-schemas/demo.yaml",
        workflow_path="workbench/workflows/demo.yaml",
        paper_metadata_path="workbench/benchmarks/paper.yaml",
        label_map_path="workbench/benchmarks/label-map.yaml",
        metrics_path="workbench/benchmarks/metrics.yaml",
        baselines_path="workbench/benchmarks/baselines.yaml",
        gold_labels_path="workbench/benchmarks/gold/demo.jsonl",
        evaluation_fields=evaluation_fields,
        default_model_profile={
            "provider_type": "anthropic",
            "provider_name": "MiniMax",
            "model_identifier": "minimax-2.7",
            "sdk_stack": "anthropic_sdk",
        },
    )
    paper = GroundedPaperMetadata(
        benchmark_id="framework-demo",
        paper_title="Framework Demo",
        paper_url="https://example.com/paper",
        citation="Example et al. (2026)",
        publication_year=2026,
        dataset_name="Framework Demo",
        dataset_url="https://example.com/dataset",
        dataset_license="CC BY 4.0",
        redistribution_status="allowed",
        task_summary="Framework primitive tests.",
        original_task_definition="Exercise reusable grounded benchmark scoring.",
    )
    metrics_config = GroundedMetricsConfig(
        benchmark_id="framework-demo",
        primary_metric_id=metrics[0].metric_id,
        metrics=metrics,
    )
    authority = GroundedAuthorityPack(
        manifest=GroundedAuthorityPackManifest(
            benchmark_id="framework-demo",
            benchmark_profiles=["canonical", "operator-primary", "smoke"],
        ),
        paper=paper,
        scenario=scenario,
        label_map=GroundedLabelMap(
            benchmark_id="framework-demo",
            record_id_field="record_id",
            dataset_label_fields=evaluation_fields,
            target_label_fields=evaluation_fields,
            field_mappings=[],
        ),
        metrics=metrics_config,
        baselines=GroundedBaselines(benchmark_id="framework-demo"),
        profiles=["canonical", "operator-primary", "smoke"],
    )
    return GroundedBenchmarkBundle(
        workspace_root=tmp_path,
        authority=authority,
        scenario=scenario,
        paper=paper,
        label_map=authority.label_map,
        metrics=metrics_config,
        baselines=authority.baselines,
    )


def test_grouped_evidence_supports_multiple_gold_groups_and_validation() -> None:
    invalid = validate_evidence_annotation(
        {"groups": [{"atoms": ["s1", "s1"]}, {"atoms": []}]}
    )
    assert invalid.is_valid is False
    assert {issue.code for issue in invalid.issues} == {
        "duplicate_evidence_atom",
        "empty_evidence_group",
    }

    gold = normalize_evidence_annotation(
        {
            "decision": "supports",
            "groups": [
                {"group_id": "g1", "atoms": ["s1", "s2"]},
                {"group_id": "g2", "atoms": ["s3"]},
            ],
        }
    )
    prediction = normalize_evidence_annotation(
        {"decision": "supports", "groups": [{"atoms": ["s3"]}]}
    )
    scored = score_grouped_evidence(prediction=prediction, gold=gold)
    assert scored["exact_match"] == pytest.approx(1.0)
    assert scored["matched_gold_group_id"] == "g2"
    assert scored["integrity_ok"] is True


def test_answer_normalization_supporting_facts_and_unanswerable_paths() -> None:
    assert answer_exact_match("The Eiffel Tower", "eiffel tower") == pytest.approx(1.0)
    assert answer_token_f1("New York City", "new york") == pytest.approx(0.8)

    gold = {
        "answer": "Paris",
        "acceptable_answers": ["Paris", "The city of Paris"],
        "supporting_facts": [{"document_id": "doc-1", "fact_id": "s1"}],
    }
    prediction = {
        "answer": "the city of paris",
        "supporting_facts": [{"document_id": "doc-1", "fact_id": "s1"}],
    }
    assert supporting_fact_exact_match(prediction, gold) == pytest.approx(1.0)
    assert supporting_fact_f1(prediction, gold) == pytest.approx(1.0)

    scored = score_qa_with_evidence(prediction, gold)
    assert scored["answer_exact_match"] == pytest.approx(1.0)
    assert scored["joint_f1"] == pytest.approx(1.0)

    unanswerable = score_qa_with_evidence(
        {"answer": "", "supporting_facts": [], "unanswerable": True},
        {"answer": "", "supporting_facts": [], "unanswerable": True},
    )
    assert unanswerable["joint_exact_match"] == pytest.approx(1.0)
    assert unanswerable["joint_f1"] == pytest.approx(1.0)


def test_stage_scoring_separates_evidence_and_qa_metrics(tmp_path: Path) -> None:
    metrics = [
        GroundedMetricDefinition(
            metric_id="evidence_f1",
            name="Evidence Group F1",
            metric_type="evidence_group_f1",
            modes=["workflow"],
            variants=["molabel_operated"],
            stages=["workflow_reviewed"],
            fields=["evidence_bundle", "decision"],
        ),
        GroundedMetricDefinition(
            metric_id="joint_decision",
            name="Joint Decision + Evidence",
            metric_type="joint_evidence_decision",
            modes=["workflow"],
            variants=["molabel_operated"],
            stages=["workflow_reviewed"],
            fields=["evidence_bundle", "decision"],
        ),
        GroundedMetricDefinition(
            metric_id="answer_em",
            name="Answer Exact Match",
            metric_type="answer_exact_match",
            modes=["workflow"],
            variants=["molabel_operated"],
            stages=["workflow_reviewed"],
            fields=["qa_bundle"],
            weight=0.0,
        ),
        GroundedMetricDefinition(
            metric_id="answer_f1",
            name="Answer Token F1",
            metric_type="answer_token_f1",
            modes=["workflow"],
            variants=["molabel_operated"],
            stages=["workflow_reviewed"],
            fields=["qa_bundle"],
            weight=0.0,
        ),
        GroundedMetricDefinition(
            metric_id="support_em",
            name="Supporting Fact Exact Match",
            metric_type="supporting_fact_exact_match",
            modes=["workflow"],
            variants=["molabel_operated"],
            stages=["workflow_reviewed"],
            fields=["qa_bundle"],
            weight=0.0,
        ),
        GroundedMetricDefinition(
            metric_id="support_f1",
            name="Supporting Fact F1",
            metric_type="supporting_fact_f1",
            modes=["workflow"],
            variants=["molabel_operated"],
            stages=["workflow_reviewed"],
            fields=["qa_bundle"],
            weight=0.0,
        ),
        GroundedMetricDefinition(
            metric_id="joint_qa",
            name="Joint QA Score",
            metric_type="joint_answer_support",
            modes=["workflow"],
            variants=["molabel_operated"],
            stages=["workflow_reviewed"],
            fields=["qa_bundle"],
            metric_options={"joint_mode": "f1"},
            weight=0.0,
        ),
    ]
    bundle = _bundle_for_metrics(
        tmp_path,
        metrics,
        evaluation_fields=["decision", "evidence_bundle", "qa_bundle"],
    )
    gold_rows = [
        {
            "record_id": "r1",
            "labels": {
                "decision": "supports",
                "evidence_bundle": {
                    "decision": "supports",
                    "groups": [{"group_id": "g1", "atoms": ["s1", "s2"]}],
                },
                "qa_bundle": {
                    "answer": "Paris",
                    "acceptable_answers": ["Paris"],
                    "supporting_facts": [{"document_id": "doc-1", "fact_id": "s1"}],
                },
            },
        }
    ]
    predictions = [
        {
            "record_id": "r1",
            "labels": {
                "decision": "supports",
                "evidence_bundle": {
                    "decision": "supports",
                    "groups": [{"atoms": ["s1", "s2"]}],
                },
                "qa_bundle": {
                    "answer": "the paris",
                    "supporting_facts": [{"document_id": "doc-1", "fact_id": "s1"}],
                },
            },
        }
    ]

    summary = score_grounded_stage(
        bundle=bundle,
        predictions=predictions,
        gold_rows=gold_rows,
        run_id="evidence-and-qa",
        stage="workflow_reviewed",
        variant="molabel_operated",
    )

    metric_values = {metric.metric_id: metric.value for metric in summary.metrics}
    assert metric_values["evidence_f1"] == pytest.approx(1.0)
    assert metric_values["joint_decision"] == pytest.approx(1.0)
    assert metric_values["answer_em"] == pytest.approx(1.0)
    assert metric_values["support_em"] == pytest.approx(1.0)
    assert summary.diagnostics["metric_family_summaries"]["evidence"][
        "evidence_f1"
    ] == pytest.approx(1.0)
    assert summary.diagnostics["metric_family_summaries"]["qa_with_evidence"][
        "joint_qa"
    ] == pytest.approx(1.0)

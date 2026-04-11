from __future__ import annotations

from pathlib import Path

import pytest

from molabel.core.quality.grounded_benchmark_primitives import (
    GroundedLabelSetArtifact,
    build_classification_diagnostics,
    normalize_label_set_artifact,
    score_multilabel_micro_f1,
    sweep_label_thresholds,
    threshold_label_scores,
    validate_label_hierarchy,
    validate_label_set_artifact,
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
    render_grounded_stage_report,
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
        description="Benchmark primitive coverage.",
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


def test_classification_diagnostics_cover_calibration_abstention_and_routing() -> None:
    gold = {
        "r1": {"intent": "billing", "needs_review": False, "should_abstain": False},
        "r2": {"intent": "refund", "needs_review": True, "should_abstain": True},
        "r3": {"intent": "travel", "needs_review": True, "should_abstain": False},
    }
    predictions = {
        "r1": {"intent": "billing", "confidence": 0.95},
        "r2": {
            "intent": "ABSTAIN",
            "confidence": 0.2,
            "abstained": True,
            "route_to_review": True,
        },
        "r3": {
            "intent": "banking",
            "confidence": 0.3,
            "route_to_review": True,
        },
    }

    diagnostics = build_classification_diagnostics(
        predictions=predictions,
        gold=gold,
        label_field="intent",
        confidence_field="confidence",
        abstain_field="abstained",
        review_route_field="route_to_review",
        review_required_field="needs_review",
        abstain_gold_field="should_abstain",
        abstain_values=["ABSTAIN"],
        low_confidence_threshold=0.4,
    )

    assert diagnostics["abstain_rate"] == pytest.approx(1 / 3)
    assert diagnostics["abstain_precision"] == pytest.approx(1.0)
    assert diagnostics["abstain_recall"] == pytest.approx(1.0)
    assert diagnostics["review_routing_precision"] == pytest.approx(1.0)
    assert diagnostics["review_routing_recall"] == pytest.approx(1.0)
    assert diagnostics["incorrect_capture_recall"] == pytest.approx(1.0)
    assert diagnostics["calibration_available"] is True
    assert diagnostics["selective_curve"]


def test_stage_scoring_renders_classification_routing_summary(tmp_path: Path) -> None:
    metrics = [
        GroundedMetricDefinition(
            metric_id="intent_accuracy",
            name="Intent Accuracy",
            metric_type="accuracy",
            modes=["workflow"],
            variants=["molabel_operated"],
            stages=["workflow_reviewed"],
            fields=["intent"],
            metric_options={
                "classification_diagnostics": {
                    "label_field": "intent",
                    "confidence_field": "confidence",
                    "abstain_field": "abstained",
                    "review_route_field": "route_to_review",
                    "review_required_field": "needs_review",
                    "abstain_gold_field": "should_abstain",
                    "abstain_values": ["ABSTAIN"],
                    "low_confidence_threshold": 0.4,
                }
            },
        ),
        GroundedMetricDefinition(
            metric_id="abstain_precision",
            name="Abstain Precision",
            metric_type="abstain_precision",
            modes=["workflow"],
            variants=["molabel_operated"],
            stages=["workflow_reviewed"],
            fields=["intent"],
            metric_options={
                "abstain_field": "abstained",
                "abstain_gold_field": "should_abstain",
                "confidence_field": "confidence",
                "abstain_values": ["ABSTAIN"],
            },
            weight=0.0,
        ),
        GroundedMetricDefinition(
            metric_id="abstain_recall",
            name="Abstain Recall",
            metric_type="abstain_recall",
            modes=["workflow"],
            variants=["molabel_operated"],
            stages=["workflow_reviewed"],
            fields=["intent"],
            metric_options={
                "abstain_field": "abstained",
                "abstain_gold_field": "should_abstain",
                "confidence_field": "confidence",
                "abstain_values": ["ABSTAIN"],
            },
            weight=0.0,
        ),
    ]
    bundle = _bundle_for_metrics(tmp_path, metrics, evaluation_fields=["intent"])
    gold_rows = [
        {
            "record_id": "r1",
            "labels": {
                "intent": "billing",
                "needs_review": False,
                "should_abstain": False,
            },
        },
        {
            "record_id": "r2",
            "labels": {
                "intent": "refund",
                "needs_review": True,
                "should_abstain": True,
            },
        },
    ]
    predictions = [
        {"record_id": "r1", "labels": {"intent": "billing", "confidence": 0.9}},
        {
            "record_id": "r2",
            "labels": {
                "intent": "ABSTAIN",
                "abstained": True,
                "route_to_review": True,
                "confidence": 0.2,
            },
        },
    ]

    summary = score_grounded_stage(
        bundle=bundle,
        predictions=predictions,
        gold_rows=gold_rows,
        run_id="classification-routing",
        stage="workflow_reviewed",
        variant="molabel_operated",
    )

    assert summary.diagnostics["classification_routing"][
        "abstain_recall"
    ] == pytest.approx(1.0)
    report = render_grounded_stage_report(
        bundle=bundle,
        summaries=[summary],
        tax_breakdown=[],
    )
    assert "classification_routing" in report
    assert "metric_family_summaries" in report


def test_multilabel_thresholding_hierarchy_and_parser_diagnostics() -> None:
    hierarchy_result = validate_label_hierarchy(
        ["policy.child"],
        {"policy.child": ["policy.parent"]},
    )
    assert hierarchy_result.is_valid is False
    assert hierarchy_result.issues[0].code == "missing_parent_label"

    artifact = normalize_label_set_artifact(
        {"scores": {"joy": 0.9, "sadness": 0.3}, "parser_failed": False}
    )
    assert threshold_label_scores(
        artifact.scores,
        threshold=0.5,
        hierarchy={"joy": ["emotion"]},
    ) == ["emotion", "joy"]

    invalid_artifact = GroundedLabelSetArtifact(
        labels=["joy", "joy"], parser_failed=True
    )
    validation = validate_label_set_artifact(
        invalid_artifact,
        vocabulary=["joy", "sadness"],
    )
    assert validation.is_valid is False
    assert validation.diagnostics["parser_failed"] is True

    gold = {
        "r1": GroundedLabelSetArtifact(labels=["joy"]),
        "r2": GroundedLabelSetArtifact(labels=[]),
        "r3": GroundedLabelSetArtifact(labels=["sadness"]),
    }
    predictions = {
        "r1": GroundedLabelSetArtifact(scores={"joy": 0.9, "sadness": 0.2}),
        "r2": GroundedLabelSetArtifact(labels=[]),
        "r3": GroundedLabelSetArtifact(labels=[], parser_failed=True),
    }
    sweep = sweep_label_thresholds(
        gold_artifacts=gold,
        predicted_artifacts=predictions,
        thresholds=[0.2, 0.5, 0.8],
    )
    assert len(sweep) == 3
    assert max(item["micro_f1"] for item in sweep) >= 0.5

    predictions["r1"].labels = threshold_label_scores(
        predictions["r1"].scores, threshold=0.5
    )
    scored = score_multilabel_micro_f1(predictions=predictions, gold=gold)
    assert scored["details"]["parser_failure_count"] == 1
    assert scored["details"]["valid_empty_count"] == 1
    assert 0.0 <= scored["value"] <= 1.0

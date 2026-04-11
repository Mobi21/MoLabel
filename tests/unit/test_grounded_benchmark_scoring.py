from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from molabel.core.quality.grounded_benchmarks import (
    GroundedAuthorityPack,
    GroundedAuthorityPackManifest,
    GroundedBaselineEntry,
    GroundedBaselines,
    GroundedBenchmarkBundle,
    GroundedBenchmarkScenario,
    GroundedLabelMap,
    GroundedMetricDefinition,
    GroundedMetricsConfig,
    GroundedOperatorCheck,
    GroundedOperatorObservation,
    GroundedOperatorSpec,
    GroundedPaperMetadata,
    GroundedTaxDefinition,
    build_operator_diagnostics,
    compute_stage_deltas,
    compute_stage_stability,
    compute_tax_breakdown,
    render_grounded_report,
    render_grounded_stage_report,
    score_grounded_predictions,
    score_grounded_stage,
    score_operator_observations,
    summarize_operator_run,
    validate_grounded_authority_pack,
    write_run_outputs,
)


def _build_bundle(tmp_path: Path) -> GroundedBenchmarkBundle:
    scenario = GroundedBenchmarkScenario(
        benchmark_id="demo-grounded",
        name="Demo Grounded Benchmark",
        description="Shared scoring smoke test.",
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
        evaluation_fields=["label", "tags"],
        default_model_profile={
            "provider_type": "anthropic",
            "provider_name": "MiniMax",
            "model_identifier": "minimax-2.7",
            "sdk_stack": "anthropic_sdk",
            "agent_role": "proposer",
        },
    )
    paper = GroundedPaperMetadata(
        benchmark_id="demo-grounded",
        paper_title="Demo Paper",
        paper_url="https://example.com/paper",
        citation="Example et al. (2026)",
        publication_year=2026,
        dataset_name="Demo Dataset",
        dataset_url="https://example.com/dataset",
        dataset_license="CC BY 4.0",
        redistribution_status="allowed",
        task_summary="Binary classification plus tags.",
        original_task_definition="Predict one class label and supporting tags.",
        original_metrics=["accuracy", "macro_f1"],
    )
    metrics = GroundedMetricsConfig(
        benchmark_id="demo-grounded",
        primary_metric_id="paper_accuracy",
        metrics=[
            GroundedMetricDefinition(
                metric_id="paper_accuracy",
                name="Paper Accuracy",
                metric_type="accuracy",
                modes=["model"],
                variants=["paper_direct"],
                stages=["paper_model"],
                fields=["label"],
                weight=1.0,
            ),
            GroundedMetricDefinition(
                metric_id="molabel_accuracy",
                name="MoLabel Accuracy",
                metric_type="accuracy",
                modes=["model", "workflow", "operator"],
                variants=["molabel_operated"],
                stages=[
                    "molabel_model",
                    "workflow_autorun",
                    "workflow_reviewed",
                    "operator_reviewed",
                ],
                fields=["label"],
                weight=1.0,
            ),
            GroundedMetricDefinition(
                metric_id="tag_f1",
                name="Tag F1",
                metric_type="set_f1",
                modes=["workflow", "operator"],
                variants=["molabel_operated"],
                stages=["workflow_autorun", "workflow_reviewed", "operator_reviewed"],
                fields=["tags"],
                weight=0.5,
            ),
        ],
        tax_definitions=[
            GroundedTaxDefinition(
                tax_id="model_tax",
                name="Model Tax",
                minuend_mode="model",
                minuend_variant="paper_direct",
                subtrahend_mode="model",
                subtrahend_variant="molabel_operated",
                minuend_stage="paper_model",
                subtrahend_stage="molabel_model",
            ),
            GroundedTaxDefinition(
                tax_id="workflow_tax",
                name="Workflow Tax",
                minuend_mode="model",
                minuend_variant="molabel_operated",
                subtrahend_mode="workflow",
                subtrahend_variant="molabel_operated",
                minuend_stage="molabel_model",
                subtrahend_stage="workflow_autorun",
            ),
            GroundedTaxDefinition(
                tax_id="review_lift",
                name="Review Lift",
                minuend_mode="workflow",
                minuend_variant="molabel_operated",
                subtrahend_mode="workflow",
                subtrahend_variant="molabel_operated",
                minuend_stage="workflow_reviewed",
                subtrahend_stage="workflow_autorun",
            ),
            GroundedTaxDefinition(
                tax_id="operator_tax",
                name="Operator Tax",
                minuend_mode="workflow",
                minuend_variant="molabel_operated",
                subtrahend_mode="operator",
                subtrahend_variant="molabel_operated",
                minuend_stage="workflow_reviewed",
                subtrahend_stage="operator_reviewed",
            ),
        ],
    )
    authority = GroundedAuthorityPack(
        manifest=GroundedAuthorityPackManifest(
            benchmark_id="demo-grounded",
            benchmark_profiles=["canonical", "operator-primary", "smoke"],
            source_manifest_paths=["authority/manifest.yaml"],
            notes=["demo authority pack"],
        ),
        paper=paper,
        scenario=scenario,
        label_map=GroundedLabelMap(
            benchmark_id="demo-grounded",
            record_id_field="record_id",
            dataset_label_fields=["label", "tags"],
            target_label_fields=["label", "tags"],
            field_mappings=[],
        ),
        metrics=metrics,
        baselines=GroundedBaselines(benchmark_id="demo-grounded"),
        operator=None,
        profiles=[
            "canonical",
            "operator-primary",
            "smoke",
        ],
    )
    authority.metrics = metrics
    authority.baselines = GroundedBaselines(
        benchmark_id="demo-grounded",
        baselines=[
            GroundedBaselineEntry(
                baseline_id="paper_baseline",
                name="Paper Baseline",
                source="paper",
                mode="model",
                variant="paper_direct",
                stage="paper_model",
                split_id="test",
                metrics={"paper_accuracy": 0.8},
            )
        ],
    )
    return GroundedBenchmarkBundle(
        workspace_root=tmp_path,
        authority=authority,
        scenario=scenario,
        paper=paper,
        label_map=authority.label_map,
        metrics=metrics,
        baselines=authority.baselines,
    )


def test_grounded_authority_pack_validation_and_stage_report(
    tmp_path: Path,
) -> None:
    bundle = _build_bundle(tmp_path)

    validation = validate_grounded_authority_pack(bundle.authority)
    assert validation.is_valid
    assert validation.issues == []
    assert [profile.profile_id for profile in validation.profiles] == [
        "canonical",
        "operator-primary",
        "smoke",
    ]
    assert bundle.authority.manifest.layout == "authority"

    gold_rows = [
        {"record_id": "r1", "labels": {"label": "yes", "tags": ["a", "b"]}},
        {"record_id": "r2", "labels": {"label": "no", "tags": ["c"]}},
    ]
    paper_predictions = [
        {"record_id": "r1", "labels": {"label": "yes"}},
        {"record_id": "r2", "labels": {"label": "yes"}},
    ]
    model_predictions = [
        {"record_id": "r1", "labels": {"label": "yes"}},
        {"record_id": "r2", "labels": {"label": "no"}},
    ]
    workflow_autorun_predictions = [
        {"record_id": "r1", "labels": {"label": "yes", "tags": ["a"]}},
        {"record_id": "r2", "labels": {"label": "no", "tags": ["c"]}},
    ]
    workflow_reviewed_predictions = [
        {"record_id": "r1", "labels": {"label": "yes", "tags": ["a", "b"]}},
        {"record_id": "r2", "labels": {"label": "no", "tags": ["c"]}},
    ]
    operator_predictions = [
        {"record_id": "r1", "labels": {"label": "no", "tags": ["a"]}},
        {"record_id": "r2", "labels": {"label": "no", "tags": []}},
    ]

    paper_summary = score_grounded_stage(
        bundle=bundle,
        predictions=paper_predictions,
        gold_rows=gold_rows,
        run_id="paper-stage",
        stage="paper_model",
        variant="paper_direct",
    )
    model_summary = score_grounded_stage(
        bundle=bundle,
        predictions=model_predictions,
        gold_rows=gold_rows,
        run_id="model-stage",
        stage="molabel_model",
        variant="molabel_operated",
    )
    workflow_autorun_summary = score_grounded_stage(
        bundle=bundle,
        predictions=workflow_autorun_predictions,
        gold_rows=gold_rows,
        run_id="workflow-autorun-stage",
        stage="workflow_autorun",
        variant="molabel_operated",
    )
    workflow_reviewed_summary = score_grounded_stage(
        bundle=bundle,
        predictions=workflow_reviewed_predictions,
        gold_rows=gold_rows,
        run_id="workflow-reviewed-stage",
        stage="workflow_reviewed",
        variant="molabel_operated",
    )
    operator_summary = score_grounded_stage(
        bundle=bundle,
        predictions=operator_predictions,
        gold_rows=gold_rows,
        run_id="operator-stage",
        stage="operator_reviewed",
        variant="molabel_operated",
    )

    taxes = compute_stage_deltas(
        [
            paper_summary,
            model_summary,
            workflow_autorun_summary,
            workflow_reviewed_summary,
            operator_summary,
        ],
        bundle.metrics,
    )
    assert {tax.tax_id for tax in taxes} == {
        "model_tax",
        "workflow_tax",
        "review_lift",
        "operator_tax",
    }
    assert any(tax.value > 0 for tax in taxes)
    assert any(tax.value < 0 for tax in taxes)

    report = render_grounded_stage_report(
        bundle=bundle,
        summaries=[
            paper_summary,
            model_summary,
            workflow_autorun_summary,
            workflow_reviewed_summary,
            operator_summary,
        ],
        tax_breakdown=taxes,
    )
    assert "paper-stage" in report
    assert "workflow_autorun" in report
    assert "workflow_reviewed" in report
    assert "review_lift" in report


def test_grounded_scoring_and_tax_pipeline(tmp_path: Path) -> None:
    bundle = _build_bundle(tmp_path)
    gold_rows = [
        {"record_id": "r1", "labels": {"label": "yes", "tags": ["a", "b"]}},
        {"record_id": "r2", "labels": {"label": "no", "tags": ["c"]}},
    ]

    paper_predictions = [
        {"record_id": "r1", "labels": {"label": "yes"}},
        {"record_id": "r2", "labels": {"label": "yes"}},
    ]
    model_predictions = [
        {"record_id": "r1", "labels": {"label": "yes"}},
        {"record_id": "r2", "labels": {"label": "no"}},
    ]
    workflow_autorun_predictions = [
        {"record_id": "r1", "labels": {"label": "yes", "tags": ["a"]}},
        {"record_id": "r2", "labels": {"label": "no", "tags": ["c"]}},
    ]
    workflow_reviewed_predictions = [
        {"record_id": "r1", "labels": {"label": "yes", "tags": ["a", "b"]}},
        {"record_id": "r2", "labels": {"label": "no", "tags": ["c"]}},
    ]
    operator_predictions = [
        {"record_id": "r1", "labels": {"label": "no", "tags": ["a"]}},
        {"record_id": "r2", "labels": {"label": "no", "tags": []}},
    ]

    paper_summary = score_grounded_stage(
        bundle=bundle,
        predictions=paper_predictions,
        gold_rows=gold_rows,
        run_id="paper-direct-run",
        stage="paper_model",
        variant="paper_direct",
    )
    model_summary = score_grounded_stage(
        bundle=bundle,
        predictions=model_predictions,
        gold_rows=gold_rows,
        run_id="molabel-model-run",
        stage="molabel_model",
        variant="molabel_operated",
    )
    workflow_autorun_summary = score_grounded_stage(
        bundle=bundle,
        predictions=workflow_autorun_predictions,
        gold_rows=gold_rows,
        run_id="workflow-autorun-run",
        stage="workflow_autorun",
        variant="molabel_operated",
    )
    workflow_reviewed_summary = score_grounded_stage(
        bundle=bundle,
        predictions=workflow_reviewed_predictions,
        gold_rows=gold_rows,
        run_id="workflow-reviewed-run",
        stage="workflow_reviewed",
        variant="molabel_operated",
    )
    operator_summary = score_grounded_stage(
        bundle=bundle,
        predictions=operator_predictions,
        gold_rows=gold_rows,
        run_id="operator-run",
        stage="operator_reviewed",
        variant="molabel_operated",
    )

    taxes = compute_stage_deltas(
        [
            paper_summary,
            model_summary,
            workflow_autorun_summary,
            workflow_reviewed_summary,
            operator_summary,
        ],
        bundle.metrics,
    )
    workflow_reviewed_summary.tax_breakdown = taxes

    assert paper_summary.overall_score == 0.5
    assert model_summary.overall_score == 1.0
    assert (
        workflow_autorun_summary.overall_score < workflow_reviewed_summary.overall_score
    )
    assert workflow_reviewed_summary.overall_score > operator_summary.overall_score
    assert {tax.tax_id for tax in taxes} == {
        "model_tax",
        "workflow_tax",
        "review_lift",
        "operator_tax",
    }

    legacy_taxes = compute_tax_breakdown(
        [paper_summary, model_summary, workflow_reviewed_summary, operator_summary],
        bundle.metrics,
    )
    assert {tax.tax_id for tax in legacy_taxes} == {
        "model_tax",
        "workflow_tax",
        "review_lift",
        "operator_tax",
    }

    legacy_report = render_grounded_report(
        bundle=bundle,
        summary=workflow_reviewed_summary,
    )
    report = render_grounded_stage_report(
        bundle=bundle,
        summaries=[
            paper_summary,
            model_summary,
            workflow_autorun_summary,
            workflow_reviewed_summary,
            operator_summary,
        ],
        tax_breakdown=taxes,
    )
    assert "Demo Grounded Benchmark" in report
    assert "workflow_tax" in report
    assert "review_lift" in report
    assert "workflow_reviewed" in report
    assert legacy_report

    summary_path, report_path = write_run_outputs(
        workflow_reviewed_summary,
        report,
        tmp_path / "workbench" / "benchmarks" / "runs",
        evidence={
            "inputs/gold_rows.json": gold_rows,
            "outputs/predictions.json": workflow_reviewed_predictions,
            "logs/test_context.json": {"api_calls": []},
        },
    )
    assert summary_path.exists()
    assert report_path.exists()
    assert workflow_reviewed_summary.summary_version == 4
    evidence_manifest = summary_path.parent / "evidence_manifest.json"
    assert evidence_manifest.exists()
    assert (summary_path.parent / "evidence" / "inputs" / "gold_rows.json").exists()
    assert (summary_path.parent / "evidence" / "outputs" / "predictions.json").exists()


def test_stage_diagnostics_cover_integrity_confusion_and_subsets(
    tmp_path: Path,
) -> None:
    bundle = _build_bundle(tmp_path)
    gold_rows = [
        {"record_id": "r1", "labels": {"label": "yes", "tags": ["a"]}},
        {"record_id": "r2", "labels": {"label": "no", "tags": ["b"]}},
    ]
    predictions = [
        {"record_id": "r1", "labels": {"label": "no", "tags": ["a"]}},
        {"record_id": "r1", "labels": {"label": "yes", "tags": ["a"]}},
        {"record_id": "r3", "labels": {"label": "yes", "tags": []}},
    ]
    context_rows = [
        {"record_id": "r1", "source_split": "test"},
        {"record_id": "r2", "source_split": "oos_test"},
    ]

    summary = score_grounded_stage(
        bundle=bundle,
        predictions=predictions,
        gold_rows=gold_rows,
        run_id="diagnostic-stage",
        stage="workflow_reviewed",
        variant="molabel_operated",
        context_rows=context_rows,
    )

    coverage = summary.diagnostics["coverage"]
    assert coverage["missing_prediction_count"] == 1
    assert coverage["extra_prediction_count"] == 1
    assert coverage["duplicate_prediction_count"] == 1
    assert "Coverage integrity warning" in " ".join(summary.notes)

    confusion = summary.diagnostics["confusion"]["label"]["top_confusions"]
    assert confusion[0]["gold"] == "no"
    assert confusion[0]["predicted"] == "<missing>"

    subsets = summary.diagnostics["subset_breakdowns"]
    assert subsets["gold.label"]["yes"]["count"] == 1
    assert subsets["context.source_split"]["test"]["count"] == 1


def test_stage_diagnostics_exact_match_uses_scored_fields_only(
    tmp_path: Path,
) -> None:
    bundle = _build_bundle(tmp_path)
    gold_rows = [
        {"record_id": "r1", "labels": {"label": "yes", "tags": ["a"]}},
        {"record_id": "r2", "labels": {"label": "no", "tags": ["b"]}},
    ]
    predictions = [
        {
            "record_id": "r1",
            "labels": {"label": "yes", "tags": ["a"], "notes": "longer proposal"},
        },
        {
            "record_id": "r2",
            "labels": {"label": "no", "tags": ["b"], "notes": "shorter review"},
        },
    ]
    context_rows = [
        {"record_id": "r1", "source_split": "test"},
        {"record_id": "r2", "source_split": "oos_test"},
    ]

    summary = score_grounded_stage(
        bundle=bundle,
        predictions=predictions,
        gold_rows=gold_rows,
        run_id="field-scoped-exact-match",
        stage="workflow_reviewed",
        variant="molabel_operated",
        context_rows=context_rows,
    )

    assert summary.metrics[0].value == pytest.approx(1.0)
    assert summary.metrics[1].value == pytest.approx(1.0)
    assert summary.diagnostics["exact_match_count"] == 2
    assert summary.diagnostics["exact_match_rate"] == pytest.approx(1.0)
    assert (
        summary.diagnostics["subset_breakdowns"]["context.source_split"]["test"][
            "exact_match_count"
        ]
        == 1
    )


def test_tax_deltas_and_stability_are_machine_readable(tmp_path: Path) -> None:
    bundle = _build_bundle(tmp_path)
    gold_rows = [
        {"record_id": "r1", "labels": {"label": "yes", "tags": ["a"]}},
        {"record_id": "r2", "labels": {"label": "no", "tags": ["b"]}},
    ]
    better_predictions = [
        {"record_id": "r1", "labels": {"label": "yes", "tags": ["a"]}},
        {"record_id": "r2", "labels": {"label": "no", "tags": ["b"]}},
    ]
    worse_predictions = [
        {"record_id": "r1", "labels": {"label": "yes", "tags": []}},
        {"record_id": "r2", "labels": {"label": "yes", "tags": []}},
    ]

    workflow_a = score_grounded_stage(
        bundle=bundle,
        predictions=worse_predictions,
        gold_rows=gold_rows,
        run_id="workflow-a",
        stage="workflow_autorun",
        variant="molabel_operated",
    )
    workflow_b = score_grounded_stage(
        bundle=bundle,
        predictions=better_predictions,
        gold_rows=gold_rows,
        run_id="workflow-b",
        stage="workflow_reviewed",
        variant="molabel_operated",
    )
    workflow_b_retry = workflow_b.model_copy(update={"run_id": "workflow-b-retry"})

    taxes = compute_stage_deltas([workflow_a, workflow_b], bundle.metrics)
    review_lift = next(tax for tax in taxes if tax.tax_id == "review_lift")
    assert "molabel_accuracy" in review_lift.metric_deltas
    assert review_lift.metric_deltas["molabel_accuracy"] > 0

    stability = compute_stage_stability([workflow_b, workflow_b_retry])
    assert len(stability) == 1
    assert stability[0].run_count == 2
    assert stability[0].overall_stddev == pytest.approx(0.0)

    report = render_grounded_stage_report(
        bundle=bundle,
        summaries=[workflow_b, workflow_b_retry],
        tax_breakdown=[],
    )
    assert "## Stability" in report


def test_additional_grounded_metric_types(tmp_path: Path) -> None:
    bundle = _build_bundle(tmp_path)
    bundle.metrics.metrics = [
        GroundedMetricDefinition(
            metric_id="binary_recall",
            name="Binary Recall",
            metric_type="binary_recall",
            modes=["model"],
            variants=["paper_direct"],
            fields=["flag"],
            positive_value=True,
        ),
        GroundedMetricDefinition(
            metric_id="jaccard",
            name="Set Jaccard",
            metric_type="jaccard",
            modes=["model"],
            variants=["paper_direct"],
            fields=["targets"],
        ),
        GroundedMetricDefinition(
            metric_id="token_mask_f1",
            name="Token Mask F1",
            metric_type="token_mask_f1",
            modes=["model"],
            variants=["paper_direct"],
            fields=["mask"],
        ),
    ]

    gold_rows = [
        {
            "record_id": "r1",
            "labels": {"flag": True, "targets": ["a", "b"], "mask": [1, 0, 1]},
        },
        {
            "record_id": "r2",
            "labels": {"flag": False, "targets": ["c"], "mask": [0, 1, 0]},
        },
    ]
    predictions = [
        {
            "record_id": "r1",
            "labels": {"flag": True, "targets": ["a"], "mask": [1, 0, 0]},
        },
        {
            "record_id": "r2",
            "labels": {"flag": True, "targets": ["c", "d"], "mask": [0, 1, 0]},
        },
    ]

    summary = score_grounded_predictions(
        bundle=bundle,
        predictions=predictions,
        gold_rows=gold_rows,
        run_id="metric-types",
        mode="model",
        variant="paper_direct",
    )

    metric_values = {metric.metric_id: metric.value for metric in summary.metrics}
    assert metric_values["binary_recall"] == 1.0
    assert 0.5 <= metric_values["jaccard"] < 1.0
    assert 0.5 <= metric_values["token_mask_f1"] < 1.0


def test_feverous_score_metric(tmp_path: Path) -> None:
    bundle = _build_bundle(tmp_path)
    bundle.metrics.metrics = [
        GroundedMetricDefinition(
            metric_id="feverous_score",
            name="FEVEROUS Score",
            metric_type="feverous_score",
            modes=["model"],
            variants=["paper_direct"],
        )
    ]

    gold_rows = [
        {
            "record_id": "r1",
            "labels": {
                "paper_label": "SUPPORTS",
                "paper_evidence_sets": [["page_a_sentence_0", "page_b_cell_1"]],
            },
        },
        {
            "record_id": "r2",
            "labels": {
                "paper_label": "NOT ENOUGH INFO",
                "paper_evidence_sets": [["page_c_sentence_0"]],
            },
        },
    ]
    predictions = [
        {
            "record_id": "r1",
            "labels": {
                "verdict": "supports",
                "evidence_atoms": ["page_a_sentence_0", "page_b_cell_1"],
            },
        },
        {
            "record_id": "r2",
            "labels": {
                "verdict": "nei",
                "evidence_atoms": [],
            },
        },
    ]

    summary = score_grounded_predictions(
        bundle=bundle,
        predictions=predictions,
        gold_rows=gold_rows,
        run_id="feverous-score",
        mode="model",
        variant="paper_direct",
    )

    assert summary.overall_score == 1.0
    assert summary.metrics[0].metric_id == "feverous_score"


def test_feverous_score_metric_accepts_scifact_verdict_vocabulary(
    tmp_path: Path,
) -> None:
    """The shared verification scorer should accept SciFact-style verdicts.

    SciFact uses SUPPORT / CONTRADICT / NOT_ENOUGH_INFO. This is semantically
    identical to FEVEROUS's SUPPORTS / REFUTES / NOT ENOUGH INFO and should
    score the same after verdict normalization.
    """
    bundle = _build_bundle(tmp_path)
    bundle.metrics.metrics = [
        GroundedMetricDefinition(
            metric_id="feverous_score",
            name="FEVEROUS Score",
            metric_type="feverous_score",
            modes=["model"],
            variants=["paper_direct"],
        )
    ]

    gold_rows = [
        {
            "record_id": "s1",
            "labels": {
                "paper_label": "SUPPORT",
                "paper_evidence_sets": [["doc_1_sentence_2"]],
            },
        },
        {
            "record_id": "s2",
            "labels": {
                "paper_label": "CONTRADICT",
                "paper_evidence_sets": [["doc_2_sentence_0", "doc_2_sentence_1"]],
            },
        },
        {
            "record_id": "s3",
            "labels": {
                "paper_label": "NOT_ENOUGH_INFO",
                "paper_evidence_sets": [[]],
            },
        },
    ]
    predictions = [
        {
            "record_id": "s1",
            "labels": {
                "verdict": "support",
                "evidence_atoms": ["doc_1_sentence_2"],
            },
        },
        {
            "record_id": "s2",
            "labels": {
                "verdict": "contradict",
                "evidence_atoms": ["doc_2_sentence_0", "doc_2_sentence_1"],
            },
        },
        {
            "record_id": "s3",
            "labels": {
                "verdict": "not_enough_info",
                "evidence_atoms": [],
            },
        },
    ]

    summary = score_grounded_predictions(
        bundle=bundle,
        predictions=predictions,
        gold_rows=gold_rows,
        run_id="feverous-score-scifact-vocab",
        mode="model",
        variant="paper_direct",
    )

    assert summary.overall_score == 1.0
    assert summary.metrics[0].metric_id == "feverous_score"


def test_operator_checklist_scoring() -> None:
    spec = GroundedOperatorSpec(
        benchmark_id="operator-demo",
        goal="Score Codex as operator.",
        checks=[
            GroundedOperatorCheck(
                check_id="uses_public_cli_or_api_only",
                phase="setup",
                description="Uses only public surfaces.",
                weight=1.0,
            ),
            GroundedOperatorCheck(
                check_id="configures_minimax_2_7_profile",
                phase="setup",
                description="Configures MiniMax 2.7.",
                weight=1.0,
            ),
            GroundedOperatorCheck(
                check_id="preserves_artifact_integrity",
                phase="scoring",
                description="Leaves artifacts valid.",
                weight=2.0,
            ),
        ],
    )

    result = score_operator_observations(
        spec,
        [
            GroundedOperatorObservation(
                check_id="uses_public_cli_or_api_only",
                passed=True,
            ),
            GroundedOperatorObservation(
                check_id="configures_minimax_2_7_profile",
                passed=False,
            ),
            GroundedOperatorObservation(
                check_id="preserves_artifact_integrity",
                passed=True,
            ),
        ],
    )

    assert result.value == 0.75
    assert result.details["missing_required"] == []
    assert result.details["per_check"]["configures_minimax_2_7_profile"] is False


def test_operator_summary_combines_label_quality_and_checklist(tmp_path: Path) -> None:
    bundle = replace(
        _build_bundle(tmp_path),
        operator=GroundedOperatorSpec(
            benchmark_id="demo-grounded",
            goal="Score Codex as operator.",
            label_quality_weight=0.8,
            checklist_weight=0.2,
            blocking_check_ids=["uses_public_cli_or_api_only"],
            checks=[
                GroundedOperatorCheck(
                    check_id="uses_public_cli_or_api_only",
                    phase="setup",
                    description="Uses only public surfaces.",
                    weight=1.0,
                ),
                GroundedOperatorCheck(
                    check_id="writes_benchmark_run_artifacts",
                    phase="scoring",
                    description="Writes summary and report.",
                    weight=1.0,
                ),
            ],
        ),
    )

    gold_rows = [
        {"record_id": "r1", "labels": {"label": "yes", "tags": ["a"]}},
        {"record_id": "r2", "labels": {"label": "no", "tags": ["b"]}},
    ]
    operator_predictions = [
        {"record_id": "r1", "labels": {"label": "yes", "tags": ["a"]}},
        {"record_id": "r2", "labels": {"label": "yes", "tags": []}},
    ]

    label_summary = score_grounded_predictions(
        bundle=bundle,
        predictions=operator_predictions,
        gold_rows=gold_rows,
        run_id="operator-labels",
        mode="operator",
        variant="molabel_operated",
    )
    combined_summary = summarize_operator_run(
        bundle=bundle,
        label_summary=label_summary,
        observations=[
            GroundedOperatorObservation(
                check_id="uses_public_cli_or_api_only",
                passed=False,
            ),
            GroundedOperatorObservation(
                check_id="writes_benchmark_run_artifacts",
                passed=True,
            ),
        ],
        run_id="operator-final",
    )

    assert combined_summary.run_id == "operator-final"
    assert combined_summary.metrics[-1].metric_id == "operator_checklist"
    assert combined_summary.metrics[-1].value == 0.5
    assert combined_summary.overall_score == 0.5
    assert any(
        "Blocking operator checks failed" in note for note in combined_summary.notes
    )

    report = render_grounded_report(bundle=bundle, summary=combined_summary)
    assert "operator_checklist" in report
    assert "`uses_public_cli_or_api_only`: `fail`" in report


def test_operator_diagnostics_capture_lift_and_truthfulness(
    tmp_path: Path,
) -> None:
    bundle = _build_bundle(tmp_path)

    gold_rows = [
        {"record_id": "r1", "labels": {"label": "yes", "tags": ["a", "b"]}},
        {"record_id": "r2", "labels": {"label": "no", "tags": ["c"]}},
    ]
    proposal_rows = [
        {"record_id": "r1", "labels": {"label": "no", "tags": ["a", "b"]}},
        {"record_id": "r2", "labels": {"label": "no", "tags": ["c"]}},
    ]
    review_rows = [
        {"record_id": "r1", "labels": {"label": "yes", "tags": ["a", "b"]}},
        {"record_id": "r2", "labels": {"label": "yes", "tags": ["c"]}},
    ]
    review_events = [
        {"record_id": "r1", "decision": "edit", "ai_was_revealed": True},
        {"record_id": "r2", "decision": "accept"},
    ]
    shell_audit = {
        "shell_commands": [
            "molabel queue claim q1",
            "molabel queue claim q1",
            "molabel review reveal-ai task-1",
            "molabel review reveal-ai task-1",
            "molabel queue status q1",
            "molabel queue status q1",
            "cat workbench/benchmarks/splits/test.jsonl",
            "cat workbench/benchmarks/splits/test.jsonl",
        ],
        "non_cli_surface_commands": [],
        "hidden_benchmark_path_commands": ["ls authority"],
        "truth_probe_commands": [],
        "queue_claim_commands": [
            "molabel queue claim q1",
            "molabel queue claim q1",
        ],
        "reveal_ai_commands": [
            "molabel review reveal-ai task-1",
            "molabel review reveal-ai task-1",
        ],
        "status_poll_commands": [
            "molabel queue status q1",
            "molabel queue status q1",
        ],
        "repeated_poll_commands": ["molabel queue status q1"],
        "duplicate_shell_commands": [
            "molabel queue claim q1",
            "molabel review reveal-ai task-1",
            "molabel queue status q1",
            "cat workbench/benchmarks/splits/test.jsonl",
        ],
        "redundant_read_commands": ["cat workbench/benchmarks/splits/test.jsonl"],
    }
    report_text = (
        "Accepted all 2 AI proposals\n"
        "Review submissions persisted: `2`\n"
        "Non-CLI surface commands: `0`\n"
        "Hidden benchmark path commands: `0`\n"
        "Truth probe commands: `0`\n"
    )

    diagnostics = build_operator_diagnostics(
        gold_rows=gold_rows,
        proposal_rows=proposal_rows,
        review_rows=review_rows,
        evaluation_fields=["label", "tags"],
        review_events=review_events,
        shell_audit=shell_audit,
        report_text=report_text,
        source_rows=[
            {"record_id": "r1", "source_split": "test"},
            {"record_id": "r2", "source_split": "oos_test"},
        ],
        benchmark_human_rows=[
            {
                "record_id": "r1",
                "labels": {"label": "no", "tags": ["a", "b"]},
                "is_intentionally_wrong": True,
            }
        ],
        benchmark_review_rows=[
            {
                "record_id": "r2",
                "labels": {"label": "yes", "tags": ["c"]},
            }
        ],
        summary_payload={
            "benchmark_id": "demo-grounded",
            "record_count": 2,
            "submitted_count": 2,
            "proposal_coverage": 2,
            "proposal_success": 2,
            "proposal_failures": 0,
            "accept_ai_rate": 0.0,
            "hidden_benchmark_path_command_count": 0,
        },
        expected_benchmark_id="demo-grounded",
    )

    assert diagnostics.record_count == 2
    assert diagnostics.proposal_exact_match_rate == pytest.approx(0.5)
    assert diagnostics.review_exact_match_rate == pytest.approx(0.5)
    assert diagnostics.changed_count == 2
    assert diagnostics.corrected_count == 1
    assert diagnostics.regressed_count == 1
    assert diagnostics.operator_lift_count == 0
    assert diagnostics.review_event_count == 2
    assert diagnostics.final_decision_count == 2
    assert diagnostics.audit_summary["repeated_poll_command_count"] == 1
    assert diagnostics.audit_summary["unnecessary_reveal_ai_command_count"] == 1
    assert diagnostics.hard_case_breakdown["proposal_wrong"]["count"] == 1
    assert (
        diagnostics.hard_case_breakdown["benchmark_intentionally_wrong"]["count"] == 1
    )
    assert diagnostics.confidence_diagnostics["available"] is False
    assert diagnostics.accept_ai_count == 1
    assert diagnostics.edit_ai_count == 1
    assert diagnostics.decision_quality["raw_decision_counts"] == {
        "accept": 1,
        "edit": 1,
    }
    assert diagnostics.truthfulness_ok is False
    assert any(
        check.check_id == "report_accept_all_ai_claim" and not check.passed
        for check in diagnostics.truthfulness_checks
    )
    assert any(
        check.check_id == "report_hidden_benchmark_path_command_count"
        and not check.passed
        for check in diagnostics.truthfulness_checks
    )
    assert any(
        check.check_id == "summary_hidden_benchmark_path_command_count"
        and not check.passed
        for check in diagnostics.truthfulness_checks
    )
    assert any(
        check.check_id == "summary_accept_ai_rate" and not check.passed
        for check in diagnostics.truthfulness_checks
    )

    operator_summary = score_grounded_stage(
        bundle=bundle,
        predictions=review_rows,
        gold_rows=gold_rows,
        run_id="diagnostics-stage",
        stage="operator_reviewed",
        variant="molabel_operated",
    )
    operator_summary = operator_summary.model_copy(
        update={"diagnostics": diagnostics.model_dump(mode="json")}
    )
    report = render_grounded_stage_report(
        bundle=bundle,
        summaries=[operator_summary],
        tax_breakdown=[],
    )
    assert "## Diagnostics" in report
    assert "truthfulness_ok" in report
    assert "operator_lift_count" in report
    assert "artifact_truthfulness" in report

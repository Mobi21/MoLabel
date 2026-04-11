from __future__ import annotations

from pathlib import Path

import pytest

from molabel.core.quality.grounded_benchmark_primitives import (
    score_anls,
    validate_grounded_anchor,
    validate_grounded_generation_artifact,
    validate_grounded_ranking_artifact,
    validate_span_annotation,
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
        description="Ranking, span, generation, and grounding primitives.",
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


def test_ranking_validation_span_validation_generation_validation_and_anchors() -> None:
    ranking_validation = validate_grounded_ranking_artifact(
        {
            "results": [{"result_id": "d1"}, {"result_id": "d1"}],
            "expected_depth": 3,
        },
        fixed_depth=3,
        require_corpus_metadata=True,
    )
    assert ranking_validation.is_valid is False
    assert {issue.code for issue in ranking_validation.issues} >= {
        "duplicate_result_id",
        "unexpected_ranking_depth",
        "missing_corpus_snapshot",
        "missing_corpus_hash",
    }

    span_validation = validate_span_annotation(
        {
            "source_text": "abcdef",
            "spans": [
                {
                    "segments": [
                        {"char_start": 2, "char_end": 1},
                        {"char_start": 0, "char_end": 2},
                    ]
                }
            ],
        }
    )
    assert span_validation.is_valid is False
    assert {issue.code for issue in span_validation.issues} >= {
        "invalid_char_offsets",
        "unordered_char_segments",
    }

    generation_validation = validate_grounded_generation_artifact(
        {
            "text": "Paris is in France.",
            "claims": [{"text": "Paris is in France.", "anchor_ids": ["a-unknown"]}],
            "available_anchor_ids": ["a-1"],
            "structured_output": {},
        },
        required_fields=["summary"],
    )
    assert generation_validation.is_valid is False
    assert {issue.code for issue in generation_validation.issues} == {
        "unknown_anchor_id",
        "missing_required_field",
    }

    doc_anchor = validate_grounded_anchor(
        {
            "anchor_type": "document",
            "document_id": "doc-1",
            "page_number": 2,
            "section_path": ["methods", "results"],
            "lossless": False,
            "warning": "Sentence-level grounding was flattened from paragraph scope.",
        }
    )
    table_anchor = validate_grounded_anchor(
        {
            "anchor_type": "table_cell",
            "document_id": "doc-1",
            "table_id": "tbl-1",
            "row_id": "r2",
            "column_id": "c4",
        }
    )
    assert doc_anchor.is_valid is True
    assert doc_anchor.issues[0].severity == "warning"
    assert table_anchor.is_valid is True


def test_stage_scoring_supports_ranking_span_generation_and_anls(
    tmp_path: Path,
) -> None:
    metrics = [
        GroundedMetricDefinition(
            metric_id="mrr",
            name="MRR",
            metric_type="mrr",
            modes=["workflow"],
            variants=["molabel_operated"],
            stages=["workflow_reviewed"],
            fields=["ranking"],
            metric_options={
                "qrels_field": "qrels",
                "k": 3,
                "fixed_depth": 3,
                "require_corpus_metadata": True,
            },
        ),
        GroundedMetricDefinition(
            metric_id="ndcg3",
            name="nDCG@3",
            metric_type="ndcg_at_k",
            modes=["workflow"],
            variants=["molabel_operated"],
            stages=["workflow_reviewed"],
            fields=["ranking"],
            metric_options={"qrels_field": "qrels", "k": 3},
            weight=0.0,
        ),
        GroundedMetricDefinition(
            metric_id="recall3",
            name="Recall@3",
            metric_type="recall_at_k",
            modes=["workflow"],
            variants=["molabel_operated"],
            stages=["workflow_reviewed"],
            fields=["ranking"],
            metric_options={"qrels_field": "qrels", "k": 3},
            weight=0.0,
        ),
        GroundedMetricDefinition(
            metric_id="precision3",
            name="Precision@3",
            metric_type="precision_at_k",
            modes=["workflow"],
            variants=["molabel_operated"],
            stages=["workflow_reviewed"],
            fields=["ranking"],
            metric_options={"qrels_field": "qrels", "k": 3},
            weight=0.0,
        ),
        GroundedMetricDefinition(
            metric_id="map",
            name="MAP",
            metric_type="map",
            modes=["workflow"],
            variants=["molabel_operated"],
            stages=["workflow_reviewed"],
            fields=["ranking"],
            metric_options={"qrels_field": "qrels", "k": 3},
            weight=0.0,
        ),
        GroundedMetricDefinition(
            metric_id="span_em",
            name="Span Exact Match",
            metric_type="span_exact_match",
            modes=["workflow"],
            variants=["molabel_operated"],
            stages=["workflow_reviewed"],
            fields=["spans"],
            weight=0.0,
        ),
        GroundedMetricDefinition(
            metric_id="span_overlap",
            name="Span Overlap F1",
            metric_type="span_overlap_f1",
            modes=["workflow"],
            variants=["molabel_operated"],
            stages=["workflow_reviewed"],
            fields=["spans"],
            weight=0.0,
        ),
        GroundedMetricDefinition(
            metric_id="source_coverage",
            name="Source Coverage",
            metric_type="source_coverage",
            modes=["workflow"],
            variants=["molabel_operated"],
            stages=["workflow_reviewed"],
            fields=["generation"],
            metric_options={"required_fields": ["summary"]},
            weight=0.0,
        ),
        GroundedMetricDefinition(
            metric_id="unsupported_rate",
            name="Unsupported Content Rate",
            metric_type="unsupported_content_rate",
            modes=["workflow"],
            variants=["molabel_operated"],
            stages=["workflow_reviewed"],
            fields=["generation"],
            metric_options={"required_fields": ["summary"]},
            weight=0.0,
        ),
        GroundedMetricDefinition(
            metric_id="grounded_generation",
            name="Grounded Generation Score",
            metric_type="grounded_generation_score",
            modes=["workflow"],
            variants=["molabel_operated"],
            stages=["workflow_reviewed"],
            fields=["generation"],
            metric_options={"required_fields": ["summary"]},
            weight=0.0,
        ),
        GroundedMetricDefinition(
            metric_id="anls",
            name="ANLS",
            metric_type="anls",
            modes=["workflow"],
            variants=["molabel_operated"],
            stages=["workflow_reviewed"],
            fields=["qa_bundle"],
            weight=0.0,
        ),
    ]
    bundle = _bundle_for_metrics(
        tmp_path,
        metrics,
        evaluation_fields=["ranking", "spans", "generation", "qa_bundle"],
    )
    gold_rows = [
        {
            "record_id": "r1",
            "labels": {
                "qrels": {"d2": 2.0, "d1": 1.0},
                "spans": {
                    "source_text": "alpha beta gamma",
                    "spans": [{"segments": [{"char_start": 6, "char_end": 10}]}],
                },
                "generation": {
                    "text": "Paris is in France.",
                    "claims": [{"claim_id": "c1", "text": "Paris is in France."}],
                    "structured_output": {"summary": "Paris is in France."},
                },
                "qa_bundle": {
                    "answer": "Invoice 100",
                    "acceptable_answers": ["invoice-100"],
                },
            },
        }
    ]
    predictions = [
        {
            "record_id": "r1",
            "labels": {
                "ranking": {
                    "results": [
                        {"result_id": "d2", "score": 0.9},
                        {"result_id": "d1", "score": 0.8},
                        {"result_id": "d3", "score": 0.1},
                    ],
                    "expected_depth": 3,
                    "corpus_snapshot_id": "snap-1",
                    "corpus_hash": "sha256:demo",
                },
                "spans": {
                    "source_text": "alpha beta gamma",
                    "spans": [{"segments": [{"char_start": 6, "char_end": 10}]}],
                },
                "generation": {
                    "text": "Paris is in France.",
                    "claims": [
                        {
                            "claim_id": "c1",
                            "text": "Paris is in France.",
                            "anchor_ids": ["a-1"],
                        }
                    ],
                    "available_anchor_ids": ["a-1"],
                    "structured_output": {"summary": "Paris is in France."},
                },
                "qa_bundle": {"answer": "invoice 100"},
            },
        }
    ]

    summary = score_grounded_stage(
        bundle=bundle,
        predictions=predictions,
        gold_rows=gold_rows,
        run_id="ranking-span-generation",
        stage="workflow_reviewed",
        variant="molabel_operated",
    )

    metric_values = {metric.metric_id: metric.value for metric in summary.metrics}
    assert metric_values["mrr"] == pytest.approx(1.0)
    assert metric_values["recall3"] == pytest.approx(1.0)
    assert metric_values["span_em"] == pytest.approx(1.0)
    assert metric_values["span_overlap"] == pytest.approx(1.0)
    assert metric_values["source_coverage"] == pytest.approx(1.0)
    assert metric_values["unsupported_rate"] == pytest.approx(0.0)
    assert metric_values["grounded_generation"] == pytest.approx(1.0)
    assert metric_values["anls"] == pytest.approx(1.0)
    assert summary.diagnostics["metric_family_summaries"]["retrieval"][
        "mrr"
    ] == pytest.approx(1.0)
    assert summary.diagnostics["metric_family_summaries"]["grounded_generation"][
        "grounded_generation"
    ] == pytest.approx(1.0)


def test_anls_respects_similarity_threshold() -> None:
    assert score_anls("invoice 100", "invoice-100") == pytest.approx(1.0)
    assert score_anls("receipt", "invoice", threshold=0.8) == pytest.approx(0.0)

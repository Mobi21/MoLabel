from __future__ import annotations

import csv
from pathlib import Path

import yaml

from molabel.core.quality.grounded_benchmarks import (
    load_grounded_benchmark,
    load_jsonl,
)
from tests.e2e.infrastructure.grounded_operator import prepare_grounded_operator_fixture

REPO_ROOT = Path(__file__).resolve().parents[2]
GROUNDED_ROOT = REPO_ROOT / "fixtures" / "benchmarks-grounded"
EXPECTED_BENCHMARKS = {
    "banking77",
    "beir",
    "clinc150",
    "cuad",
    "docvqa",
    "evidence-inference",
    "feverous",
    "goemotions",
    "hatexplain",
    "hotpotqa",
    "msmarco",
    "multispanqa",
    "qasper",
    "scifact",
    "tabfact",
    "totto",
    "toxic-spans",
    "webnlg",
}


def _raw_record_ids(
    workspace_root: Path,
    raw_format: str,
    source_path: str,
    record_id_field: str | None,
) -> set[str]:
    if raw_format == "csv":
        with (workspace_root / source_path).open(
            "r",
            encoding="utf-8",
            newline="",
        ) as handle:
            return {
                row[record_id_field or "record_id"] for row in csv.DictReader(handle)
            }

    if raw_format == "jsonl":
        rows = load_jsonl(workspace_root / source_path)
        if record_id_field is None:
            return {str(row["record_id"]) for row in rows}
        return {str(row[record_id_field]) for row in rows}

    if raw_format == "markdown":
        return {path.stem for path in workspace_root.glob(source_path)}

    raise AssertionError(f"Unsupported grounded raw format: {raw_format}")


def test_grounded_benchmark_fixtures_are_self_consistent() -> None:
    scenario_paths = sorted(GROUNDED_ROOT.glob("*/workbench/benchmarks/scenario.yaml"))
    assert scenario_paths, (
        "Expected grounded benchmark scenarios under fixtures/benchmarks-grounded"
    )

    discovered_ids = {path.parents[2].name for path in scenario_paths}
    assert discovered_ids == EXPECTED_BENCHMARKS

    for scenario_path in scenario_paths:
        workspace_root = scenario_path.parents[2]
        bundle = load_grounded_benchmark(workspace_root)
        scenario = bundle.scenario

        assert scenario.track == "grounded"
        assert set(scenario.evaluation_modes) == {"model", "workflow", "operator"}
        assert set(scenario.scoring_variants) == {"paper_direct", "molabel_operated"}
        assert bundle.authority is not None
        assert bundle.authority.manifest.layout == "authority"
        assert bundle.authority.manifest.benchmark_id == scenario.benchmark_id
        assert bundle.authority.profiles

        manifest_path = workspace_root / "workbench.project.yaml"
        task_schema_path = workspace_root / scenario.task_schema_path
        workflow_path = workspace_root / scenario.workflow_path
        gold_labels_path = workspace_root / scenario.gold_labels_path
        operator_path = (
            workspace_root / scenario.operator_path if scenario.operator_path else None
        )
        paper_gold_path = (
            workspace_root / scenario.paper_gold_path
            if scenario.paper_gold_path
            else None
        )
        molabel_gold_path = (
            workspace_root / scenario.molabel_gold_path
            if scenario.molabel_gold_path
            else None
        )

        assert manifest_path.exists(), f"Missing workspace manifest: {manifest_path}"
        assert task_schema_path.exists(), f"Missing task schema: {task_schema_path}"
        assert workflow_path.exists(), f"Missing workflow: {workflow_path}"
        assert gold_labels_path.exists(), f"Missing gold labels: {gold_labels_path}"
        if operator_path is not None:
            assert operator_path.exists()
        if paper_gold_path is not None:
            assert paper_gold_path.exists()
        if molabel_gold_path is not None:
            assert molabel_gold_path.exists()
        assert bundle.paper.dataset_license
        assert bundle.paper.paper_url
        assert bundle.paper.dataset_url
        assert bundle.label_map.field_mappings, "Expected explicit label mappings"
        assert bundle.metrics.metrics, "Expected grounded metrics"
        assert bundle.metrics.tax_definitions, "Expected grounded tax definitions"
        assert bundle.baselines.baselines, "Expected baseline entries"
        assert bundle.operator is not None, "Expected operator checklist"
        assert bundle.operator.current_labeling_engine == "MiniMax 2.7"
        assert bundle.operator.label_quality_weight > 0
        assert bundle.operator.checklist_weight > 0
        assert bundle.operator.blocking_check_ids
        assert bundle.operator.checks, "Expected operator checks"

        task_schema_doc = yaml.safe_load(task_schema_path.read_text(encoding="utf-8"))
        workflow_doc = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        task_schema_slug = task_schema_doc.get("task_schema_slug")
        assert task_schema_slug, f"Missing task_schema_slug in {task_schema_path}"

        referenced_task_schema_ids = {
            str(config["task_schema_id"])
            for step in workflow_doc.get("steps", [])
            for config in [step.get("config") or {}]
            if "task_schema_id" in config
        }
        if referenced_task_schema_ids:
            assert referenced_task_schema_ids == {task_schema_slug}, (
                "Workflow task_schema_id selectors must match the paired task schema "
                f"slug for {scenario.benchmark_id}: "
                f"{sorted(referenced_task_schema_ids)} != {[task_schema_slug]}"
            )

        raw_ids = _raw_record_ids(
            workspace_root,
            scenario.raw_format,
            scenario.source_path,
            scenario.record_id_field,
        )
        gold_rows = load_jsonl(gold_labels_path)
        gold_ids = {str(row["record_id"]) for row in gold_rows}
        assert gold_ids, f"Expected non-empty gold set for {scenario.benchmark_id}"
        assert gold_ids.issubset(raw_ids), (
            f"Gold labels do not align with source records for {scenario.benchmark_id}"
        )

        split_ids: set[str] = set()
        for relative_path in scenario.split_paths:
            split_rows = load_jsonl(workspace_root / relative_path)
            split_ids.update(
                str(
                    row.get(
                        "record_id", row.get(scenario.record_id_field or "record_id")
                    )
                )
                for row in split_rows
            )
        if split_ids:
            assert gold_ids.issubset(split_ids)

        for relative_path in scenario.human_label_paths + scenario.review_paths:
            full_path = workspace_root / relative_path
            assert full_path.exists(), f"Missing human artifact: {full_path}"
            for row in load_jsonl(full_path):
                assert str(row["record_id"]) in raw_ids


def test_operator_fixture_workspace_is_redacted() -> None:
    source_root = GROUNDED_ROOT / "clinc150"
    fixture = prepare_grounded_operator_fixture(source_root)

    assert fixture.workspace_root != fixture.authority_root
    assert fixture.authority_root.exists()
    assert fixture.workspace_root.exists()

    for relative in (
        "authority",
        "workbench/benchmarks/gold",
        "workbench/benchmarks/human-labels",
        "workbench/benchmarks/reviews",
    ):
        assert not (fixture.workspace_root / relative).exists()
        assert (fixture.authority_root / relative).exists()

    for relative in (
        "workbench/benchmarks/label-map.yaml",
        "workbench/benchmarks/metrics.yaml",
        "workbench/benchmarks/baselines.yaml",
        "workbench/benchmarks/operator.yaml",
        "workbench/benchmarks/paper.yaml",
        "workbench/benchmarks/scenario.yaml",
    ):
        assert not (fixture.workspace_root / relative).exists()
        assert (fixture.authority_root / relative).exists()

    operator_rows = load_jsonl(
        fixture.workspace_root / "workbench" / "benchmarks" / "splits" / "test.jsonl"
    )
    authority_rows = load_jsonl(
        fixture.authority_root / "workbench" / "benchmarks" / "splits" / "test.jsonl"
    )
    assert any("source_label" in row for row in authority_rows)
    assert all("source_label" not in row for row in operator_rows)

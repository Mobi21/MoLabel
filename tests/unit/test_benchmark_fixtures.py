from __future__ import annotations

import csv
import json
from pathlib import Path

import yaml

BENCHMARKS_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "benchmarks"


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict]:
    items: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            items.append(json.loads(line))
    return items


def _raw_record_ids(workspace_root: Path, scenario: dict) -> set[str]:
    source_path = scenario["source_path"]
    raw_format = scenario["raw_format"]

    if raw_format == "csv":
        csv_path = workspace_root / source_path
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            return {row[scenario["record_id_field"]] for row in reader}

    if raw_format == "jsonl":
        jsonl_path = workspace_root / source_path
        return {row[scenario["record_id_field"]] for row in _load_jsonl(jsonl_path)}

    if raw_format == "markdown":
        pattern = source_path
        return {path.stem for path in workspace_root.glob(pattern)}

    raise AssertionError(f"Unsupported raw format: {raw_format}")


def test_benchmark_fixture_workspaces_are_self_consistent() -> None:
    scenario_paths = sorted(
        BENCHMARKS_ROOT.glob("*/workbench/benchmarks/scenario.yaml")
    )
    assert scenario_paths, "Expected benchmark scenarios under fixtures/benchmarks"

    for scenario_path in scenario_paths:
        workspace_root = scenario_path.parents[2]
        scenario = _load_yaml(scenario_path)

        assert scenario["default_model_profile"]["provider_type"] == "anthropic"
        assert scenario["default_model_profile"]["provider_name"] == "MiniMax"
        assert (
            scenario["default_model_profile"]["model_identifier"]
            == "MiniMax-M2.7-highspeed"
        )
        assert scenario["default_model_profile"]["sdk_stack"] == "anthropic_sdk"
        assert "human_review" in scenario["exercise_modes"]

        manifest_path = workspace_root / "workbench.project.yaml"
        task_schema_path = workspace_root / scenario["task_schema_path"]
        workflow_path = workspace_root / scenario["workflow_path"]
        gold_labels_path = workspace_root / scenario["gold_labels_path"]

        assert manifest_path.exists(), f"Missing workspace manifest: {manifest_path}"
        assert task_schema_path.exists(), f"Missing task schema: {task_schema_path}"
        assert workflow_path.exists(), f"Missing workflow: {workflow_path}"
        assert gold_labels_path.exists(), f"Missing gold labels: {gold_labels_path}"

        raw_ids = _raw_record_ids(workspace_root, scenario)
        gold_rows = _load_jsonl(gold_labels_path)
        gold_ids = {row["record_id"] for row in gold_rows}
        message = (
            "Gold labels do not align with source records for "
            f"{scenario['scenario_id']}"
        )
        assert raw_ids == gold_ids, message

        intentional_error_count = 0
        for relative_path in scenario["human_label_paths"] + scenario["review_paths"]:
            full_path = workspace_root / relative_path
            assert full_path.exists(), f"Missing human simulation file: {full_path}"
            for row in _load_jsonl(full_path):
                assert row["record_id"] in raw_ids
                if row.get("is_intentionally_wrong"):
                    intentional_error_count += 1

        assert intentional_error_count >= scenario["expected_intentional_errors"], (
            f"Scenario {scenario['scenario_id']} expected at least "
            f"{scenario['expected_intentional_errors']} intentional errors"
        )

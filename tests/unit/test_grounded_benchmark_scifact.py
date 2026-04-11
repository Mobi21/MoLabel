from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from molabel.core.quality.grounded_benchmarks import (
    load_grounded_benchmark,
    load_jsonl,
)

ROOT = (
    Path(__file__).resolve().parents[2] / "fixtures" / "benchmarks-grounded" / "scifact"
)


ALLOWED_VERDICT_ALIASES = {
    "SUPPORT": "supports",
    "CONTRADICT": "refutes",
    "NOT_ENOUGH_INFO": "nei",
}


def _joint_score(
    gold_rows: list[dict[str, Any]],
    predictions: dict[str, dict[str, Any]],
) -> dict[str, float]:
    """Recompute the SciFact joint score inline to guard against scorer drift."""
    matches = 0
    verdict_matches = 0
    for row in gold_rows:
        record_id = row["record_id"]
        labels = row["labels"]
        gold_verdict_raw = labels["paper_label"].strip().upper()
        gold_verdict = ALLOWED_VERDICT_ALIASES[gold_verdict_raw]
        gold_sets = labels["paper_evidence_sets"]
        predicted = predictions.get(record_id, {})
        predicted_verdict = predicted.get("verdict", "").strip().lower()
        predicted_atoms = set(predicted.get("evidence_atoms", []) or [])

        verdict_ok = predicted_verdict == gold_verdict
        verdict_matches += int(verdict_ok)
        evidence_ok = gold_verdict == "nei" or any(
            set(gold_set).issubset(predicted_atoms)
            for gold_set in gold_sets
            if gold_set
        )
        matches += int(verdict_ok and evidence_ok)

    total = len(gold_rows)
    return {
        "verdict_accuracy": verdict_matches / total if total else 0.0,
        "scifact_joint_score": matches / total if total else 0.0,
    }


def test_scifact_grounded_fixture_contract() -> None:
    bundle = load_grounded_benchmark(ROOT)
    scenario = bundle.scenario

    assert scenario.benchmark_id == "scifact"
    assert scenario.track == "grounded"
    assert scenario.paper_metadata_path.endswith("paper.yaml")
    assert (
        scenario.paper_gold_path == "workbench/benchmarks/gold/paper-direct/dev.jsonl"
    )
    assert (
        scenario.molabel_gold_path
        == "workbench/benchmarks/gold/molabel-operated/dev.jsonl"
    )
    assert set(scenario.evaluation_modes) == {"model", "workflow", "operator"}
    assert set(scenario.scoring_variants) == {"paper_direct", "molabel_operated"}
    assert scenario.subset_policy["subset_size"] == 8
    assert set(scenario.evaluation_fields) == {"verdict", "evidence_atoms"}

    assert bundle.paper.dataset_name == "SciFact"
    assert bundle.paper.dataset_license == "CC BY-NC 2.0"
    assert bundle.paper.redistribution_status == "subset_allowed"

    assert bundle.label_map.record_id_field == "record_id"
    assert bundle.metrics.primary_metric_id == "scifact_joint_score_proxy"
    assert bundle.operator is not None
    assert {check.check_id for check in bundle.operator.checks} >= {
        "uses_public_cli_and_skill_only",
        "configures_minimax_2_7_profile",
        "preserves_artifact_integrity",
    }
    assert {metric.metric_id for metric in bundle.metrics.metrics} >= {
        "scifact_joint_score",
        "scifact_joint_score_proxy",
        "verdict_accuracy",
        "evidence_precision",
        "evidence_recall",
        "evidence_f1",
    }
    assert {tax.tax_id for tax in bundle.metrics.tax_definitions} == {
        "model_tax",
        "workflow_tax",
        "operator_tax",
    }


def test_scifact_grounded_files_align() -> None:
    split_rows = load_jsonl(ROOT / "workbench" / "benchmarks" / "splits" / "dev.jsonl")
    paper_gold_rows = load_jsonl(
        ROOT / "workbench" / "benchmarks" / "gold" / "paper-direct" / "dev.jsonl"
    )
    operational_gold_rows = load_jsonl(
        ROOT / "workbench" / "benchmarks" / "gold" / "molabel-operated" / "dev.jsonl"
    )
    human_rows = load_jsonl(
        ROOT / "workbench" / "benchmarks" / "human-labels" / "reviewer-reyna.jsonl"
    )
    review_rows = load_jsonl(
        ROOT / "workbench" / "benchmarks" / "reviews" / "reviewer-sota.jsonl"
    )

    assert len(split_rows) == 8
    assert len(paper_gold_rows) == 8
    assert len(operational_gold_rows) == 8

    raw_ids = {row["record_id"] for row in split_rows}
    assert raw_ids == {row["record_id"] for row in paper_gold_rows}
    assert raw_ids == {row["record_id"] for row in operational_gold_rows}

    # Paper-direct labels use SciFact's native verdict vocabulary.
    for row in paper_gold_rows:
        assert row["labels"]["paper_label"] in {
            "SUPPORT",
            "CONTRADICT",
            "NOT_ENOUGH_INFO",
        }
        # Evidence atoms follow the {doc_id}_sentence_{index} convention for
        # every non-NEI record, and NEI carries an empty set.
        for evidence_set in row["labels"]["paper_evidence_sets"]:
            for atom in evidence_set:
                assert "_sentence_" in atom
        if row["labels"]["paper_label"] == "NOT_ENOUGH_INFO":
            # NEI evidence sets must all be empty (no atoms claimed).
            assert all(
                len(evidence_set) == 0
                for evidence_set in row["labels"]["paper_evidence_sets"]
            )

    # MoLabel-operated verdicts use the FEVER-equivalent vocabulary.
    paper_by_id = {row["record_id"]: row for row in paper_gold_rows}
    op_by_id = {row["record_id"]: row for row in operational_gold_rows}
    for record_id, paper_row in paper_by_id.items():
        op_row = op_by_id[record_id]
        expected_verdict = ALLOWED_VERDICT_ALIASES[paper_row["labels"]["paper_label"]]
        assert op_row["labels"]["verdict"] == expected_verdict

        # MoLabel-operated atoms are the deduplicated flattening of the paper
        # evidence sets, preserving insertion order.
        expected_atoms: list[str] = []
        seen: set[str] = set()
        for evidence_set in paper_row["labels"]["paper_evidence_sets"]:
            for atom in evidence_set:
                if atom not in seen:
                    seen.add(atom)
                    expected_atoms.append(atom)
        assert op_row["labels"]["evidence_atoms"] == expected_atoms

    # Evidence atoms in every split record are consistent with cited_doc_ids.
    for split_row in split_rows:
        cited_docs = set(split_row["cited_doc_ids"])
        for evidence_set in split_row["evidence"]:
            for atom in evidence_set:
                assert atom["doc_id"] in cited_docs

    # Verdict distribution must include all three verdicts to be balanced.
    verdicts = {row["labels"]["paper_label"] for row in paper_gold_rows}
    assert verdicts == {"SUPPORT", "CONTRADICT", "NOT_ENOUGH_INFO"}

    human_wrong = sum(1 for row in human_rows if row.get("is_intentionally_wrong"))
    review_wrong = sum(1 for row in review_rows if row.get("is_intentionally_wrong"))
    assert human_wrong >= 2
    assert review_wrong >= 1

    # Reviewer atoms, where provided, must also follow the sentence convention.
    for row in human_rows + review_rows:
        assert row["record_id"] in raw_ids
        for atom in row["labels"].get("evidence_atoms", []) or []:
            assert "_sentence_" in atom


def test_scifact_reference_runs_bound_the_slice() -> None:
    gold_rows = load_jsonl(
        ROOT / "workbench" / "benchmarks" / "gold" / "paper-direct" / "dev.jsonl"
    )
    # Oracle predictions replay the gold verdict + flattened gold atoms.
    oracle_predictions: dict[str, dict[str, Any]] = {}
    for row in gold_rows:
        labels = row["labels"]
        verdict = ALLOWED_VERDICT_ALIASES[labels["paper_label"]]
        atoms: list[str] = []
        seen: set[str] = set()
        for evidence_set in labels["paper_evidence_sets"]:
            for atom in evidence_set:
                if atom not in seen:
                    seen.add(atom)
                    atoms.append(atom)
        oracle_predictions[row["record_id"]] = {
            "verdict": verdict,
            "evidence_atoms": atoms,
        }
    floor_predictions = {
        row["record_id"]: {"verdict": "nei", "evidence_atoms": []} for row in gold_rows
    }

    oracle = _joint_score(gold_rows, oracle_predictions)
    floor = _joint_score(gold_rows, floor_predictions)

    assert oracle["scifact_joint_score"] == pytest.approx(1.0)
    assert oracle["verdict_accuracy"] == pytest.approx(1.0)

    # One of eight records is NOT_ENOUGH_INFO.
    assert floor["scifact_joint_score"] == pytest.approx(1 / 8)
    assert floor["verdict_accuracy"] == pytest.approx(1 / 8)

    paper_run = json.loads(
        (
            ROOT
            / "workbench"
            / "benchmarks"
            / "runs"
            / "reference-paper-direct"
            / "summary.json"
        ).read_text(encoding="utf-8")
    )
    floor_run = json.loads(
        (
            ROOT
            / "workbench"
            / "benchmarks"
            / "runs"
            / "reference-model-floor"
            / "summary.json"
        ).read_text(encoding="utf-8")
    )

    assert paper_run["benchmark_id"] == "scifact"
    assert floor_run["benchmark_id"] == "scifact"
    assert paper_run["overall_score"] == pytest.approx(1.0)
    assert floor_run["overall_score"] == pytest.approx(0.125)

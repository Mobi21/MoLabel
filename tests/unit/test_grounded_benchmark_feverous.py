from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from molabel.core.quality.grounded_benchmarks import load_grounded_benchmark

BENCHMARK_ROOT = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "benchmarks-grounded"
    / "feverous"
)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _flatten_evidence_sets(evidence_sets: list[list[str]]) -> list[str]:
    flattened: list[str] = []
    seen: set[str] = set()
    for evidence_set in evidence_sets:
        for atom in evidence_set:
            if atom not in seen:
                seen.add(atom)
                flattened.append(atom)
    return flattened


def _normalize_verdict(value: str) -> str:
    normalized = value.strip().lower()
    aliases = {
        "supports": "supports",
        "supported": "supports",
        "refutes": "refutes",
        "refuted": "refutes",
        "nei": "nei",
        "not enough info": "nei",
    }
    return aliases[normalized]


def _paper_direct_score(
    gold_rows: list[dict[str, Any]],
    predictions: dict[str, dict[str, Any]],
) -> dict[str, float]:
    verdict_matches = 0
    evidence_precision_total = 0
    evidence_recall_total = 0
    evidence_f1_total = 0
    paper_direct_matches = 0

    for row in gold_rows:
        record_id = str(row["record_id"])
        labels = row["labels"]
        gold_verdict = _normalize_verdict(labels["paper_label"])
        gold_sets = labels["paper_evidence_sets"]
        gold_atoms = _flatten_evidence_sets(gold_sets)
        predicted = predictions.get(record_id, {})
        predicted_verdict = _normalize_verdict(str(predicted.get("verdict", "")))
        predicted_atoms = list(dict.fromkeys(predicted.get("evidence_atoms", [])))

        verdict_ok = predicted_verdict == gold_verdict
        verdict_matches += int(verdict_ok)

        overlap = len(set(predicted_atoms) & set(gold_atoms))
        precision = overlap / len(predicted_atoms) if predicted_atoms else 0.0
        recall = overlap / len(gold_atoms) if gold_atoms else 0.0
        evidence_precision_total += precision
        evidence_recall_total += recall
        evidence_f1_total += (
            (2 * precision * recall / (precision + recall))
            if (precision + recall)
            else 0.0
        )

        paper_direct_ok = verdict_ok and (
            gold_verdict == "nei"
            or any(
                set(gold_set).issubset(set(predicted_atoms)) for gold_set in gold_sets
            )
        )
        paper_direct_matches += int(paper_direct_ok)

    total = len(gold_rows)
    return {
        "verdict_accuracy": verdict_matches / total if total else 0.0,
        "evidence_precision": evidence_precision_total / total if total else 0.0,
        "evidence_recall": evidence_recall_total / total if total else 0.0,
        "evidence_f1": evidence_f1_total / total if total else 0.0,
        "paper_direct_score": paper_direct_matches / total if total else 0.0,
    }


def test_grounded_feverous_fixture_contract() -> None:
    bundle = load_grounded_benchmark(BENCHMARK_ROOT)

    assert bundle.scenario.benchmark_id == "feverous"
    assert bundle.scenario.track == "grounded"
    assert bundle.scenario.evaluation_modes == ["model", "workflow", "operator"]
    assert bundle.scenario.scoring_variants == ["paper_direct", "molabel_operated"]
    assert bundle.paper.dataset_license.startswith("Creative Commons")
    assert bundle.paper.repository_license == "Apache-2.0"
    assert bundle.metrics.primary_metric_id == "feverous_score_proxy"
    assert bundle.operator is not None
    assert {check.check_id for check in bundle.operator.checks} >= {
        "uses_public_cli_and_skill_only",
        "configures_minimax_2_7_profile",
        "preserves_artifact_integrity",
    }

    split_rows = _load_jsonl(
        BENCHMARK_ROOT / "workbench" / "benchmarks" / "splits" / "dev.jsonl"
    )
    paper_gold_rows = _load_jsonl(
        BENCHMARK_ROOT
        / "workbench"
        / "benchmarks"
        / "gold"
        / "paper-direct"
        / "dev.jsonl"
    )
    molabel_gold_rows = _load_jsonl(
        BENCHMARK_ROOT
        / "workbench"
        / "benchmarks"
        / "gold"
        / "molabel-operated"
        / "dev.jsonl"
    )
    human_rows = _load_jsonl(
        BENCHMARK_ROOT
        / "workbench"
        / "benchmarks"
        / "human-labels"
        / "reviewer-ira.jsonl"
    )
    review_rows = _load_jsonl(
        BENCHMARK_ROOT / "workbench" / "benchmarks" / "reviews" / "reviewer-jo.jsonl"
    )

    split_ids = {str(row["id"]) for row in split_rows}
    paper_gold_ids = {str(row["record_id"]) for row in paper_gold_rows}
    molabel_gold_ids = {str(row["record_id"]) for row in molabel_gold_rows}
    human_ids = {str(row["record_id"]) for row in human_rows}
    review_ids = {str(row["record_id"]) for row in review_rows}

    assert split_ids == paper_gold_ids == molabel_gold_ids
    assert human_ids <= split_ids
    assert review_ids <= split_ids

    # Oracle predictions on the committed slice should be perfect.
    oracle_predictions = {row["record_id"]: row["labels"] for row in molabel_gold_rows}
    exact_scores = _paper_direct_score(paper_gold_rows, oracle_predictions)
    assert exact_scores["verdict_accuracy"] == pytest.approx(1.0)
    assert exact_scores["evidence_precision"] == pytest.approx(1.0)
    assert exact_scores["evidence_recall"] == pytest.approx(1.0)
    assert exact_scores["evidence_f1"] == pytest.approx(1.0)
    assert exact_scores["paper_direct_score"] == pytest.approx(1.0)

    # Simulated human artifacts must contain intentional mistakes.
    intentional_errors = sum(
        1 for row in human_rows + review_rows if row.get("is_intentionally_wrong")
    )
    assert intentional_errors >= 2

    reference_summary_path = (
        BENCHMARK_ROOT
        / "workbench"
        / "benchmarks"
        / "runs"
        / "reference-paper-direct"
        / "summary.json"
    )
    reference_report_path = reference_summary_path.with_name("report.md")
    assert reference_summary_path.exists()
    assert reference_report_path.exists()

    summary = yaml.safe_load(reference_summary_path.read_text(encoding="utf-8"))
    assert summary["benchmark_id"] == "feverous"
    assert summary["overall_score"] == pytest.approx(1.0)
    assert summary["mode"] == "model"
    assert summary["variant"] == "paper_direct"

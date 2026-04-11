from __future__ import annotations

from collections import Counter
from pathlib import Path

from molabel.core.quality.grounded_benchmarks import (
    load_grounded_benchmark,
    load_jsonl,
)

ROOT = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "benchmarks-grounded"
    / "hatexplain"
)


def _majority_label(votes: list[str]) -> str:
    return Counter(votes).most_common(1)[0][0]


def test_hatexplain_grounded_fixture_contract() -> None:
    bundle = load_grounded_benchmark(ROOT)
    scenario = bundle.scenario

    assert scenario.benchmark_id == "hatexplain"
    assert scenario.track == "grounded"
    assert scenario.paper_metadata_path.endswith("paper.yaml")
    assert scenario.paper_gold_path == "workbench/benchmarks/gold/paper-direct.jsonl"
    assert (
        scenario.molabel_gold_path == "workbench/benchmarks/gold/molabel-operated.jsonl"
    )
    assert set(scenario.evaluation_modes) == {"model", "workflow", "operator"}
    assert set(scenario.scoring_variants) == {"paper_direct", "molabel_operated"}
    assert scenario.subset_policy["subset_size"] == 8

    assert bundle.paper.repository_license == "MIT"
    assert bundle.paper.redistribution_status == "review_required"
    assert bundle.metrics.primary_metric_id == "stance_macro_f1"
    assert bundle.operator is not None
    assert {check.check_id for check in bundle.operator.checks} >= {
        "uses_public_cli_and_skill_only",
        "configures_minimax_2_7_profile",
        "preserves_artifact_integrity",
    }
    assert {metric.metric_id for metric in bundle.metrics.metrics} >= {
        "stance_macro_f1",
        "target_jaccard",
        "rationale_token_f1",
    }
    assert bundle.label_map.record_id_field == "post_id"


def test_hatexplain_grounded_artifacts_align() -> None:
    raw_rows = load_jsonl(ROOT / "data" / "raw" / "dataset.jsonl")
    split_rows = load_jsonl(ROOT / "workbench" / "benchmarks" / "splits" / "test.jsonl")
    paper_gold = load_jsonl(
        ROOT / "workbench" / "benchmarks" / "gold" / "paper-direct.jsonl"
    )
    operational_gold = load_jsonl(
        ROOT / "workbench" / "benchmarks" / "gold" / "molabel-operated.jsonl"
    )
    human_rows = load_jsonl(
        ROOT / "workbench" / "benchmarks" / "human-labels" / "reviewer-ada.jsonl"
    )
    review_rows = load_jsonl(
        ROOT / "workbench" / "benchmarks" / "reviews" / "reviewer-noa.jsonl"
    )

    assert (
        len(raw_rows)
        == len(split_rows)
        == len(paper_gold)
        == len(operational_gold)
        == 8
    )

    raw_ids = {row["post_id"] for row in raw_rows}
    split_ids = {row["record_id"] for row in split_rows}
    paper_ids = {row["record_id"] for row in paper_gold}
    operational_ids = {row["record_id"] for row in operational_gold}
    assert raw_ids == split_ids == paper_ids == operational_ids

    raw_by_id = {row["post_id"]: row for row in raw_rows}
    split_by_id = {row["record_id"]: row for row in split_rows}
    paper_by_id = {row["record_id"]: row for row in paper_gold}
    operational_by_id = {row["record_id"]: row for row in operational_gold}

    intentional_error_count = 0
    observed_empty_rationales = False
    observed_non_empty_rationales = False

    for record_id in split_ids:
        split_row = split_by_id[record_id]
        raw_row = raw_by_id[record_id]
        paper_row = paper_by_id[record_id]
        operational_row = operational_by_id[record_id]

        assert split_row["majority_label"] == _majority_label(
            split_row["annotator_votes"]
        )
        assert paper_row["labels"]["stance_label"] == split_row["majority_label"]
        assert operational_row["labels"]["stance_label"] == split_row["majority_label"]
        assert operational_row["workflow"]["should_preserve_disagreement"] == (
            len(set(split_row["annotator_votes"])) > 1
        )

        if split_row["majority_rationale_mask"]:
            observed_non_empty_rationales = True
            assert len(split_row["majority_rationale_mask"]) == len(split_row["tokens"])
            assert len(paper_row["labels"]["rationale_token_mask"]) == len(
                split_row["tokens"]
            )
            assert len(operational_row["labels"]["rationale_token_mask"]) == len(
                split_row["tokens"]
            )
        else:
            observed_empty_rationales = True

        assert split_row["text"] == " ".join(raw_row["post_tokens"])

    assert observed_empty_rationales
    assert observed_non_empty_rationales

    for row in human_rows + review_rows:
        assert row["record_id"] in raw_ids
        if row.get("is_intentionally_wrong"):
            intentional_error_count += 1

    assert intentional_error_count >= 2

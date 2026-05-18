"""Regression tests for the live operator benchmark batch runner."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    script_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "run_all_benchmarks.py"
    )
    spec = importlib.util.spec_from_file_location("run_all_benchmarks", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_worker_count_stays_conservative() -> None:
    module = _load_module()
    assert module.resolve_worker_count(None, len(module.build_benchmarks("open"))) == 1


def test_requested_worker_count_is_clamped() -> None:
    module = _load_module()
    assert module.resolve_worker_count(0, len(module.build_benchmarks("open"))) == 1
    assert module.resolve_worker_count(99, 3) == 3


def test_aggregate_benchmark_results_classifies_acceptable_repeat_set() -> None:
    module = _load_module()
    entries = [
        {
            "benchmark": "demo",
            "test_file": "tests/demo.py",
            "k_filter": "demo",
            "mode": "open",
            "repeat_index": 1,
            "exit_code": 0,
            "duration_seconds": 12.3,
            "stdout": "",
            "stderr": "",
            "artifact": {
                "operator_label_score": 0.91,
                "operator_checklist_score": 1.0,
                "operator_overall_score": 0.937,
                "review_submission_count": 10,
                "thresholds": {
                    "acceptable_operator_label_score": 0.9,
                    "acceptable_checklist_score": 0.95,
                },
                "named_lifts": {
                    "headline_review_lift": 0.1,
                    "workflow_pipeline_delta": 0.2,
                },
                "taxes": {"review_tax": -0.1},
                "stages": {
                    "operator_reviewed": {
                        "record_count": 10,
                        "overall_score": 0.91,
                        "metrics": {"primary": 0.91},
                    }
                },
                "provider_pressure": {
                    "api_calls_total": 10,
                    "api_calls_agent": 5,
                    "api_calls_paper_direct": 5,
                    "rate_limit_retries": 0,
                    "timeout_count": 0,
                    "adapter_error_count": 0,
                    "budget_spent_usd": 0.0,
                    "budget_exhausted": False,
                    "enforcer_attempts_total": 10,
                    "enforcer_attempts_max": 1,
                    "enforcer_validation_failures": 0,
                    "enforcer_timeout_count": 0,
                    "no_submission_exit": False,
                },
                "truthfulness_ok": True,
            },
        },
        {
            "benchmark": "demo",
            "test_file": "tests/demo.py",
            "k_filter": "demo",
            "mode": "open",
            "repeat_index": 2,
            "exit_code": 0,
            "duration_seconds": 11.7,
            "stdout": "",
            "stderr": "",
            "artifact": {
                "operator_label_score": 0.95,
                "operator_checklist_score": 1.0,
                "operator_overall_score": 0.965,
                "review_submission_count": 10,
                "thresholds": {
                    "acceptable_operator_label_score": 0.9,
                    "acceptable_checklist_score": 0.95,
                },
                "named_lifts": {
                    "headline_review_lift": 0.05,
                    "workflow_pipeline_delta": 0.15,
                },
                "taxes": {"review_tax": -0.05},
                "stages": {
                    "operator_reviewed": {
                        "record_count": 10,
                        "overall_score": 0.95,
                        "metrics": {"primary": 0.95},
                    }
                },
                "provider_pressure": {
                    "api_calls_total": 10,
                    "api_calls_agent": 5,
                    "api_calls_paper_direct": 5,
                    "rate_limit_retries": 0,
                    "timeout_count": 0,
                    "adapter_error_count": 0,
                    "budget_spent_usd": 0.0,
                    "budget_exhausted": False,
                    "enforcer_attempts_total": 10,
                    "enforcer_attempts_max": 1,
                    "enforcer_validation_failures": 0,
                    "enforcer_timeout_count": 0,
                    "no_submission_exit": False,
                },
                "truthfulness_ok": True,
            },
        },
    ]

    summary = module.aggregate_benchmark_results("demo", "open", entries)
    assert summary["outcome"] == "scored-acceptable-quality"
    assert summary["mode"] == "open"
    assert summary["operator_label_score"] == 0.93
    assert summary["operator_checklist_score"] == 1.0
    assert summary["headline_review_lift"] == 0.075
    assert summary["workflow_pipeline_delta"] == 0.175
    assert summary["distribution"]["infra_invalid_count"] == 0


def test_aggregate_benchmark_results_classifies_infra_failed_without_score() -> None:
    module = _load_module()
    entry = {
        "benchmark": "demo",
        "test_file": "tests/demo.py",
        "k_filter": "demo",
        "mode": "open",
        "repeat_index": 1,
        "exit_code": 1,
        "duration_seconds": 120.0,
        "stdout": "",
        "stderr": "timed out",
        "artifact": {
            "review_submission_count": 0,
            "provider_pressure": {
                "api_calls_total": 0,
                "api_calls_agent": 0,
                "api_calls_paper_direct": 0,
                "rate_limit_retries": 0,
                "timeout_count": 1,
                "adapter_error_count": 0,
                "budget_spent_usd": 0.0,
                "budget_exhausted": False,
                "enforcer_attempts_total": 0,
                "enforcer_attempts_max": 0,
                "enforcer_validation_failures": 0,
                "enforcer_timeout_count": 1,
                "no_submission_exit": True,
            },
        },
    }

    assert module.classify_repeat(entry) == "infra-failed"
    summary = module.aggregate_benchmark_results("demo", "open", [entry])
    assert summary["outcome"] == "infra-failed"
    assert summary["distribution"]["infra_invalid_count"] == 1


def test_classify_repeat_falls_back_to_log_inference_without_artifact() -> None:
    module = _load_module()
    entry = {
        "benchmark": "hatexplain",
        "test_file": "tests/demo.py",
        "k_filter": "hatexplain",
        "mode": "open",
        "repeat_index": 1,
        "exit_code": 1,
        "duration_seconds": 121.2,
        "stdout": (
            "attempts=3, used_native=True validation_errors "
            "FAILED (121211ms, 0 API calls)"
        ),
        "stderr": "AssertionError: no review submissions",
        "artifact": None,
    }

    assert module.classify_repeat(entry) == "infra-failed"
    summary = module.aggregate_benchmark_results("hatexplain", "open", [entry])
    assert summary["provider_pressure"]["enforcer_attempts_max"] == 3
    assert summary["provider_pressure"]["enforcer_validation_failures"] >= 1


def test_log_fallback_marks_usage_limit_as_rate_limit_pressure() -> None:
    module = _load_module()
    entry = {
        "benchmark": "banking77",
        "test_file": "tests/demo.py",
        "k_filter": "banking77",
        "mode": "open",
        "repeat_index": 1,
        "exit_code": 1,
        "duration_seconds": 55.0,
        "stdout": (
            "ProviderError: Anthropic API error: 429 "
            '{"type":"error","error":{"type":"rate_limit_error",'
            '"message":"usage limit exceeded (2056)"}}\n'
            "FAILED (55000ms, 11 API calls)"
        ),
        "stderr": "",
        "artifact": None,
    }

    summary = module.aggregate_benchmark_results("banking77", "open", [entry])
    assert summary["outcome"] == "infra-failed"
    assert summary["provider_pressure"]["api_calls_total"] == 11
    assert summary["provider_pressure"]["rate_limit_retries"] >= 1
    assert summary["provider_pressure"]["budget_exhausted"] is True

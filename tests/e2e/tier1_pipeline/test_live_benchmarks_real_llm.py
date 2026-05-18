"""Real benchmark runs against MiniMax 2.7 highspeed via the Anthropic-compatible path.

These scenarios use live API setup calls through the MoLabel app plus real
provider calls through the Anthropic adapter pointed at MiniMax's base URL.
They compare structured outputs against benchmark gold labels.
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml

from molabel.core.providers.anthropic_adapter import AnthropicAdapter
from molabel.core.providers.structured_output import StructuredOutputEnforcer
from molabel.core.types import Message
from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.parallel import INDEPENDENT

REPO_ROOT = Path(__file__).resolve().parents[3]
BENCHMARKS_ROOT = REPO_ROOT / "fixtures" / "benchmarks"
MINIMAX_BASE_URL = os.environ.get(
    "MINIMAX_BASE_URL", "https://api.minimax.io/anthropic"
)


@dataclass(frozen=True)
class BenchmarkScenario:
    fixture_dir: str
    min_field_accuracy: float
    min_exact_matches: int


SCENARIOS = [
    BenchmarkScenario(
        "messy-support-ops", min_field_accuracy=0.55, min_exact_matches=2
    ),
    BenchmarkScenario(
        "claims-audit-extraction", min_field_accuracy=0.5, min_exact_matches=1
    ),
    BenchmarkScenario(
        "forum-policy-moderation", min_field_accuracy=0.6, min_exact_matches=2
    ),
]


def _load_dotenv_if_present() -> None:
    dotenv_path = REPO_ROOT / ".env"
    if not dotenv_path.exists():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


def _resolve_auth_ref() -> str | None:
    _load_dotenv_if_present()
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "ANTHROPIC_API_KEY"
    if os.environ.get("MINIMAX_API_KEY"):
        os.environ.setdefault("ANTHROPIC_API_KEY", os.environ["MINIMAX_API_KEY"])
        return "ANTHROPIC_API_KEY"
    return None


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _load_raw_records(
    workspace_root: Path, scenario: dict[str, Any]
) -> list[dict[str, Any]]:
    raw_format = scenario["raw_format"]
    source_path = scenario["source_path"]

    if raw_format == "csv":
        path = workspace_root / source_path
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    if raw_format == "jsonl":
        return _load_jsonl(workspace_root / source_path)

    if raw_format == "markdown":
        records: list[dict[str, Any]] = []
        for path in sorted(workspace_root.glob(source_path)):
            records.append(
                {"record_id": path.stem, "markdown": path.read_text(encoding="utf-8")}
            )
        return records

    raise AssertionError(f"Unsupported raw format: {raw_format}")


def _record_identifier(record: dict[str, Any], scenario: dict[str, Any]) -> str:
    if "record_id_field" in scenario:
        return str(record[scenario["record_id_field"]])
    if scenario.get("record_id_from") == "file_stem":
        return str(record["record_id"])
    raise AssertionError(
        f"Scenario is missing record id mapping: {scenario['scenario_id']}"
    )


def _build_output_schema(
    task_schema: dict[str, Any], scenario_id: str
) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []

    for field in task_schema.get("label_fields", []):
        field_name = field["name"]
        field_type = field["field_type"]

        if field_type == "categorical":
            properties[field_name] = {
                "type": "string",
                "enum": field.get("options", []),
            }
        elif field_type == "bool":
            properties[field_name] = {"type": "boolean"}
        elif field_type == "numeric":
            properties[field_name] = {"type": "number"}
        elif field_type == "multi_select":
            properties[field_name] = {
                "type": "array",
                "items": {"type": "string", "enum": field.get("options", [])},
            }
        elif field_type == "json" and field_name == "evidence_quotes":
            properties[field_name] = {
                "type": "array",
                "items": {"type": "string"},
            }
        else:
            properties[field_name] = {"type": "string"}

        if field.get("required", True):
            required.append(field_name)

    return {
        "title": f"{scenario_id}_labels",
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required,
    }


def _build_messages(
    agents_prompt: str,
    task_schema: dict[str, Any],
    scenario: dict[str, Any],
    record: dict[str, Any],
    record_id: str,
) -> list[Message]:
    system_prompt = (
        f"{agents_prompt.strip()}\n\n"
        f"Task schema title: {task_schema['title']}\n"
        f"Task instructions: {task_schema.get('instructions', '')}\n"
        "Return only the structured JSON object."
    )
    user_prompt = (
        f"Benchmark scenario: {scenario['name']}\n"
        f"Scenario description: {scenario['description']}\n"
        f"Record ID: {record_id}\n"
        "Raw record:\n"
        f"{json.dumps(record, indent=2, ensure_ascii=True)}"
    )
    return [
        Message(role="system", content=system_prompt),
        Message(role="user", content=user_prompt),
    ]


def _values_match(expected: Any, actual: Any) -> bool:
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return False
        return sorted(str(item) for item in expected) == sorted(
            str(item) for item in actual
        )
    if isinstance(expected, bool):
        return actual is expected
    if isinstance(expected, (int, float)):
        return (
            isinstance(actual, (int, float))
            and abs(float(expected) - float(actual)) < 0.01
        )
    return str(expected) == str(actual)


def _score_predictions(
    predictions: dict[str, dict[str, Any]],
    gold: dict[str, dict[str, Any]],
    evaluation_fields: list[str],
) -> tuple[float, int]:
    total_fields = 0
    matched_fields = 0
    exact_matches = 0

    for record_id, gold_labels in gold.items():
        predicted = predictions[record_id]
        record_exact = True
        for field in evaluation_fields:
            total_fields += 1
            if _values_match(gold_labels[field], predicted.get(field)):
                matched_fields += 1
            else:
                record_exact = False
        if record_exact:
            exact_matches += 1

    return matched_fields / max(total_fields, 1), exact_matches


def _scenario_paths(
    fixture_dir: str,
) -> tuple[Path, dict[str, Any], dict[str, Any], str]:
    workspace_root = BENCHMARKS_ROOT / fixture_dir
    scenario = _load_yaml(workspace_root / "workbench" / "benchmarks" / "scenario.yaml")
    task_schema = _load_yaml(workspace_root / scenario["task_schema_path"])
    agents_prompt = (workspace_root / "AGENTS.md").read_text(encoding="utf-8")
    return workspace_root, scenario, task_schema, agents_prompt


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier1
@pytest.mark.real_llm
@pytest.mark.slow
@pytest.mark.parametrize(
    "benchmark", SCENARIOS, ids=[scenario.fixture_dir for scenario in SCENARIOS]
)
async def test_live_benchmark_real_llm_with_api_setup(
    client, ctx, benchmark: BenchmarkScenario
) -> None:
    """Run each benchmark with live API setup and real MiniMax calls."""

    auth_ref = _resolve_auth_ref()
    if not auth_ref:
        pytest.skip(
            "ANTHROPIC_API_KEY or MINIMAX_API_KEY not set — skipping live benchmark"
        )

    workspace_root, scenario, task_schema, agents_prompt = _scenario_paths(
        benchmark.fixture_dir
    )
    raw_records = _load_raw_records(workspace_root, scenario)
    gold_rows = _load_jsonl(workspace_root / scenario["gold_labels_path"])
    gold = {row["record_id"]: row["labels"] for row in gold_rows}

    with checkpoint(ctx, "workspace_and_session_setup"):
        ws_resp = await client.post(
            "/api/v1/workspaces",
            json={
                "path": str(workspace_root),
                "workspace_name": f"{scenario['name']} Live Benchmark",
            },
        )
        assert ws_resp.status_code == 201, ws_resp.text
        workspace_id = ws_resp.json()["workspace_id"]

        reviewer_resp = await client.post(
            "/api/v1/reviewer-profiles",
            json={
                "display_name": f"{scenario['name']} Operator",
                "workspace_id": workspace_id,
            },
        )
        assert reviewer_resp.status_code == 201, reviewer_resp.text
        reviewer_id = str(reviewer_resp.json()["id"])
        await client.login(reviewer_id)

    with checkpoint(ctx, "provider_health_and_model_profile"):
        health_resp = await client.get(
            "/api/v1/providers/health/anthropic",
            params={"auth_ref": auth_ref, "base_url": MINIMAX_BASE_URL},
        )
        assert health_resp.status_code == 200, health_resp.text
        assert health_resp.json()["health"]["is_healthy"] is True, health_resp.text

        model_profile_resp = await client.post(
            "/api/v1/model-profiles",
            json={
                "model_profile_slug": f"{scenario['scenario_id']}-minimax-live",
                "provider_type": "anthropic",
                "provider_name": "MiniMax",
                "model_identifier": scenario["default_model_profile"][
                    "model_identifier"
                ],
                "auth_ref": auth_ref,
                "base_url": MINIMAX_BASE_URL,
                "cost_per_input_token": 0.000001,
                "cost_per_output_token": 0.000003,
            },
        )
        assert model_profile_resp.status_code == 201, model_profile_resp.text
        model_profile = model_profile_resp.json()

        profile_test_resp = await client.post(
            f"/api/v1/model-profiles/{model_profile['id']}/test"
        )
        assert profile_test_resp.status_code == 200, profile_test_resp.text
        assert profile_test_resp.json()["health"]["is_healthy"] is True, (
            profile_test_resp.text
        )

    with checkpoint(ctx, "dataset_schema_and_prompt_setup"):
        dataset_resp = await client.post(
            "/api/v1/datasets",
            json={
                "dataset_name": scenario["name"],
                "workspace_id": workspace_id,
                "source_type": scenario["raw_format"],
                "loader_plugin": scenario["loader_plugin"],
                "record_kind": "text"
                if scenario["raw_format"] != "jsonl"
                else "document",
                "canonical_id_strategy": "source_record_id",
                "indexing_mode": "projection",
            },
        )
        assert dataset_resp.status_code == 201, dataset_resp.text
        dataset_id = dataset_resp.json()["dataset_id"]

        import_resp = await client.post(
            f"/api/v1/datasets/{dataset_id}/import",
            json={
                "source_uri": str(workspace_root / scenario["source_path"]),
                "options": {},
            },
        )
        assert import_resp.status_code == 202, import_resp.text

        schema_resp = await client.post(
            "/api/v1/task-schemas",
            json={
                "workspace_id": workspace_id,
                "task_schema_slug": task_schema["task_schema_slug"],
                "task_type": task_schema["task_type"],
                "title": task_schema["title"],
                "instructions": task_schema.get("instructions"),
                "blind_review_policy": task_schema.get(
                    "blind_review_policy", "hide_agent_outputs_by_default"
                ),
                "label_fields": task_schema["label_fields"],
                "optional_fields": task_schema.get("optional_fields", []),
                "overlap_policy": task_schema.get("overlap_policy"),
                "adjudication_policy": task_schema.get("adjudication_policy"),
                "supported_agent_roles": task_schema.get("supported_agent_roles", []),
            },
        )
        assert schema_resp.status_code == 201, schema_resp.text
        task_schema_id = schema_resp.json()["task_schema_id"]

        prompt_resp = await client.post(
            "/api/v1/prompts",
            json={
                "workspace_id": workspace_id,
                "name": f"{scenario['scenario_id']}-live-prompt",
                "agent_role": "proposer",
                "task_schema_id": task_schema_id,
                "system_instructions": agents_prompt,
                "task_rubric": task_schema.get("instructions", ""),
            },
        )
        assert prompt_resp.status_code == 201, prompt_resp.text

    with checkpoint(ctx, "real_llm_predictions_vs_gold"):
        adapter = AnthropicAdapter(
            auth_ref=auth_ref,
            default_model=scenario["default_model_profile"]["model_identifier"],
            base_url=MINIMAX_BASE_URL,
        )
        enforcer = StructuredOutputEnforcer()
        output_schema = _build_output_schema(task_schema, scenario["scenario_id"])

        predictions: dict[str, dict[str, Any]] = {}
        for record in raw_records:
            record_id = _record_identifier(record, scenario)
            messages = _build_messages(
                agents_prompt, task_schema, scenario, record, record_id
            )
            result = await asyncio.to_thread(
                enforcer.enforce,
                adapter,
                messages,
                scenario["default_model_profile"]["model_identifier"],
                output_schema,
            )
            ctx.llm_calls += 1
            ctx.real_llm_calls += 1
            if result.is_valid:
                parsed = result.parsed or {}
                predictions[record_id] = parsed
            else:
                message = (
                    f"Structured output failed for {scenario['scenario_id']} "
                    f"record {record_id}: {result.validation_errors}"
                )
                raise AssertionError(message)

        field_accuracy, exact_matches = _score_predictions(
            predictions,
            gold,
            list(scenario["evaluation_fields"]),
        )
        assert field_accuracy >= benchmark.min_field_accuracy, (
            f"{scenario['scenario_id']} field accuracy {field_accuracy:.2f} below "
            f"threshold {benchmark.min_field_accuracy:.2f}"
        )
        assert exact_matches >= benchmark.min_exact_matches, (
            f"{scenario['scenario_id']} exact matches {exact_matches} below "
            f"threshold {benchmark.min_exact_matches}"
        )

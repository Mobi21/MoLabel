"""Live grounded benchmark runs against MiniMax 2.7 highspeed.

These runs exercise the grounded benchmark contract end to end for the current
MoLabel labeling engine, MiniMax 2.7 highspeed, via the Anthropic-compatible adapter
path. Each test copies a grounded fixture workspace, provisions the workspace
through the API, runs paper-direct model scoring, and writes benchmark run
artifacts with the shared grounded benchmark scorer.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml

from molabel.core.providers.anthropic_adapter import AnthropicAdapter
from molabel.core.providers.structured_output import StructuredOutputEnforcer
from molabel.core.quality.grounded_benchmarks import (
    load_grounded_benchmark,
    load_jsonl,
    render_grounded_report,
    score_grounded_predictions,
    write_run_outputs,
)
from molabel.core.types import Message
from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.logging_config import serialize_test_context
from tests.e2e.infrastructure.parallel import INDEPENDENT

REPO_ROOT = Path(__file__).resolve().parents[3]
GROUNDED_ROOT = REPO_ROOT / "fixtures" / "benchmarks-grounded"
MINIMAX_BASE_URL = os.environ.get(
    "MINIMAX_BASE_URL",
    "https://api.minimax.io/anthropic",
)


@dataclass(frozen=True)
class GroundedScenarioRun:
    fixture_dir: str


SCENARIOS = [
    GroundedScenarioRun("clinc150"),
    GroundedScenarioRun("hatexplain"),
    GroundedScenarioRun("feverous"),
    GroundedScenarioRun("banking77"),
    GroundedScenarioRun("goemotions"),
    GroundedScenarioRun("scifact"),
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
        os.environ.setdefault(key.strip(), value.strip().strip("'").strip('"'))


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


def _load_raw_records(workspace_root: Path, source_path: str) -> list[dict[str, Any]]:
    return load_jsonl(workspace_root / source_path)


def _build_output_schema(
    task_schema: dict[str, Any], benchmark_id: str
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
        elif field_type == "json" and field_name == "evidence_atoms":
            properties[field_name] = {"type": "array", "items": {"type": "string"}}
        elif field_type == "json" and field_name == "rationale_token_mask":
            properties[field_name] = {"type": "array", "items": {"type": "integer"}}
        else:
            properties[field_name] = {"type": "string"}

        if field.get("required", True):
            required.append(field_name)

    return {
        "title": f"{benchmark_id}_grounded_labels",
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required,
    }


def _build_messages(
    agents_prompt: str,
    task_schema: dict[str, Any],
    benchmark_name: str,
    description: str,
    record: dict[str, Any],
    record_id: str,
) -> list[Message]:
    system_prompt = (
        f"{agents_prompt.strip()}\n\n"
        "The current MoLabel labeling engine under test is MiniMax 2.7 highspeed.\n"
        f"Task schema title: {task_schema['title']}\n"
        f"Task instructions: {task_schema.get('instructions', '')}\n"
        "Return only the structured JSON object."
    )
    user_prompt = (
        f"Grounded benchmark: {benchmark_name}\n"
        f"Benchmark description: {description}\n"
        f"Record ID: {record_id}\n"
        "Raw record:\n"
        f"{json.dumps(record, indent=2, ensure_ascii=True)}"
    )
    return [
        Message(role="system", content=system_prompt),
        Message(role="user", content=user_prompt),
    ]


def _workspace_copy(source_root: Path) -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix=f"molabel-grounded-{source_root.name}-"))
    workspace_root = temp_dir / source_root.name
    shutil.copytree(source_root, workspace_root)
    return workspace_root


def _build_model_run_evidence(
    *,
    ctx,
    raw_records: list[dict[str, Any]],
    gold_rows: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    output_schema: dict[str, Any],
    summary,
) -> dict[str, Any]:
    return {
        "inputs/raw_records.json": raw_records,
        "inputs/gold_rows.json": gold_rows,
        "outputs/predictions.json": predictions,
        "scoring/summary_diagnostics.json": summary.diagnostics,
        "runtime/output_schema.json": output_schema,
        "runtime/test_context.json": serialize_test_context(ctx),
    }


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier1
@pytest.mark.real_llm
@pytest.mark.slow
@pytest.mark.parametrize(
    "benchmark", SCENARIOS, ids=[scenario.fixture_dir for scenario in SCENARIOS]
)
async def test_live_grounded_benchmark_real_llm_model_mode(
    client, ctx, benchmark: GroundedScenarioRun
) -> None:
    """Run grounded paper-direct model scoring with live MiniMax 2.7 highspeed calls."""

    auth_ref = _resolve_auth_ref()
    if not auth_ref:
        pytest.skip(
            "ANTHROPIC_API_KEY or MINIMAX_API_KEY not set — skipping live benchmark"
        )

    source_root = GROUNDED_ROOT / benchmark.fixture_dir
    workspace_root = _workspace_copy(source_root)
    bundle = load_grounded_benchmark(workspace_root)
    task_schema = _load_yaml(workspace_root / bundle.scenario.task_schema_path)
    agents_prompt = (workspace_root / "AGENTS.md").read_text(encoding="utf-8")
    raw_records = _load_raw_records(workspace_root, bundle.scenario.source_path)
    gold_rows = load_jsonl(
        workspace_root
        / (bundle.scenario.paper_gold_path or bundle.scenario.gold_labels_path)
    )

    with checkpoint(ctx, "workspace_and_profile_setup"):
        ws_resp = await client.post(
            "/api/v1/workspaces",
            json={
                "path": str(workspace_root),
                "workspace_name": f"{bundle.scenario.name} Live Grounded Benchmark",
            },
        )
        assert ws_resp.status_code == 201, ws_resp.text
        workspace_id = ws_resp.json()["workspace_id"]

        reviewer_resp = await client.post(
            "/api/v1/reviewer-profiles",
            json={
                "display_name": f"{bundle.scenario.name} Operator",
                "workspace_id": workspace_id,
            },
        )
        assert reviewer_resp.status_code == 201, reviewer_resp.text
        reviewer_id = str(reviewer_resp.json()["id"])
        await client.login(reviewer_id)

        health_resp = await client.get(
            "/api/v1/providers/health/anthropic",
            params={"auth_ref": auth_ref, "base_url": MINIMAX_BASE_URL},
        )
        assert health_resp.status_code == 200, health_resp.text

        model_profile_resp = await client.post(
            "/api/v1/model-profiles",
            json={
                "model_profile_slug": (
                    f"{bundle.scenario.benchmark_id}-minimax-grounded-live"
                ),
                "provider_type": "anthropic",
                "provider_name": "MiniMax",
                "model_identifier": (
                    bundle.scenario.default_model_profile.model_identifier
                ),
                "auth_ref": auth_ref,
                "base_url": MINIMAX_BASE_URL,
                "cost_per_input_token": 0.000001,
                "cost_per_output_token": 0.000003,
            },
        )
        assert model_profile_resp.status_code == 201, model_profile_resp.text

    with checkpoint(ctx, "dataset_and_schema_setup"):
        dataset_resp = await client.post(
            "/api/v1/datasets",
            json={
                "dataset_name": bundle.scenario.name,
                "workspace_id": workspace_id,
                "source_type": bundle.scenario.raw_format,
                "loader_plugin": bundle.scenario.loader_plugin,
                "record_kind": "document",
                "canonical_id_strategy": "source_record_id",
                "indexing_mode": "projection",
            },
        )
        assert dataset_resp.status_code == 201, dataset_resp.text
        dataset_id = dataset_resp.json()["dataset_id"]

        import_resp = await client.post(
            f"/api/v1/datasets/{dataset_id}/import",
            json={
                "source_uri": str(workspace_root / bundle.scenario.source_path),
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
                    "blind_review_policy",
                    "hide_agent_outputs_by_default",
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
                "name": f"{bundle.scenario.benchmark_id}-grounded-live-prompt",
                "agent_role": "proposer",
                "task_schema_id": task_schema_id,
                "system_instructions": agents_prompt,
                "task_rubric": task_schema.get("instructions", ""),
            },
        )
        assert prompt_resp.status_code == 201, prompt_resp.text

    with checkpoint(ctx, "paper_direct_model_scoring"):
        adapter = AnthropicAdapter(
            auth_ref=auth_ref,
            default_model=bundle.scenario.default_model_profile.model_identifier,
            base_url=MINIMAX_BASE_URL,
        )
        enforcer = StructuredOutputEnforcer()
        output_schema = _build_output_schema(task_schema, bundle.scenario.benchmark_id)

        predictions: list[dict[str, Any]] = []
        for record in raw_records:
            record_id = str(record[bundle.scenario.record_id_field or "record_id"])
            messages = _build_messages(
                agents_prompt,
                task_schema,
                bundle.scenario.name,
                bundle.scenario.description,
                record,
                record_id,
            )
            result = await asyncio.to_thread(
                enforcer.enforce,
                adapter,
                messages,
                bundle.scenario.default_model_profile.model_identifier,
                output_schema,
            )
            ctx.llm_calls += 1
            ctx.real_llm_calls += 1
            assert result.is_valid, (
                f"Structured output failed for {bundle.scenario.benchmark_id} "
                f"record {record_id}: {result.validation_errors}"
            )
            predictions.append({"record_id": record_id, "labels": result.parsed or {}})

        summary = score_grounded_predictions(
            bundle=bundle,
            predictions=predictions,
            gold_rows=gold_rows,
            run_id="live-paper-direct-minimax-2-7",
            mode="model",
            variant="paper_direct",
        )
        report = render_grounded_report(bundle=bundle, summary=summary)
        summary_path, report_path = write_run_outputs(
            summary,
            report,
            workspace_root / "workbench" / "benchmarks" / "runs",
            evidence=_build_model_run_evidence(
                ctx=ctx,
                raw_records=raw_records,
                gold_rows=gold_rows,
                predictions=predictions,
                output_schema=output_schema,
                summary=summary,
            ),
        )

        assert 0.0 <= summary.overall_score <= 1.0
        assert summary.record_count == len(gold_rows)
        assert summary.metrics
        assert summary_path.exists()
        assert report_path.exists()

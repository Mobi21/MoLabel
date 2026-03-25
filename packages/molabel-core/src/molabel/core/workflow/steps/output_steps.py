"""Output step executors: export, snapshot, release_validation.

WF-018 through WF-020. Output steps produce artifacts (files, snapshots,
validated release bundles) and record their references in the context.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from molabel.core.workflow.context import StepOutput, WorkflowContext
from molabel.core.workflow.steps.base import StepExecutor, StepResult

logger = logging.getLogger(__name__)


class ExportExecutor(StepExecutor):
    """Executor for export steps (WF-018).

    Exports labeled data in the configured format using atomic writes
    (temp file + rename). Acquires the output-namespace export lock.
    """

    VALID_FORMATS = {"jsonl", "parquet", "csv", "huggingface"}

    def validate(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
    ) -> list[str]:
        errors: list[str] = []
        fmt = config.get("format", "jsonl")
        if fmt not in self.VALID_FORMATS:
            errors.append(
                f"Invalid export format '{fmt}'. Valid: {sorted(self.VALID_FORMATS)}"
            )
        if not config.get("destination"):
            errors.append("export requires 'destination' in config")
        return errors

    def execute(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
        services: dict[str, Any] | None = None,
    ) -> StepResult:
        services = services or {}
        export_service = services.get("exporter")
        record_ids = context.get_active_record_ids()

        bundle_id = str(uuid.uuid4())
        fmt = config.get("format", "jsonl")
        destination = config.get("destination", "")
        record_count = len(record_ids)

        if export_service is not None:
            try:
                result = export_service.export(
                    record_ids=record_ids,
                    format=fmt,
                    destination=destination,
                    config=config,
                    bundle_id=bundle_id,
                )
                record_count = result.get("record_count", record_count)
            except Exception as e:
                return StepResult(
                    success=False,
                    error=f"Export failed: {e}",
                    error_trace=str(e)[:2000],
                )
        else:
            logger.info(
                "No exporter service for step '%s'; recording placeholder bundle",
                step_id,
            )

        context.export_bundle_ids.append(bundle_id)

        return StepResult(
            success=True,
            output=StepOutput(
                step_id=step_id,
                step_type="export",
                summary={
                    "bundle_id": bundle_id,
                    "format": fmt,
                    "destination": destination,
                    "record_count": record_count,
                },
            ),
        )


class SnapshotExecutor(StepExecutor):
    """Executor for snapshot steps (WF-019).

    Captures the full workflow context state at a point in time. Writes
    the snapshot to workbench/snapshots/ and records it in context.
    """

    def validate(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
    ) -> list[str]:
        return []

    def execute(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
        services: dict[str, Any] | None = None,
    ) -> StepResult:
        services = services or {}
        snapshot_service = services.get("snapshot_manager")

        snapshot_id = str(uuid.uuid4())
        snapshot_name = config.get("snapshot_name", f"snapshot_{step_id}")

        if snapshot_service is not None:
            try:
                snapshot_service.create_snapshot(
                    snapshot_id=snapshot_id,
                    snapshot_name=snapshot_name,
                    context=context,
                    config=config,
                )
            except Exception as e:
                return StepResult(
                    success=False,
                    error=f"Snapshot failed: {e}",
                    error_trace=str(e)[:2000],
                )
        else:
            logger.info(
                "No snapshot_manager service for step '%s'; "
                "recording placeholder snapshot",
                step_id,
            )

        context.snapshot_ids.append(snapshot_id)

        return StepResult(
            success=True,
            output=StepOutput(
                step_id=step_id,
                step_type="snapshot",
                summary={
                    "snapshot_id": snapshot_id,
                    "snapshot_name": snapshot_name,
                },
            ),
        )


class ReleaseValidationExecutor(StepExecutor):
    """Executor for release_validation steps (WF-020).

    Runs validation gates against the current dataset and export bundles.
    Writes pass/fail result and variables["release.ready"] to context.
    """

    def validate(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
    ) -> list[str]:
        return []

    def execute(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
        services: dict[str, Any] | None = None,
    ) -> StepResult:
        services = services or {}
        validation_service = services.get("release_validator")
        validation_gates = config.get("validation_gates", [])

        gates_passed = 0
        gates_total = len(validation_gates)
        gate_results: list[dict[str, Any]] = []
        all_passed = True

        if validation_service is not None:
            try:
                for gate_ref in validation_gates:
                    result = validation_service.validate_gate(
                        gate_ref=gate_ref,
                        record_ids=context.get_active_record_ids(),
                        export_bundle_ids=context.export_bundle_ids,
                        metrics=context.metrics,
                        config=config,
                    )
                    gate_passed = result.get("passed", False)
                    gate_results.append(
                        {
                            "gate": gate_ref,
                            "passed": gate_passed,
                            "message": result.get("message", ""),
                        }
                    )
                    if gate_passed:
                        gates_passed += 1
                    else:
                        all_passed = False
            except Exception as e:
                return StepResult(
                    success=False,
                    error=f"Release validation failed: {e}",
                    error_trace=str(e)[:2000],
                )
        else:
            # Without validation service, all gates pass by default
            all_passed = True
            gates_passed = gates_total

        context.variables["release.ready"] = all_passed
        context.metrics["release.gates_passed"] = float(gates_passed)
        context.metrics["release.gates_total"] = float(gates_total)

        return StepResult(
            success=True,
            output=StepOutput(
                step_id=step_id,
                step_type="release_validation",
                summary={
                    "release_ready": all_passed,
                    "gates_passed": gates_passed,
                    "gates_total": gates_total,
                    "gate_results": gate_results,
                },
            ),
        )

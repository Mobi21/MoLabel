"""Workspace lifecycle stage engine (WF-052).

Computes the current lifecycle stage of a workspace based on workflow
execution history, dataset state, and available artifacts. Uses protocol
interfaces for snapshot services (cross-track dependency on Step 3.E.4).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from molabel.core.workflow.context import WorkflowContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocols for cross-track dependencies
# ---------------------------------------------------------------------------


@runtime_checkable
class SnapshotService(Protocol):
    """Protocol for the snapshot service (cross-track dependency on 3.E.4).

    The workflow engine only depends on this interface, not the concrete
    implementation from the data management track.
    """

    def list_snapshots(self, workspace_id: str) -> list[dict[str, Any]]:
        """List snapshot metadata for a workspace."""
        ...

    def has_snapshot(self, workspace_id: str, snapshot_id: str) -> bool:
        """Check if a specific snapshot exists."""
        ...


@runtime_checkable
class DatasetService(Protocol):
    """Protocol for dataset queries (minimal interface needed by lifecycle)."""

    def get_record_count(self, workspace_id: str) -> int:
        """Return total record count for the workspace."""
        ...

    def get_labeled_count(self, workspace_id: str) -> int:
        """Return count of labeled records."""
        ...


# ---------------------------------------------------------------------------
# Lifecycle stages
# ---------------------------------------------------------------------------

LIFECYCLE_STAGES = [
    "empty",
    "data_ingested",
    "schema_configured",
    "agent_labeled",
    "review_in_progress",
    "quality_validated",
    "exported",
    "released",
]


@dataclass
class LifecycleStageInfo:
    """Information about a workspace lifecycle stage.

    Attributes:
        current_stage: The current lifecycle stage name.
        stage_index: Numeric index of the current stage (0=empty).
        prerequisites: What is needed before advancing to the next stage.
        outputs: What this stage produces when completed.
        blockers: Issues preventing advancement to the next stage.
        downstream_impacts: What would change if this stage is re-done.
        completion_criteria: What must be true for this stage to be complete.
        recommended_actions: Suggested next steps for the operator.
        stage_details: Additional metadata per stage.
    """

    current_stage: str
    stage_index: int = 0
    prerequisites: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    downstream_impacts: list[str] = field(default_factory=list)
    completion_criteria: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    stage_details: dict[str, Any] = field(default_factory=dict)


def compute_lifecycle_stage(
    context: WorkflowContext | None,
    *,
    snapshot_service: SnapshotService | None = None,
    dataset_service: DatasetService | None = None,
    workspace_id: str = "",
) -> LifecycleStageInfo:
    """Compute the current workspace lifecycle stage from workflow state.

    Examines the WorkflowContext (or queries services when context is not
    available) to determine which stage the workspace is at.

    Args:
        context: The workflow context if a workflow has been executed.
        snapshot_service: Optional snapshot service for checking snapshots.
        dataset_service: Optional dataset service for record counts.
        workspace_id: The workspace ID for service queries.

    Returns:
        LifecycleStageInfo with full details about the current stage.
    """
    if context is None:
        return LifecycleStageInfo(
            current_stage="empty",
            stage_index=0,
            prerequisites=[],
            outputs=[],
            blockers=["No workflow has been executed"],
            completion_criteria=["Ingest data into the workspace"],
            recommended_actions=["Create and run a workflow to ingest data"],
        )

    # Determine stage based on context state
    has_data = bool(context.datasets)
    has_schema_configured = bool(context.variables.get("task_schema"))
    # Fall back to record_sets only if schema is set (records alone are not
    # sufficient to indicate schema configuration)
    if not has_schema_configured:
        has_schema_configured = bool(context.record_sets) and has_data
    has_agent_run = bool(context.agent_run_ids)
    has_review = bool(context.review_queue_ids)
    has_quality_check = context.variables.get("quality.passed") is not None
    quality_passed = context.variables.get("quality.passed", False)
    has_export = bool(context.export_bundle_ids)
    has_snapshot = bool(context.snapshot_ids)
    release_ready = context.variables.get("release.ready", False)

    # Check snapshots via service if available
    if snapshot_service and workspace_id:
        try:
            snapshots = snapshot_service.list_snapshots(workspace_id)
            if snapshots:
                has_snapshot = True
        except Exception:
            logger.debug("Snapshot service unavailable for lifecycle check")

    # Determine stage
    if release_ready and has_export:
        return _build_stage_info(
            "released",
            context,
            has_snapshot=has_snapshot,
        )
    elif has_export:
        return _build_stage_info(
            "exported",
            context,
            has_snapshot=has_snapshot,
            release_ready=release_ready,
        )
    elif has_quality_check and quality_passed:
        return _build_stage_info(
            "quality_validated",
            context,
            has_snapshot=has_snapshot,
        )
    elif has_review:
        return _build_stage_info(
            "review_in_progress",
            context,
            quality_passed=quality_passed,
        )
    elif has_agent_run:
        return _build_stage_info(
            "agent_labeled",
            context,
        )
    elif has_schema_configured:
        return _build_stage_info(
            "schema_configured",
            context,
        )
    elif has_data:
        return _build_stage_info(
            "data_ingested",
            context,
        )
    else:
        return LifecycleStageInfo(
            current_stage="empty",
            stage_index=0,
            blockers=["No data ingested"],
            completion_criteria=["Run a data_ingest step"],
            recommended_actions=["Create a workflow with a data_ingest step"],
        )


def _build_stage_info(
    stage: str,
    context: WorkflowContext,
    **kwargs: Any,
) -> LifecycleStageInfo:
    """Build detailed LifecycleStageInfo for a given stage."""
    idx = LIFECYCLE_STAGES.index(stage) if stage in LIFECYCLE_STAGES else 0

    info = LifecycleStageInfo(
        current_stage=stage,
        stage_index=idx,
    )

    if stage == "data_ingested":
        info.prerequisites = ["Data source files available"]
        info.outputs = [
            f"{len(context.datasets)} dataset(s) loaded",
            f"Active record set: {context.active_record_set_id or 'none'}",
        ]
        info.completion_criteria = ["Records loaded and normalized"]
        info.recommended_actions = [
            "Configure a task schema",
            "Run data_normalize step",
            "Run an agent_run step",
        ]
        info.downstream_impacts = [
            "Re-ingesting data will invalidate all downstream outputs"
        ]

    elif stage == "schema_configured":
        info.prerequisites = ["Data ingested", "Task schema defined"]
        info.outputs = [
            "Normalized record sets available",
        ]
        info.completion_criteria = ["All records normalized to task schema"]
        info.recommended_actions = [
            "Run an agent_run step for initial labeling",
            "Start human_review for manual labeling",
        ]

    elif stage == "agent_labeled":
        info.prerequisites = ["Data ingested", "Task schema configured"]
        info.outputs = [
            f"{len(context.agent_run_ids)} agent run(s) completed",
            f"Coverage: {context.metrics.get('agent.coverage', 0.0):.1%}",
        ]
        info.completion_criteria = ["Agent run completed on target records"]
        info.recommended_actions = [
            "Review agent outputs with human_review",
            "Check quality with quality_check step",
            "Compare models with agent_compare",
        ]
        info.downstream_impacts = [
            "Re-running agent will create new outputs "
            "(previous outputs preserved in history)"
        ]

    elif stage == "review_in_progress":
        info.prerequisites = ["Data labeled (agent or human)"]
        info.outputs = [
            f"{len(context.review_queue_ids)} review queue(s) created",
        ]
        info.blockers = []
        quality_passed = kwargs.get("quality_passed", False)
        if not quality_passed:
            info.blockers.append("Quality check not yet passed")
        info.completion_criteria = [
            "All review queues processed",
            "Quality metrics meet thresholds",
        ]
        info.recommended_actions = [
            "Complete pending review tasks",
            "Run quality_check step",
            "Run agreement_analysis step",
        ]

    elif stage == "quality_validated":
        info.prerequisites = ["Reviews completed", "Quality checks passed"]
        info.outputs = [
            f"Quality agreement: {context.metrics.get('quality.agreement', 0.0):.3f}",
            f"Quality coverage: {context.metrics.get('quality.coverage', 0.0):.1%}",
        ]
        has_snapshot = kwargs.get("has_snapshot", False)
        info.completion_criteria = ["Export data in desired format"]
        info.recommended_actions = [
            "Export dataset with export step",
            "Create snapshot for versioning",
        ]
        if not has_snapshot:
            info.recommended_actions.append("Create a snapshot before exporting")

    elif stage == "exported":
        info.prerequisites = ["Quality validated", "Export completed"]
        info.outputs = [
            f"{len(context.export_bundle_ids)} export bundle(s) created",
        ]
        release_ready = kwargs.get("release_ready", False)
        if not release_ready:
            info.blockers.append("Release validation not passed")
        info.completion_criteria = ["Release validation gates passed"]
        info.recommended_actions = [
            "Run release_validation step",
            "Approve release via gate step",
        ]

    elif stage == "released":
        info.prerequisites = ["Export completed", "Release validation passed"]
        info.outputs = [
            "Dataset released and ready for distribution",
            f"{len(context.export_bundle_ids)} export bundle(s) available",
        ]
        info.completion_criteria = ["Release approved"]
        info.recommended_actions = [
            "Create a snapshot for archival",
            "Start a new iteration if needed",
        ]

    info.stage_details = {
        "datasets": len(context.datasets),
        "record_sets": len(context.record_sets),
        "agent_runs": len(context.agent_run_ids),
        "review_queues": len(context.review_queue_ids),
        "exports": len(context.export_bundle_ids),
        "snapshots": len(context.snapshot_ids),
        "metrics": dict(context.metrics),
    }

    return info

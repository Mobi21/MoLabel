"""Initial schema, frozen at the tables SQLModel created before Alembic owned them.

Revision ID: 001
Revises: None
Create Date: 2026-03-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_name", sa.String(), nullable=False),
        sa.Column("workspace_slug", sa.String(), nullable=False),
        sa.Column("core_version", sa.String(), nullable=False),
        sa.Column("root_path", sa.String(), nullable=False),
        sa.Column("manifest_path", sa.String(), nullable=False),
        sa.Column("reference_app", sa.String(), nullable=True),
        sa.Column("settings", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_workspaces_workspace_slug"),
        "workspaces",
        ["workspace_slug"],
        unique=True,
    )
    op.create_table(
        "audit_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "action",
            sa.Enum(
                "workspace_created",
                "dataset_imported",
                "dataset_reindexed",
                "workflow_created",
                "workflow_started",
                "workflow_completed",
                "task_schema_created",
                "task_schema_updated",
                "agent_run_started",
                "agent_run_completed",
                "agent_run_failed",
                "review_submitted",
                "review_draft_saved",
                "ai_revealed",
                "adjudication_resolved",
                "export_created",
                "export_validated",
                "release_created",
                "release_approved",
                "release_rejected",
                "snapshot_created",
                "snapshot_restored",
                "plugin_enabled",
                "plugin_disabled",
                "config_changed",
                "file_written",
                "reindex_triggered",
                "prompt_created",
                "prompt_refined",
                "correction_analyzed",
                "provider_detected",
                name="auditaction",
            ),
            nullable=False,
        ),
        sa.Column("actor_type", sa.String(), nullable=False),
        sa.Column("actor_id", sa.String(), nullable=True),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("file_path", sa.String(), nullable=True),
        sa.Column("file_hash_before", sa.String(), nullable=True),
        sa.Column("file_hash_after", sa.String(), nullable=True),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_audit_entries_action", "audit_entries", ["action"], unique=False
    )
    op.create_index(
        "idx_audit_entries_target",
        "audit_entries",
        ["target_type", "target_id"],
        unique=False,
    )
    op.create_index(
        "idx_audit_entries_workspace_id",
        "audit_entries",
        ["workspace_id"],
        unique=False,
    )
    op.create_table(
        "datasets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_name", sa.String(), nullable=False),
        sa.Column("dataset_slug", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("source_config", sa.JSON(), nullable=True),
        sa.Column("loader_plugin", sa.String(), nullable=True),
        sa.Column("record_kind", sa.String(), nullable=True),
        sa.Column("canonical_id_strategy", sa.String(), nullable=False),
        sa.Column("indexing_mode", sa.String(), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=True),
        sa.Column("labeled_count", sa.Integer(), nullable=True),
        sa.Column(
            "health_status",
            sa.Enum("healthy", "stale", "error", name="datasethealthstatus"),
            nullable=True,
        ),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("last_indexed_at", sa.DateTime(), nullable=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_datasets_slug", "datasets", ["dataset_slug"], unique=False)
    op.create_index(
        "idx_datasets_workspace_id", "datasets", ["workspace_id"], unique=False
    )
    op.create_table(
        "model_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("model_profile_slug", sa.String(), nullable=False),
        sa.Column(
            "provider_type",
            sa.Enum(
                "openai_compatible",
                "openrouter",
                "ollama",
                "anthropic",
                "custom",
                name="providertype",
            ),
            nullable=False,
        ),
        sa.Column("provider_name", sa.String(), nullable=True),
        sa.Column("model_identifier", sa.String(), nullable=False),
        sa.Column("transport", sa.String(), nullable=False),
        sa.Column("auth_ref", sa.String(), nullable=True),
        sa.Column("supports_structured_output", sa.Boolean(), nullable=True),
        sa.Column("supports_tool_use", sa.Boolean(), nullable=True),
        sa.Column("context_window", sa.Integer(), nullable=True),
        sa.Column("capability_tags", sa.JSON(), nullable=True),
        sa.Column("routing_metadata", sa.JSON(), nullable=True),
        sa.Column("cost_per_input_token", sa.Float(), nullable=True),
        sa.Column("cost_per_output_token", sa.Float(), nullable=True),
        sa.Column("is_available", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_model_profiles_slug",
        "model_profiles",
        ["model_profile_slug"],
        unique=False,
    )
    op.create_index(
        "idx_model_profiles_workspace_id",
        "model_profiles",
        ["workspace_id"],
        unique=False,
    )
    op.create_table(
        "plugin_installations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plugin_id", sa.String(), nullable=False),
        sa.Column("plugin_version", sa.String(), nullable=False),
        sa.Column("plugin_type", sa.String(), nullable=False),
        sa.Column("compatible_core_version", sa.String(), nullable=False),
        sa.Column("entrypoint", sa.String(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("is_compatible", sa.Boolean(), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=True),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("installed_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_plugin_installations_plugin_id",
        "plugin_installations",
        ["plugin_id"],
        unique=False,
    )
    op.create_index(
        "idx_plugin_installations_workspace_id",
        "plugin_installations",
        ["workspace_id"],
        unique=False,
    )
    op.create_table(
        "prompt_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("prompt_slug", sa.String(), nullable=False),
        sa.Column("version", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("system_instructions", sa.String(), nullable=False),
        sa.Column("task_rubric", sa.String(), nullable=True),
        sa.Column("few_shot_examples", sa.JSON(), nullable=True),
        sa.Column("instruction_patches", sa.JSON(), nullable=True),
        sa.Column("output_schema", sa.JSON(), nullable=True),
        sa.Column("parent_version_id", sa.Uuid(), nullable=True),
        sa.Column("refinement_source_batch_id", sa.Uuid(), nullable=True),
        sa.Column("is_frozen", sa.Boolean(), nullable=False),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["parent_version_id"],
            ["prompt_templates.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_prompt_templates_slug", "prompt_templates", ["prompt_slug"], unique=False
    )
    op.create_index(
        "idx_prompt_templates_workspace_id",
        "prompt_templates",
        ["workspace_id"],
        unique=False,
    )
    op.create_table(
        "reviewer_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("avatar_color", sa.String(), nullable=True),
        sa.Column("is_operator", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("preferences", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_active_at", sa.DateTime(), nullable=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "workflow_definitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workflow_slug", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("is_template", sa.Boolean(), nullable=False),
        sa.Column("template_source", sa.String(), nullable=True),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_workflow_definitions_slug",
        "workflow_definitions",
        ["workflow_slug"],
        unique=False,
    )
    op.create_index(
        "idx_workflow_definitions_workspace_id",
        "workflow_definitions",
        ["workspace_id"],
        unique=False,
    )
    op.create_table(
        "artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("file_hash", sa.String(), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("file_format", sa.String(), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=True),
        sa.Column("loader_plugin", sa.String(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("stale", sa.Boolean(), nullable=False),
        sa.Column("indexed_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "correction_batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("prompt_template_id", sa.Uuid(), nullable=False),
        sa.Column("batch_sequence", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "accumulating",
                "ready_for_analysis",
                "analyzed",
                "refinements_pending",
                "applied",
                "dismissed",
                name="correctionbatchstatus",
            ),
            nullable=False,
        ),
        sa.Column("correction_count", sa.Integer(), nullable=False),
        sa.Column("batch_threshold", sa.Integer(), nullable=False),
        sa.Column("corrections", sa.JSON(), nullable=True),
        sa.Column("analysis_results", sa.JSON(), nullable=True),
        sa.Column("proposed_refinements", sa.JSON(), nullable=True),
        sa.Column("applied_prompt_version_id", sa.Uuid(), nullable=True),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("analyzed_at", sa.DateTime(), nullable=True),
        sa.Column("applied_at", sa.DateTime(), nullable=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["applied_prompt_version_id"],
            ["prompt_templates.id"],
        ),
        sa.ForeignKeyConstraint(
            ["prompt_template_id"],
            ["prompt_templates.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_correction_batches_template_id",
        "correction_batches",
        ["prompt_template_id"],
        unique=False,
    )
    op.create_index(
        "idx_correction_batches_workspace_id",
        "correction_batches",
        ["workspace_id"],
        unique=False,
    )
    op.create_table(
        "runtime_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("runtime_profile_slug", sa.String(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("fallback_model_profile_id", sa.Uuid(), nullable=True),
        sa.Column("provider_priority", sa.JSON(), nullable=True),
        sa.Column("max_concurrent_requests", sa.Integer(), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), nullable=True),
        sa.Column("retry_config", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["fallback_model_profile_id"],
            ["model_profiles.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_runtime_profiles_slug",
        "runtime_profiles",
        ["runtime_profile_slug"],
        unique=False,
    )
    op.create_index(
        "idx_runtime_profiles_workspace_id",
        "runtime_profiles",
        ["workspace_id"],
        unique=False,
    )
    op.create_table(
        "saved_views",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.Column("view_name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("view_type", sa.String(), nullable=False),
        sa.Column("target_dataset_id", sa.Uuid(), nullable=True),
        sa.Column("filters", sa.JSON(), nullable=False),
        sa.Column("sort_config", sa.JSON(), nullable=True),
        sa.Column("column_config", sa.JSON(), nullable=True),
        sa.Column("grouping", sa.JSON(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("is_shared", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["reviewer_profiles.id"],
        ),
        sa.ForeignKeyConstraint(
            ["target_dataset_id"],
            ["datasets.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_saved_views_view_type", "saved_views", ["view_type"], unique=False
    )
    op.create_index(
        "idx_saved_views_workspace_id", "saved_views", ["workspace_id"], unique=False
    )
    op.create_table(
        "task_schemas",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_schema_slug", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("task_type", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("instructions", sa.String(), nullable=True),
        sa.Column("record_selector", sa.JSON(), nullable=True),
        sa.Column("label_fields", sa.JSON(), nullable=False),
        sa.Column("required_fields", sa.JSON(), nullable=True),
        sa.Column("optional_fields", sa.JSON(), nullable=True),
        sa.Column(
            "blind_review_policy",
            sa.Enum(
                "hide_agent_outputs_by_default",
                "show_agent_outputs",
                "no_agent",
                name="blindreviewpolicy",
            ),
            nullable=False,
        ),
        sa.Column("overlap_policy", sa.JSON(), nullable=True),
        sa.Column("adjudication_policy", sa.JSON(), nullable=True),
        sa.Column("supported_agent_roles", sa.JSON(), nullable=True),
        sa.Column("default_model_profile_id", sa.Uuid(), nullable=True),
        sa.Column("export_mapping", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_frozen", sa.Boolean(), nullable=False),
        sa.Column("file_path", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["default_model_profile_id"],
            ["model_profiles.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_task_schemas_slug", "task_schemas", ["task_schema_slug"], unique=False
    )
    op.create_index(
        "idx_task_schemas_workspace_id", "task_schemas", ["workspace_id"], unique=False
    )
    op.create_table(
        "workflow_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workflow_definition_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_version", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "running",
                "paused",
                "completed",
                "failed",
                "cancelled",
                name="workflowexecutionstatus",
            ),
            nullable=False,
        ),
        sa.Column("current_step_id", sa.String(), nullable=True),
        sa.Column("step_execution_count", sa.Integer(), nullable=True),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column("error_summary", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("paused_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workflow_definition_id"],
            ["workflow_definitions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_workflow_executions_def_id",
        "workflow_executions",
        ["workflow_definition_id"],
        unique=False,
    )
    op.create_index(
        "idx_workflow_executions_status",
        "workflow_executions",
        ["status"],
        unique=False,
    )
    op.create_index(
        "idx_workflow_executions_workspace_id",
        "workflow_executions",
        ["workspace_id"],
        unique=False,
    )
    op.create_table(
        "label_mappings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mapping_slug", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("source_system", sa.String(), nullable=False),
        sa.Column("source_format", sa.String(), nullable=True),
        sa.Column("task_schema_id", sa.Uuid(), nullable=False),
        sa.Column("field_mappings", sa.JSON(), nullable=False),
        sa.Column("value_mappings", sa.JSON(), nullable=True),
        sa.Column("type_conversions", sa.JSON(), nullable=True),
        sa.Column("unmapped_field_policy", sa.String(), nullable=False),
        sa.Column(
            "default_trust_level",
            sa.Enum(
                "ground_truth", "expert", "external", "untrusted", name="trustlevel"
            ),
            nullable=False,
        ),
        sa.Column("file_path", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_schema_id"],
            ["task_schemas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_label_mappings_slug", "label_mappings", ["mapping_slug"], unique=False
    )
    op.create_index(
        "idx_label_mappings_workspace_id",
        "label_mappings",
        ["workspace_id"],
        unique=False,
    )
    op.create_table(
        "records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(), nullable=True),
        sa.Column("sequence_index", sa.Integer(), nullable=True),
        sa.Column("content_hash", sa.String(), nullable=True),
        sa.Column("stable_fields", sa.JSON(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("record_kind", sa.String(), nullable=True),
        sa.Column("source_metadata", sa.JSON(), nullable=True),
        sa.Column("label_count", sa.Integer(), nullable=True),
        sa.Column("latest_label", sa.JSON(), nullable=True),
        sa.Column("composite_confidence", sa.Float(), nullable=True),
        sa.Column("export_eligible", sa.Boolean(), nullable=False),
        sa.Column("flags", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("artifact_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["artifact_id"],
            ["artifacts.id"],
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_records_composite_confidence",
        "records",
        ["dataset_id", "composite_confidence"],
        unique=False,
    )
    op.create_index(
        "idx_records_content_hash", "records", ["content_hash"], unique=False
    )
    op.create_index(
        "idx_records_dataset_export",
        "records",
        ["dataset_id", "export_eligible"],
        unique=False,
    )
    op.create_index("idx_records_dataset_id", "records", ["dataset_id"], unique=False)
    op.create_index("idx_records_external_id", "records", ["external_id"], unique=False)
    op.create_index(
        "idx_records_workspace_id", "records", ["workspace_id"], unique=False
    )
    op.create_table(
        "workflow_step_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workflow_execution_id", sa.Uuid(), nullable=False),
        sa.Column("step_id", sa.String(), nullable=False),
        sa.Column(
            "step_type",
            sa.Enum(
                "data_ingest",
                "data_normalize",
                "data_filter",
                "data_sample",
                "data_deduplicate",
                "agent_run",
                "agent_compare",
                "human_review",
                "human_triage",
                "human_calibration",
                "human_adjudication",
                "quality_check",
                "agreement_analysis",
                "drift_detection",
                "export",
                "snapshot",
                "release_validation",
                "loop",
                "conditional",
                "parallel",
                "gate",
                name="workflowsteptype",
            ),
            nullable=False,
        ),
        sa.Column("step_config", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "ready",
                "running",
                "waiting_for_human",
                "waiting_for_gate",
                "waiting_for_breakpoint",
                "completed",
                "failed",
                "skipped",
                "retrying",
                "partially_failed",
                "interrupted",
                "cancelled",
                name="workflowstepexecutionstatus",
            ),
            nullable=False,
        ),
        sa.Column("iteration", sa.Integer(), nullable=False),
        sa.Column("parent_step_execution_id", sa.Uuid(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error_summary", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["parent_step_execution_id"],
            ["workflow_step_executions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workflow_execution_id"],
            ["workflow_executions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_wf_step_exec_execution_id",
        "workflow_step_executions",
        ["workflow_execution_id"],
        unique=False,
    )
    op.create_index(
        "idx_wf_step_exec_status", "workflow_step_executions", ["status"], unique=False
    )
    op.create_index(
        "idx_wf_step_exec_workspace_id",
        "workflow_step_executions",
        ["workspace_id"],
        unique=False,
    )
    op.create_table(
        "adjudications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("record_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("task_schema_id", sa.Uuid(), nullable=False),
        sa.Column("adjudicator_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_step_execution_id", sa.Uuid(), nullable=True),
        sa.Column("conflicting_event_ids", sa.JSON(), nullable=False),
        sa.Column(
            "resolution",
            sa.Enum(
                "preserve_disagreement",
                "resolve",
                "downgrade",
                "exclude",
                name="adjudicationresolution",
            ),
            nullable=False,
        ),
        sa.Column("resolved_labels", sa.JSON(), nullable=True),
        sa.Column("rationale", sa.String(), nullable=True),
        sa.Column("policy_reference", sa.String(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["adjudicator_id"],
            ["reviewer_profiles.id"],
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
        ),
        sa.ForeignKeyConstraint(
            ["record_id"],
            ["records.id"],
        ),
        sa.ForeignKeyConstraint(
            ["task_schema_id"],
            ["task_schemas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workflow_step_execution_id"],
            ["workflow_step_executions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_adjudications_record_id", "adjudications", ["record_id"], unique=False
    )
    op.create_index(
        "idx_adjudications_workspace_id",
        "adjudications",
        ["workspace_id"],
        unique=False,
    )
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("task_schema_id", sa.Uuid(), nullable=False),
        sa.Column("model_profile_id", sa.Uuid(), nullable=False),
        sa.Column("runtime_profile_id", sa.Uuid(), nullable=True),
        sa.Column("prompt_template_id", sa.Uuid(), nullable=True),
        sa.Column("prompt_version", sa.String(), nullable=True),
        sa.Column(
            "agent_role",
            sa.Enum(
                "proposer",
                "critic",
                "normalizer",
                "disagreement_flagger",
                "deduper",
                "rubric_judge",
                "edge_case_miner",
                "export_prep",
                name="agentrole",
            ),
            nullable=False,
        ),
        sa.Column("adapter_plugin", sa.String(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "planned",
                "running",
                "partially_completed",
                "completed",
                "failed",
                "cancelled",
                name="agentrunstatus",
            ),
            nullable=False,
        ),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("record_filter", sa.JSON(), nullable=True),
        sa.Column("total_records", sa.Integer(), nullable=True),
        sa.Column("completed_records", sa.Integer(), nullable=True),
        sa.Column("failed_records", sa.Integer(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("error_summary", sa.String(), nullable=True),
        sa.Column("cost_estimate", sa.JSON(), nullable=True),
        sa.Column("cost_actual", sa.JSON(), nullable=True),
        sa.Column("comparison_id", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_step_execution_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
        ),
        sa.ForeignKeyConstraint(
            ["model_profile_id"],
            ["model_profiles.id"],
        ),
        sa.ForeignKeyConstraint(
            ["runtime_profile_id"],
            ["runtime_profiles.id"],
        ),
        sa.ForeignKeyConstraint(
            ["task_schema_id"],
            ["task_schemas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workflow_step_execution_id"],
            ["workflow_step_executions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_agent_runs_dataset_id", "agent_runs", ["dataset_id"], unique=False
    )
    op.create_index("idx_agent_runs_status", "agent_runs", ["status"], unique=False)
    op.create_index(
        "idx_agent_runs_workspace_id", "agent_runs", ["workspace_id"], unique=False
    )
    op.create_table(
        "dataset_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_step_execution_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("snapshot_type", sa.String(), nullable=False),
        sa.Column("parent_snapshot_id", sa.Uuid(), nullable=True),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("labeled_count", sa.Integer(), nullable=False),
        sa.Column("quality_metrics", sa.JSON(), nullable=True),
        sa.Column("label_summary", sa.JSON(), nullable=True),
        sa.Column("dataset_membership", sa.JSON(), nullable=True),
        sa.Column("workflow_state", sa.JSON(), nullable=True),
        sa.Column("prompt_versions", sa.JSON(), nullable=True),
        sa.Column("project_config", sa.JSON(), nullable=True),
        sa.Column("delta_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
        ),
        sa.ForeignKeyConstraint(
            ["parent_snapshot_id"],
            ["dataset_snapshots.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workflow_step_execution_id"],
            ["workflow_step_executions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_dataset_snapshots_dataset_id",
        "dataset_snapshots",
        ["dataset_id"],
        unique=False,
    )
    op.create_index(
        "idx_dataset_snapshots_workspace_id",
        "dataset_snapshots",
        ["workspace_id"],
        unique=False,
    )
    op.create_table(
        "review_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("queue_id", sa.String(), nullable=False),
        sa.Column("record_id", sa.Uuid(), nullable=False),
        sa.Column("task_schema_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "available", "claimed", "submitted", "skipped", name="reviewtaskstatus"
            ),
            nullable=False,
        ),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("priority_reason", sa.String(), nullable=True),
        sa.Column("claimed_by", sa.Uuid(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("claim_expired_count", sa.Integer(), nullable=False),
        sa.Column("is_overlap", sa.Boolean(), nullable=False),
        sa.Column("is_calibration", sa.Boolean(), nullable=False),
        sa.Column("draft_labels", sa.JSON(), nullable=True),
        sa.Column("agent_output_ids", sa.String(), nullable=True),
        sa.Column("ai_revealed", sa.Boolean(), nullable=False),
        sa.Column("ai_revealed_at", sa.DateTime(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["claimed_by"],
            ["reviewer_profiles.id"],
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
        ),
        sa.ForeignKeyConstraint(
            ["record_id"],
            ["records.id"],
        ),
        sa.ForeignKeyConstraint(
            ["task_schema_id"],
            ["task_schemas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_review_tasks_claimed_by", "review_tasks", ["claimed_by"], unique=False
    )
    op.create_index(
        "idx_review_tasks_queue_status",
        "review_tasks",
        ["queue_id", "status"],
        unique=False,
    )
    op.create_index(
        "idx_review_tasks_record_id", "review_tasks", ["record_id"], unique=False
    )
    op.create_index(
        "idx_review_tasks_workspace_id", "review_tasks", ["workspace_id"], unique=False
    )
    op.create_table(
        "validation_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_step_execution_id", sa.Uuid(), nullable=True),
        sa.Column("validation_plugin", sa.String(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "running",
                "passed",
                "failed",
                "warning",
                name="validationstatus",
            ),
            nullable=False,
        ),
        sa.Column("gates", sa.JSON(), nullable=True),
        sa.Column("passed_gate_count", sa.Integer(), nullable=True),
        sa.Column("total_gate_count", sa.Integer(), nullable=True),
        sa.Column("summary", sa.String(), nullable=True),
        sa.Column("report_path", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workflow_step_execution_id"],
            ["workflow_step_executions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_validation_runs_target",
        "validation_runs",
        ["target_type", "target_id"],
        unique=False,
    )
    op.create_index(
        "idx_validation_runs_workspace_id",
        "validation_runs",
        ["workspace_id"],
        unique=False,
    )
    op.create_table(
        "agent_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agent_run_id", sa.Uuid(), nullable=False),
        sa.Column(
            "event_type",
            sa.Enum(
                "run_started",
                "batch_started",
                "record_completed",
                "record_failed",
                "batch_completed",
                "retry_attempted",
                "run_completed",
                "run_failed",
                "run_cancelled",
                name="agenteventtype",
            ),
            nullable=False,
        ),
        sa.Column("record_id", sa.Uuid(), nullable=True),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_run_id"],
            ["agent_runs.id"],
        ),
        sa.ForeignKeyConstraint(
            ["record_id"],
            ["records.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_agent_events_run_id", "agent_events", ["agent_run_id"], unique=False
    )
    op.create_index(
        "idx_agent_events_run_seq",
        "agent_events",
        ["agent_run_id", "sequence_number"],
        unique=False,
    )
    op.create_table(
        "agent_outputs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agent_run_id", sa.Uuid(), nullable=False),
        sa.Column("record_id", sa.Uuid(), nullable=False),
        sa.Column("task_schema_id", sa.Uuid(), nullable=False),
        sa.Column("output_type", sa.String(), nullable=False),
        sa.Column("labels", sa.JSON(), nullable=False),
        sa.Column("raw_response", sa.JSON(), nullable=True),
        sa.Column("confidence_self_reported", sa.Float(), nullable=True),
        sa.Column("confidence_self_consistency", sa.Float(), nullable=True),
        sa.Column("confidence_logprobs", sa.Float(), nullable=True),
        sa.Column("composite_confidence", sa.Float(), nullable=True),
        sa.Column("tokens_input", sa.Integer(), nullable=True),
        sa.Column("tokens_output", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("validation_passed", sa.Boolean(), nullable=False),
        sa.Column("validation_errors", sa.JSON(), nullable=True),
        sa.Column("retry_attempt", sa.Integer(), nullable=False),
        sa.Column("is_visible_for_review", sa.Boolean(), nullable=False),
        sa.Column("normalization_status", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_run_id"],
            ["agent_runs.id"],
        ),
        sa.ForeignKeyConstraint(
            ["record_id"],
            ["records.id"],
        ),
        sa.ForeignKeyConstraint(
            ["task_schema_id"],
            ["task_schemas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_agent_outputs_record_id", "agent_outputs", ["record_id"], unique=False
    )
    op.create_index(
        "idx_agent_outputs_run_id", "agent_outputs", ["agent_run_id"], unique=False
    )
    op.create_index(
        "idx_agent_outputs_workspace_id",
        "agent_outputs",
        ["workspace_id"],
        unique=False,
    )
    op.create_table(
        "export_bundles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("task_schema_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_step_execution_id", sa.Uuid(), nullable=True),
        sa.Column("export_slug", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "validating",
                "validated",
                "packaging",
                "completed",
                "failed",
                name="exportbundlestatus",
            ),
            nullable=False,
        ),
        sa.Column(
            "export_format",
            sa.Enum(
                "jsonl",
                "parquet",
                "csv",
                "huggingface_hub",
                "plugin_custom",
                name="exportformat",
            ),
            nullable=False,
        ),
        sa.Column("output_path", sa.String(), nullable=False),
        sa.Column("output_namespace", sa.String(), nullable=True),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("include_config", sa.JSON(), nullable=True),
        sa.Column("filter_config", sa.JSON(), nullable=True),
        sa.Column("file_hash", sa.String(), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("source_snapshot_id", sa.Uuid(), nullable=True),
        sa.Column("validation_run_id", sa.Uuid(), nullable=True),
        sa.Column("packager_plugin", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["dataset_snapshots.id"],
        ),
        sa.ForeignKeyConstraint(
            ["task_schema_id"],
            ["task_schemas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workflow_step_execution_id"],
            ["workflow_step_executions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_export_bundles_dataset_id", "export_bundles", ["dataset_id"], unique=False
    )
    op.create_index(
        "idx_export_bundles_workspace_id",
        "export_bundles",
        ["workspace_id"],
        unique=False,
    )
    op.create_table(
        "releases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("release_slug", sa.String(), nullable=False),
        sa.Column("version", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "validating",
                "pending_approval",
                "approved",
                "released",
                "rejected",
                "revoked",
                name="releasestatus",
            ),
            nullable=False,
        ),
        sa.Column("export_bundle_ids", sa.JSON(), nullable=False),
        sa.Column("validation_run_ids", sa.JSON(), nullable=True),
        sa.Column("dataset_snapshot_id", sa.Uuid(), nullable=True),
        sa.Column("quality_summary", sa.JSON(), nullable=True),
        sa.Column("signed_off_by", sa.Uuid(), nullable=True),
        sa.Column("signed_off_at", sa.DateTime(), nullable=True),
        sa.Column("release_metadata", sa.JSON(), nullable=True),
        sa.Column("manifest_path", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("released_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_snapshot_id"],
            ["dataset_snapshots.id"],
        ),
        sa.ForeignKeyConstraint(
            ["signed_off_by"],
            ["reviewer_profiles.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_releases_release_slug", "releases", ["release_slug"], unique=False
    )
    op.create_index(
        "idx_releases_workspace_id", "releases", ["workspace_id"], unique=False
    )
    op.create_table(
        "cost_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agent_run_id", sa.Uuid(), nullable=False),
        sa.Column("agent_output_id", sa.Uuid(), nullable=True),
        sa.Column("model_profile_id", sa.Uuid(), nullable=False),
        sa.Column("tokens_input", sa.Integer(), nullable=False),
        sa.Column("tokens_output", sa.Integer(), nullable=False),
        sa.Column("cost_input", sa.Float(), nullable=True),
        sa.Column("cost_output", sa.Float(), nullable=True),
        sa.Column("cost_total", sa.Float(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("provider_response_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_output_id"],
            ["agent_outputs.id"],
        ),
        sa.ForeignKeyConstraint(
            ["agent_run_id"],
            ["agent_runs.id"],
        ),
        sa.ForeignKeyConstraint(
            ["model_profile_id"],
            ["model_profiles.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_cost_records_model",
        "cost_records",
        ["model_profile_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_cost_records_run", "cost_records", ["agent_run_id"], unique=False
    )
    op.create_table(
        "review_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("review_task_id", sa.Uuid(), nullable=True),
        sa.Column("record_id", sa.Uuid(), nullable=False),
        sa.Column("task_schema_id", sa.Uuid(), nullable=False),
        sa.Column("task_schema_version", sa.Integer(), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=True),
        sa.Column(
            "source",
            sa.Enum("human", "agent", "import_", name="revieweventsource"),
            nullable=False,
        ),
        sa.Column("source_system", sa.String(), nullable=True),
        sa.Column("source_file", sa.String(), nullable=True),
        sa.Column(
            "trust_level",
            sa.Enum(
                "ground_truth", "expert", "external", "untrusted", name="trustlevel"
            ),
            nullable=True,
        ),
        sa.Column("decision", sa.String(), nullable=True),
        sa.Column("labels", sa.JSON(), nullable=False),
        sa.Column("previous_labels", sa.JSON(), nullable=True),
        sa.Column("rationale", sa.String(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("ai_was_revealed", sa.Boolean(), nullable=True),
        sa.Column("review_duration_ms", sa.Integer(), nullable=True),
        sa.Column("agent_run_id", sa.Uuid(), nullable=True),
        sa.Column("agent_output_id", sa.Uuid(), nullable=True),
        sa.Column("unmapped_fields", sa.JSON(), nullable=True),
        sa.Column("supersedes_event_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_output_id"],
            ["agent_outputs.id"],
        ),
        sa.ForeignKeyConstraint(
            ["agent_run_id"],
            ["agent_runs.id"],
        ),
        sa.ForeignKeyConstraint(
            ["record_id"],
            ["records.id"],
        ),
        sa.ForeignKeyConstraint(
            ["review_task_id"],
            ["review_tasks.id"],
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_id"],
            ["reviewer_profiles.id"],
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_event_id"],
            ["review_events.id"],
        ),
        sa.ForeignKeyConstraint(
            ["task_schema_id"],
            ["task_schemas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_review_events_record_id", "review_events", ["record_id"], unique=False
    )
    op.create_index(
        "idx_review_events_reviewer_id", "review_events", ["reviewer_id"], unique=False
    )
    op.create_index(
        "idx_review_events_task_id", "review_events", ["review_task_id"], unique=False
    )
    op.create_index(
        "idx_review_events_workspace_id",
        "review_events",
        ["workspace_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_review_events_workspace_id", table_name="review_events")
    op.drop_index("idx_review_events_task_id", table_name="review_events")
    op.drop_index("idx_review_events_reviewer_id", table_name="review_events")
    op.drop_index("idx_review_events_record_id", table_name="review_events")
    op.drop_table("review_events")
    op.drop_index("idx_cost_records_run", table_name="cost_records")
    op.drop_index("idx_cost_records_model", table_name="cost_records")
    op.drop_table("cost_records")
    op.drop_index("idx_releases_workspace_id", table_name="releases")
    op.drop_index("idx_releases_release_slug", table_name="releases")
    op.drop_table("releases")
    op.drop_index("idx_export_bundles_workspace_id", table_name="export_bundles")
    op.drop_index("idx_export_bundles_dataset_id", table_name="export_bundles")
    op.drop_table("export_bundles")
    op.drop_index("idx_agent_outputs_workspace_id", table_name="agent_outputs")
    op.drop_index("idx_agent_outputs_run_id", table_name="agent_outputs")
    op.drop_index("idx_agent_outputs_record_id", table_name="agent_outputs")
    op.drop_table("agent_outputs")
    op.drop_index("idx_agent_events_run_seq", table_name="agent_events")
    op.drop_index("idx_agent_events_run_id", table_name="agent_events")
    op.drop_table("agent_events")
    op.drop_index("idx_validation_runs_workspace_id", table_name="validation_runs")
    op.drop_index("idx_validation_runs_target", table_name="validation_runs")
    op.drop_table("validation_runs")
    op.drop_index("idx_review_tasks_workspace_id", table_name="review_tasks")
    op.drop_index("idx_review_tasks_record_id", table_name="review_tasks")
    op.drop_index("idx_review_tasks_queue_status", table_name="review_tasks")
    op.drop_index("idx_review_tasks_claimed_by", table_name="review_tasks")
    op.drop_table("review_tasks")
    op.drop_index("idx_dataset_snapshots_workspace_id", table_name="dataset_snapshots")
    op.drop_index("idx_dataset_snapshots_dataset_id", table_name="dataset_snapshots")
    op.drop_table("dataset_snapshots")
    op.drop_index("idx_agent_runs_workspace_id", table_name="agent_runs")
    op.drop_index("idx_agent_runs_status", table_name="agent_runs")
    op.drop_index("idx_agent_runs_dataset_id", table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_index("idx_adjudications_workspace_id", table_name="adjudications")
    op.drop_index("idx_adjudications_record_id", table_name="adjudications")
    op.drop_table("adjudications")
    op.drop_index(
        "idx_wf_step_exec_workspace_id", table_name="workflow_step_executions"
    )
    op.drop_index("idx_wf_step_exec_status", table_name="workflow_step_executions")
    op.drop_index(
        "idx_wf_step_exec_execution_id", table_name="workflow_step_executions"
    )
    op.drop_table("workflow_step_executions")
    op.drop_index("idx_records_workspace_id", table_name="records")
    op.drop_index("idx_records_external_id", table_name="records")
    op.drop_index("idx_records_dataset_id", table_name="records")
    op.drop_index("idx_records_dataset_export", table_name="records")
    op.drop_index("idx_records_content_hash", table_name="records")
    op.drop_index("idx_records_composite_confidence", table_name="records")
    op.drop_table("records")
    op.drop_index("idx_label_mappings_workspace_id", table_name="label_mappings")
    op.drop_index("idx_label_mappings_slug", table_name="label_mappings")
    op.drop_table("label_mappings")
    op.drop_index(
        "idx_workflow_executions_workspace_id", table_name="workflow_executions"
    )
    op.drop_index("idx_workflow_executions_status", table_name="workflow_executions")
    op.drop_index("idx_workflow_executions_def_id", table_name="workflow_executions")
    op.drop_table("workflow_executions")
    op.drop_index("idx_task_schemas_workspace_id", table_name="task_schemas")
    op.drop_index("idx_task_schemas_slug", table_name="task_schemas")
    op.drop_table("task_schemas")
    op.drop_index("idx_saved_views_workspace_id", table_name="saved_views")
    op.drop_index("idx_saved_views_view_type", table_name="saved_views")
    op.drop_table("saved_views")
    op.drop_index("idx_runtime_profiles_workspace_id", table_name="runtime_profiles")
    op.drop_index("idx_runtime_profiles_slug", table_name="runtime_profiles")
    op.drop_table("runtime_profiles")
    op.drop_index(
        "idx_correction_batches_workspace_id", table_name="correction_batches"
    )
    op.drop_index("idx_correction_batches_template_id", table_name="correction_batches")
    op.drop_table("correction_batches")
    op.drop_table("artifacts")
    op.drop_index(
        "idx_workflow_definitions_workspace_id", table_name="workflow_definitions"
    )
    op.drop_index("idx_workflow_definitions_slug", table_name="workflow_definitions")
    op.drop_table("workflow_definitions")
    op.drop_table("reviewer_profiles")
    op.drop_index("idx_prompt_templates_workspace_id", table_name="prompt_templates")
    op.drop_index("idx_prompt_templates_slug", table_name="prompt_templates")
    op.drop_table("prompt_templates")
    op.drop_index(
        "idx_plugin_installations_workspace_id", table_name="plugin_installations"
    )
    op.drop_index(
        "idx_plugin_installations_plugin_id", table_name="plugin_installations"
    )
    op.drop_table("plugin_installations")
    op.drop_index("idx_model_profiles_workspace_id", table_name="model_profiles")
    op.drop_index("idx_model_profiles_slug", table_name="model_profiles")
    op.drop_table("model_profiles")
    op.drop_index("idx_datasets_workspace_id", table_name="datasets")
    op.drop_index("idx_datasets_slug", table_name="datasets")
    op.drop_table("datasets")
    op.drop_index("idx_audit_entries_workspace_id", table_name="audit_entries")
    op.drop_index("idx_audit_entries_target", table_name="audit_entries")
    op.drop_index("idx_audit_entries_action", table_name="audit_entries")
    op.drop_table("audit_entries")
    op.drop_index(op.f("ix_workspaces_workspace_slug"), table_name="workspaces")
    op.drop_table("workspaces")

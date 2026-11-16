-- Schema of a MoLabel database created by SQLModel create_all at 1fc7f65,
-- before Alembic owned the schema. It has no alembic_version table.

CREATE TABLE workspaces (
	id CHAR(32) NOT NULL,
	workspace_name VARCHAR NOT NULL,
	workspace_slug VARCHAR NOT NULL,
	core_version VARCHAR NOT NULL,
	root_path VARCHAR NOT NULL,
	manifest_path VARCHAR NOT NULL,
	reference_app VARCHAR,
	settings JSON,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	PRIMARY KEY (id)
);

CREATE TABLE audit_entries (
	id CHAR(32) NOT NULL,
	action VARCHAR(21) NOT NULL,
	actor_type VARCHAR NOT NULL,
	actor_id VARCHAR,
	target_type VARCHAR NOT NULL,
	target_id CHAR(32) NOT NULL,
	detail JSON,
	file_path VARCHAR,
	file_hash_before VARCHAR,
	file_hash_after VARCHAR,
	session_id VARCHAR,
	created_at DATETIME NOT NULL,
	workspace_id CHAR(32) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE TABLE datasets (
	id CHAR(32) NOT NULL,
	dataset_name VARCHAR NOT NULL,
	dataset_slug VARCHAR NOT NULL,
	description VARCHAR,
	source_type VARCHAR NOT NULL,
	source_config JSON,
	loader_plugin VARCHAR,
	record_kind VARCHAR,
	canonical_id_strategy VARCHAR NOT NULL,
	indexing_mode VARCHAR NOT NULL,
	record_count INTEGER,
	labeled_count INTEGER,
	health_status VARCHAR(7),
	tags JSON,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	last_indexed_at DATETIME,
	workspace_id CHAR(32) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE TABLE model_profiles (
	id CHAR(32) NOT NULL,
	model_profile_slug VARCHAR NOT NULL,
	provider_type VARCHAR(17) NOT NULL,
	provider_name VARCHAR,
	model_identifier VARCHAR NOT NULL,
	transport VARCHAR NOT NULL,
	auth_ref VARCHAR,
	supports_structured_output BOOLEAN,
	supports_tool_use BOOLEAN,
	context_window INTEGER,
	capability_tags JSON,
	routing_metadata JSON,
	cost_per_input_token FLOAT,
	cost_per_output_token FLOAT,
	is_available BOOLEAN,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	workspace_id CHAR(32) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE TABLE plugin_installations (
	id CHAR(32) NOT NULL,
	plugin_id VARCHAR NOT NULL,
	plugin_version VARCHAR NOT NULL,
	plugin_type VARCHAR NOT NULL,
	compatible_core_version VARCHAR NOT NULL,
	entrypoint VARCHAR NOT NULL,
	is_enabled BOOLEAN NOT NULL,
	is_compatible BOOLEAN NOT NULL,
	capabilities JSON,
	config JSON,
	installed_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	workspace_id CHAR(32) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE TABLE prompt_templates (
	id CHAR(32) NOT NULL,
	prompt_slug VARCHAR NOT NULL,
	version VARCHAR NOT NULL,
	name VARCHAR NOT NULL,
	description VARCHAR,
	system_instructions VARCHAR NOT NULL,
	task_rubric VARCHAR,
	few_shot_examples JSON,
	instruction_patches JSON,
	output_schema JSON,
	parent_version_id CHAR(32),
	refinement_source_batch_id CHAR(32),
	is_frozen BOOLEAN NOT NULL,
	file_path VARCHAR NOT NULL,
	created_at DATETIME NOT NULL,
	workspace_id CHAR(32) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(parent_version_id) REFERENCES prompt_templates (id),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE TABLE reviewer_profiles (
	id CHAR(32) NOT NULL,
	display_name VARCHAR NOT NULL,
	avatar_color VARCHAR,
	is_operator BOOLEAN NOT NULL,
	is_active BOOLEAN NOT NULL,
	preferences JSON,
	created_at DATETIME NOT NULL,
	last_active_at DATETIME,
	workspace_id CHAR(32) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE TABLE workflow_definitions (
	id CHAR(32) NOT NULL,
	workflow_slug VARCHAR NOT NULL,
	version INTEGER NOT NULL,
	name VARCHAR NOT NULL,
	description VARCHAR,
	steps JSON NOT NULL,
	is_template BOOLEAN NOT NULL,
	template_source VARCHAR,
	file_path VARCHAR NOT NULL,
	is_active BOOLEAN NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	workspace_id CHAR(32) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE TABLE artifacts (
	id CHAR(32) NOT NULL,
	file_path VARCHAR NOT NULL,
	file_hash VARCHAR NOT NULL,
	file_size_bytes INTEGER NOT NULL,
	file_format VARCHAR NOT NULL,
	record_count INTEGER,
	loader_plugin VARCHAR,
	metadata JSON,
	stale BOOLEAN NOT NULL,
	indexed_at DATETIME NOT NULL,
	created_at DATETIME NOT NULL,
	workspace_id CHAR(32) NOT NULL,
	dataset_id CHAR(32),
	PRIMARY KEY (id),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id),
	FOREIGN KEY(dataset_id) REFERENCES datasets (id)
);

CREATE TABLE correction_batches (
	id CHAR(32) NOT NULL,
	prompt_template_id CHAR(32) NOT NULL,
	batch_sequence INTEGER NOT NULL,
	status VARCHAR(19) NOT NULL,
	correction_count INTEGER NOT NULL,
	batch_threshold INTEGER NOT NULL,
	corrections JSON,
	analysis_results JSON,
	proposed_refinements JSON,
	applied_prompt_version_id CHAR(32),
	file_path VARCHAR NOT NULL,
	created_at DATETIME NOT NULL,
	analyzed_at DATETIME,
	applied_at DATETIME,
	workspace_id CHAR(32) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(prompt_template_id) REFERENCES prompt_templates (id),
	FOREIGN KEY(applied_prompt_version_id) REFERENCES prompt_templates (id),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE TABLE runtime_profiles (
	id CHAR(32) NOT NULL,
	runtime_profile_slug VARCHAR NOT NULL,
	mode VARCHAR NOT NULL,
	fallback_model_profile_id CHAR(32),
	provider_priority JSON,
	max_concurrent_requests INTEGER,
	timeout_seconds INTEGER,
	retry_config JSON,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	workspace_id CHAR(32) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(fallback_model_profile_id) REFERENCES model_profiles (id),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE TABLE saved_views (
	id CHAR(32) NOT NULL,
	owner_id CHAR(32),
	view_name VARCHAR NOT NULL,
	description VARCHAR,
	view_type VARCHAR NOT NULL,
	target_dataset_id CHAR(32),
	filters JSON NOT NULL,
	sort_config JSON,
	column_config JSON,
	grouping JSON,
	is_default BOOLEAN NOT NULL,
	is_shared BOOLEAN NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	workspace_id CHAR(32) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(owner_id) REFERENCES reviewer_profiles (id),
	FOREIGN KEY(target_dataset_id) REFERENCES datasets (id),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE TABLE task_schemas (
	id CHAR(32) NOT NULL,
	task_schema_slug VARCHAR NOT NULL,
	version INTEGER NOT NULL,
	task_type VARCHAR NOT NULL,
	title VARCHAR NOT NULL,
	instructions VARCHAR,
	record_selector JSON,
	label_fields JSON NOT NULL,
	required_fields JSON,
	optional_fields JSON,
	blind_review_policy VARCHAR(29) NOT NULL,
	overlap_policy JSON,
	adjudication_policy JSON,
	supported_agent_roles JSON,
	default_model_profile_id CHAR(32),
	export_mapping JSON,
	is_active BOOLEAN NOT NULL,
	is_frozen BOOLEAN NOT NULL,
	file_path VARCHAR,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	workspace_id CHAR(32) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(default_model_profile_id) REFERENCES model_profiles (id),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE TABLE workflow_executions (
	id CHAR(32) NOT NULL,
	workflow_definition_id CHAR(32) NOT NULL,
	workflow_version INTEGER NOT NULL,
	status VARCHAR(9) NOT NULL,
	current_step_id VARCHAR,
	step_execution_count INTEGER,
	context JSON,
	error_summary VARCHAR,
	started_at DATETIME,
	paused_at DATETIME,
	completed_at DATETIME,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	workspace_id CHAR(32) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(workflow_definition_id) REFERENCES workflow_definitions (id),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE TABLE label_mappings (
	id CHAR(32) NOT NULL,
	mapping_slug VARCHAR NOT NULL,
	name VARCHAR NOT NULL,
	source_system VARCHAR NOT NULL,
	source_format VARCHAR,
	task_schema_id CHAR(32) NOT NULL,
	field_mappings JSON NOT NULL,
	value_mappings JSON,
	type_conversions JSON,
	unmapped_field_policy VARCHAR NOT NULL,
	default_trust_level VARCHAR(12) NOT NULL,
	file_path VARCHAR,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	workspace_id CHAR(32) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(task_schema_id) REFERENCES task_schemas (id),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE TABLE records (
	id CHAR(32) NOT NULL,
	external_id VARCHAR,
	sequence_index INTEGER,
	content_hash VARCHAR,
	stable_fields JSON NOT NULL,
	payload JSON,
	record_kind VARCHAR,
	source_metadata JSON,
	label_count INTEGER,
	latest_label JSON,
	composite_confidence FLOAT,
	export_eligible BOOLEAN NOT NULL,
	flags JSON,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	workspace_id CHAR(32) NOT NULL,
	dataset_id CHAR(32) NOT NULL,
	artifact_id CHAR(32),
	PRIMARY KEY (id),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id),
	FOREIGN KEY(dataset_id) REFERENCES datasets (id),
	FOREIGN KEY(artifact_id) REFERENCES artifacts (id)
);

CREATE TABLE workflow_step_executions (
	id CHAR(32) NOT NULL,
	workflow_execution_id CHAR(32) NOT NULL,
	step_id VARCHAR NOT NULL,
	step_type VARCHAR(18) NOT NULL,
	step_config JSON NOT NULL,
	status VARCHAR(22) NOT NULL,
	iteration INTEGER NOT NULL,
	parent_step_execution_id CHAR(32),
	result JSON,
	error_summary VARCHAR,
	started_at DATETIME,
	completed_at DATETIME,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	workspace_id CHAR(32) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(workflow_execution_id) REFERENCES workflow_executions (id),
	FOREIGN KEY(parent_step_execution_id) REFERENCES workflow_step_executions (id),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE TABLE adjudications (
	id CHAR(32) NOT NULL,
	record_id CHAR(32) NOT NULL,
	dataset_id CHAR(32) NOT NULL,
	task_schema_id CHAR(32) NOT NULL,
	adjudicator_id CHAR(32) NOT NULL,
	workflow_step_execution_id CHAR(32),
	conflicting_event_ids JSON NOT NULL,
	resolution VARCHAR(21) NOT NULL,
	resolved_labels JSON,
	rationale VARCHAR,
	policy_reference VARCHAR,
	metadata JSON,
	created_at DATETIME NOT NULL,
	workspace_id CHAR(32) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(record_id) REFERENCES records (id),
	FOREIGN KEY(dataset_id) REFERENCES datasets (id),
	FOREIGN KEY(task_schema_id) REFERENCES task_schemas (id),
	FOREIGN KEY(adjudicator_id) REFERENCES reviewer_profiles (id),
	FOREIGN KEY(workflow_step_execution_id) REFERENCES workflow_step_executions (id),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE TABLE agent_runs (
	id CHAR(32) NOT NULL,
	dataset_id CHAR(32) NOT NULL,
	task_schema_id CHAR(32) NOT NULL,
	model_profile_id CHAR(32) NOT NULL,
	runtime_profile_id CHAR(32),
	prompt_template_id CHAR(32),
	prompt_version VARCHAR,
	agent_role VARCHAR(20) NOT NULL,
	adapter_plugin VARCHAR,
	status VARCHAR(19) NOT NULL,
	config JSON,
	record_filter JSON,
	total_records INTEGER,
	completed_records INTEGER,
	failed_records INTEGER,
	retry_count INTEGER NOT NULL,
	error_summary VARCHAR,
	cost_estimate JSON,
	cost_actual JSON,
	comparison_id CHAR(32),
	started_at DATETIME,
	completed_at DATETIME,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	workspace_id CHAR(32) NOT NULL,
	workflow_step_execution_id CHAR(32),
	PRIMARY KEY (id),
	FOREIGN KEY(dataset_id) REFERENCES datasets (id),
	FOREIGN KEY(task_schema_id) REFERENCES task_schemas (id),
	FOREIGN KEY(model_profile_id) REFERENCES model_profiles (id),
	FOREIGN KEY(runtime_profile_id) REFERENCES runtime_profiles (id),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id),
	FOREIGN KEY(workflow_step_execution_id) REFERENCES workflow_step_executions (id)
);

CREATE TABLE dataset_snapshots (
	id CHAR(32) NOT NULL,
	dataset_id CHAR(32) NOT NULL,
	workflow_step_execution_id CHAR(32),
	name VARCHAR NOT NULL,
	description VARCHAR,
	snapshot_type VARCHAR NOT NULL,
	parent_snapshot_id CHAR(32),
	record_count INTEGER NOT NULL,
	labeled_count INTEGER NOT NULL,
	quality_metrics JSON,
	label_summary JSON,
	dataset_membership JSON,
	workflow_state JSON,
	prompt_versions JSON,
	project_config JSON,
	delta_data JSON,
	created_at DATETIME NOT NULL,
	workspace_id CHAR(32) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(dataset_id) REFERENCES datasets (id),
	FOREIGN KEY(workflow_step_execution_id) REFERENCES workflow_step_executions (id),
	FOREIGN KEY(parent_snapshot_id) REFERENCES dataset_snapshots (id),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE TABLE review_tasks (
	id CHAR(32) NOT NULL,
	queue_id VARCHAR NOT NULL,
	record_id CHAR(32) NOT NULL,
	task_schema_id CHAR(32) NOT NULL,
	status VARCHAR(9) NOT NULL,
	priority INTEGER NOT NULL,
	priority_reason VARCHAR,
	claimed_by CHAR(32),
	claimed_at DATETIME,
	claim_expired_count INTEGER NOT NULL,
	is_overlap BOOLEAN NOT NULL,
	is_calibration BOOLEAN NOT NULL,
	draft_labels JSON,
	agent_output_ids VARCHAR,
	ai_revealed BOOLEAN NOT NULL,
	ai_revealed_at DATETIME,
	submitted_at DATETIME,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	workspace_id CHAR(32) NOT NULL,
	dataset_id CHAR(32) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(record_id) REFERENCES records (id),
	FOREIGN KEY(task_schema_id) REFERENCES task_schemas (id),
	FOREIGN KEY(claimed_by) REFERENCES reviewer_profiles (id),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id),
	FOREIGN KEY(dataset_id) REFERENCES datasets (id)
);

CREATE TABLE validation_runs (
	id CHAR(32) NOT NULL,
	target_type VARCHAR NOT NULL,
	target_id CHAR(32) NOT NULL,
	workflow_step_execution_id CHAR(32),
	validation_plugin VARCHAR,
	status VARCHAR(7) NOT NULL,
	gates JSON,
	passed_gate_count INTEGER,
	total_gate_count INTEGER,
	summary VARCHAR,
	report_path VARCHAR,
	started_at DATETIME,
	completed_at DATETIME,
	created_at DATETIME NOT NULL,
	workspace_id CHAR(32) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(workflow_step_execution_id) REFERENCES workflow_step_executions (id),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE TABLE agent_events (
	id CHAR(32) NOT NULL,
	agent_run_id CHAR(32) NOT NULL,
	event_type VARCHAR(16) NOT NULL,
	record_id CHAR(32),
	sequence_number INTEGER NOT NULL,
	payload JSON,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(agent_run_id) REFERENCES agent_runs (id),
	FOREIGN KEY(record_id) REFERENCES records (id)
);

CREATE TABLE agent_outputs (
	id CHAR(32) NOT NULL,
	agent_run_id CHAR(32) NOT NULL,
	record_id CHAR(32) NOT NULL,
	task_schema_id CHAR(32) NOT NULL,
	output_type VARCHAR NOT NULL,
	labels JSON NOT NULL,
	raw_response JSON,
	confidence_self_reported FLOAT,
	confidence_self_consistency FLOAT,
	confidence_logprobs FLOAT,
	composite_confidence FLOAT,
	tokens_input INTEGER,
	tokens_output INTEGER,
	latency_ms INTEGER,
	validation_passed BOOLEAN NOT NULL,
	validation_errors JSON,
	retry_attempt INTEGER NOT NULL,
	is_visible_for_review BOOLEAN NOT NULL,
	normalization_status VARCHAR,
	created_at DATETIME NOT NULL,
	workspace_id CHAR(32) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(agent_run_id) REFERENCES agent_runs (id),
	FOREIGN KEY(record_id) REFERENCES records (id),
	FOREIGN KEY(task_schema_id) REFERENCES task_schemas (id),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE TABLE export_bundles (
	id CHAR(32) NOT NULL,
	dataset_id CHAR(32) NOT NULL,
	task_schema_id CHAR(32) NOT NULL,
	workflow_step_execution_id CHAR(32),
	export_slug VARCHAR NOT NULL,
	status VARCHAR(10) NOT NULL,
	export_format VARCHAR(15) NOT NULL,
	output_path VARCHAR NOT NULL,
	output_namespace VARCHAR,
	record_count INTEGER NOT NULL,
	include_config JSON,
	filter_config JSON,
	file_hash VARCHAR,
	file_size_bytes INTEGER,
	source_snapshot_id CHAR(32),
	validation_run_id CHAR(32),
	packager_plugin VARCHAR,
	created_at DATETIME NOT NULL,
	workspace_id CHAR(32) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(dataset_id) REFERENCES datasets (id),
	FOREIGN KEY(task_schema_id) REFERENCES task_schemas (id),
	FOREIGN KEY(workflow_step_execution_id) REFERENCES workflow_step_executions (id),
	FOREIGN KEY(source_snapshot_id) REFERENCES dataset_snapshots (id),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE TABLE releases (
	id CHAR(32) NOT NULL,
	release_slug VARCHAR NOT NULL,
	version VARCHAR NOT NULL,
	name VARCHAR NOT NULL,
	description VARCHAR,
	status VARCHAR(16) NOT NULL,
	export_bundle_ids JSON NOT NULL,
	validation_run_ids JSON,
	dataset_snapshot_id CHAR(32),
	quality_summary JSON,
	signed_off_by CHAR(32),
	signed_off_at DATETIME,
	release_metadata JSON,
	manifest_path VARCHAR,
	created_at DATETIME NOT NULL,
	released_at DATETIME,
	revoked_at DATETIME,
	workspace_id CHAR(32) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(dataset_snapshot_id) REFERENCES dataset_snapshots (id),
	FOREIGN KEY(signed_off_by) REFERENCES reviewer_profiles (id),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE TABLE cost_records (
	id CHAR(32) NOT NULL,
	agent_run_id CHAR(32) NOT NULL,
	agent_output_id CHAR(32),
	model_profile_id CHAR(32) NOT NULL,
	tokens_input INTEGER NOT NULL,
	tokens_output INTEGER NOT NULL,
	cost_input FLOAT,
	cost_output FLOAT,
	cost_total FLOAT,
	latency_ms INTEGER,
	provider_response_metadata JSON,
	created_at DATETIME NOT NULL,
	workspace_id CHAR(32) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(agent_run_id) REFERENCES agent_runs (id),
	FOREIGN KEY(agent_output_id) REFERENCES agent_outputs (id),
	FOREIGN KEY(model_profile_id) REFERENCES model_profiles (id),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE TABLE review_events (
	id CHAR(32) NOT NULL,
	review_task_id CHAR(32),
	record_id CHAR(32) NOT NULL,
	task_schema_id CHAR(32) NOT NULL,
	task_schema_version INTEGER NOT NULL,
	reviewer_id CHAR(32),
	source VARCHAR(7) NOT NULL,
	source_system VARCHAR,
	source_file VARCHAR,
	trust_level VARCHAR(12),
	decision VARCHAR,
	labels JSON NOT NULL,
	previous_labels JSON,
	rationale VARCHAR,
	confidence FLOAT,
	ai_was_revealed BOOLEAN,
	review_duration_ms INTEGER,
	agent_run_id CHAR(32),
	agent_output_id CHAR(32),
	unmapped_fields JSON,
	supersedes_event_id CHAR(32),
	created_at DATETIME NOT NULL,
	workspace_id CHAR(32) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(review_task_id) REFERENCES review_tasks (id),
	FOREIGN KEY(record_id) REFERENCES records (id),
	FOREIGN KEY(task_schema_id) REFERENCES task_schemas (id),
	FOREIGN KEY(reviewer_id) REFERENCES reviewer_profiles (id),
	FOREIGN KEY(agent_run_id) REFERENCES agent_runs (id),
	FOREIGN KEY(agent_output_id) REFERENCES agent_outputs (id),
	FOREIGN KEY(supersedes_event_id) REFERENCES review_events (id),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE UNIQUE INDEX ix_workspaces_workspace_slug ON workspaces (workspace_slug);

CREATE INDEX idx_audit_entries_workspace_id ON audit_entries (workspace_id);

CREATE INDEX idx_audit_entries_action ON audit_entries (action);

CREATE INDEX idx_audit_entries_target ON audit_entries (target_type, target_id);

CREATE INDEX idx_datasets_slug ON datasets (dataset_slug);

CREATE INDEX idx_datasets_workspace_id ON datasets (workspace_id);

CREATE INDEX idx_model_profiles_workspace_id ON model_profiles (workspace_id);

CREATE INDEX idx_model_profiles_slug ON model_profiles (model_profile_slug);

CREATE INDEX idx_plugin_installations_plugin_id ON plugin_installations (plugin_id);

CREATE INDEX idx_plugin_installations_workspace_id ON plugin_installations (workspace_id);

CREATE INDEX idx_prompt_templates_workspace_id ON prompt_templates (workspace_id);

CREATE INDEX idx_prompt_templates_slug ON prompt_templates (prompt_slug);

CREATE INDEX idx_workflow_definitions_workspace_id ON workflow_definitions (workspace_id);

CREATE INDEX idx_workflow_definitions_slug ON workflow_definitions (workflow_slug);

CREATE INDEX idx_correction_batches_template_id ON correction_batches (prompt_template_id);

CREATE INDEX idx_correction_batches_workspace_id ON correction_batches (workspace_id);

CREATE INDEX idx_runtime_profiles_slug ON runtime_profiles (runtime_profile_slug);

CREATE INDEX idx_runtime_profiles_workspace_id ON runtime_profiles (workspace_id);

CREATE INDEX idx_saved_views_view_type ON saved_views (view_type);

CREATE INDEX idx_saved_views_workspace_id ON saved_views (workspace_id);

CREATE INDEX idx_task_schemas_workspace_id ON task_schemas (workspace_id);

CREATE INDEX idx_task_schemas_slug ON task_schemas (task_schema_slug);

CREATE INDEX idx_workflow_executions_status ON workflow_executions (status);

CREATE INDEX idx_workflow_executions_def_id ON workflow_executions (workflow_definition_id);

CREATE INDEX idx_workflow_executions_workspace_id ON workflow_executions (workspace_id);

CREATE INDEX idx_label_mappings_workspace_id ON label_mappings (workspace_id);

CREATE INDEX idx_label_mappings_slug ON label_mappings (mapping_slug);

CREATE INDEX idx_records_dataset_id ON records (dataset_id);

CREATE INDEX idx_records_dataset_export ON records (dataset_id, export_eligible);

CREATE INDEX idx_records_content_hash ON records (content_hash);

CREATE INDEX idx_records_composite_confidence ON records (dataset_id, composite_confidence);

CREATE INDEX idx_records_external_id ON records (external_id);

CREATE INDEX idx_records_workspace_id ON records (workspace_id);

CREATE INDEX idx_wf_step_exec_execution_id ON workflow_step_executions (workflow_execution_id);

CREATE INDEX idx_wf_step_exec_workspace_id ON workflow_step_executions (workspace_id);

CREATE INDEX idx_wf_step_exec_status ON workflow_step_executions (status);

CREATE INDEX idx_adjudications_workspace_id ON adjudications (workspace_id);

CREATE INDEX idx_adjudications_record_id ON adjudications (record_id);

CREATE INDEX idx_agent_runs_dataset_id ON agent_runs (dataset_id);

CREATE INDEX idx_agent_runs_status ON agent_runs (status);

CREATE INDEX idx_agent_runs_workspace_id ON agent_runs (workspace_id);

CREATE INDEX idx_dataset_snapshots_dataset_id ON dataset_snapshots (dataset_id);

CREATE INDEX idx_dataset_snapshots_workspace_id ON dataset_snapshots (workspace_id);

CREATE INDEX idx_review_tasks_record_id ON review_tasks (record_id);

CREATE INDEX idx_review_tasks_queue_status ON review_tasks (queue_id, status);

CREATE INDEX idx_review_tasks_claimed_by ON review_tasks (claimed_by);

CREATE INDEX idx_review_tasks_workspace_id ON review_tasks (workspace_id);

CREATE INDEX idx_validation_runs_target ON validation_runs (target_type, target_id);

CREATE INDEX idx_validation_runs_workspace_id ON validation_runs (workspace_id);

CREATE INDEX idx_agent_events_run_id ON agent_events (agent_run_id);

CREATE INDEX idx_agent_events_run_seq ON agent_events (agent_run_id, sequence_number);

CREATE INDEX idx_agent_outputs_record_id ON agent_outputs (record_id);

CREATE INDEX idx_agent_outputs_run_id ON agent_outputs (agent_run_id);

CREATE INDEX idx_agent_outputs_workspace_id ON agent_outputs (workspace_id);

CREATE INDEX idx_export_bundles_workspace_id ON export_bundles (workspace_id);

CREATE INDEX idx_export_bundles_dataset_id ON export_bundles (dataset_id);

CREATE INDEX idx_releases_workspace_id ON releases (workspace_id);

CREATE INDEX idx_releases_release_slug ON releases (release_slug);

CREATE INDEX idx_cost_records_model ON cost_records (model_profile_id, created_at);

CREATE INDEX idx_cost_records_run ON cost_records (agent_run_id);

CREATE INDEX idx_review_events_reviewer_id ON review_events (reviewer_id);

CREATE INDEX idx_review_events_workspace_id ON review_events (workspace_id);

CREATE INDEX idx_review_events_record_id ON review_events (record_id);

CREATE INDEX idx_review_events_task_id ON review_events (review_task_id);

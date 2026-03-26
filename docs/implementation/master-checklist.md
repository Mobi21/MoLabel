# MoLabel Master Feature Checklist

Every item from the PRD, ADRs, architecture specs, and AGENTS.md. Each item is granular enough for a single coding agent session.

---

## SC: Project Scaffolding & Build System

- [x] `SC-001` uv workspace monorepo with four Python packages: molabel-core, molabel-app, molabel-plugins, molabel-depolarize (source: AGENTS.md, Repository Layout; PRD 25.2)
- [x] `SC-002` Namespace package convention: no `__init__.py` at `src/molabel/` level in core, app, plugins; separate `molabel_depolarize` namespace (source: AGENTS.md, Namespace Package Convention)
- [x] `SC-003` Python 3.12+ with pyproject.toml for each package; uv sync bootstraps all (source: CLAUDE.md, Bootstrap)
- [x] `SC-004` Frontend project at `frontend/` with React 19 + TypeScript + Vite + package.json (source: ADR-001, Decision; CLAUDE.md)
- [x] `SC-005` Tauri v2 desktop shell at `src-tauri/` with Rust Cargo config (source: ADR-002, Decision; CLAUDE.md)
- [x] `SC-006` Module boundary enforcement: core never imports app/plugins/depolarize; app depends on core only; plugins depends on core only; depolarize depends on core + plugins (source: AGENTS.md, Module Boundary Rules)
- [x] `SC-007` OpenAPI codegen pipeline: FastAPI generates OpenAPI spec → TypeScript client auto-generated (source: ADR-001, Decision; AGENTS.md)
- [x] `SC-008` Dev mode: `uv run fastapi dev` + `npm run dev` with Vite proxying API requests (source: ADR-002, Development Mode; CLAUDE.md)
- [x] `SC-009` `uv run molabel-dev` command starts FastAPI + frontend dev server together (source: CLAUDE.md, Bootstrap)
- [x] `SC-010` Ruff for Python linting/formatting; prettier + eslint for TypeScript (source: AGENTS.md, Conventions; CLAUDE.md)
- [x] `SC-011` CI quality gates: pytest, vitest, ruff, tsc, OpenAPI sync check, Playwright E2E (source: PRD 22.5.1)
- [x] `SC-012` CI generates coverage reports, bundle size report, Lighthouse accessibility score (non-blocking) (source: PRD 22.5.1)

---

## DM: Data Model & Database

- [x] `DM-001` Three storage layers: file-canonical, DB-canonical (SQLite WAL), derived cache — with explicit ownership per object type (source: data-model.md, Overview; PRD 13.1-13.3)
- [x] `DM-002` SQLite in WAL mode for concurrent reader sessions; write operations use queue-level locking (source: data-model.md; workflow-execution.md, SQLite WAL Mode)
- [x] `DM-003` All enum types: ReviewEventSource, TrustLevel, AgentRunStatus, WorkflowStepType, WorkflowStepCategory, LoopTermination, AdjudicationResolution, ExportFormat, ProviderType, WorkflowExecutionStatus, WorkflowStepExecutionStatus, AgentRole, AgentEventType, ReviewDecision, ValidationStatus, ReleaseStatus, AuditAction, BlindReviewPolicy, CorrectionBatchStatus, ReviewTaskStatus, DatasetHealthStatus, ExportBundleStatus (source: data-model.md, Enum Types)
- [x] `DM-004` Workspace domain object with SQLModel: id, workspace_name, workspace_slug, core_version, root_path, manifest_path, reference_app, settings, timestamps (source: data-model.md, Workspace)
- [x] `DM-005` Artifact domain object: file_path, file_hash, file_format, record_count, loader_plugin, stale flag, indexed_at (source: data-model.md, Artifact)
- [x] `DM-006` Dataset domain object: dataset_name, dataset_slug, source_type, source_config, loader_plugin, record_kind, canonical_id_strategy, indexing_mode, health_status, tags (source: data-model.md, Dataset)
- [x] `DM-007` Record domain object: external_id, content_hash, stable_fields, payload, record_kind, source_metadata, label_count, latest_label, composite_confidence, export_eligible, flags (source: data-model.md, Record)
- [x] `DM-008` TaskSchema domain object: task_schema_slug, version, task_type, title, instructions, record_selector, label_fields, required_fields, optional_fields, blind_review_policy, overlap_policy, adjudication_policy, supported_agent_roles, default_model_profile_or_routing_profile, export_mapping, is_active, is_frozen (source: data-model.md, TaskSchema; PRD 15.3.3)
- [x] `DM-009` ModelProfile domain object: model_profile_slug, provider_type, model_identifier, transport, auth_ref (env var/local secret reference, not raw project-file secret), supports_structured_output, supports_tool_use, context_window, routing_policy_metadata, cost fields, is_available (source: data-model.md, ModelProfile; PRD 15.3.2)
- [x] `DM-010` RuntimeProfile domain object: runtime_profile_slug, mode, fallback_model_profile_id, provider_priority, max_concurrent_requests, timeout_seconds, retry_config (source: data-model.md, RuntimeProfile)
- [x] `DM-011` ReviewTask domain object: queue_id, record_id, task_schema_id, status, priority, priority_reason, claimed_by, claimed_at, claim_expired_count, is_overlap, is_calibration, draft_labels, ai_revealed (source: data-model.md, ReviewTask; session-and-identity.md)
- [x] `DM-012` ReviewEvent domain object (append-only): source, source_system, trust_level, decision, labels, previous_labels, rationale, confidence, ai_was_revealed, review_duration_ms, supersedes_event_id (source: data-model.md, ReviewEvent)
- [x] `DM-013` AgentRun domain object: dataset_id, task_schema_id, model_profile_id, runtime_profile_id, prompt_template_id, agent_role, adapter_used, provider_or_runtime, model_identifier, status, config, record_filter, cost_estimate, cost_actual, comparison_id, retry_count, partial_failure_summary, downstream_queue_linkage (source: data-model.md, AgentRun; PRD 15.4.1)
- [x] `DM-014` AgentEvent domain object: event_type, record_id, sequence_number, payload (source: data-model.md, AgentEvent)
- [x] `DM-015` AgentOutput domain object: output_type, labels, raw_response, confidence signals (self_reported, self_consistency, logprobs, composite), tokens, latency, validation_passed, validation_errors, retry_attempt, is_visible_for_review, accept_edit_reject_ai_eligibility (source: data-model.md, AgentOutput; PRD 15.4.2)
- [x] `DM-016` Adjudication domain object: record_id, adjudicator_id, conflicting_event_ids, resolution, resolved_labels, rationale, policy_reference (source: data-model.md, Adjudication)
- [x] `DM-017` WorkflowDefinition domain object: workflow_slug, version, steps, is_template, template_source, file_path, is_active (source: data-model.md, WorkflowDefinition)
- [x] `DM-018` WorkflowExecution domain object: workflow_definition_id, status, current_step_id, context (serialized WorkflowContext JSON), timestamps (source: data-model.md, WorkflowExecution)
- [x] `DM-019` WorkflowStepExecution domain object: step_id, step_type, step_config, status, iteration, parent_step_execution_id, result, error details (source: data-model.md, WorkflowStepExecution)
- [x] `DM-020` PromptTemplate domain object: prompt_slug, version, system_instructions, task_rubric, few_shot_examples, instruction_patches, output_schema, parent_version_id, refinement_source_batch_id, is_frozen (source: data-model.md, PromptTemplate)
- [x] `DM-021` CorrectionBatch domain object: prompt_template_id, batch_sequence, status, correction_count, batch_threshold, corrections, analysis_results, proposed_refinements (source: data-model.md, CorrectionBatch)
- [x] `DM-022` DatasetSnapshot domain object: snapshot_type (full/delta), parent_snapshot_id, quality_metrics, label_summary, dataset_membership, workflow_state, delta_data (source: data-model.md, DatasetSnapshot)
- [x] `DM-023` LabelMapping domain object: mapping_slug, source_system, source_format, field_mappings, value_mappings, type_conversions, unmapped_field_policy, default_trust_level (source: data-model.md, LabelMapping)
- [x] `DM-024` ValidationRun domain object with gate results and validation report (source: data-model.md, Entity Relationship)
- [x] `DM-025` ExportBundle domain object with status lifecycle and file references (source: data-model.md, Entity Relationship; PRD 15.9)
- [x] `DM-026` Release domain object with draft/validating/pending_approval/approved/released/rejected/revoked lifecycle (source: data-model.md, ReleaseStatus enum)
- [x] `DM-027` PluginInstallation domain object tracking installed plugins per workspace (source: data-model.md, Entity Relationship)
- [x] `DM-028` AuditEntry domain object with all AuditAction types (source: data-model.md, AuditAction enum)
- [x] `DM-029` SavedView domain object for saved filter/sort configurations (source: data-model.md, Entity Relationship)
- [x] `DM-030` ReviewerProfile domain object: display_name, avatar_color, is_operator, is_active, preferences (source: session-and-identity.md, Reviewer Profiles)
- [x] `DM-031` CostRecord domain object for tracking per-run and per-query costs (source: data-model.md, Entity Relationship)
- [x] `DM-032` Entity relationships with correct foreign keys and indexes per data-model.md ER diagram (source: data-model.md, Entity Relationship Summary)
- [x] `DM-033` Conflict detection and repair: file-changed-on-disk, file-deleted, plugin-unavailable, schema-mismatch, DB-draft-modified-elsewhere (source: PRD 13.5; data-model.md)
- [x] `DM-034` Workspace manifest contract: workbench.project.yaml with all minimal fields (workspace_id, workspace_name, core_version, enabled_plugins, datasets, task_schemas, etc.) (source: PRD 13.6-13.8)

---

## DB: Database Migrations

- [x] `DB-001` Alembic migration infrastructure at `packages/molabel-core/src/molabel/core/migrations/` (source: database-migrations.md)
- [x] `DB-002` Initial schema migration (001_initial_schema.py) creating all tables (source: database-migrations.md)
- [x] `DB-003` Auto-migration on app startup: detect schema version, run pending migrations, show progress (source: database-migrations.md, User Experience)
- [x] `DB-004` Pre-migration backup: create timestamped backup before running migrations (source: database-migrations.md, Backup Strategy)
- [x] `DB-005` Multi-skip upgrade support: Alembic handles jumping multiple versions (source: database-migrations.md, Multi-Skip Upgrades)
- [x] `DB-006` Schema version in workspace manifest: core_version field, newer-version warning (source: database-migrations.md, Schema Version)

---

## WF: Workflow Engine

- [x] `WF-001` Workflow YAML parser: parse workflow definition files from `workbench/workflows/` (source: ADR-003, Workflow Definition)
- [x] `WF-002` WorkflowContext dataclass: datasets, record_sets, active_record_set_id, agent_run_ids, agent_outputs, review_queue_ids, metrics, step_outputs, variables, export/snapshot references (source: workflow-execution.md, Shared Workflow Context)
- [x] `WF-003` Step type registry: register all ~20 step types across 6 categories (source: ADR-003, Step Type Catalog)
- [x] `WF-004` data_ingest step implementation with inputs/outputs/side-effects per spec (source: workflow-execution.md, Data Steps)
- [x] `WF-005` data_normalize step implementation (source: workflow-execution.md, Data Steps)
- [x] `WF-006` data_filter step implementation (source: workflow-execution.md, Data Steps)
- [x] `WF-007` data_sample step implementation with strategies: random, stratified, confidence_based, active_learning (source: workflow-execution.md, Data Steps)
- [x] `WF-008` data_deduplicate step implementation with exact, fuzzy, embedding strategies (source: workflow-execution.md, Data Steps)
- [x] `WF-009` agent_run step implementation with full I/O spec (source: workflow-execution.md, Agent Steps)
- [x] `WF-010` agent_compare step implementation for multi-model runs (source: workflow-execution.md, Agent Steps)
- [x] `WF-011` human_review step implementation with queue creation and waiting_for_human state (source: workflow-execution.md, Human Steps)
- [x] `WF-012` human_triage step implementation with configurable categories (source: workflow-execution.md, Human Steps)
- [x] `WF-013` human_calibration step implementation with shared calibration set and min_reviewers (source: workflow-execution.md, Human Steps)
- [x] `WF-014` human_adjudication step implementation (source: workflow-execution.md, Human Steps)
- [x] `WF-015` quality_check step implementation with min_agreement, min_coverage, min_confidence (source: workflow-execution.md, Quality Steps)
- [x] `WF-016` agreement_analysis step implementation: Cohen's kappa, Fleiss' kappa, confusion matrices (source: workflow-execution.md, Quality Steps)
- [x] `WF-017` drift_detection step implementation with reference snapshot comparison (source: workflow-execution.md, Quality Steps)
- [x] `WF-018` export step implementation with atomic write (temp + rename) (source: workflow-execution.md, Output Steps)
- [x] `WF-019` snapshot step implementation (source: workflow-execution.md, Output Steps)
- [x] `WF-020` release_validation step implementation with validation gates (source: workflow-execution.md, Output Steps)
- [x] `WF-021` loop step implementation: container orchestrating body steps across iterations (source: workflow-execution.md, Loop Execution)
- [x] `WF-022` Loop termination: count-based (source: workflow-execution.md, Termination Strategies)
- [x] `WF-023` Loop termination: metric-based with threshold evaluation (source: workflow-execution.md, Termination Strategies)
- [x] `WF-024` Loop termination: coverage-based with review/agent/any scopes (source: workflow-execution.md, Termination Strategies)
- [x] `WF-025` Loop termination: manual with operator prompt (source: workflow-execution.md, Termination Strategies)
- [x] `WF-026` Loop body step reset between iterations; metrics/variables accumulate, record_sets get iteration suffixes (source: workflow-execution.md, Loop Body Step Reset)
- [x] `WF-027` Nested loop support (source: workflow-execution.md, Nested Loops)
- [x] `WF-028` conditional step implementation with predicate evaluation against WorkflowContext (source: workflow-execution.md, Conditional Branching)
- [x] `WF-029` Predicate expression language: comparison, boolean, membership, access operators (source: workflow-execution.md, Predicate Evaluation)
- [x] `WF-030` Transitive skip propagation for conditional branches (source: workflow-execution.md, Transitive Skip Propagation)
- [x] `WF-031` parallel step implementation with concurrent child execution (source: workflow-execution.md, Parallel Step Execution)
- [x] `WF-032` Parallel context merging: record_sets, agent_run_ids, metrics (last-write-wins), variables (source: workflow-execution.md, Context Merging)
- [x] `WF-033` Parallel failure modes: default (partially_failed) and fail-fast (source: workflow-execution.md, Failure Modes)
- [x] `WF-034` gate step implementation: pause for operator approval with optional reason requirement (source: workflow-execution.md, Control Steps)
- [x] `WF-035` Step execution state machine: pending → ready → running → {completed, failed, waiting_for_human, waiting_for_gate, waiting_for_breakpoint, partially_failed, interrupted, cancelled} (source: workflow-execution.md, State Machine)
- [x] `WF-036` Predecessor resolution: implicit (YAML order) and explicit (depends_on) DAG building (source: workflow-execution.md, Predecessor Resolution)
- [x] `WF-037` Breakpoint behavior: waiting_for_breakpoint state, operator continue/edit-config/skip/cancel actions (source: workflow-execution.md, Breakpoint Behavior)
- [x] `WF-038` pause_on_every_step workflow mode (source: workflow-execution.md, Breakpoint Behavior)
- [x] `WF-039` Error handling: step failure pauses workflow, operator recovery actions (retry, skip, cancel, resume) (source: workflow-execution.md, Error Handling)
- [x] `WF-040` Partial step failure: agent_run partial success with retry-remaining, accept-partial, retry-all options (source: workflow-execution.md, Partial Step Failure)
- [x] `WF-041` Step timeout handling: configurable per step, default 1 hour for automated, no timeout for human/gate (source: workflow-execution.md, Timeout Handling)
- [x] `WF-042` Concurrency constraints: one active workflow per workspace, lock hierarchy (migration > dataset indexing > export > task schema edit), and visible lock ownership state for operators (source: workflow-execution.md, Concurrency and Locking; PRD 18.7)
- [x] `WF-043` WorkflowContext persistence: serialized to JSON after every step completion, transactional with step status update (source: workflow-execution.md, Context Persistence)
- [x] `WF-044` Crash recovery: detect interrupted steps on startup, transition to paused/interrupted, quarantine partial outputs, expose logs, and offer explicit resume/retry/cleanup actions (source: workflow-execution.md, Crash Recovery; PRD 21.6-21.7)
- [x] `WF-045` Workflow versioning: version increments on edit after execution; frozen once executed (source: ADR-003, Consequences; data-model.md, WorkflowDefinition)
- [x] `WF-046` Built-in template: Quick Agentic Label (source: ADR-003; PRD 15.0.5)
- [x] `WF-047` Built-in template: Human-in-the-Loop Review (source: ADR-003; PRD 15.0.5)
- [x] `WF-048` Built-in template: Full Quality Pipeline (source: ADR-003; PRD 15.0.5)
- [x] `WF-049` Built-in template: Benchmark Authority (source: ADR-003; PRD 15.0.5)
- [x] `WF-050` Built-in template: Agent Comparison (source: ADR-003; PRD 15.0.5)
- [x] `WF-051` Built-in template: Iterative Refinement (source: ADR-003; PRD 15.0.5)
- [x] `WF-052` Workspace lifecycle stage model: compute current stage, prerequisites, outputs, blockers, downstream impacts, completion criteria, and recommended next actions (source: PRD 15.10; PRD 16.5.1; PRD 18.4)

---

## PV: Provider System

- [x] `PV-001` ModelProviderPlugin protocol with check_health, list_models, complete, stream_complete, estimate_cost, supports_structured_output, supports_logprobs (source: plugin-interfaces.md, ModelProviderPlugin)
- [x] `PV-002` OpenAI-compatible provider adapter (source: PRD 15.3.1; PRD 24.1)
- [x] `PV-003` OpenRouter provider adapter (source: PRD 15.3.1; PRD 24.1)
- [x] `PV-004` Ollama provider adapter (source: PRD 15.3.1; PRD 24.1)
- [x] `PV-005` Anthropic direct provider adapter (source: PRD 15.3.1; PRD 24.1)
- [x] `PV-006` Custom provider adapter via plugin interface (source: PRD 15.3.1)
- [x] `PV-007` Provider auto-detection: scan Ollama at localhost:11434, check env vars for API keys on startup and on-demand, show discovered providers with health status, and offer model-profile creation from discoveries (source: PRD 15.13.1; PRD 29)
- [x] `PV-008` Model profile management: create, update, test connectivity, one-click switch per-project/per-task/per-agent-role/per-run while preserving the exact profile used for every agent run (source: PRD 15.3.1-15.3.2)
- [x] `PV-009` Runtime profile management: routing modes (offline_preferred, cloud_preferred, hybrid, local_only), fallback model, concurrency limits (source: data-model.md, RuntimeProfile)
- [x] `PV-010` Structured output enforcement: provider-native first (OpenAI response_format, Anthropic tool_use, Ollama format:json), prompt-based JSON fallback (source: ADR-004, Structured Output; PRD 15.11.5)
- [x] `PV-011` Output validation against task JSON schema with auto-retry (up to 3 times) (source: ADR-004; PRD 15.11.5)
- [x] `PV-012` Cost estimation: pre-run estimate based on token count and provider pricing (source: PRD 15.13.3)
- [x] `PV-013` Cost tracking: actual cost from API response, estimate-vs-actual delta, running totals per project/model/role, optional budget alerts (source: PRD 15.13.3)
- [x] `PV-014` Offline degradation: local features work offline, cloud failures show clear error with alternatives (source: PRD 15.13.4)
- [x] `PV-015` HuggingFace Hub authentication: token via env var, validation before push, write permission check (source: PRD 15.13.5)
- [x] `PV-016` Provider health indicators: online/offline/error status visible at all times (source: PRD 15.13.4)

---

## AG: Agent System

- [x] `AG-001` Agent roles: proposer, critic, normalizer, disagreement_flagger, deduper, rubric_judge, edge_case_miner, export_prep (source: PRD 15.4; data-model.md, AgentRole)
- [x] `AG-002` Agent run lifecycle: pending → planned → running → {completed, partially_completed, failed, cancelled}; failed runs preserve completed outputs separately and require explicit rerun actions (source: PRD 15.4.1; PRD 21.4; data-model.md, AgentRunStatus)
- [x] `AG-003` Agent run orchestration: batch processing of records with progress events (source: data-model.md, AgentEvent)
- [x] `AG-004` Agent output normalization and validation against task schema (source: PRD 15.4.2)
- [x] `AG-005` Agent output binding to review queues through explicit references (source: PRD 15.4.2)
- [x] `AG-006` Multi-model comparison runs: same task across N models simultaneously, per-record comparison (source: PRD 15.13.2; ADR-003)
- [x] `AG-007` Comparison aggregate view: agreement matrix, distribution charts, cost comparison, latency comparison, toggleable per-record vs aggregate analysis, exportable comparison data (source: PRD 15.13.2)
- [x] `AG-008` Multi-signal confidence scoring: self-reported, self-consistency (multiple runs), logprobs — configurable weights (source: ADR-004, Active Learning)
- [x] `AG-009` Prompt refinement from corrections: accumulate corrections, batch threshold (default 25), pattern extraction, generate refinements (source: ADR-004, Prompt Refinement; PRD 15.11.1)
- [x] `AG-010` Prompt refinement user review: present refinements for accept/modify/reject before applying (source: ADR-004, Prompt Refinement)
- [x] `AG-011` Correction batch lifecycle: accumulating → ready_for_analysis → analyzed → refinements_pending → {applied, dismissed} (source: data-model.md, CorrectionBatchStatus)
- [x] `AG-012` Feedback loop error handling: queue failed batches, retry on next provider connection, persist to disk, preserve raw correction library, and notify users of queued/failed refinement attempts (source: PRD 15.11.1.1)
- [x] `AG-013` Prompt management: YAML files under workbench/prompts/, immutable once used, composable layers (base + rubric + few-shot + patches), auto-versioning (source: ADR-004, Prompt Management; PRD 15.11.4)
- [x] `AG-014` Active learning queue priority: low-confidence-first, uncertainty sampling, stratified sampling, disagreement-first (source: ADR-004, Active Learning; PRD 15.11.2)
- [x] `AG-015` Agent performance analytics: per-field accuracy, trends over time, error patterns, confidence calibration curves, cost tracking, prompt version comparison (source: ADR-004, Performance Analytics; PRD 15.11.3)
- [x] `AG-016` AgentAdapterPlugin protocol for external agent integration (source: plugin-interfaces.md)

---

## DT: Data Management

- [x] `DT-001` Workspace bootstrap: open folder, prefer manifest-driven startup, fall back to heuristic project detection for reference apps/legacy projects, initialize or rebuild DB state from canonical files, scan files, infer metadata, show missing requirements (source: PRD 15.1; PRD 18.10; PRD 21.5)
- [x] `DT-002` File-backed artifact indexing: scan files, compute hashes, detect staleness (source: data-model.md, Artifact)
- [x] `DT-003` Data sources: CSV, JSONL, Parquet, JSON, YAML, Markdown (source: ADR-005, Data Sources; PRD 15.2)
- [x] `DT-004` HuggingFace dataset imports: browse, search, stream, splits, auth (source: ADR-005, Data Sources; PRD 15.12.6)
- [x] `DT-005` Import from labeling tools: Label Studio, Argilla, Prodigy, generic formats (source: ADR-005, Data Sources; PRD 15.12.6)
- [x] `DT-006` DataLoaderPlugin protocol: metadata, supported_formats, can_load, load_records, get_schema, estimate_record_count (source: plugin-interfaces.md, DataLoaderPlugin)
- [ ] `DT-007` Dataset catalog surface: name, source, records, labeled, health, last_updated, plugin/task-type indicators, direct links into explorer/review/export, grouping, search, bulk ops (source: ADR-005, Surface 1; PRD 15.12.1)
- [ ] `DT-008` Record inspector (360-view): source data panel, pre-labels with trust levels, all agent outputs across runs/models, all human review events, adjudication status/history, export inclusion status, quality signals/flags, lineage/activity trail (source: ADR-005, Surface 2; PRD 15.12.2)
- [ ] `DT-009` Dataset analytics surface: label distribution charts, quality metrics (kappa, coverage), drift detection, pre-label analysis, cross-dataset comparison views, per-dataset activity summaries (source: ADR-005, Surface 3; PRD 15.12.3)
- [x] `DT-010` Pre-label import as review events with trust levels: ground_truth, expert, external, untrusted (source: ADR-005, Pre-Labels; PRD 15.12.5)
- [x] `DT-011` Visual label mapping editor: field mapping, value transformation, partial mapping, unmapped field preservation (source: ADR-005, Label Mapping; PRD 15.12.5)
- [x] `DT-012` Reusable saved mapping configurations (source: ADR-005, Label Mapping)
- [x] `DT-013` Dataset snapshots: create named/timestamped snapshots, browse, compare (diff), restore as non-destructive restored state using full-state references (labels, agent outputs, review state, quality metrics, dataset membership) (source: ADR-005, Snapshots; PRD 15.12.4)
- [x] `DT-014` Snapshot storage: lightweight delta references, JSON metadata files under workbench/snapshots/ with snapshot metadata, record state references, agent run references, review-event summary, quality metrics, and dataset membership (source: ADR-005, Snapshots; PRD 15.12.4.1)
- [ ] `DT-015` Generic data explorer: table view, record view, raw JSON, schema view, field search, sorting, filtering, saved views, sample views, subset export, lineage inspection, copyable IDs/paths, and support for chat transcripts, preference pairs, tool-call traces, and evaluation records (source: PRD 15.2; PRD 16.8)
- [x] `DT-016` Large-file posture: raw data on disk, SQLite stores metadata/projections, DuckDB+Polars for analytical scans (source: PRD 19.3; PRD 18.11)
- [x] `DT-017` Reindexing: detect file changes on disk, selective or full reindex, stale markers (source: PRD 21.1)
- [x] `DT-018` Filesystem drift detection and conflict resolution UI (source: PRD 13.4-13.5; PRD 21.1)
- [x] `DT-019` Dataset operations engine: clustering, disagreement mining, edge-case mining, and challenge-set curation services (source: PRD 15.8; PRD 16.12)
- [x] `DT-020` Derived subset model: saved subset definitions, lineage-aware derived slices, and subset promotion across curation/export/release flows (source: PRD 15.8; PRD 16.12)

---

## RV: Review System

- [x] `RV-001` Blind first-pass review: hide agent outputs by default per blind_review_policy (source: PRD 15.5)
- [x] `RV-002` AI reveal mechanism: explicit user action to reveal agent suggestion, with tracking (ai_revealed, ai_revealed_at) (source: PRD 15.5; session-and-identity.md)
- [x] `RV-003` Review decisions: accept, accept_ai, edit_ai, reject_ai, correct, reject, skip (source: data-model.md, ReviewDecision)
- [x] `RV-004` Review event append-only guarantee: corrections create new events with supersedes_event_id (source: PRD 19.1; data-model.md)
- [x] `RV-005` Draft saving: auto-save every 10 seconds, draft_labels preserved on claim expiry (source: session-and-identity.md, Draft Preservation)
- [x] `RV-006` Calibration queues: shared calibration set, min_reviewers threshold (source: workflow-execution.md, human_calibration)
- [x] `RV-007` Overlap review: N copies of each item, prevent same reviewer claiming same record twice (source: session-and-identity.md, Overlap Review)
- [x] `RV-008` Queue assignment ordering: priority (active learning first, then workflow-assigned items, then general pool) → creation time; optional sticky assignment (source: session-and-identity.md, Queue Assignment Ordering; PRD 18.8)
- [x] `RV-009` ReviewWorkflowPlugin protocol: build_queue, validate_submission, compute_overlap_assignments (source: plugin-interfaces.md, ReviewWorkflowPlugin)
- [x] `RV-010` Rationale capture field for review submissions (source: PRD 15.5)
- [x] `RV-011` Duplicate-submission prevention (source: PRD 16.7)

---

## AJ: Adjudication

- [x] `AJ-001` Disagreement detection from overlap review and human-agent comparison (source: PRD 15.6)
- [x] `AJ-002` Adjudication queue with severity levels (low, medium, high) and type classification (source: api-specification.md, Adjudication)
- [x] `AJ-003` Adjudication resolutions: preserve_disagreement, resolve, downgrade, exclude (source: data-model.md, AdjudicationResolution)
- [x] `AJ-004` Side-by-side reviewer comparison and agent comparison panels (source: PRD 15.6)
- [x] `AJ-005` Policy excerpt display in adjudication context (source: PRD 15.6; api-specification.md)
- [x] `AJ-006` AdjudicationPlugin protocol: detect_disagreements, suggest_resolution, get_policy_context (source: plugin-interfaces.md)
- [x] `AJ-007` Adjudication creates corresponding review_event for append-only audit trail (source: data-model.md, Adjudication constraints)

---

## QA: Quality & Validation

- [x] `QA-001` Agreement metrics: Cohen's kappa, Krippendorff's alpha, Fleiss' kappa, percent agreement (source: ADR-005, Quality Metrics; PRD 15.7)
- [x] `QA-002` Human-agent agreement rates by field and label value (source: ADR-005, Quality Metrics)
- [x] `QA-003` Label distribution views per field, per dataset, per label source (source: PRD 15.7; ADR-005)
- [x] `QA-004` Agent vs human delta analysis (source: PRD 15.7)
- [x] `QA-005` Reviewer throughput metrics (source: PRD 15.7)
- [x] `QA-006` Calibration summaries (source: PRD 15.7)
- [x] `QA-007` Drift detection: label distribution comparison, chi-squared, KL divergence, visual alerts (source: ADR-005, Drift Detection)
- [x] `QA-008` Readiness dashboard with configurable project gates (source: PRD 15.7)
- [x] `QA-009` ValidationPlugin protocol: validate_export, validate_release (source: plugin-interfaces.md)
- [x] `QA-010` Validation run lifecycle: pending → running → {passed, failed, warning} (source: data-model.md, ValidationStatus)

---

## EX: Export & Release

- [x] `EX-001` Export formats: JSONL, Parquet, CSV (source: PRD 15.14; PRD 24.1)
- [x] `EX-002` HuggingFace Hub push with token validation, write permission check, and preflight verification hook for the export builder (source: PRD 15.14; PRD 15.13.5)
- [x] `EX-003` Custom export formats via ExportPackagerPlugin (source: PRD 15.14; plugin-interfaces.md)
- [x] `EX-004` Export builder: configurable inclusion of record data, labels, agent labels, review metadata, adjudication history, provenance (source: PRD 15.14)
- [x] `EX-005` Export filters: minimum agreement threshold, exclude-flagged, configurable field inclusion/exclusion (source: PRD 15.14)
- [x] `EX-006` Atomic export flow: validate → render to temp/quarantine → verify ordering/schema → compare with existing → atomic replace → refresh index/audit; preserve previous canonical files and keep interrupted partial outputs out of canonical targets (source: PRD 14.5; PRD 21.3; PRD 21.7)
- [x] `EX-007` Canonical output path contract: stable paths under workbench/exports/, workbench/reports/, etc. (source: PRD 14.6)
- [x] `EX-008` Release preflight checks: validation gates, privacy/license gates when configured, frozen split/release views as immutable validation targets (source: PRD 15.9)
- [x] `EX-009` Release bundle inspection, diff against previous bundle, and release report generation (source: PRD 15.9; PRD 16.11; PRD 18.4)
- [x] `EX-010` Release lifecycle: draft → validating → pending_approval → approved → released; also rejected/revoked (source: data-model.md, ReleaseStatus)
- [x] `EX-011` Human signoff requirement before marking release ready (source: PRD 16.11)
- [x] `EX-012` ExportPackagerPlugin protocol: validate_config, export_records, get_file_extension (source: plugin-interfaces.md)
- [x] `EX-013` Export determinism: stable ordering, reproducible across machines (source: PRD 14.1)
- [x] `EX-014` Canonical write conflict rules: block blind overwrite, show diff, allow refresh/rebase (source: PRD 14.3)
- [x] `EX-015` Release and export report generation under canonical workbench report paths with readiness and validation summaries (source: PRD 15.9; PRD 18.4)
- [x] `EX-016` Frozen split and release views for inspection before approval, export, or revocation (source: PRD 15.9)

---

## PL: Plugin SDK

- [x] `PL-001` Plugin discovery via Python entry points: `molabel.plugins` group, register function (source: plugin-interfaces.md, Plugin Discovery)
- [x] `PL-002` PluginRegistry: register_data_loader, register_task_type, register_model_provider, register_record_renderer, register_review_workflow, register_adjudication, register_agent_adapter, register_validation, register_export_packager, register_reference_app, register_record_normalizer, register_workflow_stage_provider, register_dashboard_panel, register_project_template (source: plugin-interfaces.md, Plugin Registry; PRD 18.5)
- [x] `PL-003` PluginMetadata: plugin_id, version, compatible_core, description, author, url, tags, semantic-compatibility metadata, supported file types/record kinds, and capability declarations (source: plugin-interfaces.md, Common Types; PRD 17.2; PRD 17.8)
- [x] `PL-004` Plugin error isolation: loading errors caught per-plugin, surfaced in UI without preventing others (source: plugin-interfaces.md)
- [x] `PL-005` DataLoaderPlugin protocol implementation (source: plugin-interfaces.md, DataLoaderPlugin)
- [x] `PL-006` TaskTypePlugin protocol: task_type_id, get_label_field_definitions, get_default_review_form_schema, validate_labels, get_default_agent_prompt_template, get_export_columns (source: plugin-interfaces.md, TaskTypePlugin)
- [x] `PL-007` RecordRendererPlugin protocol: get_list_columns, get_detail_layout, get_review_layout, render_preview (source: plugin-interfaces.md, RecordRendererPlugin)
- [x] `PL-008` ReviewWorkflowPlugin protocol (source: plugin-interfaces.md, ReviewWorkflowPlugin)
- [x] `PL-009` AdjudicationPlugin protocol (source: plugin-interfaces.md)
- [x] `PL-010` AgentAdapterPlugin protocol (source: plugin-interfaces.md)
- [x] `PL-011` ValidationPlugin protocol (source: plugin-interfaces.md)
- [x] `PL-012` ExportPackagerPlugin protocol (source: plugin-interfaces.md)
- [x] `PL-013` ReferenceAppPlugin protocol: workspace templates, custom screens, validation gates, project dashboards, and bootstrap rules (source: plugin-interfaces.md; PRD 17.7)
- [x] `PL-014` Plugin UI model tier 1: JSON schema declaration for forms, columns, layouts rendered generically (source: PRD 17.5.1; ADR-001)
- [x] `PL-015` Plugin UI model tier 2: custom React component bundles loaded via dynamic import with error boundaries, typed props contracts, self-contained ES module bundles, and atomic plugin-version updates (source: PRD 17.5.2; ADR-001)
- [x] `PL-016` Plugin lifecycle hooks: discovery, install, activation, compatibility check, migration, disable, uninstall (source: PRD 17.3)
- [x] `PL-017` Plugin compatibility enforcement: incompatible versions fail clearly, workspace remains readable, block writes that depend on incompatible plugin (source: PRD 17.8; PRD 21.2)
- [x] `PL-018` Plugin context: core_version, workspace_root, plugin_data_dir, settings (source: plugin-interfaces.md, PluginContext)
- [x] `PL-019` Plugin manifest and capability contract: entrypoint, manifest format, supported schemas/tasks, list/detail/review/adjudication renderers, export formats, validation hooks, and job/command surfaces (source: PRD 17.2; PRD 17.5; PRD 17.8)
- [x] `PL-020` Additional extension APIs and template support: record normalizers, workflow stage providers, home-screen/dashboard panels, and project template plugins with preconfigured task schemas, queues, agent roles, validation gates, export mappings, and recommended provider/runtime profiles (source: PRD 17.7.1; PRD 18.5)

---

## API: REST API Endpoints

- [x] `API-001` Base URL `/api/v1/`, cursor-based pagination, error envelope, filtering, sorting conventions (source: api-specification.md, Conventions)
- [x] `API-002` Common response types: PaginatedResponse, ErrorDetail, ErrorResponse, TimestampMixin (source: api-specification.md)
- [x] `API-003` GET /workspaces — list all workspaces (source: api-specification.md)
- [x] `API-004` GET /workspaces/{id} — workspace detail with health diagnostics (source: api-specification.md)
- [x] `API-005` POST /workspaces — create/bootstrap workspace (source: api-specification.md)
- [x] `API-006` POST /workspaces/{id}/reindex — trigger background reindex (source: api-specification.md)
- [x] `API-007` GET /datasets — list datasets with pagination and filters (source: api-specification.md)
- [x] `API-008` GET /datasets/{id} — dataset detail with statistics (source: api-specification.md)
- [x] `API-009` POST /datasets — register/import new dataset (source: api-specification.md)
- [x] `API-010` POST /datasets/{id}/import — import with label mapping from external sources (source: api-specification.md)
- [x] `API-011` GET /datasets/{id}/records — paginated record list with filtering (source: api-specification.md)
- [x] `API-012` GET /datasets/{id}/records/{id} — full record detail (360-view) (source: api-specification.md)
- [x] `API-013` GET /datasets/{id}/analytics — dataset-level analytics (source: api-specification.md)
- [x] `API-014` POST /datasets/{id}/snapshots — create snapshot (source: api-specification.md)
- [x] `API-015` GET /datasets/{id}/snapshots — list snapshots (source: api-specification.md)
- [x] `API-016` GET /datasets/{id}/snapshots/{id}/diff — compare snapshots (source: api-specification.md)
- [x] `API-017` POST /label-mappings/preview — preview label mapping (source: api-specification.md)
- [x] `API-018` POST /label-mappings — save reusable mapping (source: api-specification.md)
- [x] `API-019` GET /workflows — list workflow definitions (source: api-specification.md)
- [x] `API-020` GET /workflows/{id} — full workflow detail with YAML and steps (source: api-specification.md)
- [x] `API-021` POST /workflows — create workflow from template or YAML (source: api-specification.md)
- [x] `API-022` PUT /workflows/{id} — update workflow definition (source: api-specification.md)
- [x] `API-023` POST /workflows/{id}/execute — start workflow execution (source: api-specification.md)
- [x] `API-024` GET /workflows/{id}/executions — list executions (source: api-specification.md)
- [x] `API-025` GET /workflows/{id}/executions/{id} — execution detail with per-step state (source: api-specification.md)
- [x] `API-026` POST /workflows/{id}/executions/{id}/steps/{id}/advance — advance paused step (source: api-specification.md)
- [x] `API-027` POST /workflows/{id}/executions/{id}/pause — pause running execution (source: api-specification.md)
- [x] `API-028` POST /workflows/{id}/executions/{id}/cancel — cancel execution (source: api-specification.md)
- [x] `API-029` GET /task-schemas — list task schemas (source: api-specification.md)
- [x] `API-030` GET /task-schemas/{id} — task schema detail (source: api-specification.md)
- [x] `API-031` POST /task-schemas — create task schema (source: api-specification.md)
- [x] `API-032` PUT /task-schemas/{id} — update (creates new version if frozen) (source: api-specification.md)
- [x] `API-033` GET /providers — list discovered providers with health (source: api-specification.md)
- [x] `API-034` POST /providers/scan — trigger auto-detection (source: api-specification.md)
- [x] `API-035` GET /model-profiles — list model profiles (source: api-specification.md)
- [x] `API-036` POST /model-profiles — create model profile (source: api-specification.md)
- [x] `API-037` PUT /model-profiles/{id} — update model profile (source: api-specification.md)
- [x] `API-038` POST /model-profiles/{id}/test — test connectivity (source: api-specification.md)
- [x] `API-039` GET /runtime-profiles — list runtime profiles (source: api-specification.md)
- [x] `API-040` POST /runtime-profiles — create runtime profile (source: api-specification.md)
- [x] `API-041` GET /agent-runs — list with filtering (source: api-specification.md)
- [x] `API-042` GET /agent-runs/{id} — agent run detail (source: api-specification.md)
- [x] `API-043` POST /agent-runs — start agent run (source: api-specification.md)
- [x] `API-044` POST /agent-runs/compare — multi-model comparison run (source: api-specification.md)
- [x] `API-045` POST /agent-runs/{id}/cancel — cancel run (source: api-specification.md)
- [x] `API-046` GET /agent-runs/{id}/outputs — list outputs for run (source: api-specification.md)
- [x] `API-047` GET /agent-runs/{id}/outputs/{record_id} — output for specific record (source: api-specification.md)
- [x] `API-048` GET /agent-runs/comparison/{id} — comparison results with aggregate metrics (source: api-specification.md)
- [x] `API-049` GET /agent-runs/analytics — performance analytics dashboard data (source: api-specification.md)
- [x] `API-050` GET /prompts — list prompt templates (source: api-specification.md)
- [x] `API-051` GET /prompts/{id} — prompt detail with version history (source: api-specification.md)
- [x] `API-052` POST /prompts — create prompt template (source: api-specification.md)
- [x] `API-053` PUT /prompts/{id} — create new version (source: api-specification.md)
- [x] `API-054` GET /prompts/{id}/diff — diff between versions (source: api-specification.md)
- [x] `API-055` GET /corrections — list correction batches (source: api-specification.md)
- [x] `API-056` POST /corrections/analyze — trigger refinement analysis (source: api-specification.md)
- [x] `API-057` GET /corrections/{id}/refinement — get suggested refinement (source: api-specification.md)
- [x] `API-058` GET /review/queue — get next item (atomic claim) (source: api-specification.md)
- [x] `API-059` GET /review/queue/stats — queue statistics (source: api-specification.md)
- [x] `API-060` POST /review/events — submit review (source: api-specification.md)
- [x] `API-061` POST /review/events/draft — save draft (source: api-specification.md)
- [x] `API-062` POST /review/events/{id}/reveal-ai — record AI reveal (source: api-specification.md)
- [x] `API-063` GET /review/events — list review events (source: api-specification.md)
- [x] `API-064` GET /adjudication/queue — disagreement queue (source: api-specification.md)
- [x] `API-065` GET /adjudication/{id} — adjudication detail (source: api-specification.md)
- [x] `API-066` POST /adjudication/{id}/resolve — submit resolution (source: api-specification.md)
- [x] `API-067` GET /quality/dashboard — quality metrics dashboard (source: api-specification.md)
- [x] `API-068` POST /exports — create export bundle (source: PRD 15.9; api-specification.md)
- [x] `API-069` GET /exports/{id} — export bundle detail (source: PRD 15.9)
- [x] `API-070` POST /releases — create release (source: PRD 15.9)
- [x] `API-071` POST /releases/{id}/approve — approve release (source: PRD 15.9)
- [x] `API-072` GET /audit — filterable audit history (source: PRD 16.5.1)
- [x] `API-073` POST /session — create or switch session (source: api-specification.md, Authentication)
- [x] `API-074` GET /reviewers — list profiles (source: api-specification.md)
- [x] `API-075` POST /reviewers — create reviewer profile (source: api-specification.md)
- [x] `API-076` GET /plugins — list installed plugins (source: PRD 16.13; api-specification.md)
- [x] `API-077` POST /assistant/query — AI assistant query with streaming response (source: ai-assistant.md; api-specification.md)
- [x] `API-078` GET /assistant/context — current assistant context summary (source: ai-assistant.md; api-specification.md)
- [x] `API-079` GET /quality/agreement — agreement-specific metrics payload (source: api-specification.md)
- [x] `API-080` GET /quality/drift — drift-specific metrics payload (source: api-specification.md)
- [x] `API-081` GET /exports — list export bundles (source: api-specification.md)
- [x] `API-082` POST /exports/preview — preview export composition before bundle creation (source: api-specification.md)
- [x] `API-083` POST /exports/{id}/validate — run validation on an export bundle (source: api-specification.md)
- [x] `API-084` POST /exports/{id}/download — package or download an export bundle artifact (source: api-specification.md)
- [x] `API-085` POST /exports/{id}/push-hf — push an export bundle to HuggingFace Hub (source: api-specification.md)
- [x] `API-086` GET /releases — list releases (source: api-specification.md)
- [x] `API-087` GET /releases/{id} — release detail (source: api-specification.md)
- [x] `API-088` GET /plugins/{id} — plugin detail and compatibility state (source: api-specification.md)
- [x] `API-089` POST /plugins/{id}/enable — enable a plugin for use (source: api-specification.md)
- [x] `API-090` POST /plugins/{id}/disable — disable a plugin with safety checks (source: api-specification.md)
- [x] `API-091` GET /audit/{id} — audit event detail with replayable context (source: api-specification.md)
- [x] `API-092` GET /session — get current session info from cookie state (source: api-specification.md)
- [x] `API-093` GET /costs — cost summary across workspace, model, role, and time (source: api-specification.md)
- [x] `API-094` GET /costs/estimate — estimate cost for a proposed agent run (source: api-specification.md)

---

## SSE: Real-Time Events

- [x] `SSE-001` Queue events stream: `/api/v1/events/queue/{queue_id}` — item claimed, submitted, skipped, expired (source: session-and-identity.md, SSE Event Streams)
- [x] `SSE-002` Workflow events stream: `/api/v1/events/workflow/{execution_id}` — step completions, state changes (source: session-and-identity.md)
- [x] `SSE-003` Provider events stream: `/api/v1/events/providers` — status changes, availability updates (source: session-and-identity.md)
- [x] `SSE-004` Agent run progress stream: `/api/v1/events/agent-runs/{agent_run_id}` (source: api-specification.md; PRD 18.9)
- [x] `SSE-005` SSE authentication via session cookie (source: session-and-identity.md)

---

## SE: Session & Multi-Reviewer

- [x] `SE-001` Reviewer profile creation: display_name, auto-assigned avatar_color, UUID id (source: session-and-identity.md, Reviewer Profiles)
- [x] `SE-002` Session cookie: molabel_session, signed token with reviewer_id, HttpOnly, SameSite=Strict (source: session-and-identity.md, Session Cookie)
- [x] `SE-003` First visit flow: "Who are you?" screen with profile list and create-new (source: session-and-identity.md, First Visit Flow)
- [x] `SE-004` Session validation on every API request: verify signature, extract id, update last_active_at (debounced) (source: session-and-identity.md, Session Validation)
- [x] `SE-005` Profile switching: replace cookie, auto-save drafts, preserve claims (source: session-and-identity.md, Profile Switching)
- [x] `SE-006` Atomic queue claim: UPDATE...WHERE...(SELECT...LIMIT 1) pattern preventing double-assignment; one-item-at-a-time claims only, no bulk claim hoarding (source: session-and-identity.md, Claim Mechanics; PRD 18.8)
- [x] `SE-007` Claim timeout: default 30 min, configurable; background task checks every 60s (source: session-and-identity.md, Claim Timeout)
- [x] `SE-008` Claim expiry notification via X-MoLabel-Notification header and frontend toast, including reclaimed notifications after reconnect when claims expired offline (source: session-and-identity.md, Claim Expiry Notification; PRD 18.8)
- [x] `SE-009` Same-profile multi-session handling: independent claims, draft last-write-wins, audit warning (source: session-and-identity.md, Same-Profile Multi-Session)
- [x] `SE-010` Mission control reviewer visibility: active/idle/offline status based on last_active_at plus current queue positions for active reviewers (source: session-and-identity.md, Session Visibility; PRD 18.8)
- [x] `SE-011` Application secret auto-generation on first launch, stored in workbench/.molabel/app_secret (source: session-and-identity.md)
- [x] `SE-012` Network binding: configurable MOLABEL_HOST (0.0.0.0 default, 127.0.0.1 for single-user) (source: session-and-identity.md, Security)

---

## AI: AI Assistant

- [x] `AI-001` AssistantContextBuilder: assemble focused context from SQLite state and cached metrics (source: ai-assistant.md, Context Assembly Pipeline)
- [x] `AI-002` Context priority budget: system prompt (~500), screen/workflow (~200), queue stats (~200), blockers (~300), recent runs (~500), validation gates (~200), record context (~500), project summary (~200) — total ~2600 tokens (source: ai-assistant.md)
- [x] `AI-003` Five assistant modes: Guide, Explain, Operator, Agent Monitor, Troubleshoot — auto-detected from query + screen (source: ai-assistant.md, Mode Detection)
- [x] `AI-004` System prompt with mode instructions and behavioral rules for step explanations, blocker explanations, queue/run "why is this here?" answers, next-action recommendations, and action preparation without silent execution (source: ai-assistant.md, System Prompt Structure; PRD 15.10; PRD 16.13)
- [x] `AI-005` Conversation history: last 5 exchanges in browser memory, reset on screen navigation (source: ai-assistant.md, Conversation History)
- [x] `AI-006` Provider integration: uses user's configured model profiles, shows unavailable state clearly (source: ai-assistant.md, Provider Integration)
- [x] `AI-007` Error handling: timeout, rate limit, offline, context failure, invalid response, no model configured (source: ai-assistant.md, Error Handling)
- [x] `AI-008` Cost control: 4000-token input budget, estimated cost per query, usage tracked alongside agent costs (source: ai-assistant.md, Cost Control)
- [x] `AI-009` Streaming response via SSE within POST response body (source: ai-assistant.md, API Integration)
- [x] `AI-010` Can be disabled entirely in project settings (source: ai-assistant.md)

---

## FE: Frontend Screens & Components

- [ ] `FE-001` App shell: left navigation rail, central workspace canvas, right-side contextual inspector, command bar (Cmd+K) (source: PRD 16.3, 16.5)
- [ ] `FE-002` Persistent workflow rail or stage indicator visible from any screen (source: PRD 16.5)
- [ ] `FE-003` Background-job indicators visible from any screen (source: PRD 16.5)
- [ ] `FE-004` Home screen: workspace status, active workflow stage, key counts, blockers, pending queues, recent runs, primary action (source: PRD 16.5.1; ux-and-ai-strategy.md 5.1)
- [ ] `FE-005` Workflow screen: visual workflow builder (React Flow), create/edit/execute workflows, full lifecycle view, stage prerequisites/outputs/blockers, explicit completion criteria, downstream impact visibility, one-click next actions (source: PRD 15.10; PRD 16.5.1; ux-and-ai-strategy.md 5.2)
- [ ] `FE-006` Workflow builder: drag-and-drop canvas, step nodes, edge connections, branching/loops visualization, execution state overlay (source: ADR-001, Context)
- [ ] `FE-007` Dataset catalog screen: dataset cards/rows with health, counts, plugin/task-type indicators, and links into explorer/review/export (source: PRD 15.12.1; PRD 16.5.1; ux-and-ai-strategy.md 5.3)
- [ ] `FE-008` Dataset explorer screen: large-table browsing (TanStack Table), virtual scrolling, filter chips, schema panel, copyable IDs/paths, fast record detail transitions, plugin-rendered previews (source: PRD 16.8)
- [ ] `FE-009` Record inspector component (360-view): source data, all labels, export inclusion status, quality, and lineage/activity panels (source: ADR-005; PRD 15.12.2)
- [ ] `FE-010` Task schema editor screen: versioning, label/rubric editing, overlap/adjudication config, model selection, export target preview, validation before save (source: PRD 16.6)
- [ ] `FE-011` Model and runtime configuration screen: profile CRUD, provider health indicators, test connectivity (source: PRD 16.6)
- [ ] `FE-012` Agent run builder screen: role selection, model profile, runtime override, compare mode, prompt version, subset targeting, dry-run preview, cost estimate, run history links (source: PRD 16.9)
- [ ] `FE-013` Mission control screen: live run monitoring, event timeline, logs, artifact delta preview, queue impact preview, blocker summary, reviewer sessions with queue positions, and active lock visibility (source: PRD 16.9; PRD 18.7-18.8; ux-and-ai-strategy.md 12.1)
- [ ] `FE-014` Review queue screen: fully keyboard-driven (1-5, Tab, Enter, n/p, Esc, Space, a/e/x, r, g+num, Cmd-K, ?) (source: PRD 16.7)
- [ ] `FE-015` Review screen features: sticky scoring controls, side panels, optional AI drawer, blind-review indicator, queue position, estimated time, save draft, submit final (source: PRD 16.7)
- [ ] `FE-016` Adjudication screen: multiple reviewer panes, agent output pane, policy pane, record history, action toolbar, resolution reasoning (source: PRD 16.10)
- [ ] `FE-017` Quality dashboard screen: agreement metrics, readiness gates, quality trends (source: PRD 16.4)
- [ ] `FE-018` Curation screen: saved subsets, inclusion/exclusion rules, disagreement/edge-case facets, clustering outputs, bulk operations, provenance preview (source: PRD 16.12)
- [ ] `FE-019` Export packaging screen: bundle contents preview, blockers, validation history, diff, HuggingFace access verification, frozen release-view preview, human signoff (source: PRD 15.13.5; PRD 16.11)
- [ ] `FE-020` Release validation screen: frozen split/release view inspection, validation gates, and release report access (source: PRD 15.9; PRD 16.4; PRD 16.11)
- [ ] `FE-021` Plugin management screen: inventory, compatibility, enabled/disabled, required-by-project, manifest inspection, upgrade guidance (source: PRD 16.13)
- [ ] `FE-022` Audit history screen: filterable events, actor/timestamp, affected object links, file write and job events, replayable context for failed writes or interrupted jobs (source: PRD 16.5.1)
- [ ] `FE-023` Settings screen: project settings, assistant model selection, claim timeout, network binding (source: ux-and-ai-strategy.md 5)
- [ ] `FE-024` AI assistant panel: right-side inspector/support panel, collapsed by default, Cmd+/ shortcut, suggested questions, markdown rendering, "show context" toggle, cost indicator, queue/run explanations, and action preparation previews without silent execution (source: ai-assistant.md, UI Integration; PRD 16.13)
- [ ] `FE-025` "Switch profile" button in app header with display name and avatar color (source: session-and-identity.md)
- [ ] `FE-026` Agent performance charts: time-series accuracy, confidence calibration curves, error patterns, cost-per-label (Recharts) (source: ADR-001, ADR-004; PRD 15.11.3)
- [ ] `FE-027` Side-by-side model comparison view with diff highlighting, agreement indicators, per-record vs aggregate toggle, and comparison-data export action (source: ADR-001; PRD 15.13.2)
- [ ] `FE-028` Prompt editor with diff view between versions (source: PRD 15.11.4)
- [ ] `FE-029` Label mapping editor UI: visual field mapping, value transformation table (source: PRD 15.12.5)
- [ ] `FE-030` Zustand stores for workflow editor state, UI preferences, active run tracking (source: ADR-001; AGENTS.md)
- [ ] `FE-031` TanStack Query + auto-generated OpenAPI client for all API calls (source: ADR-001; AGENTS.md)
- [x] `FE-032` Tailwind CSS + shadcn/ui component library (source: ADR-001; AGENTS.md)
- [ ] `FE-033` Stage-level explainability: "Explain this step" action per workflow stage plus blocker explanation and next recommended action support (source: PRD 15.10; ux-and-ai-strategy.md 8.2)
- [ ] `FE-034` Export-level explainability: which records included/excluded, why, validation results (source: ux-and-ai-strategy.md 8.3)
- [ ] `FE-035` Queue ergonomics: bulk actions, quick filters, saved views, resume-where-left-off, skip-with-reason, assign-to-me, jump-to-most-urgent (source: ux-and-ai-strategy.md 7.3)
- [ ] `FE-036` "Delegate This Step" feature for safe delegation steps (normalization, deduplication, etc.) (source: ux-and-ai-strategy.md 12.3)

---

## TA: Tauri Desktop Shell

- [ ] `TA-001` Tauri v2 project setup at src-tauri/ with window management config (source: ADR-002)
- [ ] `TA-002` Python/FastAPI sidecar process management: spawn, health monitor, restart on crash, graceful shutdown (source: ADR-002, Architecture)
- [ ] `TA-003` System tray: persistent icon showing workflow status, quick access to projects, background running when window closed (source: ADR-002)
- [ ] `TA-004` Native file dialogs for dataset import and export (source: ADR-002)
- [ ] `TA-005` Auto-updater: check on startup, differential updates, user consent (source: ADR-002)
- [ ] `TA-006` Dev mode parity: all features work in browser-tab mode, Tauri features degrade gracefully (source: ADR-002, Consequences)
- [ ] `TA-007` Distribution: .dmg (macOS), .msi/.exe (Windows), .AppImage/.deb (Linux) (source: ADR-002)
- [ ] `TA-008` Python sidecar packaging: PyInstaller/PyApp binary for end users (source: ADR-002)
- [ ] `TA-009` System notifications for completed jobs (source: PRD 24.1)
- [ ] `TA-010` Localhost HTTP communication between webview and sidecar on 127.0.0.1:port (source: ADR-002)
- [ ] `TA-011` Native OS integration: file associations and deep linking for local projects/artifacts (source: PRD 24.1)

---

## DX: Developer Experience & Documentation

- [ ] `DX-001` Contributor command docs: one documented path for bootstrap, GUI dev mode, tests, bootstrap verification, plugin compatibility verification, UI smoke verification, export determinism verification, plus fixture workspace usage for local UI/export testing (source: PRD 22.5; PRD 25.4)
- [ ] `DX-002` Plugin authoring DX: plugin scaffold path or command, sample plugin/template path, short "build a plugin" guide, and contributor quickstart validated against the 30-minute local verify target (source: PRD 17.8; PRD 25.4)

---

## TS: Testing Infrastructure

- [ ] `TS-001` Python unit tests (pytest) for core domain logic, workflow engine, queue management, review state machine, prompt versioning, label mapping, schema validation (source: PRD 22.2)
- [ ] `TS-002` Python integration tests for SQLite operations, file I/O, plugin loading, agent run orchestration (source: PRD 22.2)
- [ ] `TS-003` FastAPI endpoint tests using httpx.AsyncClient (source: PRD 22.2)
- [ ] `TS-004` Frontend component tests: vitest + React Testing Library (source: PRD 22.2)
- [ ] `TS-005` Frontend integration tests with MSW (Mock Service Worker) for API mocking (source: PRD 22.2)
- [ ] `TS-006` Playwright E2E tests for critical user flows (source: PRD 22.2)
- [ ] `TS-007` ~15 parameterized workflow fixture YAMLs: linear, branching, looping (all 4 termination types), nested loops, parallel, conditional, error cases, all 6 templates (source: PRD 22.2; ADR-003)
- [ ] `TS-008` Provider adapter tests with VCR-style recorded response cassettes + optional --live-providers flag (source: PRD 22.2)
- [ ] `TS-009` Fixture projects: plain text classification, conversation-window review, trajectory records, plugin-mismatch/drift-recovery (source: PRD 22.3)
- [ ] `TS-010` Export determinism snapshot tests (source: PRD 22.2)
- [ ] `TS-011` Plugin SDK verification: install, register, incompatible version fail, fixture workspace round-trip (source: PRD 22.6)
- [ ] `TS-012` Migration tests: fixture databases at known schema versions, upgrade to head, verify data integrity (source: database-migrations.md, Testing)
- [ ] `TS-013` Tauri desktop smoke test checklist: file dialogs, system tray, auto-update, sleep/wake, file associations, deep linking (source: PRD 22.5.2; PRD 24.1)
- [ ] `TS-014` Performance targets: home <2s, explorer <1s, record detail <500ms, review nav <300ms, workflow builder responsive for 50 steps, agent run start <2s, export 10k records/min JSONL (source: PRD 23.1)

---

## DP: DePolarize Reference App

- [ ] `DP-001` molabel-depolarize package with separate molabel_depolarize namespace (source: AGENTS.md; PRD 26)
- [ ] `DP-002` DePolarize ReferenceAppPlugin: register function, workspace templates, custom screens, validation gates (source: PRD 17.7; plugin-interfaces.md)
- [ ] `DP-003` Asset A turn-level text labeling task type (ordinal_text_review) (source: PRD 26)
- [ ] `DP-004` Asset B context-window review task type (source: PRD 26)
- [ ] `DP-005` Asset C trajectory/decision-point review task type (source: PRD 26)
- [ ] `DP-006` DePolarize-specific schemas: social_distance, aversion, incivility ordinal scales (source: PRD 15.3.4)
- [ ] `DP-007` DePolarize project bootstrap rules and path inference (source: PRD 26)
- [ ] `DP-008` DePolarize export formats: asset_a_review_export serializer (source: PRD 26)
- [ ] `DP-009` DePolarize readiness gates: release_readiness validation plugin (source: PRD 26)
- [ ] `DP-010` DePolarize project dashboard (source: PRD 26)
- [ ] `DP-011` YAML manifest-backed governance (source: PRD 26)

---

## BP: Built-in Plugins (molabel-plugins)

- [ ] `BP-001` Text labeling task type plugin (source: PRD 24.1; PRD 17.6)
- [ ] `BP-002` Chat/conversation review task type plugin (source: PRD 24.1; PRD 17.6)
- [ ] `BP-003` Pairwise ranking task type plugin (source: PRD 24.1; PRD 17.6)
- [ ] `BP-004` Extraction task type plugin (source: PRD 24.1; PRD 17.6)
- [ ] `BP-005` PDF/document review task type plugin (source: PRD 24.1; PRD 17.6)
- [x] `BP-006` Built-in data loaders: CSV, JSONL, Parquet, JSON, YAML, Markdown, HuggingFace (source: ADR-005; PRD 15.12.6)
- [x] `BP-007` Built-in export packagers: JSONL, Parquet, CSV, HuggingFace Hub push (source: PRD 15.14)
- [ ] `BP-008` Built-in model provider plugins: OpenAI-compatible, OpenRouter, Ollama, Anthropic (source: PRD 15.3.1)
- [ ] `BP-009` At least one non-DePolarize example plugin proving core reusability (source: PRD 29)

---

**Total items: 424 checklist items covering the traced implementation scope.**

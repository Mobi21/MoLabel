# MoLabel Implementation Plan

Note: As of 2026-03-27, the canonical product direction is agent-first and CLI-primary. This document remains useful as a delivery record, but new work should be reprioritized behind:

1. CLI completeness and additive `/api/v1/cli/*` operator coverage.
2. Bundled agent skills and machine-readable command contracts.
3. Benchmark-grade sample projects and CLI-driven evaluation.
4. GUI refinement as manual control room, review surface, and observability layer.

Fully sequenced plan organized into phases with parallel tracks. Every checklist item appears in exactly one step.

---

## Phase 1: Foundation

Everything else depends on this. Mostly sequential.

### Step 1.1: Monorepo Scaffolding [M]
- Completes: `SC-001`, `SC-002`, `SC-003`, `SC-010`
- Produces: uv workspace with 4 Python packages, pyproject.toml files, namespace package structure, ruff config
- Depends on: nothing
- Status: completed

### Step 1.2: Frontend & Tauri Project Setup [M]
- Completes: `SC-004`, `SC-005`, `FE-032`
- Produces: `frontend/` with React 19, TypeScript, Vite, Tailwind CSS, shadcn/ui, package.json; `src-tauri/` with initial Cargo config
- Depends on: nothing (parallel with 1.1)
- Status: completed

### Step 1.3: Core Domain Types & Enums [L]
- Completes: `DM-003`, `PL-003`, `PL-018`
- Produces: `molabel.core.types` module with all enum types, PluginMetadata, PluginContext, common dataclasses
- Depends on: Step 1.1
- Status: completed

### Step 1.4: SQLite Data Model — Core Tables [XL]
- Completes: `DM-001`, `DM-002`, `DM-004`, `DM-005`, `DM-006`, `DM-007`, `DM-008`, `DM-009`, `DM-010`, `DM-030`, `DM-031`, `DM-032`
- Produces: SQLModel classes for workspace, artifact, dataset, record, task_schema, model_profile, runtime_profile, reviewer_profile, cost_record; entity relationships and indexes
- Depends on: Step 1.3
- Status: completed

### Step 1.5: SQLite Data Model — Review & Agent Tables [L]
- Completes: `DM-011`, `DM-012`, `DM-013`, `DM-014`, `DM-015`, `DM-016`
- Produces: SQLModel classes for review_task, review_event, agent_run, agent_event, agent_output, adjudication
- Depends on: Step 1.4
- Status: completed

### Step 1.6: SQLite Data Model — Workflow, Prompt, Export Tables [L]
- Completes: `DM-017`, `DM-018`, `DM-019`, `DM-020`, `DM-021`, `DM-022`, `DM-023`, `DM-024`, `DM-025`, `DM-026`, `DM-027`, `DM-028`, `DM-029`
- Produces: SQLModel classes for workflow_definition, workflow_execution, workflow_step_execution, prompt_template, correction_batch, dataset_snapshot, label_mapping, validation_run, export_bundle, release, plugin_installation, audit_entry, saved_view
- Depends on: Step 1.5
- Status: completed

### Step 1.7: Database Migration Infrastructure [M]
- Completes: `DB-001`, `DB-002`, `DB-003`, `DB-004`, `DB-005`, `DB-006`
- Produces: Alembic setup, initial migration, auto-migrate on startup, backup strategy
- Depends on: Step 1.6
- Status: completed

### Step 1.8: Workspace Manifest Contract [M]
- Completes: `DM-033`, `DM-034`
- Produces: workbench.project.yaml parser/writer, conflict detection logic, workspace bootstrap from manifest
- Depends on: Step 1.4
- Status: completed

### Step 1.9: Plugin Discovery & Registry [M]
- Completes: `PL-001`, `PL-002`, `PL-004`, `PL-016`
- Produces: PluginRegistry concrete implementation, entry point discovery, error-isolated loading, lifecycle hooks
- Depends on: Step 1.3
- Status: completed

### Step 1.10: FastAPI App Skeleton & API Conventions [M]
- Completes: `API-001`, `API-002`, `SC-006`
- Produces: FastAPI app with /api/v1/ base, pagination, error envelope, filtering/sorting; module boundary enforcement verified
- Depends on: Step 1.4
- Status: completed

### Step 1.11: OpenAPI Codegen Pipeline [M]
- Completes: `SC-007`, `SC-008`, `SC-009`
- Produces: OpenAPI spec → TypeScript client codegen, dev mode with proxy, molabel-dev command
- Depends on: Step 1.10, Step 1.2
- Status: completed

### Step 1.12: CI Pipeline [M]
- Completes: `SC-011`, `SC-012`
- Produces: GitHub Actions CI with pytest, vitest, ruff, tsc, OpenAPI sync, Playwright placeholder
- Depends on: Step 1.11
- Status: completed

### Gate 1: Foundation Verification
- [x] All items: SC-001 through SC-012, DM-001 through DM-034, DB-001 through DB-006, PL-001 through PL-004, PL-016, PL-018, API-001, API-002, FE-032
- [x] Verification: `uv sync` succeeds; all imports verified; Alembic migrations apply cleanly to v001; ruff check/format passes
- Note: `npm install` and `npm run build` not run (frontend files created but deps not installed); pytest has 0 tests collected (test files are Phase 2+)

---

## Phase 2: Core Backend Systems

Parallel tracks after Phase 1. Three independent tracks.

### Track A: Plugin Interfaces & Built-in Loaders

#### Step 2.A.1: Plugin Protocol Definitions [L]
- Completes: `PL-005`, `PL-006`, `PL-007`, `PL-008`, `PL-009`, `PL-010`, `PL-011`, `PL-012`, `PL-013`, `PL-017`, `PL-019`, `PL-020`, `DT-006`, `EX-012`, `RV-009`, `AJ-006`, `AG-016`, `QA-009`
- Produces: Core plugin protocol classes, manifest/capability contract, and extension APIs for normalizers, stage providers, dashboard panels, project templates, and plugin-owned workflow/export/review hooks
- Depends on: Gate 1
- Status: completed

#### Step 2.A.2: Built-in Data Loaders [L]
- Completes: `BP-006`
- Produces: CSV, JSONL, Parquet, JSON, YAML, Markdown data loader plugins; HuggingFace loader built on the shared DataLoaderPlugin contract
- Depends on: Step 2.A.1
- Status: completed

#### Step 2.A.3: Built-in Export Packagers [M]
- Completes: `BP-007`
- Produces: JSONL, Parquet, CSV export packager plugins; HuggingFace Hub push packager built on the shared ExportPackagerPlugin contract
- Depends on: Step 2.A.1, Step 2.B.5
- Status: completed

#### Step 2.A.4: Plugin UI Model [M]
- Completes: `PL-014`, `PL-015`
- Produces: JSON schema UI renderer for plugin forms/columns; dynamic React component loader with typed props and error boundaries
- Depends on: Step 2.A.1
- Status: completed

### Track B: Provider System

#### Step 2.B.1: Provider Adapter Framework [M]
- Completes: `PV-001`
- Produces: ModelProviderPlugin protocol concrete base; health check, completion, streaming, cost estimation interfaces
- Depends on: Gate 1
- Status: completed

#### Step 2.B.2: OpenAI-Compatible & OpenRouter Adapters [L]
- Completes: `PV-002`, `PV-003`
- Produces: OpenAI-compatible and OpenRouter provider adapters with structured output, logprobs support
- Depends on: Step 2.B.1
- Status: completed

#### Step 2.B.3: Ollama & Anthropic Adapters [M]
- Completes: `PV-004`, `PV-005`, `PV-006`
- Produces: Ollama and Anthropic provider adapters; custom adapter support
- Depends on: Step 2.B.1
- Status: completed

#### Step 2.B.4: Provider Auto-Detection [M]
- Completes: `PV-007`, `PV-016`
- Produces: Startup and on-demand auto-detection scan (Ollama localhost, env var API keys), health status indicators, model profile creation from discovered providers
- Depends on: Step 2.B.2, Step 2.B.3
- Status: completed

#### Step 2.B.5: Structured Output & Cost Tracking [M]
- Completes: `PV-010`, `PV-011`, `PV-012`, `PV-013`, `PV-014`, `PV-015`
- Produces: Provider-native structured output + JSON fallback; schema validation with retry; cost estimation + actual tracking with delta/budget alerts; offline degradation; HF Hub auth
- Depends on: Step 2.B.2, Step 2.B.3
- Status: completed

#### Step 2.B.6: Model & Runtime Profile Services [M]
- Completes: `PV-008`, `PV-009`
- Produces: Model profile management, runtime profile management, profile switching rules across workspace/task/run scopes, and connectivity test services
- Depends on: Step 2.B.4, Step 2.B.5
- Status: completed

### Track C: Session & Identity

#### Step 2.C.1: Reviewer Profiles & Session Management [M]
- Completes: `SE-001`, `SE-002`, `SE-003`, `SE-004`, `SE-005`, `SE-011`, `SE-012`
- Produces: Reviewer profile and session services, signed session cookies, "Who are you?" flow, profile switching, app secret generation, network binding config
- Depends on: Gate 1
- Status: completed

#### Step 2.C.2: Queue Claim Model [M]
- Completes: `SE-006`, `SE-007`, `SE-008`, `SE-009`, `SE-010`
- Produces: Atomic claim mechanism, claim timeout with background task, expiry notifications, multi-session handling, mission control reviewer visibility
- Depends on: Step 2.C.1
- Status: completed

### Gate 2: Core Backend Verification
- [x] All items from Phase 2 tracks A, B, C
- [x] Verification: plugin loading with test plugin; provider health checks pass against mock; model/runtime profile switching works; reviewer profile CRUD works; claim/release cycle works; data loaders parse fixture files; exports produce valid output
- 395 unit tests pass, 20 skipped (optional deps: pyarrow); 48 frontend tests pass; ruff and tsc clean

---

## Phase 3: Workflow Engine & Data Management

Two parallel tracks, both requiring Phase 2.

### Track D: Workflow Engine

#### Step 3.D.1: Workflow YAML Parser & Context [L]
- Completes: `WF-001`, `WF-002`, `WF-003`, `WF-036`, `WF-045`
- Produces: YAML parser, WorkflowContext dataclass, step type registry, predecessor DAG builder, workflow versioning
- Depends on: Gate 2
- Status: completed

#### Step 3.D.2: Step Execution Engine & State Machine [L]
- Completes: `WF-035`, `WF-037`, `WF-038`, `WF-042`, `WF-043`, `WF-044`
- Produces: Step state machine, breakpoint handling, pause_on_every_step, concurrency/locking with visible ownership, context persistence, crash recovery with partial-output quarantine
- Depends on: Step 3.D.1
- Status: completed

#### Step 3.D.3: Data Step Implementations [L]
- Completes: `WF-004`, `WF-005`, `WF-006`, `WF-007`, `WF-008`
- Produces: data_ingest, data_normalize, data_filter, data_sample, data_deduplicate step executors
- Depends on: Step 3.D.2
- Status: completed

#### Step 3.D.4: Agent Step Implementations [M]
- Completes: `WF-009`, `WF-010`
- Produces: agent_run and agent_compare step executors integrated with provider system
- Depends on: Step 3.D.2
- Status: completed

#### Step 3.D.5: Human Step Implementations [M]
- Completes: `WF-011`, `WF-012`, `WF-013`, `WF-014`
- Produces: human_review, human_triage, human_calibration, human_adjudication step executors with queue creation and waiting_for_human
- Depends on: Step 3.D.2
- Status: completed

#### Step 3.D.6: Quality & Output Step Implementations [M]
- Completes: `WF-015`, `WF-016`, `WF-017`, `WF-018`, `WF-019`, `WF-020`
- Produces: quality_check, agreement_analysis, drift_detection, export, snapshot, release_validation step executors
- Depends on: Step 3.D.2
- Status: completed

#### Step 3.D.7: Control Step Implementations — Loop [L]
- Completes: `WF-021`, `WF-022`, `WF-023`, `WF-024`, `WF-025`, `WF-026`, `WF-027`
- Produces: loop step with all 4 termination strategies, body step reset, nested loop support
- Depends on: Step 3.D.2
- Status: completed

#### Step 3.D.8: Control Step Implementations — Conditional, Parallel, Gate [L]
- Completes: `WF-028`, `WF-029`, `WF-030`, `WF-031`, `WF-032`, `WF-033`, `WF-034`
- Produces: conditional (predicate evaluation, branch execution, skip propagation), parallel (concurrent execution, context merging, failure modes), gate step
- Depends on: Step 3.D.2
- Status: completed

#### Step 3.D.9: Error Handling & Recovery [M]
- Completes: `WF-039`, `WF-040`, `WF-041`
- Produces: Step failure handling (retry, skip, cancel, resume), partial step failure, timeout handling
- Depends on: Step 3.D.7, Step 3.D.8
- Status: completed

#### Step 3.D.10: Built-in Workflow Templates [M]
- Completes: `WF-046`, `WF-047`, `WF-048`, `WF-049`, `WF-050`, `WF-051`
- Produces: 6 YAML template files: Quick Agentic Label, Human-in-the-Loop, Full Quality Pipeline, Benchmark Authority, Agent Comparison, Iterative Refinement
- Depends on: Step 3.D.9
- Status: completed

#### Step 3.D.11: Lifecycle Stage Engine [M]
- Completes: `WF-052`
- Produces: Workspace lifecycle stage computation with prerequisites, outputs, blockers, downstream impacts, completion criteria, and recommended next actions
- Depends on: Step 3.D.9, Step 3.E.4
- Status: completed

### Track E: Data Management Hub

#### Step 3.E.1: Workspace Bootstrap & Indexing [L]
- Completes: `DT-001`, `DT-002`, `DT-016`, `DT-017`, `DT-018`
- Produces: Manifest-first workspace bootstrap with heuristic fallback, DB rebuild from canonical files, file scanning, metadata extraction, record projection, stale detection, reindex, drift detection, DuckDB/Polars integration
- Depends on: Gate 2
- Status: completed

#### Step 3.E.2: Data Source Adapters [M]
- Completes: `DT-003`, `DT-004`, `DT-005`
- Produces: Local file ingest (CSV, JSONL, Parquet, JSON, YAML, MD), HuggingFace import, Label Studio/Argilla/Prodigy import adapters
- Depends on: Step 3.E.1
- Status: completed

#### Step 3.E.3: Pre-label Import & Label Mapping [L]
- Completes: `DT-010`, `DT-011`, `DT-012`
- Produces: Pre-label import as review events with trust levels, label mapping engine (field mapping, value transformation), saved mapping configs
- Depends on: Step 3.E.2
- Status: completed

#### Step 3.E.4: Dataset Snapshots [M]
- Completes: `DT-013`, `DT-014`
- Produces: Named snapshot create/browse/compare/restore, delta storage, JSON metadata files with full-state references
- Depends on: Step 3.E.1
- Status: completed

#### Step 3.E.5: Dataset Operations & Derived Sets [M]
- Completes: `DT-019`, `DT-020`
- Produces: Clustering, disagreement mining, edge-case mining, challenge-set curation, saved subset definitions, lineage-aware derived slices, and subset promotion services
- Depends on: Step 3.E.3, Step 3.E.4
- Status: completed

### Gate 3: Engine Verification
- [x] All items from Phase 3 tracks D, E
- [x] Verification: 605 unit tests pass (20 skipped for optional deps), ruff clean. Workflow engine with all 21 step executors, 6 templates, 4 loop termination strategies, conditional/parallel/gate control flow, lifecycle stages. Data management with workspace bootstrap, 6 file format loaders, HuggingFace/Label Studio/Argilla/Prodigy adapters, pre-label import with mapping, snapshots with delta storage, derived subsets with lineage.

---

## Phase 4: Agent System & Review

Three parallel tracks.

### Track F: Agent Orchestration

#### Step 4.F.1: Agent Run Orchestration [L]
- Completes: `AG-001`, `AG-002`, `AG-003`, `AG-004`, `AG-005`
- Produces: Agent run lifecycle with explicit reruns, batch processing with events, output normalization/validation, output binding to review queues
- Depends on: Gate 3
- Status: completed

#### Step 4.F.2: Multi-Model Comparison [M]
- Completes: `AG-006`, `AG-007`
- Produces: Comparison run creation, per-record comparison, aggregate views (agreement matrix, distributions, cost, latency), toggleable analysis modes, comparison-data export
- Depends on: Step 4.F.1
- Status: completed

#### Step 4.F.3: Confidence Scoring & Active Learning [M]
- Completes: `AG-008`, `AG-014`
- Produces: Multi-signal confidence scoring (self-reported, self-consistency, logprobs), configurable weights, prioritization strategies (low-confidence-first, uncertainty, stratified, disagreement-first)
- Depends on: Step 4.F.1
- Status: completed

#### Step 4.F.4: Prompt Management & Versioning [M]
- Completes: `AG-013`
- Produces: Prompt YAML files, immutable-once-used, composable layers, auto-versioning, prompt editor backend
- Depends on: Gate 3
- Status: completed

#### Step 4.F.5: Agent Feedback Loop [L]
- Completes: `AG-009`, `AG-010`, `AG-011`, `AG-012`
- Produces: Correction accumulation, batch threshold, pattern extraction, refinement generation, user review flow, queued retries, correction preservation, queued/failed attempt notifications
- Depends on: Step 4.F.4, Step 4.F.1
- Status: completed

#### Step 4.F.6: Agent Performance Analytics [M]
- Completes: `AG-015`
- Produces: Per-field accuracy, trends, error patterns, confidence calibration, cost tracking, prompt version comparison, and analytics fed by AgentAdapterPlugin integrations
- Depends on: Step 4.F.1
- Status: completed

### Track G: Review & Adjudication System

#### Step 4.G.1: Review Event System [L]
- Completes: `RV-001`, `RV-002`, `RV-003`, `RV-004`, `RV-005`, `RV-010`, `RV-011`
- Produces: Blind review enforcement, AI reveal tracking, review decisions, append-only events, draft saving, rationale capture, duplicate prevention
- Depends on: Gate 3
- Status: completed

#### Step 4.G.2: Queue Management & Overlap [M]
- Completes: `RV-006`, `RV-007`, `RV-008`
- Produces: Calibration queues, overlap review (N copies, prevent self-overlap), queue assignment ordering, sticky assignment, and ReviewWorkflowPlugin-backed queue behavior
- Depends on: Step 4.G.1
- Status: completed

#### Step 4.G.3: Adjudication System [L]
- Completes: `AJ-001`, `AJ-002`, `AJ-003`, `AJ-004`, `AJ-005`, `AJ-007`
- Produces: Disagreement detection, adjudication queue, resolution types, side-by-side views, policy display, AdjudicationPlugin-backed resolution flow, audit trail via review_event
- Depends on: Step 4.G.1
- Status: completed

### Track H: Quality & Export

#### Step 4.H.1: Quality Metrics Engine [L]
- Completes: `QA-001`, `QA-002`, `QA-003`, `QA-004`, `QA-005`, `QA-006`, `QA-007`, `QA-008`, `QA-010`
- Produces: Agreement metrics (kappa, alpha), human-agent agreement, label distributions, delta analysis, throughput, calibration summaries, drift detection, readiness gates, and ValidationPlugin-backed gate execution
- Depends on: Gate 3
- Status: completed

#### Step 4.H.2: Export & Release System [L]
- Completes: `EX-001`, `EX-002`, `EX-003`, `EX-004`, `EX-005`, `EX-006`, `EX-007`, `EX-008`, `EX-009`, `EX-010`, `EX-011`, `EX-013`, `EX-014`
- Produces: Export in all formats, HF Hub push with preflight verification, custom via plugins, configurable inclusion, filters, atomic/quarantined write flow, canonical paths, release lifecycle, human signoff, determinism, conflict rules
- Depends on: Step 4.H.1
- Status: completed

#### Step 4.H.3: Frozen Release Views & Reporting [M]
- Completes: `EX-015`, `EX-016`
- Produces: Frozen split/release views for inspection, canonical readiness/validation report generation, and release-facing reporting surfaces
- Depends on: Step 4.H.2
- Status: completed

### Gate 4: Backend Feature Verification
- [x] All items from Phase 4 tracks F, G, H
- [x] Verification: full agent run with provider, corrections generate refinements, active learning prioritizes queue, review flow works end-to-end with blind review and AI reveal, overlap review works, adjudication resolves disagreements, quality metrics compute correctly, frozen release views render, readiness reports generate, and exports produce valid files in all formats

---

## Phase 5: REST API Layer

Single track, depends on all backend systems.

### Step 5.1: Workspace & Dataset API Endpoints [L]
- Completes: `API-003`, `API-004`, `API-005`, `API-006`, `API-007`, `API-008`, `API-009`, `API-010`, `API-011`, `API-012`, `API-013`, `API-014`, `API-015`, `API-016`, `API-017`, `API-018`
- Produces: All workspace, dataset, record, snapshot, label mapping REST endpoints with Pydantic response models
- Depends on: Gate 4
- Status: completed

### Step 5.2: Workflow API Endpoints [M]
- Completes: `API-019`, `API-020`, `API-021`, `API-022`, `API-023`, `API-024`, `API-025`, `API-026`, `API-027`, `API-028`
- Produces: Workflow CRUD, execute, execution detail, step advance, pause, cancel endpoints
- Depends on: Gate 4
- Status: completed

### Step 5.3: Task Schema & Provider API Endpoints [M]
- Completes: `API-029`, `API-030`, `API-031`, `API-032`, `API-033`, `API-034`, `API-035`, `API-036`, `API-037`, `API-038`, `API-039`, `API-040`
- Produces: Task schema CRUD, provider listing/scan, model profile CRUD/test, runtime profile CRUD endpoints
- Depends on: Gate 4
- Status: completed

### Step 5.4: Agent Run & Prompt API Endpoints [L]
- Completes: `API-041`, `API-042`, `API-043`, `API-044`, `API-045`, `API-046`, `API-047`, `API-048`, `API-049`, `API-050`, `API-051`, `API-052`, `API-053`, `API-054`, `API-055`, `API-056`, `API-057`
- Produces: Agent run CRUD/compare/cancel/outputs/analytics, prompt CRUD/diff, correction batch/analyze/refinement endpoints
- Depends on: Gate 4
- Status: completed

### Step 5.5: Review & Adjudication API Endpoints [M]
- Completes: `API-058`, `API-059`, `API-060`, `API-061`, `API-062`, `API-063`, `API-064`, `API-065`, `API-066`
- Produces: Review queue (atomic claim), queue stats, review event submission/draft/reveal-ai, review history, adjudication queue/detail/resolve endpoints
- Depends on: Gate 4
- Status: completed

### Step 5.6: Quality, Export, Session, Audit API Endpoints [M]
- Completes: `API-067`, `API-068`, `API-069`, `API-070`, `API-071`, `API-072`, `API-073`, `API-074`, `API-075`, `API-076`, `API-079`, `API-080`, `API-081`, `API-082`, `API-083`, `API-084`, `API-085`, `API-086`, `API-087`, `API-088`, `API-089`, `API-090`, `API-091`, `API-092`, `API-093`, `API-094`
- Produces: Quality dashboard/detail endpoints, export/release CRUD + preview/validate/download/push flows, session management, reviewer profiles, plugin listing/detail/toggle, audit history/detail, cost summary/estimate endpoints
- Depends on: Gate 4
- Status: completed

### Step 5.7: Assistant Backend & API [M]
- Completes: `AI-001`, `AI-002`, `AI-003`, `AI-004`, `AI-006`, `AI-007`, `AI-008`, `AI-009`, `AI-010`, `API-077`, `API-078`
- Produces: AssistantContextBuilder, assistant query/context endpoints, provider integration, cost/error handling, disable controls, streaming responses
- Depends on: Gate 4
- Status: completed

### Step 5.8: SSE Event Streams [M]
- Completes: `SSE-001`, `SSE-002`, `SSE-003`, `SSE-004`, `SSE-005`
- Produces: Queue events, workflow events, provider events, agent run progress SSE streams with session auth
- Depends on: Step 5.2, Step 5.4, Step 5.5
- Status: completed

### Gate 5: API Layer Verification
- [x] All API-* and SSE-* items, plus assistant backend items completed in Phase 5
- [x] Verification: `uv run pytest tests/integration/` passes for all endpoints; OpenAPI spec generates valid TypeScript client; all endpoints return Pydantic models; SSE streams deliver events; assistant query/context endpoints stream correctly

---

## Phase 6: Frontend Implementation

Three parallel tracks after Gate 5.

### Track I: App Shell & Navigation

#### Step 6.I.1: App Shell & Layout [L]
- Completes: `FE-001`, `FE-002`, `FE-003`, `FE-025`, `FE-030`, `FE-031`
- Produces: Left nav rail, central canvas, right inspector, command bar (Cmd+K), workflow rail, background-job indicators, profile switcher, Zustand stores, TanStack Query setup with OpenAPI client
- Depends on: Gate 5

#### Step 6.I.2: Home Screen [M]
- Completes: `FE-004`
- Produces: Workspace status, workflow stage, key counts, blockers, pending queues, recent runs, primary action
- Depends on: Step 6.I.1

#### Step 6.I.3: Settings & Profile Screens [M]
- Completes: `FE-023`
- Produces: Settings screen (project settings, assistant model selection, claim timeout, network binding)
- Depends on: Step 6.I.1

### Track J: Core Data Screens

#### Step 6.J.1: Dataset Catalog & Explorer [L]
- Completes: `FE-007`, `FE-008`, `DT-007`, `DT-015`
- Produces: Dataset catalog with health/counts/plugin indicators/links; data explorer with TanStack Table, virtual scrolling, filters, sorting, saved views, schema panel, copyable IDs/paths
- Depends on: Gate 5

#### Step 6.J.2: Record Inspector (360-View) [L]
- Completes: `FE-009`, `DT-008`
- Produces: Source data panel, labels panel (pre-labels + agent + human + adjudication), export inclusion state, quality panel, lineage/activity panel
- Depends on: Step 6.J.1

#### Step 6.J.3: Dataset Analytics Screen [M]
- Completes: `DT-009`, `FE-026`
- Produces: Label distribution charts, quality metrics, drift detection visuals, pre-label analysis, cross-dataset comparisons, activity summaries (Recharts)
- Depends on: Step 6.J.1

#### Step 6.J.4: Label Mapping Editor [M]
- Completes: `FE-029`
- Produces: Visual field mapping UI, value transformation table, mapping preview
- Depends on: Step 6.J.1

### Track K: Workflow & Agent Screens

#### Step 6.K.1: Workflow Builder Screen [XL]
- Completes: `FE-005`, `FE-006`, `FE-033`
- Produces: React Flow canvas, drag-and-drop step nodes, edge connections, branching/loop visualization, execution state overlay, stage explainability, YAML generation
- Depends on: Gate 5

#### Step 6.K.2: Mission Control Screen [L]
- Completes: `FE-013`
- Produces: Live run monitoring, event timeline, logs, artifact delta, queue impact, blocker summary, reviewer sessions with queue positions, active lock display
- Depends on: Step 6.K.1

#### Step 6.K.3: Agent Run Builder & Comparison Screens [L]
- Completes: `FE-012`, `FE-027`
- Produces: Role/model/runtime selection, compare mode, prompt version, subset targeting, cost estimate; side-by-side model comparison with diff highlighting, per-record/aggregate toggle, comparison export
- Depends on: Step 6.K.1

#### Step 6.K.4: Prompt Editor Screen [M]
- Completes: `FE-028`
- Produces: Prompt version list, diff view, few-shot example management, refinement review UI
- Depends on: Step 6.K.3

### Gate 6A: Core Frontend Verification
- [ ] All items from tracks I, J, K
- [ ] Verification: `cd frontend && npm run test && npm run build` passes; home screen loads with data; workflow builder creates and executes workflows; data explorer browses records; mission control shows live updates

---

## Phase 7: Review, Adjudication & Remaining Screens

Depends on Gate 6A.

### Track L: Review & Adjudication UI

#### Step 7.L.1: Review Queue Screen [XL]
- Completes: `FE-014`, `FE-015`, `FE-035`
- Produces: Full keyboard-driven review (all shortcuts from PRD 16.7), sticky scoring, AI drawer with blind-review indicator, queue position, draft save, submit; queue ergonomics (bulk actions, filters, saved views, skip-with-reason)
- Depends on: Gate 6A

#### Step 7.L.2: Adjudication Screen [L]
- Completes: `FE-016`
- Produces: Multi-reviewer panes, agent output pane, policy pane, record history, action toolbar, resolution reasoning
- Depends on: Step 7.L.1

### Track M: Quality, Curation, Export Screens

#### Step 7.M.1: Quality Dashboard Screen [M]
- Completes: `FE-017`
- Produces: Agreement metrics display, readiness gates, quality trend charts
- Depends on: Gate 6A

#### Step 7.M.2: Curation Screen [L]
- Completes: `FE-018`, `FE-036`
- Produces: Saved subsets, inclusion/exclusion rules, disagreement/edge-case facets, clustering, bulk operations, provenance, "Delegate This Step"
- Depends on: Gate 6A

#### Step 7.M.3: Export & Release Screens [M]
- Completes: `FE-019`, `FE-020`, `FE-034`
- Produces: Bundle preview, blockers, validation history, diff, HF access verification, frozen release views, report access, human signoff, export-level explainability
- Depends on: Gate 6A

### Track N: Admin Screens

#### Step 7.N.1: Plugin Management Screen [M]
- Completes: `FE-021`
- Produces: Plugin inventory, compatibility, enable/disable, required-by-project, manifest inspection
- Depends on: Gate 6A

#### Step 7.N.2: Audit History Screen [M]
- Completes: `FE-022`
- Produces: Filterable audit events, actor/timestamp, object links, file write/job events, replayable failure/interruption context
- Depends on: Gate 6A

#### Step 7.N.3: Task Schema Editor Screen [M]
- Completes: `FE-010`, `FE-011`
- Produces: Task schema versioning, label/rubric editing, overlap/adjudication config, model selection, export target preview; model/runtime config screen
- Depends on: Gate 6A

### Gate 7: Frontend Surface Verification
- [ ] All non-assistant frontend items through Phase 7
- [ ] Verification: all screens render and function; keyboard shortcuts work in review; adjudication flow completes; export and release screens render against frozen-view/report data; Playwright smoke tests pass; built-in plugin completeness closes at Gate 9

---

## Phase 8: Assistant Frontend

### Step 8.1: Assistant Frontend Panel [M]
- Completes: `FE-024`, `AI-005`
- Produces: Right-side support panel, collapsed by default, Cmd+/, suggested questions, markdown rendering, "show context" toggle, cost indicator, conversation history in browser memory
- Depends on: Step 5.7, Gate 6A

### Gate 8: Assistant Verification
- [ ] All AI-* items and the assistant frontend panel
- [ ] Verification: assistant responds with context-grounded answers; mode detection works; cost tracked; disable toggle works; streaming works

---

## Phase 9: Built-in Task Plugins

### Step 9.1: Text Labeling Plugin [M]
- Completes: `BP-001`
- Produces: Text labeling TaskTypePlugin: label fields, review form schema, validation, prompt template, export columns
- Depends on: Gate 4

### Step 9.2: Chat/Conversation Review Plugin [M]
- Completes: `BP-002`
- Produces: Chat review TaskTypePlugin with conversation window rendering
- Depends on: Step 9.1

### Step 9.3: Pairwise Ranking Plugin [M]
- Completes: `BP-003`
- Produces: Pairwise preference ranking TaskTypePlugin
- Depends on: Step 9.1

### Step 9.4: Extraction Plugin [M]
- Completes: `BP-004`
- Produces: Extraction TaskTypePlugin for structured information extraction
- Depends on: Step 9.1

### Step 9.5: PDF/Document Review Plugin [M]
- Completes: `BP-005`
- Produces: PDF/document review TaskTypePlugin
- Depends on: Step 9.1

### Step 9.6: Built-in Provider Plugins [M]
- Completes: `BP-008`
- Produces: Provider plugin wrappers for OpenAI-compatible, OpenRouter, Ollama, Anthropic registered via entry points
- Depends on: Gate 2

### Step 9.7: Non-DePolarize Example Plugin [M]
- Completes: `BP-009`
- Produces: A standalone example plugin (e.g., sentiment analysis) proving core reusability without DePolarize
- Depends on: Step 9.1

### Gate 9: Plugin Verification
- [ ] All BP-* items
- [ ] Verification: each plugin loads and registers; task type plugins validate labels; export packagers produce valid output; provider plugins connect to endpoints

---

## Phase 10: DePolarize Reference App

### Step 10.1: DePolarize Package Setup [M]
- Completes: `DP-001`, `DP-002`, `DP-007`, `DP-011`
- Produces: molabel-depolarize package, ReferenceAppPlugin registration, project bootstrap rules, manifest governance
- Depends on: Gate 9

### Step 10.2: DePolarize Task Types [L]
- Completes: `DP-003`, `DP-004`, `DP-005`, `DP-006`
- Produces: Asset A turn-level labeling, Asset B context-window review, Asset C trajectory review, DePolarize-specific schemas
- Depends on: Step 10.1

### Step 10.3: DePolarize Export & Validation [M]
- Completes: `DP-008`, `DP-009`, `DP-010`
- Produces: DePolarize export formats, release_readiness validation gate, project dashboard
- Depends on: Step 10.2

### Gate 10: DePolarize Verification
- [ ] All DP-* items
- [ ] Verification: DePolarize plugin loads on generic core; fixture workspace bootstraps; review, adjudicate, export, validate flows work; release gates pass

---

## Phase 11: Tauri Desktop Shell

### Step 11.1: Tauri Project Setup [M]
- Completes: `TA-001`, `TA-010`
- Produces: src-tauri/ with Cargo config, window management, localhost HTTP sidecar communication
- Depends on: Gate 9

### Step 11.2: Sidecar Process Management [L]
- Completes: `TA-002`, `TA-008`
- Produces: Python sidecar spawn/monitor/restart/shutdown, PyInstaller packaging config
- Depends on: Step 11.1

### Step 11.3: System Tray & Native Features [M]
- Completes: `TA-003`, `TA-004`, `TA-009`, `TA-011`
- Produces: Persistent tray icon with status, native file dialogs, system notifications, file associations, deep links
- Depends on: Step 11.2

### Step 11.4: Auto-Updater & Distribution [M]
- Completes: `TA-005`, `TA-006`, `TA-007`
- Produces: Auto-updater with user consent, dev mode parity, platform-specific distributions
- Depends on: Step 11.3

### Gate 11: Tauri Verification
- [ ] All TA-* items
- [ ] Verification: `cargo tauri dev` launches app with sidecar; system tray works; native file dialogs work; file associations and deep links resolve correctly; dev mode parity confirmed

---

## Phase 12: Testing & Polish

### Step 12.1: Python Unit Tests [L]
- Completes: `TS-001`
- Produces: Comprehensive pytest unit tests for core domain logic
- Depends on: Gate 10

### Step 12.2: Python Integration Tests [L]
- Completes: `TS-002`, `TS-003`
- Produces: Integration tests for SQLite, file I/O, plugin loading, agent orchestration; FastAPI endpoint tests
- Depends on: Step 12.1

### Step 12.3: Workflow Fixture YAMLs [M]
- Completes: `TS-007`
- Produces: ~15 parameterized workflow fixtures covering all scenarios
- Depends on: Step 12.1

### Step 12.4: Provider Adapter Tests [M]
- Completes: `TS-008`
- Produces: VCR-style recorded response cassettes for all provider adapters, --live-providers flag
- Depends on: Step 12.1

### Step 12.5: Frontend Tests [L]
- Completes: `TS-004`, `TS-005`
- Produces: vitest + RTL component tests, MSW integration tests
- Depends on: Gate 7

### Step 12.6: E2E Tests [L]
- Completes: `TS-006`, `TS-013`
- Produces: Playwright E2E tests for critical user flows; Tauri desktop smoke test checklist
- Depends on: Gate 11

### Step 12.7: Fixture Projects & Plugin SDK Tests [M]
- Completes: `TS-009`, `TS-010`, `TS-011`, `TS-012`
- Produces: 4 fixture projects, export determinism snapshot tests, plugin SDK round-trip tests, migration upgrade tests
- Depends on: Step 12.2

### Step 12.8: Performance Validation [M]
- Completes: `TS-014`
- Produces: Performance benchmarks verified against PRD 23.1 targets
- Depends on: Gate 11

### Step 12.9: Developer Experience & Plugin Authoring Docs [S]
- Completes: `DX-001`, `DX-002`
- Produces: Contributor command docs, verification command docs, plugin scaffold/template path, build-a-plugin guide, validated quickstart path
- Depends on: Step 12.7

### Gate 12: Final Verification
- [ ] All TS-* and DX-* items
- [ ] Verification: `uv run pytest` all pass; `npm run test` all pass; `npx playwright test` critical paths pass; CI pipeline green; performance targets met; all 6 workflow templates execute end-to-end; DePolarize reference app runs on extracted core; at least one non-DePolarize plugin works; review events are append-only; exports are deterministic; contributor/plugin-author docs are accurate

---

## Coverage Audit Summary

| Category | IDs | Count |
|----------|-----|-------|
| SC | SC-001 to SC-012 | 12 |
| DM | DM-001 to DM-034 | 34 |
| DB | DB-001 to DB-006 | 6 |
| WF | WF-001 to WF-052 | 52 |
| PV | PV-001 to PV-016 | 16 |
| AG | AG-001 to AG-016 | 16 |
| DT | DT-001 to DT-020 | 20 |
| RV | RV-001 to RV-011 | 11 |
| AJ | AJ-001 to AJ-007 | 7 |
| QA | QA-001 to QA-010 | 10 |
| EX | EX-001 to EX-016 | 16 |
| PL | PL-001 to PL-020 | 20 |
| API | API-001 to API-094 | 94 |
| SSE | SSE-001 to SSE-005 | 5 |
| SE | SE-001 to SE-012 | 12 |
| AI | AI-001 to AI-010 | 10 |
| FE | FE-001 to FE-036 | 36 |
| TA | TA-001 to TA-011 | 11 |
| DX | DX-001 to DX-002 | 2 |
| TS | TS-001 to TS-014 | 14 |
| DP | DP-001 to DP-011 | 11 |
| BP | BP-001 to BP-009 | 9 |
| **Total** | | **424** |

Every checklist ID appears in exactly one implementation step. 100% coverage.

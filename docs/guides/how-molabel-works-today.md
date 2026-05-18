# How MoLabel Works Today

This document explains the current MoLabel system as it exists in this repo.
It is meant to answer the practical question: what are the moving parts, which
surface is responsible for what, and how does a project move from raw data to a
reviewed release.

For product intent, read the PRD. For benchmark-specific behavior, read
[Grounded Benchmark Framework](grounded-benchmark-framework.md).

## 1. Core Idea

MoLabel is a local-first data operations workbench. It is designed to manage
the full lifecycle of labeled data:

1. ingest source data,
2. define the task schema and prompt,
3. run model or agent proposals,
4. route records through human review,
5. adjudicate disagreements,
6. compute quality and readiness metrics,
7. export and release a stable dataset artifact.

The important architectural decision is that MoLabel is not only an annotation
UI. It is a workflow-and-artifact system with auditability, repeatability, and
file ownership built into the core model.

## 2. Product Surfaces

MoLabel has four main runtime surfaces.

### 2.1 CLI

The intended public operating surface is the `molabel` CLI in `cli/`. It
groups operations into command families such as:

- `workspace`
- `dataset`
- `task-schema`
- `prompt`
- `workflow`
- `queue`
- `review`
- `adjudication`
- `quality`
- `export`
- `release`
- `artifact`
- `benchmark`

In the benchmark harness, external agents are expected to use this CLI rather
than reaching into private APIs or hidden files.

### 2.2 Backend API

The backend lives in `packages/molabel-app/src/molabel/app`. It is a FastAPI
application with a single `/api/v1` router tree. It exposes domains including:

- workspaces and datasets,
- task schemas and prompts,
- workflows and agent runs,
- queue, review, corrections, and adjudication,
- providers and model/runtime profiles,
- quality, exports, releases, and audit,
- CLI-oriented endpoints under `/api/v1/cli`,
- SSE events for real-time updates.

The backend is the system of operational coordination. It is not meant to be
the everyday human authoring surface.

### 2.3 Frontend

The frontend in `frontend/` is the manual control room. Its job is inspection,
review, and operational visibility:

- browsing data and workflow state,
- manual review and adjudication,
- queue operations,
- observability and mission-control style status.

This repo contains the React application, but it is not ready as a public or
primary operating surface yet. Treat it as a work-in-progress control-room UI,
not as a completed production shell.

### 2.4 Desktop Shell

`src-tauri/` packages the system into a desktop application. It is responsible
for windowing, local app behavior, and managing the backend sidecar. Business
logic stays out of Tauri.

### 2.5 Assistant Surface Status

The backend still mounts assistant-related API routes, but the product
direction has moved away from an in-app assistant being the main AI surface.
Current direction is:

- external agent plus CLI for primary operation,
- GUI for control-room and manual operations,
- assistant APIs treated as secondary or transitional.

## 3. Package Map

The repo is a `uv` workspace monorepo with strict package boundaries.

- `packages/molabel-core`
  Core library for storage, domain models, workflow execution, providers,
  prompt handling, plugins, review, quality, and benchmark scoring.
- `packages/molabel-app`
  FastAPI backend. It depends on `molabel-core` only.
- `packages/molabel-plugins`
  Built-in plugin implementations layered on top of core contracts.
- `packages/molabel-depolarize`
  Separate reference implementation under a separate namespace.
- `cli`
  TypeScript CLI and bundled skill surface.
- `frontend`
  React application.
- `src-tauri`
  Desktop shell.

These boundaries matter. Core must not import app, plugins, or depolarize.
Frontend only talks to backend through the API.

## 4. Storage Ownership

MoLabel uses three storage layers with explicit ownership rules.

### 4.1 Files On Disk

Files are canonical for portable project artifacts:

- raw input data,
- workflow definitions,
- task schemas and prompts,
- exports,
- benchmark authority material,
- release manifests and reports.

These artifacts should survive a database reset and should remain inspectable in
the workspace tree.

### 4.2 SQLite Operational State

SQLite is canonical for operational coordination:

- queue state,
- review events and drafts,
- agent run records,
- claims and sessions,
- audit events,
- runtime metadata.

SQLite is not where the canonical project definition is supposed to live.

### 4.3 Derived State

Derived caches and analytics outputs can be regenerated. They are authoritative
for nothing.

The key rule is simple: if the DB and the canonical files disagree, MoLabel
should surface the conflict and identify which side owns the truth.

## 5. Canonical Workspace Shape

The exact workspace layout depends on the project, but the operating model is:

- config artifacts live on disk,
- benchmark and release artifacts live under stable `workbench/` namespaces,
- generated machine outputs are written to stable file paths,
- human-authored artifacts are not silently overwritten.

The benchmark fixtures in `fixtures/` show the pattern clearly. Grounded
benchmark workspaces carry a `workbench/` tree for task schemas, workflows,
splits, gold views, review artifacts, and run outputs.

## 6. End-To-End Lifecycle

This is the main MoLabel workflow from source data to release.

### 6.1 Dataset Intake

Source data is imported through the loader system. The repo already supports
loader plugins and benchmark fixtures use JSONL heavily. Import creates record
references and establishes the working dataset.

### 6.2 Task Definition

The task is defined by a task schema plus prompt and, in many cases, a workflow
definition.

- task schema: what fields are produced and how they are typed,
- prompt: how the model is instructed,
- workflow: how data, agent, human, quality, and export steps are sequenced.

These are intended to be explicit, inspectable artifacts rather than hidden UI
state.

### 6.3 Agent Proposal

Agent or model runs generate structured proposals over the active record set.
These runs create durable operational records:

- run status,
- per-record outputs,
- events and progress,
- confidence and cost metadata when available.

### 6.4 Human Review

Review happens through queues. A reviewer typically:

1. claims a task,
2. sees the record under the configured blind-review policy,
3. optionally reveals the AI proposal,
4. submits a final decision.

Decision types in the current model include:

- `accept` or `accept_ai`
- `edit_ai`
- `reject_ai`
- `correct`
- `reject`
- `skip`

The append-only review event stream is important. The benchmark framework uses
final persisted review decisions rather than trusting free-form operator text.

### 6.5 Corrections And Adjudication

When there is disagreement or downstream correction work, MoLabel routes the
affected records into adjudication or correction flows. This is where the
system resolves conflicting human and agent outcomes into a releaseable view.

### 6.6 Quality And Readiness

Quality steps compute metrics such as:

- agreement,
- coverage,
- drift,
- readiness gates,
- benchmark scores for explicit evaluation runs.

These outputs are meant to be durable, machine-readable artifacts rather than
only UI summaries.

### 6.7 Export And Release

Once quality gates are acceptable, MoLabel produces export bundles and release
artifacts. Export writes files atomically. Release validation writes explicit
reports and approval state.

## 7. Workflow Execution Model

The workflow engine is YAML-defined and centered on a shared workflow context.
Step types fall into six categories:

- data
- agent
- human
- quality
- output
- control

Examples of supported step types include:

- `data_ingest`, `data_filter`, `data_sample`, `data_deduplicate`
- `agent_run`, `agent_compare`
- `human_review`, `human_triage`, `human_calibration`, `human_adjudication`
- `quality_check`, `agreement_analysis`, `drift_detection`
- `export`, `snapshot`, `release_validation`
- `loop`, `conditional`, `parallel`, `gate`

At runtime each step reads from and writes to the shared workflow context. Human
steps can pause execution. Control steps branch or orchestrate child steps.

## 8. Plugin And Provider Architecture

MoLabel is built to be extensible rather than hard-coded around one task type
or one model vendor.

- `molabel-core` defines the domain contracts and provider/plugin interfaces.
- `molabel-plugins` provides built-in task-type implementations.
- provider adapters in core handle model backends such as OpenAI-compatible,
  OpenRouter, Ollama, Anthropic, and custom adapters.
- model profiles and runtime profiles describe how a given model should be
  invoked in practice.

This separation is why the benchmark can insist on a specific current engine,
MiniMax 2.7 highspeed through the Anthropic-compatible path, without baking that choice
into the whole product architecture.

## 9. Review And Adjudication Semantics

The review system is one of the load-bearing parts of MoLabel.

Important behaviors:

- claims are explicit and expire,
- drafts are part of the operational state,
- blind review can hide AI outputs until reveal,
- reveal events are auditable,
- final submissions are append-only events,
- adjudication is a first-class queue rather than an afterthought.

This matters operationally and for the grounded benchmark. The benchmark uses
review-event truth, reveal behavior, and audit traces as part of the measured
operator behavior.

## 10. Session, Identity, And Audit

MoLabel tracks who is acting, what they claimed, and what they changed.

Important operational consequences:

- queue claims belong to explicit identities and can expire,
- draft and submission behavior is attributable,
- reveal-AI actions are auditable,
- workflow and export actions can be tied back to runtime state,
- benchmark operator runs can be audited from command logs plus persisted state.

This is not secondary bookkeeping. Identity and audit are part of how MoLabel
keeps review and release operations reproducible.

## 11. Quality And Benchmarking

MoLabel includes both general quality surfaces and benchmark-specific scoring.

- general quality features measure agreement, drift, readiness, and related
  operational metrics,
- grounded benchmarks measure a paper-backed task slice with gold labels,
  human-review artifacts, operator checks, and evidence bundles.

The current grounded benchmark framework lives in
`molabel.core.quality.grounded_benchmarks` and is exercised by live end-to-end
tests.

## 12. Benchmark And Audit Artifacts

One recurring pattern in MoLabel is that important evaluation results are
written as durable artifacts rather than only returned in memory.

Grounded benchmark runs now emit:

- `summary.json`
- `report.md`
- `evidence_manifest.json`
- `evidence/` with raw inputs, outputs, logs, scoring diagnostics, and runtime
  context

That same artifact-first mindset shows up elsewhere in exports, release
validation, workflow definitions, and prompt/task-schema storage.

## 13. Current Entry Points

Current repo-verified entrypoints:

- `uv run molabel-dev`
  Starts the backend and Vite frontend together for development.
- `uv run pytest tests/e2e/`
  Exercises the backend, workflow, review, and benchmark paths.
- grounded benchmark e2e tests in `tests/e2e/tier1_pipeline/`
  are the best current demonstration of end-to-end execution.

The repo direction is clearly CLI-primary, but this guide intentionally
distinguishes that direction from the currently confirmed dev entrypoint.

## 14. Stable Versus Transitional

Stable or largely real today:

- core data model and workflow concepts,
- FastAPI backend router structure,
- review/adjudication operational model,
- grounded benchmark scoring, diagnostics, and evidence bundles,
- CLI command families and benchmark harness usage.

Still transitional:

- some frontend pages and integration depth,
- parts of the CLI packaging and public install story,
- some older docs that still describe a GUI-first or HTMX-first architecture,
- grounded benchmark fixture layout, which still carries `workbench/`
  scaffolding alongside the authority-pack contract.

## 15. What To Read Next

- [Grounded Benchmark Framework](grounded-benchmark-framework.md)
- [MoLabel Data Model](../architecture/data-model.md)
- [Workflow Execution Specification](../architecture/workflow-execution.md)
- [Session And Identity](../architecture/session-and-identity.md)
- [API Specification](../architecture/api-specification.md)

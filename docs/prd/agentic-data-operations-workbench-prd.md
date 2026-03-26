# Agentic Data Operations Workbench PRD

Date: 2026-03-22
Status: Draft
Document type: Standalone OSS product PRD
Intended repository: new standalone GitHub repo
Reference implementation: DePolarize local workbench and phase-2 data program

## 1. Executive Summary

This PRD defines a new open-source product: a local-first, GUI-first, modular data operations workbench for agent-assisted labeling, human review, adjudication, dataset curation, model-orchestrated workflows, and release control.

The product should not be positioned as another generic annotation tool.
It should be positioned as a dataset control plane that handles the full lifecycle:

- intake,
- normalization,
- task configuration,
- agent proposal generation,
- model and provider selection,
- blind human review,
- overlap review,
- adjudication,
- quality measurement,
- dataset operations,
- export packaging,
- and release validation.

The first proof point is DePolarize, but the product must be general enough to support many task types, data formats, and project structures.

The app must be mainly GUI-driven.
The GUI is the primary product surface.
CLI, SDK, and file-level contracts exist to support automation, reproducibility, and power users, but the core workflow must be operable end to end without leaving the app.
The product must also be provider-agnostic so projects can switch easily between local and hosted model backends without redesigning workflows.

## 2. Why This Product Should Exist

There are good open-source tools adjacent to this idea.
There is not a strong open-source tool that cleanly combines all of these in one local-first product:

- agentic labeling and proposal generation,
- easy model and provider switching,
- human review and adjudication,
- generic multi-format data management,
- post-review promotion and release workflows,
- and dataset operations beyond annotation.

Today, these capabilities usually exist as pieces of a stack rather than one coherent product.

That creates a real product opportunity.

## 3. Market Landscape And Product Gap

As of March 22, 2026, the closest open-source neighbors are:

### 3.1 Label Studio OSS

Official sources:

- [Label Studio](https://labelstud.io/)
- [ML backend docs](https://labelstud.io/guide/ml_create)
- [Product comparison](https://labelstud.io/guide/label_studio_compare.html)

Strengths:

- strong multi-format annotation,
- configurable labeling interfaces,
- model prediction and pre-labeling support,
- mature annotation-centric workflows.

Weakness for this product direction:

- center of gravity remains annotation and evaluation,
- not designed as a full local-first data control plane with first-class dataset operations, adjudication policy, provenance, promotion, and release gating.

### 3.2 Argilla

Official sources:

- [Argilla quickstart](https://docs.argilla.io/latest/getting_started/quickstart/)
- [Argilla annotation guides](https://docs.argilla.io/v2.3/how_to_guides/annotate/)
- [Argilla task distribution](https://docs.argilla.io/latest/how_to_guides/distribution/)

Strengths:

- excellent open-source fit for text and LLM data workflows,
- human feedback collection,
- suggestions and responses,
- dataset-centric UX.

Weakness for this product direction:

- still closer to annotation and feedback collection than a full end-to-end data operations workbench,
- does not by itself own project-specific release, promotion, or dataset lifecycle control.

### 3.3 distilabel

Official sources:

- [distilabel quickstart](https://distilabel.argilla.io/dev/sections/getting_started/quickstart/)
- [distilabel documentation](https://distilabel.argilla.io/latest/)

Strengths:

- strong pipeline story for synthetic data generation and AI-feedback workflows,
- strongest open-source neighbor for agentic or model-assisted dataset generation.

Weakness for this product direction:

- pipeline engine, not the human review GUI and project control plane described here.

### 3.4 doccano

Official sources:

- [doccano](https://doccano.github.io/doccano/)
- [doccano roadmap](https://doccano.github.io/doccano/roadmap/)

Strengths:

- simple, approachable, open-source annotation workflow,
- good for straightforward text labeling.

Weakness for this product direction:

- too narrow for agent orchestration, review governance, post-review operations, and heterogeneous data programs.

### 3.5 FiftyOne

Official sources:

- [FiftyOne docs](https://docs.voxel51.com/)
- [Annotation guide](https://docs.voxel51.com/user_guide/annotation.html)
- [Plugin ecosystem](https://docs.voxel51.com/plugins/plugins_ecosystem/annotation.html)

Strengths:

- strong dataset browsing, curation, plugin architecture, and visualization,
- powerful inspiration for dataset operations and extensibility.

Weakness for this product direction:

- stronger as a curation and visualization platform than as an agentic review and release-control workbench.

### 3.6 OpenRefine

Official source:

- [OpenRefine](https://openrefine.org/)

Strengths:

- excellent local-first data cleanup and transformation model,
- strong inspiration for file-backed data operations.

Weakness for this product direction:

- not an annotation, review, or agent workflow product.

### 3.7 Product Gap Summary

Nearest current combinations are:

- `Argilla + distilabel`
- `Label Studio + custom ML or agent backends`
- `FiftyOne + annotation plugins + external review stack`

None of those combinations delivers a clean local-first product where one GUI owns:

- data intake,
- agent proposal workflows,
- human review,
- adjudication,
- dataset operations,
- quality metrics,
- export preparation,
- and release control.

That is the gap this product should fill.

## 4. Product Positioning

This product should not be pitched as:

- another labeling tool,
- a Label Studio competitor,
- or a hosted workflow platform.

It should be pitched as:

- a `local-first agentic data operations workbench`,
- a `human-in-the-loop review and adjudication system for AI-generated labels`,
- and a `dataset control plane for labeling, curation, quality, and release`.

This positioning is stronger because it emphasizes the full operational lifecycle rather than one narrow surface.

## 5. Core Product Thesis

The best version of this project is not “labeling with agents.”

The best version is:

- agents as first-class proposal and analysis workers,
- model and runtime selection as first-class operational controls,
- humans as first-class reviewers and adjudicators,
- datasets as first-class operational objects,
- and release-quality outputs as first-class deliverables.

The product wins if it makes it easy to move from messy source data to reviewed, traceable, exportable dataset artifacts inside one mostly GUI-driven local tool.

## 6. Product Principles

### 6.1 GUI-first

The GUI is the primary way users operate the system.
Core workflows must not require shell knowledge.

### 6.2 Local-first

The default deployment is local.
The product should work fully on one machine without mandatory cloud dependencies.

### 6.3 Modular

The system must support many task types, data formats, and project structures through a plugin and adapter model, not through hard-coded app forks.

### 6.4 Provider-agnostic

The system must not be tied to one model vendor, one agent runtime, or one API shape.
Projects must be able to switch between model providers and local runtimes with minimal reconfiguration.

### 6.5 File-backed and reproducible

Canonical project outputs must remain inspectable on disk.
The app database is an operational layer, not hidden truth.

### 6.6 Human authority

Agents can propose, critique, normalize, and prioritize.
Humans own decisions that define benchmark truth, adjudication, and release status.

### 6.7 End-to-end coverage

The product must handle the lifecycle from intake to release packaging, not stop at annotation.

### 6.8 Calm operational design

The GUI should feel focused, readable, and fast.
It should avoid enterprise clutter and generic dashboard noise.

### 6.9 Process legibility

The product must always explain:

- what stage the project is in,
- what inputs are missing,
- what is blocked,
- what the next highest-value action is,
- and what happens after that action completes.

## 7. Product Goals

### 7.1 Primary goals

- Provide one mostly GUI-driven local app for dataset work from start to end.
- Support agent-assisted labeling and human review in the same product.
- Support multiple data formats and task types through modular extensions.
- Support post-review operations such as adjudication, dataset curation, readiness gates, and exports.
- Allow easy switching across model providers and local runtimes such as OpenRouter, Ollama, OpenAI-compatible endpoints, and other adapters.
- Be easy to bootstrap on a fresh machine from a checked-out repository or local project folder.
- Be open-source and generic enough for use beyond DePolarize.

### 7.2 Secondary goals

- Make dataset operations as important as annotation.
- Make blind review and AI reveal tracking easy to enforce.
- Preserve provenance and auditability across the full workflow.
- Make provider choice and model switching operationally simple rather than a setup burden.
- Make DePolarize a strong reference implementation without hard-coding the product around it.

## 8. Non-Goals

- Multi-tenant SaaS.
- Enterprise-grade auth, RBAC, or organization management.
- Managed cloud hosting.
- Replacing Git or files with a database-only system.
- Solving every possible multimodal workflow.
- Autonomous release approval without human signoff.

## 9. Target Users

### 9.1 Dataset operator

Responsible for intake, task setup, agent runs, queue management, exports, and release readiness.

### 9.2 Reviewer

Responsible for blind review, overlap review, calibration, and rationale entry.

### 9.3 Adjudicator

Responsible for disagreement resolution, preserved disagreement decisions, exclusion, and tier or release decisions.

### 9.4 Research engineer

Responsible for plugin creation, workflow configuration, schema contracts, and integrations.

### 9.5 Reference-app maintainer

Responsible for packaging a project-specific implementation such as DePolarize on top of the generic core.

## 10. Product Shape

The product consists of two layers.

### 10.1 Generic OSS core

The standalone open-source repository should contain:

- the local app shell,
- the core data model,
- the workspace bootstrap and indexing system,
- the generic explorer,
- the task and queue engine,
- the workflow-state engine,
- the plugin runtime,
- the model-provider and runtime adapter layer,
- the agent orchestration layer,
- the supportive AI layer,
- the review and adjudication framework,
- the dataset operations engine,
- the validation and export framework,
- and the GUI component system.

### 10.2 Reference implementations

Project-specific implementations should live as first-party or third-party plugins.

The first reference implementation should be DePolarize.
It should prove that the core can support:

- turn-level text review,
- context-window review,
- trajectory-style records,
- manifest-backed governance,
- and release gating.

## 11. Why DePolarize Is A Strong Starting Point

The current DePolarize repo already demonstrates that the problem is real.
It contains:

- a real local FastAPI workbench shell,
- an existing SQLite data model for artifacts, records, review events, AI suggestions, adjudications, jobs, validation runs, releases, split freezes, and UI preferences,
- repo bootstrap and artifact indexing,
- and real surfaces for review, adjudication, quality, promotion, release, manifests, and jobs.

That means the OSS product should not start from a blank whiteboard.
It should extract and generalize the viable concepts already proven in DePolarize.

## 12. Scope

### 12.1 In scope for the standalone product

- local workspace bootstrap,
- file-backed data indexing,
- generic multi-format data explorer,
- project and task configuration,
- provider and model configuration,
- agent-assisted proposal workflows,
- blind human review,
- overlap and calibration workflows,
- adjudication,
- quality metrics,
- dataset operations,
- workflow guidance and monitoring,
- export packaging,
- validation and release gates,
- plugin architecture,
- and GUI-first operation across all critical flows.

### 12.2 Out of scope

- hosted team administration,
- cloud billing,
- enterprise identity management,
- marketplace distribution,
- real-time multi-user collaboration,
- and full multimodal parity across all media types.

## 13. Source Of Truth And Data Ownership

The product must have an explicit ownership model.

### 13.1 Canonical storage layers

There are three storage layers:

1. Project files on disk
2. Local operational database
3. Derived cache artifacts

### 13.2 Source-of-truth matrix

Project files on disk are authoritative for:

- imported source artifacts,
- project configuration,
- plugin configuration,
- review exports,
- adjudication exports,
- packaged dataset outputs,
- validation reports,
- release manifests,
- and human-authored docs and policies.

The local database is authoritative for:

- indexed metadata,
- queue state,
- saved GUI views,
- reviewer profiles,
- draft reviews not yet exported,
- job history,
- UI preferences,
- and cached projections used for fast navigation.

Derived cache artifacts are authoritative for nothing.
They can always be regenerated.

### 13.3 Object ownership table

Each core object type must have one explicit ownership class.

Canonical-on-disk objects:

- source datasets,
- task configuration files,
- plugin configuration files,
- review exports,
- adjudication exports,
- validation reports,
- export bundles,
- release manifests,
- and project policy or governance documents.

DB-canonical objects:

- reviewer profiles,
- local drafts,
- queue state,
- saved views,
- audit events not yet exported,
- plugin install state,
- and local UI preferences.

Derived-cache objects:

- row-count caches,
- sampled preview caches,
- clustering outputs that can be regenerated,
- and materialized analytical views.

Ephemeral UI objects:

- current panel selection,
- current unsaved filter state,
- in-progress drag or bulk-selection state,
- and transient notifications.

### 13.4 Sync rule

If the database and canonical files disagree, the product must:

- surface the conflict,
- identify which side is canonical for that object type,
- and offer a repair path.

The product must never silently choose one side.

### 13.5 Conflict states

The product must detect and distinguish:

- file changed on disk since last load,
- file deleted on disk,
- plugin required for file is unavailable,
- schema version mismatch,
- and DB draft exists for an object whose canonical file was modified elsewhere.

Each conflict type must have a visible recovery path in the GUI.

### 13.6 Workspace manifest contract

The standalone product should define one canonical workspace manifest so a project can move between machines and repositories without hidden setup.

Suggested shape:

- workspace identifier
- enabled plugins
- dataset registrations
- task schema registrations
- export targets
- validation gates
- agent profile references
- model profile references
- runtime profile references
- and optional reference-app metadata

The manifest should live in a stable path such as:

- `workbench.project.yaml`

The exact filename can change, but the product must have one documented project manifest contract.

### 13.7 Minimal workspace manifest fields

The minimal generic workspace manifest must define:

- `workspace_id`
- `workspace_name`
- `core_version`
- `enabled_plugins`
- `datasets`
- `task_schemas`
- `export_targets`
- `validation_gates`
- `agent_profiles`
- `model_profiles`
- `runtime_profiles`
- and optional `reference_app`

Each dataset entry must declare at minimum:

- dataset identifier,
- one or more source paths,
- loader plugin,
- record kind,
- canonical ID strategy,
- and indexing mode.

Each task schema entry must declare at minimum:

- task schema identifier,
- task type plugin,
- label or rubric definition path,
- review flow type,
- adjudication policy reference,
- default model profile or routing profile when agent support is required,
- and export target mapping.

The first version may keep the manifest simple, but it must be sufficient for the app to reconstruct:

- what datasets exist,
- how they are loaded,
- which task types apply,
- which model or runtime profiles are available,
- which plugins are required,
- and where canonical outputs should be written.

### 13.8 Example workspace manifest

```yaml
workspace_id: demo-local-workspace
workspace_name: Demo Local Workspace
core_version: 0.1
enabled_plugins:
  - core.text_labeling
  - core.chat_review
  - depolarize.reference_app
model_profiles:
  - model_profile_id: openrouter_general
    provider: openrouter
    model: anthropic/claude-sonnet-4
    transport: openai_compatible
    auth_ref: env:OPENROUTER_API_KEY
  - model_profile_id: ollama_local
    provider: ollama
    model: llama3.1:8b
    transport: ollama_http
runtime_profiles:
  - runtime_profile_id: local_only
    mode: offline_preferred
datasets:
  - dataset_id: asset_a_candidates
    source_paths:
      - phase-2/data/derived/asset-a/pilot-001/candidates.jsonl
    loader_plugin: depolarize.asset_a_loader
    record_kind: text_turn
    canonical_id_strategy: source_record_id
    indexing_mode: projection
task_schemas:
  - task_schema_id: asset_a_review_v1
    task_type_plugin: depolarize.asset_a_review
    definition_path: workbench/config/task-schemas/asset_a_review_v1.yaml
agent_profiles:
  - agent_profile_id: default_proposer
    role: proposer
    model_profile_id: openrouter_general
export_targets:
  - export_id: asset_a_review_export
    output_namespace: depolarize/asset_a/reviews
validation_gates:
  - depolarize.release_readiness
reference_app:
  app_id: depolarize
```

## 14. Canonical Write Contract

Every important write path must be deterministic and inspectable.

### 14.1 Write principles

- Canonical writes target stable file paths under a project workspace.
- File formats must be documented per plugin.
- Writes must use temp-file plus atomic rename when possible.
- Human-authored files must show a diff preview before overwrite.
- Machine-authored exports must preserve stable ordering where possible.
- Writes must record the source file hash or version observed when the edit session began.

### 14.2 Core write categories

The product must support canonical writes for:

- review event exports,
- adjudication exports,
- packaged labeled datasets,
- project validation reports,
- release reports,
- agent run manifests,
- and task configuration snapshots.

### 14.3 Write conflict rules

If a canonical target changed on disk after the current editing session began, the product must:

- block blind overwrite by default,
- show a structured diff,
- allow refresh and rebase,
- and require explicit force-overwrite for machine-authored files only.

Human-authored files must never be force-overwritten without a diff and explicit confirmation.

### 14.4 Failure behavior

If a canonical write fails, the product must:

- preserve the local draft state,
- keep the previous canonical file untouched,
- show the exact error,
- and log the failed write in audit history.

### 14.5 Atomic export flow

All canonical exports must follow this flow:

1. validate output payload,
2. render to temp location,
3. verify deterministic ordering and schema,
4. compare with existing target when present,
5. atomically replace target,
6. refresh index and audit log.

### 14.6 Canonical output path contract

The core must define a stable output path strategy so exports are reproducible across machines.

Required rules:

- each plugin must declare its output namespaces,
- output paths must be relative to the workspace root,
- path templates may include workspace, dataset, task schema, run, and export identifiers,
- machine-generated outputs must never be written to ambiguous ad hoc paths,
- and human-authored project docs must never be mixed into machine-generated directories.

At minimum, the product should reserve stable top-level areas such as:

- `workbench/config/`
- `workbench/exports/`
- `workbench/reports/`
- `workbench/runs/`
- `workbench/cache/`

Reference apps may map these to project-native locations, but the mapping must be explicit in project configuration.

## 15. Functional Requirements

### 15.0 Composable workflow engine

The product must support a fully composable workflow engine rather than a fixed lifecycle. Workflows are user-defined directed graphs of steps, not a hardcoded sequence.

#### 15.0.1 Workflow definition model

Workflows are defined as YAML files (file-backed, version-controllable). A visual workflow builder in the GUI (React Flow) generates and edits the YAML. Advanced users may edit YAML directly. The YAML is the source of truth.

#### 15.0.2 Workflow step types

The workflow engine must support approximately 20 step types across six categories:

Data steps:
- `data_ingest` — attach or import source data,
- `data_normalize` — clean and standardize records,
- `data_filter` — subset records by criteria,
- `data_sample` — random or stratified sampling,
- `data_deduplicate` — remove or flag duplicate records.

Agent steps:
- `agent_run` — run a configured agent role against targeted records,
- `agent_compare` — run the same task across multiple models and collect comparison data.

Human steps:
- `human_review` — standard blind review with optional AI reveal,
- `human_triage` — first-pass sorting or prioritization,
- `human_calibration` — calibration review pass for inter-annotator alignment,
- `human_adjudication` — resolve disagreements between reviewers or between human and agent.

Quality steps:
- `quality_check` — run validation gates and quality metrics,
- `agreement_analysis` — compute agreement metrics across reviewers and agents,
- `drift_detection` — detect label or data drift over time.

Output steps:
- `export` — package labeled data for output,
- `snapshot` — capture a named point-in-time dataset state,
- `release_validation` — run release readiness gates and generate reports.

Control steps:
- `loop` — repeat a group of steps until a termination condition is met,
- `conditional` — branch execution based on a metric or status,
- `parallel` — run multiple steps simultaneously,
- `gate` — pause execution for manual operator approval before proceeding.

#### 15.0.3 Loop termination conditions

Loop steps must support four termination mechanisms:
- count-based: repeat N times,
- metric-based: repeat until a quality metric exceeds a threshold,
- coverage-based: repeat until all target items are labeled,
- manual: repeat until an operator explicitly advances the workflow.

Each loop step specifies which termination conditions apply.

#### 15.0.4 Workflow execution model

Workflows execute with a hybrid automatic-plus-breakpoint model:
- Non-human steps (ingest, normalize, agent runs, quality checks, exports) execute automatically.
- Human steps (review, triage, calibration, adjudication) pause automatically and wait for human work to complete.
- Gate steps pause and wait for operator approval.
- Any step can be configured to pause before executing (like a debugger breakpoint).
- Users can also set the workflow to pause at every step for full manual control.

The execution model is configurable per step and per workflow.

#### 15.0.5 Built-in workflow templates

The product must ship with at least six built-in workflow templates:

1. Quick Agentic Label — ingest, agent run, export. No human review.
2. Human-in-the-Loop Review — ingest, agent run, human review, export.
3. Full Quality Pipeline — ingest, normalize, agent run, triage, calibration loop (agent plus human calibration repeating until agreement threshold), human review, adjudication, quality check, export, release validation.
4. Benchmark Authority — ingest, sample, human review (no agent), overlap review, adjudication, export.
5. Agent Comparison — ingest, agent compare (N models), human review, agreement analysis, export.
6. Iterative Refinement — ingest, loop (agent run, human calibration, until agreement threshold), full human review, export.

Templates are starting points. Users may modify any template or build workflows from scratch.

#### 15.0.6 Recommended lifecycle (template reference)

The following 12-step sequence remains a recommended reference lifecycle for comprehensive projects. It is captured as the Full Quality Pipeline template:

1. ingest or attach source data,
2. normalize and index,
3. define task schema,
4. sample or select working set,
5. run agents,
6. triage or first-pass review,
7. overlap review,
8. adjudication,
9. quality and readiness analysis,
10. curation and subset building,
11. export packaging,
12. release validation and audit.

This sequence is not mandatory. Projects may use any subset, reorder steps, add loops, or define entirely custom workflows.

### 15.1 Workspace bootstrap

The product must:

- open a local project folder,
- detect known project structure if a reference plugin exists,
- support generic workspaces even without a reference plugin,
- initialize the local DB,
- scan supported files,
- infer artifact and record metadata,
- and show missing requirements clearly.

### 15.2 Generic data explorer

The explorer must support:

- CSV,
- JSONL,
- Parquet,
- YAML,
- JSON,
- Markdown metadata,
- Hugging Face dataset imports,
- chat transcripts,
- preference pairs,
- tool-call traces,
- and evaluation records.

The explorer must support:

- table view,
- record view,
- raw JSON view,
- schema view,
- field search,
- sorting,
- filtering,
- saved views,
- sample views,
- subset export,
- and lineage inspection.

### 15.3 Project and task configuration

The GUI must allow users to:

- create or open a project,
- choose installed plugins,
- define task schemas,
- define label or rubric structures,
- configure review passes,
- configure overlap rates,
- configure adjudication policy,
- configure agent roles,
- configure provider and model profiles,
- configure runtime routing rules,
- and define export targets.

### 15.3.1 Model and provider connectivity

The product must treat model access as a first-class configurable subsystem rather than a hidden implementation detail.

Required behavior:

- support named model profiles and runtime profiles,
- support one-click switching between configured profiles in the GUI,
- support per-project defaults, per-task defaults, per-agent-role defaults, and per-run overrides,
- support local-only, self-hosted, hosted, and hybrid routing modes,
- and preserve the exact profile used for every agent run.

The first-party provider layer must support at minimum:

- OpenAI-compatible HTTP endpoints,
- OpenRouter,
- Ollama,
- Anthropic direct adapters where useful,
- and generic custom adapters through the provider interface.

The system must support in-house or self-hosted models through:

- OpenAI-compatible endpoints,
- local HTTP endpoints,
- Ollama-style local runtimes,
- or custom provider plugins.

### 15.3.2 Model profile contract

Each model profile must define at minimum:

- `model_profile_id`
- provider adapter
- model identifier
- transport type
- auth or credential reference
- structured output support
- tool-use support when applicable
- context window or capability tags when known
- and routing policy metadata

Credential values should not be stored directly in project files when avoidable.
Project files should reference environment variables, local secret stores, or runtime-specific secret references.

### 15.3.3 Task schema contract

Task schemas must be canonical project objects, not just DB state.

Each task schema must define:

- `task_schema_id`
- `task_type`
- `version`
- `title`
- `instructions`
- `record_selector`
- `label_fields` or `rubric_fields`
- `required_fields`
- `optional_fields`
- `blind_review_policy`
- `overlap_policy`
- `adjudication_policy`
- `supported_agent_roles`
- `default_model_profile` or `routing_profile` when agent support is required
- and `export_mapping`

Task schema versions must be immutable once used in completed review events.
Changes create a new task schema version rather than silently mutating the old one.

### 15.3.4 Example task schema

```yaml
task_schema_id: asset_a_review_v1
task_type: ordinal_text_review
version: 1
title: Asset A Review
instructions: docs/phase-2/annotation-handbook.md
record_selector:
  dataset_id: asset_a_candidates
label_fields:
  - name: social_distance
    type: ordinal
    scale: [1, 2, 3, 4, 5]
  - name: aversion
    type: ordinal
    scale: [1, 2, 3, 4, 5]
  - name: incivility
    type: ordinal
    scale: [1, 2, 3, 4, 5]
optional_fields:
  - name: rationale
    type: text
blind_review_policy: hide_agent_outputs_by_default
overlap_policy:
  mode: sampled_overlap
adjudication_policy:
  plugin: depolarize.asset_a_adjudication
default_model_profile: openrouter_general
supported_agent_roles:
  - proposer
  - critic
export_mapping:
  serializer: depolarize.asset_a_review_export
```

### 15.4 Agent-assisted workflows

Agents must be first-class citizens rather than hidden “predictions.”

The product must support at minimum these agent roles:

- proposer,
- critic,
- normalizer,
- disagreement flagger,
- deduper,
- rubric judge,
- edge-case miner,
- export-prep agent.

Each agent run must capture:

- provider or runtime,
- model identifier,
- model profile identifier,
- prompt or policy version,
- run parameters,
- targeted records,
- structured outputs,
- confidence or score fields when available,
- and run provenance.

### 15.4.1 Agent run contract

The agent system must use an explicit run lifecycle.

Required run states:

- `pending`
- `planned`
- `running`
- `partially_completed`
- `completed`
- `failed`
- `cancelled`

Each run must record:

- `agent_run_id`
- agent role
- plugin or adapter used
- provider or runtime
- model identifier
- model profile identifier
- runtime profile identifier
- prompt, rubric, or policy version
- input dataset or subset reference
- output schema identifier
- execution timestamps
- retry count
- partial-failure summary when applicable
- and downstream queue linkage when outputs are used for review.

### 15.4.2 Agent output contract

Each agent output record must declare:

- target record identifier,
- output type,
- structured payload,
- confidence or score fields when available,
- normalization status,
- review visibility status,
- and whether the output is eligible for accept-AI, edit-AI, or reject-AI workflows.

Agent outputs must bind to review queues through explicit references, not by heuristic file matching.
The same task must be rerunnable against a different model profile without redefining the task schema.

### 15.5 Review workflows

The product must support:

- blind first-pass review,
- optional AI reveal,
- AI reveal tracking,
- accept-AI flows,
- edit-AI flows,
- reject-AI flows,
- calibration queues,
- overlap review,
- queue assignment,
- rationale capture,
- and draft saving.

### 15.6 Adjudication workflows

The product must support:

- disagreement queues,
- side-by-side reviewer comparison,
- side-by-side agent comparison,
- policy excerpts,
- resolution states,
- preserved disagreement states,
- downgrade or exclusion states,
- and export of adjudication outcomes.

### 15.7 Quality and readiness workflows

The product must support:

- agreement metrics,
- disagreement summaries,
- label distribution views,
- agent versus human delta analysis,
- reviewer throughput,
- calibration summaries,
- and readiness dashboards for configured project gates.

### 15.8 Dataset operations

Dataset operations must be a first-class product area.

The product must support:

- filtering,
- clustering,
- sampling,
- deduplication,
- disagreement mining,
- edge-case mining,
- active-learning queues,
- challenge-set curation,
- subset promotion,
- export validation,
- and lineage-aware derived slices.

### 15.9 Release and export workflows

The product must support:

- export packaging,
- release preflight checks,
- privacy and license gates when configured,
- frozen split or release views,
- report generation,
- and release bundle inspection.

### 15.10 Workflow guidance and monitoring

The product must expose the project lifecycle as a first-class operational model.

Required behavior:

- show the current workflow stage for the project,
- show prerequisites and outputs for each stage,
- show blockers and missing inputs,
- compute and display recommended next actions,
- and show how jobs, agent runs, human queues, exports, and validations affect downstream stages.

The product must also include a supportive AI layer that can:

- explain the current step,
- explain why a record or run is in a queue,
- explain blockers and validator failures,
- summarize what changed,
- and prepare actions without silently executing them.

The supportive AI assistant must use the user's own configured model providers. The system assembles focused context server-side (current workflow state, active queue stats, recent agent runs, validation results, relevant record data) and passes it to the user's chosen model. The assistant can be disabled entirely.

#### 15.10.1 AI assistant context assembly

The assistant builds a focused context window before each query containing:

- current screen and workflow step name,
- current queue stats (pending, completed, blocked counts),
- last 5 agent runs with status and accuracy summary,
- current validation gate statuses,
- active blockers with explanations,
- and relevant record data if the user is asking about a specific record.

Context is assembled server-side by a dedicated context builder that pulls from SQLite and cached metrics.

Total context is budgeted to 4000 tokens maximum to keep costs low and latency fast.

The assistant system prompt defines five modes matching the UX strategy:

- Guide (help through process),
- Explain (explain labels, steps, metrics),
- Operator (help run jobs, queues, exports),
- Agent Monitor (explain agent behavior),
- Troubleshoot (diagnose failures).

The assistant auto-detects the appropriate mode based on the user's question and current screen.

If the user's configured model provider is unavailable, the assistant shows a "Provider unavailable" message rather than failing silently.

### 15.11 Agent feedback loop

The product must support a closed feedback loop where human annotations actively improve agent performance.

#### 15.11.1 Prompt refinement

As humans correct agent labels, the system must:

- accumulate corrections with field-level detail (what the agent proposed versus what the human chose),
- after a configurable batch threshold (default 25 corrections), analyze correction patterns,
- generate prompt refinements including few-shot examples and instruction patches,
- present refinements to the user for review before applying them,
- and apply approved refinements to the next agent run.

##### 15.11.1.1 Feedback loop error handling

If the correction analysis call to the LLM fails (provider offline, rate limited, timeout), the correction batch is queued and retried on the next successful provider connection.

Queued correction batches are persisted to disk so they survive app restarts.

If the generated refinements are malformed (cannot be parsed as valid prompt additions), the system discards them and logs the failure in audit history.

The user is notified of failed or queued refinement attempts via the notification area.

The correction library (raw corrections) is always preserved regardless of whether refinement generation succeeds.

#### 15.11.2 Active learning queue priority

The system must use agent confidence to prioritize human review queues:

- low-confidence items should be presented to humans first,
- confidence is computed using multiple signals: agent self-reported confidence in structured output, multi-run self-consistency (running the same item through the agent multiple times), and logprobs when available from the provider,
- items with highest composite uncertainty get human review first.

#### 15.11.3 Agent performance analytics

The system must track and display comprehensive agent performance metrics:

- accuracy versus human labels per field, per label value, and overall,
- agreement trend over time and across prompt versions,
- error pattern analysis identifying content types where the agent consistently fails,
- cost per correct label and cost per label including errors,
- throughput in labels per minute per model,
- confidence calibration curve showing whether agent confidence scores are well-calibrated,
- and prompt version comparison with clear indication of whether version N+1 improved over version N.

#### 15.11.4 Prompt management

Agent prompts must be first-class versioned project artifacts:

- prompts are stored as YAML files under `workbench/prompts/`,
- each prompt version is immutable once used in a completed agent run,
- prompts are composable: base system instructions plus task-specific rubric plus few-shot examples from correction batches,
- correction batches are stored alongside prompts in `workbench/prompts/corrections/`,
- the GUI must include a prompt editor with diff view between versions,
- and each agent run records exactly which prompt version was used.

#### 15.11.5 Structured output enforcement

The system must ensure agents return valid structured data:

- use provider-native structured output when available (OpenAI response_format, Anthropic tool_use, Ollama format:json),
- fall back to prompt-based JSON mode plus parse and validate when native support is unavailable,
- validate every agent output against the task schema,
- auto-retry up to three times on validation failure,
- and flag records as agent_error when all retries fail so humans review them without agent suggestions.

### 15.12 Data management hub

Data management must be a first-class product area with three dedicated surfaces.

#### 15.12.1 Dataset catalog

The dataset catalog must support:

- browsing all registered datasets with source info, record counts, health indicators, and last indexed time,
- plugin and task-type indicators,
- direct links into explorer, review, and export surfaces,
- and cross-dataset comparison of label distributions and quality metrics.

#### 15.12.2 Record inspector

The record inspector must provide a 360-degree view of any record showing:

- source data,
- all pre-labels from imports with trust level indicators,
- all agent outputs across all runs and models,
- all review events from human reviewers,
- adjudication status and history,
- export inclusion status,
- quality signals and flags,
- and full lineage and activity trail for that record.

#### 15.12.3 Dataset analytics

The product must provide dataset-level analytics including:

- label distribution charts,
- cross-dataset comparison views,
- drift detection over time,
- pre-label analysis showing how imported labels compare with agent and human labels,
- and per-dataset activity summaries.

#### 15.12.4 Dataset snapshots

The product must support user-triggered dataset snapshots:

- a snapshot captures the full state at a point in time including record labels, agent outputs, review events, quality metrics, and dataset membership,
- snapshots are stored as lightweight delta references not full copies of data,
- snapshots are named and timestamped,
- two snapshots can be compared to show what changed between them,
- and snapshots can be used for rollback or as export baselines.

##### 15.12.4.1 Snapshot storage design

Snapshots are stored as JSON metadata files under `workbench/snapshots/` with naming pattern `{snapshot_name}_{timestamp}.json`.

Each snapshot file contains:

- snapshot metadata (name, timestamp, creator),
- record state references (record ID to label values plus status at capture time),
- agent run references (list of agent_run_ids that existed at capture time),
- review event count and last event ID at capture time,
- quality metric values at capture time,
- and dataset membership (list of record IDs included).

Snapshots do NOT copy source data or full review event history — they store references and summary values.

Comparison between two snapshots computes:

- records added or removed,
- labels changed (field-level diff),
- new agent runs since previous snapshot,
- new review events since previous snapshot,
- and quality metric deltas.

Restoration from a snapshot does NOT roll back review events (which are append-only) — it creates a new "restored" state based on the snapshot's label values.

#### 15.12.5 Pre-label import and label mapping

The product must handle pre-existing labels from external sources:

- pre-labels are imported as review events with source set to import and a configurable trust level (ground_truth, expert, external, untrusted),
- the import screen includes a visual label mapping editor where users map source fields to target task schema fields,
- the mapping editor supports field name mapping, value transformation (float to ordinal, category to category), and partial mapping,
- unmapped fields are preserved as reference-only fields viewable in the record inspector but outside the review pipeline,
- saved mappings are reusable across imports from the same source format.

#### 15.12.6 Data sources

The product must support:

- local files in CSV, JSONL, Parquet, JSON, YAML, and Markdown formats,
- HuggingFace datasets library imports,
- and structured imports from Label Studio, Argilla, and Prodigy export formats.

Cloud storage, databases, and REST API sources are supported via data loader plugins.

### 15.13 Multi-provider enhancements

#### 15.13.1 Provider auto-detection

The system must automatically detect available providers:

- scan for a running Ollama instance at localhost:11434,
- check environment variables for known API keys (OPENAI_API_KEY, ANTHROPIC_API_KEY, OPENROUTER_API_KEY, and others),
- show discovered providers with health status indicators (online, offline, error),
- and offer to create model profiles from discovered providers.

#### 15.13.2 Multi-model comparison runs

The system must support running the same agent task across multiple models simultaneously:

- per-record comparison view showing side-by-side labels from each model with diff highlighting,
- aggregate comparison view showing distribution charts, agreement matrix between models, cost comparison, and latency comparison,
- toggle between per-record and aggregate views,
- and export of comparison data for analysis.

#### 15.13.3 Cost tracking

The system must track provider costs:

- estimate cost before a run based on token count and known provider pricing (configurable per model profile),
- record actual cost after a run based on API response data including tokens used,
- show delta between estimated and actual,
- maintain running totals per project, per model, per agent role,
- and optionally support budget alerts.

#### 15.13.4 Offline behavior

The system must degrade gracefully when internet is unavailable:

- all non-cloud features work offline: data management, workflow building, human review, export, local model agent runs,
- cloud provider calls fail with a clear error and offer alternatives: switch to local model, queue for later, or skip the agent step,
- provider health indicators show red and green status at all times,
- no explicit offline mode toggle is needed.

#### 15.13.5 HuggingFace Hub authentication

HuggingFace Hub push requires a valid HuggingFace API token.

Tokens are stored as environment variable references (e.g., `env:HF_TOKEN`), not directly in project files.

Before attempting a push, the system validates the token and checks write permissions on the target repository.

If validation fails, the system shows a clear error with instructions for creating or refreshing the token.

The export builder shows a "Verify HF access" button before starting the push.

### 15.14 Export formats

The product must support:

- JSONL (one record per line, UTF-8),
- Parquet (efficient columnar, compressed),
- CSV (universal),
- HuggingFace Hub push (direct upload to HuggingFace datasets),
- and custom formats via export packager plugins.

The export builder must support configurable inclusion of:

- record data,
- human labels (final),
- agent labels (for comparison),
- review metadata,
- adjudication history,
- record IDs and provenance,
- and configurable filters such as minimum agreement threshold and exclude-flagged.

## 16. GUI Requirements

### 16.1 GUI is primary

All critical workflows must be operable in the GUI:

- import,
- explore,
- configure,
- run agents,
- review,
- adjudicate,
- inspect quality,
- curate subsets,
- export,
- and validate release readiness.

The CLI and SDK are secondary convenience surfaces.

### 16.2 Frontend technology

The GUI is built as a React 19 plus TypeScript single-page application using shadcn/ui components and Tailwind CSS. The frontend communicates with the FastAPI backend exclusively via a REST API with auto-generated typed client (OpenAPI codegen). Real-time updates use Server-Sent Events (SSE). The app runs inside a Tauri v2 desktop shell providing native window management, system tray, native file dialogs, and auto-update.

### 16.2.1 Functional interface priorities

The GUI requirements in this PRD are about operational clarity and low-friction execution, not visual styling.

The interface must optimize for:

- always-visible workflow state,
- clear next actions,
- low-friction queue work,
- easy provider and model switching,
- explainability of blockers and failures,
- progressive disclosure for advanced controls,
- and fast movement between project, queue, run, and record context.

### 16.3 Navigation model

The default navigation should include:

- Home
- Workflow
- Data
- Tasks
- Agents
- Mission Control
- Review
- Adjudication
- Quality
- Curation
- Exports
- Releases
- Plugins
- Settings

The default layout should use:

- a left navigation rail for primary areas,
- a central workspace canvas for the current task,
- a right-side contextual inspector for metadata, policies, filters, and history,
- and a command bar for global search and quick actions.

### 16.4 Critical screens

The product must include at minimum:

- workspace home,
- workflow screen,
- dataset catalog,
- dataset explorer,
- task schema editor,
- model and runtime configuration screen,
- agent run builder,
- mission control or live run monitor,
- review queue screen,
- adjudication screen,
- quality dashboard,
- dataset operations screen,
- export packaging screen,
- release validation screen,
- plugin management screen,
- and audit history screen.

### 16.5 Shell behavior

The shell must provide:

- a persistent workflow rail or stage indicator,
- a persistent left navigation rail,
- a global command bar,
- a central task canvas,
- a right-side contextual inspector and support panel,
- breadcrumb or workspace context,
- and background-job indicators visible from any screen.

### 16.5.1 Home, catalog, and audit requirements

The Home screen must support:

- current workspace status,
- current workflow stage,
- active blockers,
- recent runs,
- pending queues,
- and one-click resume into the most urgent workflow.

The dataset catalog must support:

- dataset cards or rows,
- plugin and task-type indicators,
- record counts,
- last indexed time,
- health or drift state,
- and direct links into explorer, review, and export surfaces.

The audit history screen must support:

- filterable event history,
- actor and timestamp visibility,
- affected object links,
- file write and job run events,
- and replayable context for failed writes or interrupted jobs.

The workflow screen must support:

- full lifecycle view,
- stage prerequisites,
- stage outputs,
- stage blockers,
- explicit completion criteria,
- and one-click next actions.

### 16.6 Project setup and task editor requirements

The project setup and task editor screens must support:

- project bootstrap status,
- installed plugin list,
- installed provider and runtime profiles,
- task schema versioning,
- label or rubric editing,
- overlap and adjudication configuration,
- default model selection and fallback routing,
- export target preview,
- and validation before save.

### 16.7 Review screen requirements

The review screen must be fully keyboard-driven with vim-style efficiency:

- number keys (1-5) for ordinal label values,
- letter keys for category labels,
- Tab and Shift-Tab to move between fields,
- Enter to submit and advance to next record,
- n and p (or arrow keys) for next and previous record,
- Escape to skip with reason,
- Space to reveal AI suggestion (with tracking),
- a to accept AI, e to edit AI (pre-fill from suggestion), x to reject AI,
- r to open rationale entry,
- g plus number to jump to a specific record,
- Cmd-K or Ctrl-K for a command palette,
- and question mark to show all available shortcuts.

The review screen must also support:

- sticky scoring controls,
- side panels for metadata and policy,
- optional AI drawer,
- clear blind-review state indicator,
- queue position and estimated remaining time,
- save draft,
- submit final,
- and duplicate-submission prevention.

### 16.8 Explorer screen requirements

The data explorer must support:

- large-table browsing,
- visible filter chips,
- schema side panel,
- copyable IDs and paths,
- fast record detail transitions,
- and plugin-rendered custom record previews.

### 16.9 Agent run builder requirements

The agent run builder must support:

- role selection,
- model profile selection,
- provider and runtime override,
- compare-across-models mode,
- prompt or policy version selection,
- subset targeting,
- dry-run preview when available,
- cost or token estimate when available,
- and structured run-history links after execution.

The mission control screen must support:

- live run monitoring,
- event timeline,
- logs and streamed status,
- artifact delta preview,
- queue impact preview,
- and current blocker summary across jobs, agents, validations, and exports.

### 16.10 Adjudication screen requirements

The adjudication screen must support:

- multiple reviewer panes,
- agent output pane,
- policy pane,
- record history,
- action toolbar,
- and explicit resolution reasoning.

### 16.11 Export and release screen requirements

The export and release screens must support:

- bundle contents preview,
- blocker summaries,
- validation history,
- diff against previous bundle when available,
- and explicit human signoff before marking a release ready.

### 16.12 Curation screen requirements

The curation screen must support:

- saved subset definitions,
- visible inclusion and exclusion rules,
- disagreement and edge-case facets,
- clustering or grouping outputs when available,
- bulk-add and bulk-remove operations,
- and provenance preview for any derived subset.

### 16.13 Plugin management screen requirements

The plugin management screen must support:

- installed plugin inventory,
- compatibility state,
- enabled and disabled state,
- required-by-project indicators,
- plugin manifest inspection,
- and safe upgrade or rollback guidance.

The support panel must support:

- current step explanation,
- blocker explanation,
- next recommended action,
- "why is this here?" explanations for queue items and runs,
- validator failure explanation,
- and optional action preparation without silent execution.

## 17. Modularity And Extension Model

Modularity is a hard requirement.

### 17.1 Plugin categories

The product must support at least these plugin categories:

- data loaders,
- model providers,
- record renderers,
- task types,
- review forms,
- adjudication renderers,
- agent adapters,
- validation gates,
- export packagers,
- and reference-app bundles.

### 17.2 Required plugin contract

Each plugin must be able to declare:

- plugin identifier and version,
- compatible core version,
- supported file types,
- supported record kinds,
- schema or task definitions,
- list columns,
- detail renderer,
- review renderer,
- adjudication renderer,
- export formats,
- validation hooks,
- and job or command surfaces.

### 17.3 Plugin lifecycle contract

Each plugin must also define lifecycle hooks for:

- discovery,
- install,
- activation,
- compatibility check,
- migration or upgrade,
- disable,
- and uninstall safety.

If a plugin cannot satisfy compatibility checks, the core must keep the workspace readable and block only writes that depend on that plugin.

### 17.4 Minimal plugin interfaces

At minimum, the core must expose typed interfaces for:

- `DataLoaderPlugin`
- `TaskTypePlugin`
- `ModelProviderPlugin`
- `RecordRendererPlugin`
- `ReviewWorkflowPlugin`
- `AdjudicationPlugin`
- `AgentAdapterPlugin`
- `ValidationPlugin`
- `ExportPackagerPlugin`
- `ReferenceAppPlugin`

The first implementation may keep these as Python protocols or abstract base classes, but the contract must be explicit in the repo.

### 17.5 Plugin SDK interface contract

Each plugin interface must define:

- required metadata fields,
- registration entrypoint,
- compatibility check method,
- initialization hook,
- capability declaration method,
- validation hook,
- export or writeback hook when applicable,
- and failure mode behavior.

Renderer-capable plugins must also define:

- list-row renderer,
- detail renderer,
- and side-panel or inspector renderer.

Workflow-capable plugins must also define:

- queue builder,
- submission validator,
- and canonical export serializer.

### 17.5.1 Plugin UI model

Plugins provide custom frontend UI through a two-tier model:

Tier one: JSON schema declaration. Plugins declare their UI via JSON schema including form field definitions, column definitions, renderer configuration, and layout parameters. The core React app renders these generically using shared components. This is the default and covers approximately 90 percent of plugin UI needs.

Tier two: custom React component overrides. For advanced cases, plugins may provide custom React component bundles that the core app loads dynamically. Custom components must be self-contained and use only the documented plugin SDK props. This tier is optional and reserved for cases where JSON schema cannot express the needed UI such as custom visualization widgets, specialized review interfaces, or interactive record renderers.

#### 17.5.2 Plugin React component loading

Custom React components from plugins are loaded via dynamic import (`React.lazy` with `import()`).

Plugin React bundles are pre-built as ES module files (.mjs) and placed in a known directory (`workbench/plugins/{plugin_id}/ui/`).

The core app wraps each plugin component in an error boundary so a broken plugin component cannot crash the app.

Plugin components receive a typed props contract defined by the core: `PluginRecordRendererProps`, `PluginReviewFormProps`, `PluginDetailPanelProps` — each containing the record data, task schema, review state, and callback functions.

Plugin components must NOT import from the core app bundle — they receive everything through props.

Plugin component versions are tied to the plugin version — when a plugin updates, its component bundle updates atomically.

### 17.6 Task type plugins

The core should support task type plugins for:

- text labeling,
- chat or conversation windows,
- pairwise ranking,
- extraction,
- rubric scoring,
- trajectory review,
- document or PDF review,
- and future multimodal tasks.

### 17.7 Reference app plugins

A reference-app plugin may add:

- project bootstrap rules,
- project-specific manifests,
- readiness gates,
- project dashboards,
- and domain-specific workflows.

This is how DePolarize should be packaged.

### 17.7.1 Project template plugins

The core should also support project template or starter plugins for very different use cases.

Examples:

- benchmark-authority text review,
- conversation QA,
- pairwise preference adjudication,
- red-teaming and safety review,
- tool-use trace review,
- document extraction QA.

Templates should preconfigure:

- task schemas,
- queues,
- agent roles,
- validation gates,
- export mappings,
- and recommended provider/runtime profiles.

### 17.8 Plugin packaging and compatibility

Plugins must be distributable as normal versioned packages.

The product should define:

- a plugin manifest format,
- a Python entrypoint contract,
- semantic version compatibility rules,
- core-to-plugin API stability guarantees,
- plugin migration hooks for project upgrades,
- and failure behavior when an installed plugin is incompatible with the current workspace.

The product should also provide:

- a plugin scaffold command,
- a sample plugin repository or template,
- and fixture projects that plugin authors can use for testing.

### 17.9 Example plugin manifest

```yaml
plugin_id: depolarize.reference_app
version: 0.1.0
compatible_core: ">=0.1,<0.2"
plugin_type: reference_app
entrypoint: depolarize.plugin:register
supports:
  record_kinds:
    - text_turn
    - conversation_window
    - trajectory_record
  task_types:
    - depolarize.asset_a_review
    - depolarize.asset_b_window_review
    - depolarize.asset_c_trajectory_review
validations:
  - depolarize.release_readiness
exports:
  - depolarize.asset_a_review_export
recommended_model_profiles:
  - openrouter_general
  - ollama_local
```

## 18. System Architecture

### 18.1 Recommended stack

- Backend: FastAPI (Python 3.12+)
- Provider and runtime contracts: typed adapter interfaces
- Core models: SQLModel
- Validation: Pydantic
- Local DB: SQLite in WAL mode
- Analytics: DuckDB plus Polars where useful
- Frontend: React 19 plus TypeScript, built with Vite
- Workflow builder: React Flow
- UI components: shadcn/ui plus Tailwind CSS
- Data tables: TanStack Table
- Charts: Recharts
- State management: Zustand
- API client: TanStack Query plus auto-generated OpenAPI client
- Desktop shell: Tauri v2
- Real-time updates: Server-Sent Events (SSE)
- Jobs: local Python job runner with subprocess and in-process adapters
- Python packaging: uv
- Frontend packaging: npm
- Python testing: pytest
- Frontend testing: vitest
- E2E testing: Playwright
- Python linting: ruff
- Frontend linting: prettier plus eslint

### 18.2 Why this stack

- The product requires rich interactive UIs: drag-and-drop workflow builder, interactive data explorer, real-time mission control, side-by-side model comparison, agent performance charts. These require a real frontend framework.
- React has the largest ecosystem for the components needed: React Flow for node-graph workflow building, shadcn/ui for modern accessible components, TanStack Table for high-performance data browsing.
- Tauri v2 provides a native desktop experience (system tray, native file dialogs, auto-update) at a fraction of Electron's size (~5-10MB vs ~200MB). It manages the Python/FastAPI backend as a sidecar process.
- FastAPI auto-generates an OpenAPI spec. A codegen pipeline produces a fully typed TypeScript client, giving end-to-end type safety between Python backend and React frontend without GraphQL complexity.
- SSE provides real-time push for mission control, queue coordination, and workflow progress without the complexity of WebSocket.
- The app can also run in web-only dev mode (FastAPI at localhost, React dev server) without Tauri for development convenience.

### 18.3 Core package boundaries

The standalone repo should be organized into packages similar to:

- `core`
- `storage`
- `indexing`
- `tasks`
- `workflow`
- `providers`
- `agents`
- `monitoring`
- `assistant`
- `review`
- `quality`
- `curation`
- `exports`
- `validation`
- `ui`
- `plugins`
- `reference_apps`

#### 18.3.1 Module-to-package mapping

The internal modules listed above map to the four Python packages defined in AGENTS.md as follows:

`molabel-core` contains: `core`, `storage`, `indexing`, `tasks`, `workflow`, `providers`, `agents`, `monitoring`, `assistant`, `review`, `quality`, `curation`, `exports`, `validation`, `plugins`.

`molabel-app` contains: `ui` (FastAPI routes, API endpoints, SSE streams).

`molabel-plugins` contains: built-in task type implementations, built-in data loaders, built-in export packagers.

`molabel-depolarize` contains: `reference_apps` (DePolarize-specific schemas, views, jobs).

### 18.4 Core runtime responsibilities

`core` owns:

- application settings,
- workspace lifecycle,
- plugin registration,
- audit logging,
- and global service wiring.

`storage` owns:

- SQLite models,
- canonical file I/O,
- migrations,
- and transaction rules.

`indexing` owns:

- file scanning,
- metadata extraction,
- record projection,
- and drift detection.

`tasks` owns:

- queue creation,
- task configuration,
- and assignment rules.

`workflow` owns:

- stage model,
- completion criteria,
- blockers,
- and next-action computation.

`providers` owns:

- model provider adapters,
- runtime profiles,
- model profiles,
- routing rules,
- and provider capability metadata.

`agents` owns:

- agent adapter interface,
- run orchestration,
- run manifests,
- and agent output normalization.

`monitoring` owns:

- live run status,
- event timelines,
- log aggregation,
- artifact delta reporting,
- and queue impact previews.

`assistant` owns:

- supportive AI summaries,
- step explanations,
- blocker explanations,
- next-action recommendations,
- and action preparation flows.

`review` owns:

- review state machine,
- blind review enforcement,
- overlap handling,
- and adjudication pipeline inputs.

`quality` owns:

- agreement metrics,
- delta analysis,
- and readiness summaries.

`curation` owns:

- filtering,
- mining,
- clustering,
- and derived subset operations.

`exports` owns:

- labeled dataset packaging,
- project export formats,
- and release bundle preparation.

`validation` owns:

- plugin-defined checks,
- release gates,
- and report generation.

`ui` owns:

- navigation,
- screen composition,
- interaction patterns,
- and shared functional UI primitives.

`plugins` owns:

- generic plugin loading,
- plugin metadata,
- and plugin lifecycle.

`reference_apps` owns:

- project-specific packages such as DePolarize.

### 18.5 Public extension APIs

The OSS repo must define stable extension APIs for:

- dataset loaders,
- model providers,
- record normalizers,
- record renderers,
- review schemas,
- adjudication schemas,
- agent adapters,
- validation checks,
- export packagers,
- workflow stage providers,
- and home-screen or dashboard panels.

Anything outside these APIs should be treated as internal and not promised to plugin authors.

### 18.6 Repo-transfer strategy

The new OSS repository should be created by extraction, not wholesale transplant.

Recommended extraction order:

1. Extract generic workspace, artifact, record, review, job, validation, and UI primitives from the current DePolarize workbench.
2. Create a DePolarize reference package that re-registers project-specific schemas, assets, jobs, manifests, and dashboards.
3. Replace direct path-based DePolarize assumptions in the core with plugin-owned project detection and artifact inference.
4. Add at least one non-DePolarize sample plugin to prove the core is genuinely reusable.

The OSS repo should not depend on DePolarize internals for core startup.

### 18.7 Job and locking contract

The product must define explicit concurrency and locking behavior.

Required rules:

- only one canonical write operation may target the same output namespace at a time,
- background indexing may continue during read-only operations,
- reindexing must not mutate canonical files,
- destructive or conflicting writes must be blocked while an export or migration is in progress,
- and users must be able to see active locks and the action that owns them.

Lock scopes should include at minimum:

- workspace-level migration lock,
- dataset-level indexing lock,
- output-namespace export lock,
- and task-schema edit lock.

### 18.8 Multi-session support

The local FastAPI server must support multiple concurrent reviewer sessions:

- lightweight reviewer profiles with name and identifier, no enterprise auth,
- queue assignment prevents two reviewers from receiving the same item,
- SQLite WAL mode handles concurrent reads from multiple sessions,
- write operations use queue-level locking to prevent conflicts,
- and the mission control screen shows active reviewer sessions and their current queue positions.

Queue assignment uses a claim-based model: when a reviewer requests the next item, the server atomically claims it by writing the reviewer's ID and a timestamp to the review task record.

Claims have a configurable timeout (default 30 minutes) — if a reviewer does not submit or save a draft within the timeout, the claim is released and the item returns to the available pool.

Abandoned claims are detected by a periodic background task (every 60 seconds).

When a reviewer reconnects after being offline, any expired claims are shown as "reclaimed" notifications.

Queue priority order: items from active learning (low confidence) first, then items assigned by the workflow, then general pool.

Bulk claim is not supported — reviewers get one item at a time to prevent hoarding.

### 18.9 API and real-time communication

The frontend communicates with the backend via REST API only:

- FastAPI auto-generates an OpenAPI spec from Pydantic response models,
- a codegen pipeline produces a fully typed TypeScript client from the spec,
- TanStack Query manages caching and data fetching on the frontend,
- real-time updates (agent run progress, queue changes, workflow transitions, reviewer activity) use Server-Sent Events (SSE),
- SSE endpoints include at minimum: agent run events, queue events, and workflow events,
- and the OpenAPI spec and TypeScript client must stay in sync (enforced by CI).

### 18.10 Generic project detection rules

The core must support two startup paths:

1. explicit manifest startup
2. heuristic detection for reference apps or legacy projects

Heuristic detection should be a convenience only.
Manifest-driven startup is the stable contract.

### 18.11 DuckDB and Polars usage

DuckDB is used for analytical queries over large source files that remain on disk (CSV, Parquet, JSONL). SQLite handles operational state (metadata, projections, drafts, workflow state); DuckDB handles analytical scans that would be slow or impractical in SQLite.

DuckDB use cases:

- dataset distribution analysis (label frequencies, value distributions across millions of records),
- cross-dataset comparison queries,
- large-file sampling for review queue generation,
- and agreement computation over full datasets.

Polars is used as the in-memory DataFrame library for data transformation, filtering, and computation within the Python backend. Where the backend needs to load, reshape, or compute over tabular data in-process, Polars is the standard tool rather than pandas.

DuckDB and Polars are not used by the frontend. All analytical results are served to the React frontend via REST API endpoints. The frontend never directly queries DuckDB or loads Polars frames.

## 19. Core Data Model

The core should support at minimum these domain objects:

- workspace
- artifact
- dataset
- record
- task schema
- model profile
- runtime profile
- review task
- review event
- agent run
- agent event
- agent output
- adjudication
- validation run
- export bundle
- release
- plugin installation
- audit entry
- saved view
- reviewer profile

### 19.1 Append-only review truth

Review events must be append-only.
Corrections create new events rather than mutating history away.

### 19.2 Generic record payload plus typed projections

Records should support:

- stable typed fields for generic operations,
- plus payload JSON for plugin-specific details.

### 19.3 Large-file posture

The product must not require copying large datasets into SQLite.

Rules:

- raw data stays on disk,
- SQLite stores metadata, projections, state, and drafts,
- analytical scans may use DuckDB or Polars over source files,
- and the UI must degrade gracefully on large files.

### 19.4 Core identifiers

The core must standardize identifiers for at least:

- workspace,
- dataset,
- artifact,
- record,
- task schema,
- review task,
- review event,
- agent run,
- agent output,
- adjudication,
- validation run,
- export bundle,
- and release.

Identifiers must be stable enough for audit history, cross-file references, and export manifests.

### 19.5 Task and agent linkage

The data model must support explicit joins between:

- dataset and record,
- task schema and review task,
- model profile and agent run,
- runtime profile and agent run,
- review task and review event,
- agent run and agent output,
- agent run and agent event,
- agent output and review visibility state,
- adjudication and the reviewed object,
- export bundle and its source records,
- and validation run and the bundle or dataset it checked.

## 20. Critical User Flows

### 20.1 Start a new project

1. User opens a local folder.
2. Product detects project type or offers generic setup.
3. User chooses plugins, project template, and default task types.
4. User configures provider and runtime profiles.
5. Product bootstraps DB and indexes data.
6. User lands on a home screen with detected datasets, blockers, and next actions.

### 20.2 Import and configure a dataset

1. User imports local files or points to existing project files.
2. Product indexes records and artifacts.
3. User configures task schema, labels, rubric, model defaults, and export targets.
4. Product validates config and saves canonical project files.

### 20.3 Run agents

1. User selects a dataset or subset.
2. User chooses one or more agent roles.
3. User can switch model profile or runtime profile without redefining the task.
4. Product runs the configured agents locally or through configured providers.
5. Product stores agent outputs with provenance.
6. User sees run history and proposal coverage in the GUI.

### 20.4 Review records

1. User opens a review queue.
2. Product shows blind review by default.
3. User labels, explains, and optionally reveals agent proposals.
4. Product records reveal state and review timing metadata.
5. User submits or saves draft.

### 20.5 Adjudicate disagreements

1. User opens the adjudication queue.
2. Product surfaces disagreements, policy, history, and agent context.
3. User chooses preserve, resolve, downgrade, or exclude.
4. Product records adjudication and updates readiness views.

### 20.6 Curate and export a slice

1. User filters or mines a subset.
2. Product shows blockers, quality signals, and provenance.
3. User packages an export.
4. Product runs validation and release checks.
5. User approves release bundle.

## 21. Failure Modes And Recovery

The PRD must define failure behavior, not leave it implicit.

### 21.1 Filesystem drift

If files change outside the app:

- detect it,
- mark affected views stale,
- and offer selective or full reindex.

### 21.2 Plugin mismatch

If a plugin version no longer matches project config:

- warn immediately,
- degrade non-critical screens gracefully,
- and block destructive writes until resolved.

### 21.3 Export failure

If export packaging fails:

- preserve previous canonical files,
- preserve draft state,
- show exact failure,
- and allow retry after fix.

### 21.4 Agent failure

If an agent run fails:

- record partial status,
- preserve completed outputs separately,
- and make reruns explicit rather than silent.

### 21.5 Database reset

If the local DB is reset:

- canonical project files remain intact,
- the app can rebuild its state from files,
- and draft-only state is clearly identified as locally ephemeral.

### 21.6 Interrupted job recovery

If the app or machine stops during a job:

- the job run must resume as `failed` or `interrupted`, not disappear,
- partial machine-authored outputs must be marked incomplete,
- and the user must be able to inspect logs and explicitly rerun or clean up.

### 21.7 Interrupted jobs and partial outputs

If a job or export is interrupted mid-run, the product must:

- mark the run as interrupted,
- keep partial outputs quarantined from canonical targets,
- expose cleanup or retry actions,
- and avoid treating quarantined partial outputs as valid artifacts.

## 22. Verification Requirements

The product must ship with a clear verification contract.

### 22.1 Required verification areas

- bootstrap and reindex correctness,
- plugin loading correctness,
- provider and model profile switching correctness,
- OpenAI-compatible adapter correctness,
- OpenRouter adapter correctness,
- Ollama adapter correctness,
- review event append-only guarantees,
- blind-review and AI-reveal tracking,
- adjudication persistence,
- export determinism,
- validation and release reporting,
- and drift recovery behavior.

### 22.2 Verification modes

The repo should include:

- Python unit tests (pytest) for core domain logic, workflow engine, queue management, review state machine, prompt versioning, label mapping, and schema validation,
- Python integration tests for SQLite operations, file I/O, plugin loading, and agent run orchestration,
- FastAPI endpoint tests using httpx.AsyncClient,
- Frontend component tests (vitest plus React Testing Library) for individual React components,
- Frontend integration tests using MSW (Mock Service Worker) to mock API endpoints,
- Playwright end-to-end tests for critical user flows,
- parameterized workflow engine tests using approximately 15 workflow fixture YAML files covering linear, branching, looping (all four termination types), nested loops, parallel, conditional, error cases, and all six built-in templates,
- provider adapter tests using recorded response cassettes (VCR-style) by default with an optional --live-providers flag for real API calls using developer keys,
- representative fixture projects,
- and export determinism snapshot tests.

### 22.3 Required fixture projects

The repo should include fixture projects that cover at minimum:

- plain text classification or scoring,
- conversation-window review,
- trajectory or multi-step records,
- and a plugin-mismatch or drift-recovery case.

### 22.4 Reference-app verification

The DePolarize reference app must prove that the generic core supports:

- turn-level text review,
- conversation-window review,
- trajectory-style records,
- and project-specific release gates.

### 22.5 Verification commands

The repo should ship one documented command path for:

- bootstrap verification,
- plugin compatibility verification,
- UI smoke verification,
- and export determinism verification.

### 22.5.1 CI quality gates

The CI pipeline must enforce these gates before merging:

- all Python tests pass (pytest),
- all frontend tests pass (vitest),
- Python lint and format pass (ruff),
- TypeScript compiles without errors (tsc),
- OpenAPI spec is in sync with the auto-generated TypeScript client,
- and E2E critical paths pass (Playwright).

The CI pipeline should generate but not gate on:

- Python coverage report,
- frontend coverage report,
- bundle size report,
- and Lighthouse accessibility score.

### 22.5.2 Tauri desktop testing

Tauri-specific features (native file dialogs, system tray, auto-update, sleep and wake behavior) should be tested manually before releases using a documented smoke test checklist. Automated Playwright E2E tests run against the web app at localhost rather than inside the Tauri shell.

### 22.6 Plugin SDK verification

The core repository must test that:

- a plugin can be installed into a clean environment,
- a plugin can register task types and screens without patching core code,
- incompatible plugin versions fail clearly,
- and a fixture workspace can round-trip through bootstrap, review, export, and validation using only documented plugin APIs.

## 23. Performance And Interaction Constraints

The GUI should feel fast on a local laptop.

Required constraints:

- workspace home should open in under 2 seconds on a warm cache for a normal local project,
- dataset explorer transitions should feel immediate for indexed views,
- review next-record navigation should be sub-second,
- long-running jobs must stream progress,
- and the UI must remain usable while indexing or agent runs occur in background.

Exact benchmarks can evolve, but operational responsiveness is part of product quality, not a later optimization.

### 23.1 Performance targets with dataset sizes

- Workspace home: under 2 seconds on warm cache for projects up to 100,000 records.
- Dataset explorer page load: under 1 second for indexed views up to 100,000 records, with virtual scrolling for larger datasets.
- Record detail (360 view): under 500ms for a single record with up to 50 review events and 10 agent outputs.
- Review next-record navigation: under 300ms.
- Workflow builder: responsive drag-and-drop for workflows with up to 50 steps.
- Agent run start: under 2 seconds from click to first SSE progress event.
- Export packaging: scales linearly, targeting 10,000 records per minute for JSONL.

## 24. Release Definition

### 24.1 Ship requirements

- Tauri v2 native desktop app with React frontend
- composable workflow engine with GUI builder (React Flow) and YAML output
- six built-in workflow templates
- generic workspace bootstrap
- file-backed artifact and record indexing
- full data management hub: dataset catalog, record inspector (360-view), dataset analytics
- dataset snapshots (user-triggered, full state)
- pre-label import with visual label mapping editor
- data sources: local files, HuggingFace, Label Studio, Argilla, Prodigy import
- task schema definition
- provider and model profile management with auto-detection
- first-party provider adapters for OpenAI-compatible endpoints, OpenRouter, Ollama, and Anthropic
- multi-model comparison runs with per-record and aggregate views
- cost estimation and tracking
- agent feedback loop: prompt refinement from human corrections, active learning queue priority
- multi-signal agent confidence scoring
- agent performance analytics dashboard
- file-backed YAML prompt templates with auto-versioning
- structured output enforcement with provider-native plus fallback
- at least one text review task plugin
- at least one chat or conversation review plugin
- agent proposal runs with provenance
- workflow screen and mission control screen with SSE real-time updates
- supportive AI guide using user-configured providers
- full keyboard-driven review screen with vim-style shortcuts
- blind review plus AI reveal tracking
- overlap review and adjudication
- quality dashboard
- dataset filtering and subset export
- exports in JSONL, Parquet, CSV, and HuggingFace Hub push
- validation and export bundle flow
- plugin runtime with JSON schema UI plus optional React component overrides
- multi-reviewer support (concurrent sessions, queue locking)
- graceful offline degradation
- DePolarize reference app
- pairwise ranking plugin
- extraction plugin
- PDF or document review plugin
- richer curation views such as clustering and disagreement mining
- native OS integration features (system notifications, file associations, deep linking)

### 24.2 Out of scope

- remote collaboration
- hosted deployments
- enterprise auth
- multimodal image or video-heavy workflows
- plugin marketplace

### 24.3 Explicit exclusions

The product should not attempt:

- universal support for every labeling pattern,
- broad parity with hosted annotation suites,
- automatic conflict resolution across arbitrary plugin upgrades,
- or a cloud coordination layer.

## 25. Open-Source Repository Strategy

This should not be open-sourced directly as `DePolarize Workbench`.

It should be structured as:

- one generic OSS core repo,
- one first-party DePolarize reference plugin or reference app package,
- and optional later example projects for other data programs.

### 25.1 Why this split matters

- broader audience,
- cleaner architecture,
- less project-specific baggage,
- better contributor story,
- and better long-term adoption odds.

### 25.2 Initial repository structure

Suggested top-level shape:

- `packages/molabel-core/` — core library (Python)
- `packages/molabel-app/` — FastAPI backend (Python)
- `packages/molabel-plugins/` — built-in plugins (Python)
- `packages/molabel-depolarize/` — DePolarize reference app (Python)
- `frontend/` — React frontend (TypeScript)
- `src-tauri/` — Tauri desktop shell (Rust)
- `docs/`
- `tests/`
- `fixtures/`

### 25.3 Extraction mapping from the current DePolarize workbench

The initial extraction should map existing concepts as follows:

- current workspace, artifact, dataset, and record models into generic core storage and indexing,
- current reviewer, review task, review event, AI suggestion, and adjudication models into generic review and agent modules,
- current jobs and validation models into generic job and validation modules,
- current explorer, catalog, review, adjudication, quality, and release surfaces into generic UI primitives,
- and current path-based bootstrap inference into the DePolarize reference-app plugin.

The first extraction should prefer wrapping and renaming over rewriting behavior from scratch.

### 25.4 Developer experience requirements

The new repo must be easy for contributors to run and extend.

Required DX standards:

- one documented bootstrap command for local development,
- one documented command to run the GUI in dev mode,
- one documented command to run tests,
- one plugin scaffold path,
- fixture workspaces for local UI and export testing,
- and a short “build a plugin” guide in the repo.

The repo should optimize for a contributor being able to:

1. clone,
2. install,
3. run the app,
4. open a fixture project,
5. make a plugin change,
6. and verify it locally in under 30 minutes.

### 25.5 Packaging recommendation

The first OSS repo should ship as a Python monorepo with:

- one main local web application package,
- one core library,
- built-in plugins for generic task types,
- and a first-party DePolarize reference package.

This keeps transfer complexity lower than splitting into multiple repositories too early.

If the project grows, separate repositories can come later for community plugins.

## 26. DePolarize Reference App Scope

The DePolarize package should prove the generic product can handle:

- Asset A turn-level labeling,
- Asset B context-window review,
- Asset C decision-point or trajectory review,
- YAML manifest-backed governance,
- promotion-style readiness checks,
- and release validation surfaces.

It should add project-specific:

- schemas,
- views,
- handbooks and policy links,
- export formats,
- and readiness dashboards.

### 26.1 What stays out of core

The DePolarize reference package, not the OSS core, should own:

- asset-specific label semantics,
- project-specific path inference rules,
- project-specific manifests and governance meanings,
- project-specific jobs and export paths,
- policy copy,
- and domain-specific readiness logic.

That split must remain explicit or the OSS repo will collapse back into a DePolarize-specific application.

## 27. Risks

### 27.1 Becoming too broad

Risk:
the product becomes a vague “AI data platform” instead of a sharp local workbench.

Mitigation:
hold to the specific lifecycle defined here and ship only the minimum plugin set that proves the thesis.

### 27.2 Recreating generic labeling tools badly

Risk:
the product chases parity with annotation platforms instead of differentiating.

Mitigation:
keep the wedge on local-first data operations, agents, human review governance, and release control.

### 27.3 Hidden-state drift

Risk:
SQLite becomes secret truth.

Mitigation:
keep canonical files explicit, documented, and recoverable.

### 27.4 Plugin sprawl

Risk:
plugins become ad hoc and incompatible.

Mitigation:
define a strict plugin contract and compatibility model early.

## 28. Final Recommendation

This should be pursued as a standalone open-source product.

The right product is:

- GUI-first,
- local-first,
- modular,
- provider-agnostic,
- file-backed,
- agent-aware,
- human-in-the-loop,
- and designed for the full data lifecycle from intake to release.

The right strategy is:

- extract a generic OSS core,
- ship DePolarize as the first reference implementation,
- and win on the category that existing OSS tools do not own cleanly:
  local-first agentic data operations with human review, adjudication, curation, and release control.

## 29. Compact Ship Checklist

The PRD should be considered implementation-ready only if all of the following are true:

- the app ships as a Tauri v2 desktop application with React frontend and FastAPI backend,
- the composable workflow engine supports all six built-in templates including loops and conditionals,
- the GUI workflow builder (React Flow) can create, edit, and execute workflows without editing YAML manually,
- the new repo contains a generic core that starts without DePolarize internals,
- the repo contains a documented plugin SDK contract including JSON schema UI and optional React component overrides,
- the repo contains a documented workspace manifest contract,
- the repo contains a documented provider and model profile contract,
- provider auto-detection discovers available providers on startup,
- multi-model comparison runs work with per-record and aggregate views,
- the agent feedback loop generates prompt refinements from human corrections,
- active learning queue priority uses multi-signal confidence scoring,
- the agent performance dashboard shows accuracy, trends, error patterns, and cost,
- the data management hub includes dataset catalog, record inspector (360-view), and dataset analytics,
- dataset snapshots capture and compare full state,
- pre-label import with label mapping works for external annotation sources,
- the GUI can bootstrap a workspace, build workflows, explore data, run agents, review, adjudicate, curate, export, and validate without dropping to the shell,
- the review screen is fully keyboard-driven,
- model providers can be switched without redefining project workflows,
- multiple concurrent reviewers can work through the same queue without conflicts,
- review events are append-only and AI reveal state is preserved,
- canonical writes are deterministic, conflict-aware, and recoverable,
- exports support JSONL, Parquet, CSV, and HuggingFace Hub push,
- cost estimation and tracking works across providers,
- the system degrades gracefully when offline,
- CI enforces all quality gates (Python tests, frontend tests, lint, type-check, OpenAPI sync, E2E),
- at least one non-DePolarize example plugin exists,
- and the DePolarize reference app runs successfully on the extracted core.

# MoLabel Product Requirements Document

Date: 2026-03-27
Status: Draft
Document type: Canonical product direction
Repository: MoLabel

## 1. Executive Summary

MoLabel is a local-first, agent-operable data operations workbench for labeling, review, adjudication, data cleanup, quality control, export preparation, and release management.

The product is no longer GUI-first.

The primary operating surface is:

- the `molabel` CLI,
- the backend REST and SSE API behind that CLI,
- and bundled agent skills that teach coding agents how to operate the system safely.

The GUI remains important, but its role is different:

- manual operation for users who do not want heavy AI involvement,
- visual inspection of data and workflow state,
- human review and adjudication,
- and observability into what agents changed, why, and with what quality.

MoLabel should be usable end to end by an external agent such as Codex CLI while still remaining fully operable by a human through the GUI.

## 2. Product Thesis

The strongest version of MoLabel is not “a labeling app with an assistant.”

It is:

- a file-canonical data workbench,
- a safe operating layer for external agents,
- a human-in-the-loop review and adjudication system,
- and a benchmarkable environment for testing how well agents handle messy research data workflows.

The product wins if an agent can take a project from messy source data to reviewed, auditable, exportable outputs while humans retain authority over corrections, adjudication, and release decisions.

## 3. Why This Product Should Exist

Open-source tools exist for annotation, dataset browsing, pipeline execution, and synthetic data generation.

The missing combination is:

- local-first operation,
- file-canonical project state,
- first-class external agent operation,
- full human review and adjudication,
- strong data-management workflows,
- and benchmarkable end-to-end evaluation of agent performance on real project structures.

MoLabel should fill that gap.

## 4. Product Positioning

MoLabel should not be pitched as:

- another annotation tool,
- a chat assistant inside a desktop app,
- or a GUI wrapper around a hidden automation stack.

MoLabel should be pitched as:

- an agent-operable data operations platform,
- a local-first control plane for research labeling and dataset preparation,
- and a human-governed review environment for AI-driven data work.

## 5. Primary Actors

MoLabel has three primary actors:

### 5.1 External Agent Operator

Examples:

- Codex CLI,
- Claude Code,
- other coding agents that can run shell commands and inspect structured output.

Responsibilities:

- bootstrap or open a workspace,
- inspect canonical artifacts,
- normalize and prepare data,
- run labeling and comparison workflows,
- inspect quality signals,
- prepare exports and releases,
- and respond to benchmark and evaluation loops.

### 5.2 Human Authority

Responsibilities:

- define schemas, prompts, policies, and release criteria,
- review or correct labels,
- adjudicate disagreements,
- approve or reject risky changes,
- and overrule both agents and other humans when needed.

### 5.3 Manual GUI Operator

This actor is not secondary in capability.
It is secondary in product center of gravity.

Users who prefer manual operation must still be able to complete the full workflow through the GUI without requiring an external agent.

## 6. Product Surfaces

### 6.1 Primary Surface: CLI

The `molabel` CLI is the canonical operator interface for agents.

It must be:

- local-first,
- path-aware,
- file-aware,
- JSON-first for structured reads,
- NDJSON-first for long-running streams,
- deterministic in exit codes and error envelopes,
- and safe for mutating canonical artifacts.

### 6.2 Primary Machine Contract: Backend API

The backend remains the canonical business-logic layer.

The CLI operates through:

- existing `/api/v1/*` routes,
- additive `/api/v1/cli/*` routes,
- and SSE event streams for long-running and observable operations.

The product does not expose a separate first-class Python SDK at this stage.

### 6.3 Secondary Surface: GUI

The GUI is the control room.

It must excel at:

- manual data exploration,
- manual task setup,
- human review,
- adjudication,
- quality inspection,
- workflow observability,
- and understanding what the agent did.

The GUI is not the product's primary operating identity.

## 7. Core Product Principles

### 7.1 Agent-Operable By Default

Every important workflow should be executable by an external agent through the CLI and backend API without private knowledge of internals.

### 7.2 Human Authority Is Explicit

Agents can propose, prepare, run, and summarize.
Humans retain authority over adjudication, policy, and release decisions unless a workflow explicitly encodes a different rule.

### 7.3 Manual Completeness

Everything important must still be manually operable in the GUI.
The product cannot strand non-agent users.

### 7.4 Local-First And File-Canonical

Canonical project state lives on disk.
The database stores operational state, indexes, and derived views.
Human-authored files must not be silently overwritten.

### 7.5 Deterministic Machine Interfaces

Agents need stable contracts.
CLI commands, event streams, manifests, and artifact writes must be machine-readable, explicit, and safe.

### 7.6 Provider Agnosticism

The operating harness may be Codex CLI, but the labeling model itself remains provider-configurable.
The current labeling engine used in MoLabel is MiniMax 2.7 through the
Anthropic-compatible adapter path.
Primary documentation, benchmark fixtures, and test harnesses should state that
explicitly while the implementation remains provider-configurable underneath.

### 7.7 Auditability Over Automation Theater

The product should make it easy to see:

- what changed,
- who or what changed it,
- what quality signals exist,
- and where human review intervened.

## 8. What MoLabel Must Handle End To End

MoLabel must support the full lifecycle:

1. open or bootstrap a workspace,
2. ingest messy source data,
3. normalize and structure that data,
4. define task schemas and labeling policy,
5. run one or more labeling agents,
6. compare agent outputs when useful,
7. route hard or risky cases to human review,
8. support human correction and human-from-scratch labeling,
9. detect and resolve disagreement through adjudication,
10. measure quality, calibration, and failure modes,
11. curate, subset, and package outputs,
12. validate releases and preserve traceability.

## 9. Assistant Removal

The in-app assistant is removed from the product thesis.

MoLabel is not centered on an internal assistant panel that narrates the workflow.
Instead, the core AI story is:

- external agents operate the system,
- bundled skills teach them how,
- and the GUI lets humans inspect and control the results.

Legacy assistant endpoints or UI can remain temporarily during migration, but they are not part of the intended product direction.

## 10. Agent Skills

MoLabel should ship skills that are specific to the product rather than generic shell guidance.

Those skills must teach agents how to:

- detect the current workspace safely,
- inspect the command manifest,
- read canonical artifacts before editing,
- write canonical artifacts with conflict checks,
- run workflows and monitor event streams,
- inspect review and adjudication state,
- compare outputs against gold labels,
- and summarize where human intervention is required.

The reference harness is Codex CLI.
The skills should still be general enough to extend to other coding agents later.

## 11. Benchmark And Evaluation Program

Benchmarking is not optional.
It is part of the product definition.

MoLabel must ship benchmark-grade sample projects that let us evaluate how well an agent can:

- clean messy data,
- apply rubrics consistently,
- detect uncertainty and disagreement,
- respond to bad human labels,
- handle multi-stage workflows,
- and preserve auditability while doing so.

All major benchmark families should be designed, not just one initial benchmark.

Required benchmark families:

- messy text classification,
- chat and conversation review,
- structured document extraction,
- pairwise preference or ranking,
- multi-label taxonomy work,
- and at least one complex multi-stage research project that combines multiple layers of labeling, review, adjudication, and data repair.

Each benchmark project should include:

- raw messy source data,
- normalized target shape,
- task schemas and workflow YAML,
- gold labels,
- gold review outcomes,
- simulated human labels,
- simulated human review decisions,
- intentionally obvious human mistakes in some scenarios,
- and expected evaluation outputs.

## 12. Research-Oriented Agent Strengths

MoLabel should lean into the strengths of modern agents and LLMs:

- high-throughput first-pass structuring,
- rubric application when schemas and examples are explicit,
- iterative improvement through correction loops,
- triage of ambiguous or risky items,
- and artifact-aware operation when state is exposed through files and stable machine interfaces.

MoLabel should also explicitly design around their weaknesses:

- hallucination under underspecified rubrics,
- brittle handling of messy edge cases without normalization,
- poor confidence calibration without gold labels,
- and over-automation risk when human gates are weak.

## 13. Non-Goals

MoLabel should not:

- reintroduce a central in-app assistant as the product centerpiece,
- hide canonical project state behind GUI-only actions,
- require private internal APIs for agent operation,
- collapse human review and adjudication into opaque automation,
- or optimize only for benchmark demos while neglecting manual usability.

## 14. Acceptance Criteria

MoLabel meets this direction when all of the following are true:

- Codex CLI can operate representative MoLabel projects end to end through the public CLI and backend API.
- The CLI surface is stable enough to be documented through a manifest and bundled skills.
- The GUI remains sufficient for full manual workflow completion.
- Benchmark projects exist across all required task families.
- Benchmarks can compare agent outputs against gold labels and against simulated human stages.
- The system can expose cases where the human is wrong, the agent is wrong, or both are inconsistent.
- Quality, provenance, and audit trails remain visible throughout the workflow.

## 15. Priority Workstreams

The near-term product work should be prioritized in this order:

1. CLI completeness and operator-safe machine interfaces.
2. Bundled Codex-first MoLabel skills and command manifests.
3. Benchmark-grade sample projects and evaluation loops.
4. Agent-observable workflow, review, adjudication, and quality surfaces.
5. GUI refinement as control room, manual fallback, and inspection layer.

## 16. Immediate Documentation Consequences

The following docs must align with this PRD:

- `docs/architecture/ai-assistant.md` should become an agent-operations architecture doc rather than an assistant doc.
- `docs/prd/ux-and-ai-strategy.md` should describe CLI-primary operation and GUI-as-control-room UX.
- implementation sequencing should prioritize CLI completeness, agent skills, and benchmark fixtures ahead of further assistant-style GUI work.

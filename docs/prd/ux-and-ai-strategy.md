# MoLabel UX And Agent Operations Strategy

Date: 2026-03-27
Status: Draft
Related PRD: [`agentic-data-operations-workbench-prd.md`](./agentic-data-operations-workbench-prd.md)

## 1. Purpose

This document explains how MoLabel should feel after the shift to an agent-first, CLI-primary product.

The key change is simple:

- the CLI is the primary operating surface for agents,
- the backend API is the execution contract behind it,
- and the GUI is the manual control room and observability layer.

MoLabel should no longer feel like a GUI app with an assistant bolted on.
It should feel like a serious data-work system that both agents and humans can operate, with the GUI excelling at visibility and human judgment.

## 2. Product Experience Model

### 2.1 CLI-Primary For Agents

External agents should be able to:

- find the workspace,
- inspect current project state,
- read and write canonical artifacts safely,
- run workflows,
- inspect review and adjudication state,
- observe quality signals,
- and prepare exports and releases.

The UX requirement here is not visual polish.
It is contract clarity:

- stable commands,
- stable JSON output,
- stable event streams,
- and explicit errors.

### 2.2 GUI As Control Room

The GUI should be optimized for:

- seeing the data,
- seeing workflow progress,
- seeing what the agent changed,
- performing manual review,
- adjudicating disagreement,
- and stepping in when automation is wrong.

The GUI is where humans understand the project, not where the core agent story begins.

### 2.3 Manual Completeness

Users who do not want heavy AI involvement must still be able to do everything manually through the GUI.

That includes:

- importing and cleaning data,
- defining task schemas,
- labeling manually,
- reviewing and adjudicating,
- running quality checks,
- and exporting final outputs.

## 3. No In-App Assistant As Primary UX

The in-app assistant is removed from the primary product story.

The GUI should not depend on:

- an assistant panel as the main guide,
- conversational explanations as the primary workflow mechanism,
- or a narrator model sitting between the user and the real project state.

Where context or explanations are useful, the system should prefer:

- explicit workflow status,
- visible blockers,
- structured run summaries,
- and inspectable provenance.

## 4. Recommended GUI Mental Model

The GUI should use three overlapping mental models.

### 4.1 Workspace Model

Shows:

- what data exists,
- what schemas and workflows exist,
- what providers and profiles are configured,
- what artifacts are canonical,
- and what the current project health is.

### 4.2 Process Model

Shows:

- what stage the project is in,
- what is blocked,
- what requires human action,
- what the agent last did,
- and what the next useful step is.

### 4.3 Evidence Model

Shows:

- labels,
- agent outputs,
- human review events,
- adjudication history,
- confidence and quality signals,
- and data provenance.

This third model becomes more important in an agent-first system because users need to judge the agent's work, not just complete form fields.

## 5. Screen Strategy

The GUI screen model still works, but the emphasis changes.

### 5.1 Home

Purpose:
the fastest answer to:

- what state is the project in,
- what did the agent do recently,
- what is blocked,
- and what requires human attention now.

### 5.2 Workflow

Purpose:
show the end-to-end lifecycle as an observable process map.

Must make it obvious:

- which steps were agent-run,
- which are waiting on humans,
- what failed,
- and what artifacts or outputs each stage produced.

### 5.3 Data

Purpose:
inspect messy source material, cleaned forms, schema projections, and lineage.

### 5.4 Tasks

Purpose:
define rubrics, task schemas, review policy, overlap rules, adjudication policy, and export mappings.

### 5.5 Agents

Purpose:
inspect agent runs, compare models, see uncertainty, and understand failure patterns.

This is not a place to chat with an assistant.
It is a place to inspect real operational behavior.

### 5.6 Review

Purpose:
help humans finish review quickly and clearly.

### 5.7 Adjudication

Purpose:
resolve disagreements between:

- multiple humans,
- humans and agents,
- or conflicting workflow outputs.

### 5.8 Quality

Purpose:
show whether the project is trustworthy enough to move forward.

### 5.9 Exports And Releases

Purpose:
package outputs and make approval decisions with evidence.

## 6. CLI UX Requirements

The CLI is part of the product UX, not just a backend tool.

It should optimize for agent operation by default:

- `--json` as the default mental model,
- NDJSON for streaming operations,
- deterministic exit behavior,
- strong manifest and help output,
- safe artifact read, diff, and write flows,
- and commands that map cleanly to project concepts instead of generic CRUD.

## 7. Benchmark UX Requirements

Benchmark projects should feel like real project work, not toy examples.

The UX must support seeing how the system behaves when:

- source data is messy,
- a rubric is layered or ambiguous,
- multiple review passes are required,
- a human is obviously wrong,
- an agent is obviously wrong,
- and adjudication must reconcile those failures.

The GUI should make these cases legible.
The CLI should make them automatable.

## 8. Research Project Fit

This product direction is especially strong for research-style data work because those projects often require:

- messy source cleanup,
- iterative schema refinement,
- multiple rounds of labeling,
- explicit review and adjudication,
- provenance,
- and exportable, auditable outputs.

MoLabel should therefore optimize for:

- hard cases over toy happy paths,
- traceability over hidden automation,
- and benchmarkability over vague claims of “AI assistance.”

## 9. Success Criteria

The UX strategy is working when:

- agents can operate the system end to end through the CLI,
- humans can understand what the agent did without guessing,
- manual users can still complete the same work in the GUI,
- and benchmark projects clearly expose where human or agent judgment breaks down.

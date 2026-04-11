# Agent Operations Architecture

Date: 2026-03-27
Status: Draft
Related: `docs/prd/agentic-data-operations-workbench-prd.md`

## Overview

This document replaces the old in-app assistant architecture direction.

MoLabel is no longer centered on a supportive assistant panel inside the app.
The product now assumes that an external agent operates the system through the CLI and backend API, while humans use the GUI for manual work, inspection, review, adjudication, and approval.

The file path is retained for continuity, but the architectural role has changed.

## Primary Operating Model

MoLabel now uses this operating model:

1. An external agent operates the system through `molabel`.
2. The CLI talks to backend REST and SSE endpoints.
3. The backend owns business logic, workflow execution, state transitions, and safe writes.
4. Canonical project artifacts remain on disk.
5. Humans inspect, review, correct, adjudicate, and approve through the GUI or equivalent explicit workflows.

## Core Architectural Rule

The public agent contract is:

- `molabel` CLI,
- backend `/api/v1/*` and `/api/v1/cli/*` endpoints,
- SSE streams for long-running visibility,
- bundled agent skills and command manifests.

There is no first-class direct Python SDK in this phase.

## Actor Model

### External Agent

Examples:

- Codex CLI as the reference validation harness,
- other coding agents later.

Responsibilities:

- detect or bootstrap workspaces,
- inspect artifacts and manifests,
- run workflows,
- inspect quality signals,
- prepare exports and releases,
- and react to benchmark and evaluation feedback.

### Human Reviewer Or Operator

Responsibilities:

- configure policy and task schemas,
- review outputs,
- correct labels,
- adjudicate disagreements,
- and approve risky or release-affecting decisions.

### Labeling Model

The agent harness and the labeling model are separate concerns.

Examples:

- Codex CLI may be the operator,
- while Minimax 2.7 or another provider-backed model may do the actual labeling work.

This separation is intentional.

## Interface Layers

### CLI Layer

The CLI must be:

- JSON-first,
- explicit about workspace context,
- safe about canonical file writes,
- stable enough for agent automation,
- and able to expose long-running operations through machine-readable streams.

### Backend Layer

The backend remains the system of execution.

It is responsible for:

- workflow orchestration,
- queue creation and human-step waiting,
- review and adjudication state,
- artifact conflict checks,
- event emission,
- quality computation,
- export and release logic.

### GUI Layer

The GUI is the control room, not the primary AI surface.

It should specialize in:

- manual operation,
- data browsing,
- review and adjudication,
- workflow observability,
- provenance inspection,
- and understanding what the agent did.

## Context And Explainability

Removing the in-app assistant does not remove the need for context assembly.

MoLabel still needs machine-readable context for:

- workflow status,
- blockers,
- recent runs,
- queue state,
- record history,
- and quality signals.

That context should be exposed through structured CLI and backend surfaces rather than a chat-oriented assistant UX.

## Safety Boundaries

### Human-Authored Files

Canonical human-authored files must not be overwritten silently.

Mutating flows should use:

- explicit selectors,
- expected hashes or revisions,
- structured conflict responses,
- and audit trails.

### Human Authority

Agents may operate the system broadly, but they should not silently erase human authority in:

- adjudication,
- release approval,
- policy changes,
- or other high-impact governance actions.

### Explainable Automation

For every major action, the system should make it easy to answer:

- what changed,
- which command or workflow caused it,
- which model or agent acted,
- and what quality or confidence evidence exists.

## Legacy Assistant Migration

Existing assistant endpoints and UI components may remain in the codebase temporarily, but they are legacy from the old product direction.

Migration intent:

- do not invest further in assistant-first UX,
- prefer reusable context and status endpoints,
- and redirect AI-related product work into CLI, workflow, review, and evaluation capabilities.

## Architectural Priorities

The highest-priority architectural work after this shift is:

1. complete the CLI operator surface,
2. complete additive CLI-oriented backend endpoints,
3. improve event and status visibility for machine control loops,
4. enrich bundled skills and manifests,
5. add benchmark-grade projects for end-to-end evaluation.

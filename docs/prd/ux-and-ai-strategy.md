# Agentic Data Operations Workbench UX And AI Strategy

Date: 2026-03-22
Status: Companion strategy note
Related PRD: [`agentic-data-operations-workbench-prd.md`](./agentic-data-operations-workbench-prd.md)

## 0. Architecture Update Note

Since this strategy was written, the following major architectural decisions have been made:

- The frontend has moved from HTMX plus Jinja2 to React 19 plus TypeScript with shadcn/ui components.
- The app ships as a Tauri v2 native desktop application.
- The workflow lifecycle is now fully composable (user-defined DAGs) rather than a fixed 12-step sequence.
- An agent feedback loop has been added (prompt refinement from corrections plus active learning).
- Data management has been elevated to a full data hub with snapshots and label mapping.
- Multi-model comparison runs and provider auto-detection have been added.

See the ADRs in `docs/architecture/` and the updated PRD for full details. The UX recommendations below remain directionally valid but implementation references to HTMX should be read as React.

## 1. Why This Note Exists

The PRD now defines the product shape.
This note focuses on how to make the product:

- easier to understand from start to finish,
- more useful for non-expert operators,
- stronger in an agent-heavy tooling ecosystem,
- easier to switch across model providers and local runtimes,
- and more modular across very different labeling projects.

## 2. Repo-Grounded Findings

The current DePolarize workbench already proves several good instincts:

- the overview page already tells the user what to do next in plain language,
- the review surface already uses a stepper for triage, calibration, review, and export,
- the app already has separate surfaces for review, adjudication, quality, release, jobs, and manifests,
- and the data model already treats review events, AI suggestions, adjudications, jobs, validation runs, releases, and audit data as first-class objects.

The current weakness is not a lack of screens.
The weakness is that the product is still page-driven rather than process-driven.
Users can see many surfaces, but the workbench does not yet fully own the mental model of:

- where they are,
- what step they are in,
- what is complete,
- what remains,
- what is blocked,
- and what the best next action is.

## 3. The Most Important Product Upgrade

The biggest upgrade is to make the workbench own the workflow narrative.

The product should not feel like:

- files,
- routes,
- or feature tabs.

It should feel like:

- a guided operational process.

The user should always be able to answer five questions in under ten seconds:

1. What project am I in?
2. What phase am I in?
3. What is the next highest-value action?
4. What is blocked and why?
5. What happens after I complete this step?

## 4. The Right GUI Mental Model

The app should use three overlapping mental models:

### 4.1 Workspace model

This answers:

- what data exists,
- what plugins and task schemas are active,
- what model and runtime profiles are active,
- what jobs and validations are available,
- and what the current project health looks like.

### 4.2 Process model

This answers:

- what stage the work is in,
- what stage is next,
- and how work flows from intake to release.

This is the most important missing layer.

### 4.3 Queue model

This answers:

- what needs human attention right now,
- which items are pending,
- which items are risky,
- and who or what acted on them already.

## 5. Screen Model Recommendation

The current PRD is directionally right.
I would sharpen it into the following top-level screens:

- Home
- Workflow
- Data
- Tasks
- Agents
- Review
- Adjudication
- Quality
- Curation
- Exports
- Releases
- Plugins
- Mission Control
- Settings

### 5.1 Home

Purpose:
the single best answer to “what should I do now?”

Must show:

- project identity,
- active workflow stage,
- key counts,
- current blockers,
- pending human queues,
- recent agent runs,
- recent exports,
- and a strong primary action.

### 5.2 Workflow

Purpose:
the process map from start to finish.

This should be a dedicated screen, not just a status card.

Must show:

- the full lifecycle,
- current stage,
- completed stages,
- blocked stages,
- stage prerequisites,
- stage outputs,
- and stage owners.

This is where non-expert users learn the process.

### 5.3 Data

Purpose:
explore datasets, subsets, records, schemas, and provenance.

### 5.4 Tasks

Purpose:
configure task schemas, review flows, overlap rules, adjudication rules, and export mappings.

### 5.5 Agents

Purpose:
configure, run, monitor, and compare agent roles and outputs.

### 5.6 Review

Purpose:
finish human work quickly and consistently.

### 5.7 Adjudication

Purpose:
resolve or preserve disagreement with context.

### 5.8 Quality

Purpose:
explain reliability, drift, disagreement, throughput, and human versus agent deltas.

### 5.9 Curation

Purpose:
turn reviewed data into useful subsets, challenge sets, slices, and exports.

### 5.10 Exports and Releases

Purpose:
package outputs, validate them, and explain readiness.

## 6. Workflow UX: How To Make The Process Understandable

The workflow screen should be the backbone of the app.

Recommended lifecycle:

1. Attach or ingest data
2. Normalize and index
3. Define task schema
4. Run agents
5. Triage
6. Human review
7. Overlap review
8. Adjudication
9. Quality checks
10. Curation
11. Export packaging
12. Release validation

Each stage card should show:

- purpose,
- what inputs it needs,
- what output it creates,
- whether it is ready,
- whether it is blocked,
- estimated effort,
- and one recommended next action.

Each stage should also support an “Explain this step” action.

## 7. Queue Design Recommendations

Queues should be central to the product.
Users should not have to hunt for records.

### 7.1 Queue types

At minimum:

- triage queue,
- review queue,
- overlap queue,
- adjudication queue,
- edge-case queue,
- export-blocker queue,
- and validation-failure queue.

### 7.2 Queue behavior

Every queue should show:

- why an item is in the queue,
- what action is expected,
- what happens after completion,
- what priority the item has,
- and what context the user needs before acting.

### 7.3 Queue ergonomics

Queues should support:

- bulk actions,
- quick filters,
- saved views,
- resume where I left off,
- skip with reason,
- assign to me,
- and jump to most urgent.

### 7.4 Queue transparency

Each queue item should expose:

- source dataset,
- task schema version,
- agent suggestions present or absent,
- prior reviews,
- adjudication status,
- export impact,
- and any active blockers.

## 8. Explainability Surfaces

The app should explain both the data and the workflow.

### 8.1 Record-level explainability

For any record, the user should be able to see:

- why this item is in the queue,
- what the task is asking,
- what labels or rubric fields mean,
- what the agent suggested,
- whether the agent output is safe to view in blind mode,
- what prior humans did,
- and what will happen after submission.

### 8.2 Stage-level explainability

For any workflow stage, the user should be able to see:

- why this stage exists,
- whether it is optional or required,
- what will break if it is skipped,
- and what artifacts it will produce.

### 8.3 Export-level explainability

For any export or release bundle, the user should be able to see:

- which records are included,
- why they were included,
- which records were excluded,
- what validation checks passed,
- what checks failed,
- and what still blocks release.

## 9. The Supportive AI Assistant

This is one of the strongest ideas.
It should not be a generic chatbot bolted onto the side.

It should be a workflow-aware guide.

### 9.1 What it should do

The assistant should help the user understand:

- what this screen is for,
- what their current task is,
- what is blocked,
- what they have left to do,
- what the next best action is,
- and how to interpret system output.

### 9.2 What it should not do

It should not:

- replace human judgment silently,
- auto-hide process complexity,
- or obscure what files and outputs actually changed.

### 9.3 Best assistant modes

The assistant should have explicit modes:

- Guide mode
- Explain mode
- Operator mode
- Agent monitor mode
- Troubleshooting mode

Guide mode:
helps the user through the process.

Explain mode:
explains labels, steps, metrics, and outputs.

Operator mode:
helps run jobs, queues, exports, and validations.

Agent monitor mode:
explains what agents are doing and whether they succeeded.

Troubleshooting mode:
helps diagnose failed jobs, missing plugins, and drift conflicts.

### 9.4 Best assistant UI pattern

The assistant should live in the right-side inspector and command bar, not as a floating chat toy.

Recommended actions:

- “What am I doing on this screen?”
- “What should I do next?”
- “Why is this blocked?”
- “Explain this metric”
- “Summarize changes since yesterday”
- “Show me the items that need human review”
- “Explain why this export failed”

### 9.5 Best assistant data access

The assistant should be grounded in:

- workspace manifest,
- active task schema,
- active queue,
- recent job runs,
- validation reports,
- and audit history.

This is what makes it useful instead of generic.

## 10. External Agent Integration Strategy

The product should not try to become every agent runtime.
It should become the best place to supervise, compare, and operationalize agents.

### 10.1 What to build natively

Build natively:

- agent run registry,
- agent output normalization,
- agent status monitoring,
- queue generation from agent outputs,
- prompt and schema version tracking,
- and review visibility controls.

### 10.2 What to integrate rather than rebuild

Integrate rather than rebuild:

- coding-agent runtimes,
- external planning agents,
- generic MCP-connected tools,
- and project-specific local automations.

### 10.3 Best integration model

The right integration model is an adapter layer.

The workbench should treat external agents as worker providers with:

- provider identity,
- runtime type,
- capabilities,
- tool access profile,
- input contract,
- output contract,
- and monitoring hooks.

### 10.4 Good first integrations

Good targets include:

- Claude Code via MCP and project-level subagents
- OpenHands as a local or Docker-based runtime
- Aider as a repo-aware terminal assistant
- OpenCode-style MCP-enabled local agents

Why these matter:

- modern AI-native users already expect local agent workflows,
- they want their tool stack to stay composable,
- and they do not want to abandon existing agent tools just to use the workbench.

## 11. How The Supportive AI Should Work With External Agents

The assistant should not directly “be” the coding agent.
It should orchestrate and explain.

Better model:

- the workbench assistant is the narrator and supervisor,
- external agents are workers,
- humans remain decision-makers.

That gives the product a clean mental model:

- AI guide,
- AI workers,
- human authority.

## 12. Three Product Features That Would Make This Feel Native To The New AI World

### 12.1 Mission Control

A live operations view for:

- active agents,
- queued work,
- failed steps,
- waiting-for-human decisions,
- and release blockers.

This should feel like mission control, not a log dump.

### 12.2 Explain My Project

A guided mode that can answer:

- what this project is,
- how this workflow works,
- what the labels mean,
- what is done,
- and what remains.

This is especially valuable for new contributors.

### 12.3 Delegate This Step

For certain safe steps, the UI should offer:

- delegate normalization,
- delegate deduplication,
- delegate disagreement mining,
- delegate export preflight summarization,
- but not delegate final human truth decisions silently.

## 13. How To Keep Modularity Strong Without Becoming Vague

The product needs opinionated structure plus flexible plugins.

### 13.1 Make workflows composable but template-guided

The workflow structure should be composable per project but guided by strong templates.

Projects vary in:

- data type,
- task schema,
- review logic,
- export logic,
- validation logic,
- and workflow shape.

The product should ship opinionated templates that cover common patterns (quick agentic label, human-in-the-loop review, full quality pipeline, benchmark authority, agent comparison, iterative refinement) while allowing users to compose custom workflows from the full step type catalog. Templates provide the structure; the composable engine provides the flexibility. Projects should not vary in whether the product has a process at all — every project uses the workflow engine — but the specific steps, their order, and their branching logic are project-specific.

See ADR-003 for the full composable workflow engine design.

### 13.2 Let plugins customize the right layer

Plugins should own:

- record parsing,
- record rendering,
- task schema fields,
- label or rubric semantics,
- review form layout,
- adjudication logic,
- export serializer,
- validation checks,
- custom workflow step types,
- and workflow templates.

The core should own:

- workflow engine and execution model,
- navigation,
- queue semantics,
- agent run model,
- audit model,
- and writeback model.

### 13.3 Use project templates

Templates should exist for:

- text labeling project,
- chat review project,
- pairwise preference project,
- extraction project,
- rubric-scoring project,
- trajectory project,
- and reference-app project.

Templates will matter more than raw plugin flexibility for real usability.

## 14. Biggest Recommendations

If I had to prioritize the next upgrades, they would be:

1. Add a dedicated Workflow screen that explains the entire lifecycle.
2. Add a supportive AI guide grounded in workflow, queues, and validation state.
3. Turn queues into the main human work surface.
4. Add Mission Control for agent and job monitoring.
5. Keep external agent providers integrated through adapters, not baked into the core.
6. Add project templates so modularity feels usable, not abstract.
7. Make every stage explain its purpose, inputs, outputs, blockers, and next action.

## 15. Bottom Line

The product becomes much better when it stops behaving like a stack of tools and starts behaving like:

- a guided workflow system,
- a queue-driven human-in-the-loop workbench,
- and a supervisor for both human and agent work.

That is the right shape for the new AI world:

- agents do more work,
- humans supervise and adjudicate,
- and the GUI keeps the whole process understandable from intake to release.

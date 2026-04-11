# MoLabel Agent Benchmark And Evaluation Strategy

Date: 2026-03-27
Status: Draft
Related:

- `docs/prd/agentic-data-operations-workbench-prd.md`
- `docs/prd/ux-and-ai-strategy.md`
- `docs/research/grounded-benchmark-system.md`
- `docs/research/paper-backed-benchmark-candidates.md`
- `Documentation/plans/deep-planner/agent-first-repositioning-2026-03-27.md`

## Status Note

This document remains the product-direction draft for MoLabel benchmark and
evaluation work.

The current repo-specific grounded benchmark architecture, rebuild
recommendation, fixture contract, scoring split, and migration plan now live in:

- `docs/research/grounded-benchmark-system.md`
- `docs/research/paper-backed-benchmark-candidates.md`

That research document should be treated as the canonical system blueprint for
the grounded benchmark reset until this PRD is fully rewritten around it.

## 1. Purpose

MoLabel needs benchmark projects that prove an external agent can operate the system on real project shapes, not just toy examples.

These benchmarks must test:

- data cleanup,
- data management,
- labeling,
- human review,
- human-from-scratch labeling,
- adjudication,
- quality analysis,
- and end-to-end project operation through the CLI.

The reference harness is Codex CLI.
The current labeling engine in MoLabel is MiniMax 2.7 via the
Anthropic-compatible adapter path.
The architecture remains provider-configurable, but benchmark documentation and
test harnesses should name MiniMax 2.7 explicitly as the current engine under
test.

## 2. What The Benchmarks Must Prove

Each benchmark family should let us answer:

1. Can the agent understand the workspace and task setup?
2. Can it clean or normalize messy source data correctly?
3. Can it apply the rubric with acceptable accuracy?
4. Can it recognize uncertainty and route hard cases to review?
5. Can it behave sensibly when a simulated human is wrong?
6. Can it preserve auditability while doing all of the above?

## 3. Required Benchmark Families

All of these should be designed.

### 3.1 Messy Text Classification

Focus:

- noisy user text,
- inconsistent formatting,
- duplicates,
- partial metadata,
- ambiguous sentiment or stance cases.

### 3.2 Chat And Conversation Review

Focus:

- multi-turn structure,
- policy and safety review,
- assistant quality judgment,
- conflicting human judgments,
- moderation-like edge cases.

### 3.3 Structured Document Extraction

Focus:

- receipts,
- invoices,
- forms,
- OCR-style noise,
- inconsistent formatting,
- normalization before extraction.

### 3.4 Pairwise Preference Or Ranking

Focus:

- comparing two candidates,
- hidden confounders,
- obvious but instructive bad-human judgments,
- adjudication after disagreement.

### 3.5 Multi-Label Taxonomy Work

Focus:

- hierarchical or overlapping labels,
- class imbalance,
- rubric overlap,
- false confidence,
- label dependencies.

### 3.6 Complex Multi-Stage Research Project

Focus:

- multiple datasets or views,
- multiple rounds of cleanup and labeling,
- human labeling from scratch in some stages,
- human review of agent outputs in other stages,
- adjudication,
- release gating,
- and quality analysis across the whole workflow.

This benchmark is especially important because it best matches real research operations.

## 4. Required Assets Per Benchmark

Each grounded benchmark should include a canonical authority pack plus an
optional reference workspace:

- raw source files with deliberate messiness,
- normalized or target-shape expectations,
- task schema and workflow materials,
- prompt and policy files where relevant,
- gold labels,
- gold review outcomes,
- simulated human labeling events,
- simulated human review events,
- simulated adjudication-relevant conflicts,
- expected quality metrics or acceptance thresholds,
- and expected CLI-visible summaries.

The authority pack is canonical. The reference workspace is transitional and is
only there to support maintainer baselines and compatibility during migration.

## 5. Human Simulation Requirements

We need both kinds of simulated human behavior.

### 5.1 Gold-Standard Human Artifacts

These represent the trusted answer set:

- gold labels,
- gold review outcomes,
- gold adjudication outcomes.

### 5.2 Flawed Human Artifacts

These represent human mistakes that the system and the agent should be able to inspect and challenge.

Requirements:

- mistakes should sometimes be intentionally extreme and obvious,
- mistakes should exist in both labeling and review stages,
- and the benchmark should expose whether the agent notices, escalates, or incorrectly accepts the bad human input.

This is necessary to test:

- “human in the loop but wrong,”
- “agent disagrees with the human,”
- and “both are inconsistent and need adjudication.”

## 6. Data Messiness Requirements

Benchmarks should not start from already-clean task-ready data only.

They should include problems like:

- malformed records,
- nested or inconsistent structure,
- duplicate or near-duplicate records,
- inconsistent IDs,
- missing fields,
- contradictory metadata,
- mixed formatting,
- OCR-like corruption,
- and long-tail edge cases.

The goal is to test whether the agent can use MoLabel as a workbench, not just whether it can classify neat JSONL rows.

## 7. Evaluation Modes

Each benchmark should support multiple evaluation modes.

### 7.1 Label Quality Evaluation

Compare agent-produced labels against gold labels.

### 7.2 Workflow Operation Evaluation

Evaluate whether the agent:

- found the right commands,
- edited artifacts safely,
- used the workflow and review system correctly,
- and handled failures without corrupting project state.

Because MoLabel is explicitly an external-agent workbench, this operator layer
is not secondary. Codex-as-operator quality should be treated as a primary
benchmark surface alongside raw model accuracy.

### 7.3 Human-Interaction Evaluation

Evaluate whether the agent:

- routed difficult items,
- challenged obviously bad human inputs,
- preserved disagreement when appropriate,
- and avoided silently flattening review complexity.

### 7.4 Recovery Evaluation

Evaluate whether the agent can recover from:

- bad inputs,
- broken workflow assumptions,
- failed runs,
- partial failures,
- and confusing human decisions.

## 8. CLI-Driven Test Strategy

The benchmark system should be runnable through the CLI.

For grounded operator benchmarks, this must mean more than running a prepared
workspace. The benchmark should start from benchmark authority materials and
require Codex to construct the MoLabel project through the CLI.

At minimum, the evaluation loop should cover:

1. inspect the paper and benchmark authority materials,
2. inspect source artifacts and raw dataset shape,
3. bootstrap or create the workspace through the CLI,
4. create/import the dataset,
5. do cleanup, normalization, or slicing work,
6. create the task schema,
7. create prompts,
8. create or select the workflow,
9. run labeling or comparison workflows,
10. inspect quality and disagreement,
11. trigger or inspect human-review stages,
12. resolve or preserve disagreement,
13. produce exports or benchmark summaries.

The tests should verify both outcome correctness and operational correctness.

## 9. Repo Structure Recommendation

Recommended additions:

- benchmark authority packs under `fixtures/benchmarks-grounded/`
- raw dataset slices or download/bootstrap instructions in those authority packs
- gold and flawed-human artifacts stored as canonical benchmark authority files
- optional reference workspaces for maintainer debugging or baseline comparison
- CLI-oriented evaluation tests under `tests/e2e/` that create and operate projects from those authority packs end to end
- reusable benchmark scoring helpers for comparing labels, review paths, and adjudication decisions

## 10. Scoring Dimensions

Each benchmark should score at least these dimensions:

- label accuracy against gold,
- normalization correctness,
- disagreement detection quality,
- handling of wrong-human scenarios,
- adjudication behavior,
- workflow completion correctness,
- and auditability of resulting artifacts and events.

Operator-first grounded benchmarks should also score:

- use of public CLI-and-skill surfaces only,
- correct MiniMax 2.7 labeling-engine setup,
- data preparation correctness,
- task schema quality,
- prompt quality,
- workflow design quality,
- artifact integrity after operator actions,
- disagreement preservation quality,
- and a composite operator score that combines:
  - final MoLabel-operated label quality
  - operator-process discipline
  - project-construction quality
  - blocking failures for critical misuse such as bypassing public surfaces or
    damaging benchmark artifacts
- and wrong-human challenge quality.

## 11. Priority Order

All benchmark families are required, but the work should still be phased for delivery.

Recommended order:

1. establish the common benchmark workspace contract,
2. build one benchmark from each major task family at minimum viable depth,
3. add the complex multi-stage research benchmark,
4. deepen each benchmark with harder edge cases and richer human simulation,
5. wire the full set into CLI-driven regression runs.

## 12. Definition Of Success

The benchmark program is successful when:

- a Codex-driven run can start from paper and authority materials rather than a prepared project,
- a Codex-driven run can create and operate each benchmark project through the public CLI,
- MoLabel can compare resulting outputs against gold artifacts,
- the system can expose obvious bad-human cases cleanly,
- and the results are strong enough to guide real product iteration rather than anecdotal demos.

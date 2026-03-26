# Workflow Execution Specification

Date: 2026-03-23
Status: Draft
Related: PRD Section 15.0, ADR-003

> **Note:** All enum values and field definitions in this document must match the canonical data model (`data-model.md`). If there is a discrepancy, `data-model.md` is authoritative.

## Overview

ADR-003 defines *what* the composable workflow engine is: YAML-defined workflows composed from ~20 step types across 6 categories, with loops, conditionals, parallel execution, and breakpoints. The PRD defines the step type catalog and loop termination strategies.

This document specifies *how* workflows execute at runtime: the data flow between steps, the step execution lifecycle, error handling, concurrency rules, and persistence model. An engineer should be able to implement the workflow executor from this spec and ADR-003 together.

## Workflow Data Flow

### The Core Problem

Steps in a workflow are not isolated functions. An `agent_run` step needs to know which records to operate on (determined by a preceding `data_ingest` or `data_filter`). A `quality_check` step needs access to metrics produced by `agreement_analysis`. A `conditional` step needs to evaluate predicates against accumulated state.

### Design: Shared Workflow Context

Each workflow execution maintains a `WorkflowContext` that accumulates state as steps complete. Steps read from and write to this context. The context is the sole mechanism for inter-step data flow — steps never communicate directly.

```python
@dataclass
class WorkflowContext:
    workspace_id: str
    workflow_execution_id: str
    workflow_version: int

    # Dataset and record tracking
    datasets: dict[str, DatasetReference]      # dataset_id -> reference
    record_sets: dict[str, RecordSet]           # step_id -> records this step operated on
    active_record_set_id: str | None            # step_id of the "current" record set

    # Agent tracking
    agent_run_ids: list[str]                    # accumulated agent run IDs (ordered)
    agent_outputs: dict[str, AgentOutputRef]    # agent_run_id -> output reference

    # Human work tracking
    review_queue_ids: list[str]                 # accumulated queue IDs (ordered)
    adjudication_queue_ids: list[str]           # accumulated adjudication queue IDs

    # Quality metrics
    metrics: dict[str, float]                   # named metrics (agreement, coverage, etc.)

    # Step-level bookkeeping
    step_outputs: dict[str, StepOutput]         # step_id -> output summary
    step_timings: dict[str, StepTiming]         # step_id -> start/end timestamps

    # User-defined variables (for conditionals and templates)
    variables: dict[str, Any]                   # user-defined variables

    # Export and snapshot references
    export_bundle_ids: list[str]
    snapshot_ids: list[str]
```

The `active_record_set_id` field tracks which step's output records are the "current" working set. Steps that filter, sample, or deduplicate records update this field so downstream steps implicitly operate on the narrowed set.

### Step Type Input/Output/Side-Effect Catalog

Each step type defines exactly what it reads from `WorkflowContext`, what it writes back, and what database or filesystem side effects it produces.

#### Data Steps

**`data_ingest`**

- Inputs: `config.source` (file path, glob, or HuggingFace dataset reference), `config.loader_plugin` (optional, auto-detected if omitted)
- Outputs: writes `datasets[dataset_id]` with the new `DatasetReference`; writes `record_sets[step_id]` with all ingested record IDs; sets `active_record_set_id` to this step's ID
- Side effects: creates records in SQLite (`records` table), indexes source files, writes audit entry

**`data_normalize`**

- Inputs: reads `active_record_set_id` to determine which records to normalize; reads `config.schema_ref` for the target schema
- Outputs: writes `record_sets[step_id]` (same record IDs, now normalized); sets `active_record_set_id`; writes `step_outputs[step_id]` with normalization summary (records normalized, fields mapped, warnings)
- Side effects: updates record payloads in SQLite with normalized field values; writes audit entry

**`data_filter`**

- Inputs: reads `record_sets[active_record_set_id]` for the input records; reads `config.filter_expression` for the predicate
- Outputs: writes `record_sets[step_id]` with the filtered subset; sets `active_record_set_id`; writes `step_outputs[step_id]` with filter summary (input count, output count, filter expression)
- Side effects: none (filtering is a projection, not a mutation); writes audit entry

**`data_sample`**

- Inputs: reads `record_sets[active_record_set_id]`; reads `config.sample_strategy` (random, stratified, confidence_based, active_learning), `config.sample_size`, `config.seed` (optional)
- Outputs: writes `record_sets[step_id]` with the sampled subset; sets `active_record_set_id`; writes `step_outputs[step_id]` with sample summary
- Side effects: none; writes audit entry

**`data_deduplicate`**

- Inputs: reads `record_sets[active_record_set_id]`; reads `config.strategy` (exact, fuzzy, embedding), `config.threshold` (for fuzzy/embedding), `config.action` (remove or flag)
- Outputs: writes `record_sets[step_id]` with deduplicated records (or all records with duplicate flags); sets `active_record_set_id`; writes `step_outputs[step_id]` with dedup summary (duplicates found, clusters, action taken); writes `metrics["dedup.duplicate_rate"]`
- Side effects: if `config.action` is `remove`, marks duplicate records as excluded in SQLite; if `flag`, writes duplicate_cluster metadata to records; writes audit entry

#### Agent Steps

**`agent_run`**

- Inputs: reads `record_sets[active_record_set_id]` for target records; reads `config.prompt_ref` for the prompt template; reads `config.model` (or `config.model_profile_id`) for the model; reads `config.agent_role` (defaults to `proposer`)
- Outputs: appends to `agent_run_ids`; writes `agent_outputs[agent_run_id]`; writes `record_sets[step_id]` (same records, now with agent outputs attached); sets `active_record_set_id`; writes `step_outputs[step_id]` with run summary (records processed, success count, failure count, cost, latency); writes `metrics["agent.accuracy"]` if ground truth exists, `metrics["agent.coverage"]`, `metrics["agent.avg_confidence"]`
- Side effects: creates `agent_runs` row in SQLite; creates `agent_outputs` rows per record; creates `agent_events` rows for progress tracking; writes audit entry; acquires dataset-level indexing lock during execution

**`agent_compare`**

- Inputs: reads `record_sets[active_record_set_id]`; reads `config.models` (list of model profile IDs); reads `config.prompt_ref`
- Outputs: appends multiple entries to `agent_run_ids` (one per model); writes `agent_outputs` for each; writes `record_sets[step_id]`; sets `active_record_set_id`; writes `step_outputs[step_id]` with comparison summary (per-model accuracy, agreement matrix, cost comparison); writes `metrics["compare.inter_model_agreement"]`
- Side effects: creates multiple `agent_runs` rows; creates `agent_outputs` rows; writes audit entry; acquires dataset-level indexing lock

#### Human Steps

**`human_review`**

- Inputs: reads `record_sets[active_record_set_id]`; reads `config.sample_strategy` and `config.sample_size` (optional, to review a subset); reads `config.task_schema_id`; reads `config.breakpoint` (defaults to `true`)
- Outputs: appends to `review_queue_ids`; writes `record_sets[step_id]` (records that were reviewed); sets `active_record_set_id`; writes `step_outputs[step_id]` with review summary (reviewed count, accept/edit/reject counts, avg time per record); writes `metrics["review.coverage"]`, `metrics["review.accept_ai_rate"]`
- Side effects: creates `review_tasks` rows in SQLite; review events are written as reviewers complete work (append-only `review_events` table); emits SSE events for queue progress; step remains in `running` state until all queue items are completed or the operator advances
- Blocking: this step always pauses the workflow. It transitions from `running` to `waiting_for_human` and resumes only when the queue is fully processed or the operator explicitly advances.

**`human_triage`**

- Inputs: reads `record_sets[active_record_set_id]`; reads `config.task_schema_id`; reads `config.categories` (the triage buckets, e.g., ["pass", "fail", "needs_review"])
- Outputs: appends to `review_queue_ids`; writes `record_sets[step_id]` partitioned by triage outcome; sets `active_record_set_id` to the primary output category; writes `step_outputs[step_id]` with triage distribution; writes `variables["triage.<category>.count"]` for each category
- Side effects: creates `review_tasks` with triage-mode flag; writes review events as triage decisions are made
- Blocking: pauses for human work like `human_review`

**`human_calibration`**

- Inputs: reads `record_sets[active_record_set_id]`; reads `config.sample_size` (the shared calibration set size); reads `config.min_reviewers` (minimum reviewers who must complete calibration); reads `config.task_schema_id`
- Outputs: appends to `review_queue_ids`; writes `step_outputs[step_id]` with calibration results (per-reviewer agreement, discussion items); writes `metrics["calibration.agreement"]`, `metrics["calibration.reviewer_count"]`
- Side effects: creates a single shared calibration queue; each reviewer gets the same items; writes review events
- Blocking: pauses until `min_reviewers` have completed the calibration set

**`human_adjudication`**

- Inputs: reads `record_sets[active_record_set_id]` (typically filtered to disagreement records); reads `config.task_schema_id`; reads `config.adjudication_policy` (plugin reference)
- Outputs: appends to `adjudication_queue_ids`; writes `record_sets[step_id]` with adjudicated records; sets `active_record_set_id`; writes `step_outputs[step_id]` with adjudication summary (resolved, preserved_disagreement, excluded counts); writes `metrics["adjudication.resolution_rate"]`
- Side effects: creates `adjudications` rows in SQLite; writes audit entries for each resolution
- Blocking: pauses for human work

#### Quality Steps

**`quality_check`**

- Inputs: reads `record_sets[active_record_set_id]`; reads `metrics` for current quality state; reads `config.min_agreement`, `config.min_coverage`, `config.min_confidence` (optional thresholds)
- Outputs: writes `step_outputs[step_id]` with pass/fail result and details; writes `metrics["quality.agreement"]`, `metrics["quality.coverage"]`, `metrics["quality.confidence"]`; writes `variables["quality.passed"]` as boolean
- Side effects: creates a `validation_runs` row in SQLite with the quality report; writes audit entry
- Note: this step does NOT block the workflow — it writes metrics and a pass/fail signal. Use a `conditional` step after it to branch on the result, or a `gate` step to require human approval.

**`agreement_analysis`**

- Inputs: reads `record_sets[active_record_set_id]`; reads `review_queue_ids` to find review events; reads `agent_run_ids` to find agent outputs; reads `config.analysis_type` (inter_annotator, human_agent, or both)
- Outputs: writes `step_outputs[step_id]` with detailed agreement report (Cohen's kappa, Fleiss' kappa, per-field agreement, confusion matrices); writes `metrics["agreement.kappa"]`, `metrics["agreement.percent_agreement"]`, `metrics["agreement.human_agent_agreement"]`
- Side effects: stores agreement report as a derived artifact; writes audit entry

**`drift_detection`**

- Inputs: reads `record_sets[active_record_set_id]`; reads `config.reference_snapshot_id` or `config.reference_step_id` (what to compare against); reads `config.drift_threshold`
- Outputs: writes `step_outputs[step_id]` with drift report (distribution shift per field, new categories, missing categories); writes `metrics["drift.max_shift"]`, `metrics["drift.affected_fields"]`; writes `variables["drift.detected"]` as boolean
- Side effects: stores drift report; writes audit entry

#### Output Steps

**`export`**

- Inputs: reads `record_sets[active_record_set_id]`; reads `config.format` (jsonl, parquet, csv, huggingface); reads `config.destination` (path or HuggingFace repo); reads `config.include_fields` and `config.exclude_fields` (optional); reads `config.filters` (optional, e.g., minimum agreement)
- Outputs: appends to `export_bundle_ids`; writes `step_outputs[step_id]` with export summary (record count, file size, destination path)
- Side effects: writes export files to the configured destination using atomic write (temp file + rename); creates `export_bundles` row in SQLite; acquires output-namespace export lock; writes audit entry

**`snapshot`**

- Inputs: reads `record_sets[active_record_set_id]`; reads full `WorkflowContext` state; reads `config.snapshot_name`
- Outputs: appends to `snapshot_ids`; writes `step_outputs[step_id]` with snapshot reference
- Side effects: writes snapshot JSON file to `workbench/snapshots/`; creates snapshot metadata in SQLite; writes audit entry

**`release_validation`**

- Inputs: reads `record_sets[active_record_set_id]`; reads `metrics`; reads `config.validation_gates` (list of validation plugin references); reads `export_bundle_ids` for the bundles to validate
- Outputs: writes `step_outputs[step_id]` with validation report (per-gate pass/fail, blockers, warnings); writes `variables["release.ready"]` as boolean; writes `metrics["release.gates_passed"]`, `metrics["release.gates_total"]`
- Side effects: creates `validation_runs` rows for each gate; writes validation report file to `workbench/reports/`; writes audit entry

#### Control Steps

**`loop`**

- Inputs: reads `config.steps` (list of step IDs that form the loop body); reads `config.termination` (type, parameters, `max_iterations`); reads `WorkflowContext` for termination evaluation
- Outputs: writes `step_outputs[step_id]` with loop summary (iterations completed, termination reason); writes `variables["loop.<step_id>.iteration"]` with current iteration count
- Side effects: see "Loop Execution" section below; the loop body steps produce their own side effects each iteration
- Note: the loop step itself is a container — it orchestrates execution of its body steps, not a single atomic operation

**`conditional`**

- Inputs: reads `config.predicate` (expression evaluated against `WorkflowContext`); reads `config.then_steps` (step IDs for true branch); reads `config.else_steps` (optional, step IDs for false branch)
- Outputs: writes `step_outputs[step_id]` with branch taken and predicate result; writes `variables["conditional.<step_id>.branch"]` as `"then"` or `"else"`
- Side effects: marks non-taken branch steps as `skipped`; see "Conditional Branching" section

**`parallel`**

- Inputs: reads `config.steps` (list of step IDs to run concurrently); reads `config.fail_fast` (boolean, default `false`)
- Outputs: writes `step_outputs[step_id]` with parallel summary (per-child status, timing); merges child step outputs into `WorkflowContext` (last-write-wins for conflicting keys, with a warning in the step output)
- Side effects: child steps produce their own side effects; see "Parallel Step Execution" section

**`gate`**

- Inputs: reads `config.message` (displayed to operator); reads `config.require_reason` (boolean, whether operator must provide a reason to proceed)
- Outputs: writes `step_outputs[step_id]` with gate decision (approved/rejected), operator ID, reason, timestamp
- Side effects: writes audit entry with operator approval
- Blocking: always pauses. Requires explicit operator action in mission control to proceed or cancel.

## Step Execution Lifecycle

### State Machine

Each step execution goes through these states (matching the canonical `WorkflowStepExecutionStatus` enum in `data-model.md`):

```
pending → ready → running → completed
                         ↘ failed
                         ↘ waiting_for_human
                         ↘ waiting_for_gate
                         ↘ partially_failed
               ↘ waiting_for_breakpoint
               ↘ skipped

failed → retrying → running → ...
running → interrupted (on crash recovery)
running → cancelled / pending → cancelled / ready → cancelled
```

State definitions:

- **pending**: step is registered but has unmet predecessors
- **ready**: all predecessor steps are `completed` (or `skipped` if optional); step is eligible to execute
- **running**: step is actively executing (automated steps) or has created queues/work items (human steps before they pause)
- **waiting_for_human**: step has created review/triage/calibration/adjudication queues and is waiting for human work to complete
- **waiting_for_gate**: step requires explicit operator approval
- **waiting_for_breakpoint**: step has a user-configured breakpoint and is waiting for operator confirmation before transitioning to `running`
- **completed**: step finished successfully; outputs written to `WorkflowContext`
- **failed**: step encountered an error; execution pauses for operator intervention
- **skipped**: step was skipped because a conditional branch was not taken, or operator chose to skip a failed step, or all predecessors were skipped
- **retrying**: operator triggered a retry of a failed step; step re-executes from scratch with current `WorkflowContext`
- **partially_failed**: a parallel step where some children failed but others completed successfully
- **interrupted**: the application crashed while the step was running; detected and set during crash recovery on restart
- **cancelled**: step was cancelled by the operator (or as part of a workflow cancellation)

### Transition Rules

1. When a step completes, the executor evaluates all steps whose predecessor list includes the completed step. If all predecessors of a step are now `completed` or `skipped`, that step transitions to `ready`.

2. When a step transitions to `ready`, the executor starts it immediately (for automated steps) or transitions it to `running` then immediately to `waiting_for_human`/`waiting_for_gate` (for human/gate steps).

3. When a step fails, the executor pauses the workflow. No further steps are started. The operator sees the error in mission control and can retry, skip, or cancel.

4. A step configured with `breakpoint: true` transitions from `ready` to `waiting_for_breakpoint` and waits for operator confirmation before transitioning to `running`.

### Predecessor Resolution

Steps declare predecessors implicitly through their position in the YAML (linear ordering) or explicitly through a `depends_on` field. The executor builds a DAG from these declarations at workflow start.

For linear workflows (steps listed in sequence without `depends_on`), each step depends on the step immediately before it.

For complex workflows, `depends_on` is a list of step IDs:

```yaml
steps:
  - id: review_a
    type: human_review
    config: ...
  - id: review_b
    type: human_review
    config: ...
  - id: merge_results
    type: quality_check
    depends_on: [review_a, review_b]
    config: ...
```

## Conditional Branching

### Predicate Evaluation

The `conditional` step evaluates a predicate expression against the `WorkflowContext`. Predicates use a simple expression language:

```yaml
- id: check_quality
  type: conditional
  config:
    predicate: "metrics['quality.agreement'] >= 0.90"
    then_steps: [export]
    else_steps: [more_review, recheck_quality]
```

Supported predicate operations:
- Comparison: `>=`, `<=`, `>`, `<`, `==`, `!=`
- Boolean: `and`, `or`, `not`
- Membership: `in`
- Access: `metrics[key]`, `variables[key]`, `step_outputs[step_id].status`
- Literals: numbers, strings, booleans

The predicate evaluator is intentionally limited — no function calls, no loops, no side effects. If a predicate references a metric or variable that does not exist in the context, the predicate evaluates to `false` and a warning is logged.

### Branch Execution

When the conditional evaluates:

1. The taken branch's steps transition to `pending` (and then immediately to `ready` if their other predecessors are satisfied).
2. The not-taken branch's steps are marked `skipped`.
3. Downstream steps that depend only on skipped steps are also marked `skipped` (transitive skip propagation).
4. Downstream steps that depend on at least one non-skipped predecessor proceed normally when that predecessor completes.

### Transitive Skip Propagation

Skip propagation follows this rule: a step is auto-skipped if and only if ALL of its predecessors are `skipped`. If a step has multiple predecessors and at least one will complete, the step waits for that predecessor and proceeds.

Example:

```
conditional → [then: step_A] → step_C
           → [else: step_B] → step_C
```

If the `then` branch is taken, `step_B` is skipped but `step_C` is NOT skipped because `step_A` (a non-skipped predecessor) will complete.

## Parallel Step Execution

### Semantics

When a `parallel` step starts, all of its child steps are started concurrently. Child steps execute independently — they each read from the `WorkflowContext` as it was when the parallel step started. Child step outputs are merged into the context when the parallel step completes.

### Concurrency Within Parallel

- Each child step runs in its own execution context (its own asyncio task or thread, depending on whether it's I/O-bound or CPU-bound).
- Agent run children each acquire the dataset-level indexing lock independently. If two agent runs target the same dataset, they execute sequentially due to the lock. If they target different datasets, they run truly in parallel.
- Human steps within a parallel block create their queues concurrently. Reviewers can work on them in any order.

### Failure Modes

**Default behavior (`fail_fast: false`):**

1. If a child step fails, the parallel step enters `partially_failed` state.
2. Other running children continue to completion.
3. When all children have reached a terminal state (`completed`, `failed`, or `skipped`), the parallel step itself is marked `partially_failed`.
4. The operator can retry failed children individually, skip them, or cancel the entire parallel step.
5. The parallel step completes only when all children are `completed` or `skipped`.

**Fail-fast behavior (`fail_fast: true`):**

1. If a child step fails, the parallel step immediately sends cancellation signals to all other running children.
2. Running automated steps are cancelled at their next cancellation checkpoint (between records for agent runs, between batches for data operations).
3. Running human steps have their queues frozen (no new items claimed, in-progress items can be completed).
4. The parallel step is marked `failed` once all children have stopped.
5. The operator can retry the entire parallel step.

### Context Merging

When parallel children complete, their outputs are merged into the parent `WorkflowContext`:

- `record_sets`: each child writes to its own `step_id` key — no conflict possible.
- `agent_run_ids`: appended in completion order.
- `review_queue_ids`: appended in completion order.
- `metrics`: merged with last-write-wins semantics. If two children write the same metric key, the one that completed later wins. A warning is included in the parallel step's output.
- `variables`: same last-write-wins merge as metrics.
- `active_record_set_id`: set to `null` after parallel completion. The next step must explicitly reference a `record_set` by step ID or use a new `data_filter`/`data_sample` to establish a new active set.

## Loop Execution

### General Loop Mechanics

A `loop` step repeats its body steps until a termination condition is met or `max_iterations` is reached.

Each iteration:

1. The loop body steps execute in order (as if they were a standalone sub-workflow).
2. After all body steps complete, the termination condition is evaluated.
3. If the condition is met, the loop completes. If not, a new iteration begins.
4. The `WorkflowContext` is NOT reset between iterations. Each iteration sees the accumulated state from all previous iterations. This is intentional — iterative refinement works because the agent re-runs on records that were corrected in the previous iteration.
5. The loop writes `variables["loop.<step_id>.iteration"]` with the current (0-indexed) iteration count before each iteration starts.

### Termination Strategies

**Count-based (`type: count`):**

```yaml
termination:
  type: count
  count: 3
  max_iterations: 3  # same as count, but explicit safety limit
```

- Before each iteration, check `current_iteration < count`.
- If false, the loop completes with reason `"count_reached"`.
- Simple and predictable. Used for fixed multi-pass workflows.

**Metric-based (`type: metric`):**

```yaml
termination:
  type: metric
  metric: "quality.agreement"
  operator: ">="
  threshold: 0.90
  max_iterations: 5
```

- After each iteration's body steps complete, read `metrics[metric]` from the `WorkflowContext`.
- If the metric satisfies the operator/threshold condition, the loop completes with reason `"metric_threshold_met"`.
- If the metric does not exist in the context, the condition is not met (loop continues). A warning is logged.
- If `max_iterations` is reached without the condition being met, the loop completes with reason `"max_iterations_reached"` and the step output includes a warning.

**Coverage-based (`type: coverage`):**

```yaml
termination:
  type: coverage
  target_coverage: 0.95
  coverage_scope: "review"  # what counts as "covered": review, agent, or any
  max_iterations: 10
```

- After each iteration, compute coverage: the fraction of records in `record_sets[active_record_set_id]` that have been reviewed/labeled (depending on `coverage_scope`).
- `"review"` scope: record is covered if it has at least one human review event.
- `"agent"` scope: record is covered if it has at least one agent output.
- `"any"` scope: record is covered if it has either.
- If coverage >= `target_coverage`, the loop completes with reason `"coverage_target_met"`.
- Writes `metrics["loop.<step_id>.coverage"]` after each iteration.

**Manual (`type: manual`):**

```yaml
termination:
  type: manual
  max_iterations: 20  # safety limit
```

- After each iteration, the loop pauses and transitions to `waiting_for_gate`.
- The operator sees a prompt in mission control: "Iteration N complete. Continue or stop?"
- If the operator chooses "continue", the next iteration begins.
- If the operator chooses "stop", the loop completes with reason `"operator_stopped"`.
- If `max_iterations` is reached, the loop completes with reason `"max_iterations_reached"` regardless of operator input.

### Loop Body Step Reset

At the start of each iteration, the body steps are reset to `pending` state. Their previous execution records are preserved (for audit), but the step execution state machine starts fresh. This means:

- A body step that `failed` in iteration 1 starts fresh in iteration 2.
- Step outputs from previous iterations are overwritten in `step_outputs` (the current iteration's output is what matters for downstream steps within the loop body).
- Metrics and variables accumulate — they are NOT reset.
- Record sets from previous iterations remain accessible by step ID (e.g., `record_sets["agent_label__iter_0"]`), with iteration-suffixed keys. The unsuffixed key (`record_sets["agent_label"]`) always points to the latest iteration.

### Nested Loops

Loops can contain other loops. The inner loop runs to completion (all its iterations) before the outer loop evaluates its termination condition. There is no special interaction between loop levels — the shared `WorkflowContext` is the communication mechanism.

The iteration variable naming uses dot notation for nesting: `variables["loop.outer_loop.iteration"]` = 2, `variables["loop.inner_loop.iteration"]` = 4.

## Error Handling and Recovery

### Step Failure

When a step fails:

1. The step is marked `failed` with the error message, stack trace (truncated to 2000 chars), and timestamp.
2. The workflow execution transitions to `paused` state.
3. All `pending` and `ready` steps remain in their current state (not cancelled).
4. An SSE event is emitted: `{"type": "workflow_step_failed", "step_id": "...", "error": "..."}`.
5. The error is visible in mission control with the step name, error summary, and a "View details" link.

### Operator Recovery Actions

**Retry:** Re-runs the failed step from scratch using the current `WorkflowContext`. The step transitions `failed → retrying → running`. Previous outputs from this step (if any, from a partial failure) are discarded. A new `step_execution` record is created (the failed one is preserved for audit).

**Skip:** Marks the step as `skipped`. Downstream steps evaluate as described in the skip propagation rules. The operator must confirm the skip with an acknowledgment that downstream steps may lack expected inputs.

**Cancel:** Cancels the entire workflow execution. All `pending`, `ready`, and `running` steps transition to `cancelled`. Running automated steps are interrupted at their next cancellation checkpoint. Running human steps have their queues frozen.

**Resume:** After the operator has addressed the root cause (e.g., fixed a configuration, added missing data), they can resume the workflow. The failed step is retried automatically.

### Partial Step Failure

Some steps can partially succeed. For example, an `agent_run` that processes 1000 records but fails on record 501:

1. The step is marked `partially_failed` (not `failed`).
2. The step output includes both the successful outputs (records 1-500) and the error details (record 501 onward).
3. The operator can choose to:
   - **Retry remaining**: re-run only the unprocessed records.
   - **Accept partial**: mark the step as `completed` with a partial flag. Downstream steps see only the successfully processed records.
   - **Retry all**: re-run the entire step from scratch.
   - **Skip**: skip the step entirely.

### Timeout Handling

Steps have configurable timeouts:
- Automated steps: default 1 hour, configurable per step via `config.timeout_seconds`.
- Human steps: no timeout (they wait indefinitely for human work). The queue claim timeout (30 minutes) is separate — it governs individual item claims, not the step as a whole.
- Gate steps: no timeout.

When an automated step times out, it is treated as a failure with error message `"Step timed out after {N} seconds"`.

## Concurrency and Locking

### Workspace-Level Constraints

- Only ONE workflow execution can be active per workspace at a time. Starting a new workflow while one is running/paused requires cancelling the existing one first.
- Multiple workflow executions can exist in `completed`, `failed`, or `cancelled` states simultaneously (for history).

### Lock Hierarchy

Locks are acquired in a strict hierarchy to prevent deadlocks:

1. **Workspace migration lock** — held during schema migrations, database upgrades. Blocks all other operations.
2. **Dataset indexing lock** — held during data ingestion, normalization, and agent runs that write to a dataset. Multiple datasets can be locked concurrently. Read operations (queries, exports) do not require this lock due to SQLite WAL mode.
3. **Output namespace export lock** — held during export writes. Prevents two exports from writing to the same output directory concurrently.
4. **Task schema edit lock** — held when modifying a task schema. Prevents edits while reviews using that schema are in progress.

### Human Steps and Locks

Human steps do not acquire locks. They create queues (a write operation, briefly holding a database transaction) and then wait. While waiting, other operations can proceed freely. Individual review event submissions are atomic transactions that do not require exclusive locks.

### Agent Run Concurrency

Within a `parallel` step, multiple agent runs can execute concurrently if they target different datasets. If they target the same dataset, the dataset indexing lock serializes them. The executor does not detect this in advance — it relies on the lock to enforce ordering.

### SQLite WAL Mode

The application runs SQLite in WAL (Write-Ahead Logging) mode. This allows:
- Multiple concurrent readers (reviewer sessions, mission control queries, data explorer).
- One writer at a time (serialized by SQLite's internal locking).
- Readers never block writers and vice versa.

Write operations that might contend (review event submission, agent output writes) use short transactions with immediate retry on `SQLITE_BUSY` (up to 3 retries with 100ms backoff).

## Workflow Execution Persistence

### Database Schema

```sql
CREATE TABLE workflow_executions (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    workflow_name TEXT NOT NULL,
    workflow_version INTEGER NOT NULL,
    workflow_definition_id TEXT NOT NULL,  -- FK to workflow_definitions
    status TEXT NOT NULL,                 -- pending, running, paused, completed, failed, cancelled
    context TEXT NOT NULL,                -- serialized WorkflowContext (JSON)
    started_at TEXT,
    completed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
);

CREATE TABLE workflow_step_executions (
    id TEXT PRIMARY KEY,
    workflow_execution_id TEXT NOT NULL,
    step_id TEXT NOT NULL,               -- matches step.id in the workflow YAML
    step_type TEXT NOT NULL,
    iteration INTEGER DEFAULT 0,         -- loop iteration (0 for non-loop steps)
    status TEXT NOT NULL,                -- pending, ready, running, waiting_for_human,
                                         -- waiting_for_gate, waiting_for_breakpoint,
                                         -- completed, failed, skipped, retrying,
                                         -- partially_failed, interrupted, cancelled
    step_config TEXT NOT NULL,           -- step config snapshot (JSON)
    result TEXT,                         -- StepOutput serialized (JSON)
    error_message TEXT,
    error_trace TEXT,
    started_at TEXT,
    completed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (workflow_execution_id)
        REFERENCES workflow_executions(id)
);

CREATE INDEX idx_step_exec_workflow
    ON workflow_step_executions(workflow_execution_id, step_id);
CREATE INDEX idx_step_exec_status
    ON workflow_step_executions(workflow_execution_id, status);
```

### Context Persistence

The `WorkflowContext` is serialized to JSON and written to the `workflow_executions.context` column after every step completion. This is the transaction boundary: a step is considered complete only when both its `step_execution` row is updated to `completed` AND the workflow execution's `context` is updated, in a single transaction.

This ensures that if the application crashes between step completions, the context is consistent with the last completed step.

### Crash Recovery

On application startup, the executor checks for workflow executions in `running` or `paused` state:

1. Any step executions in `running` state are transitioned to `interrupted`.
2. The workflow execution is transitioned to `paused`.
3. The `WorkflowContext` reflects the state as of the last completed step (because context writes are transactional with step completions).
4. Mission control shows the paused workflow with a "Resume" action.
5. On resume, `interrupted` steps are treated like `failed` steps — the operator can retry or skip them.

Steps that were `waiting_for_human` or `waiting_for_gate` at crash time are left in that state — they are safe to resume because no automated work was in progress.

### Execution History

Completed workflow executions and their step executions are never deleted. They form an audit trail. The mission control screen shows execution history with filtering by status, date range, and workflow name. Each historical execution can be inspected to see the full step-by-step timeline, context evolution, and outputs.

## Breakpoint Behavior

Any step can have `breakpoint: true` in its config. This affects the transition from `ready` to `running`:

1. Instead of auto-starting, the step transitions to `waiting_for_breakpoint`.
2. Mission control shows a "Step ready: {step_name}. Continue?" prompt with the step's config summary and the current `WorkflowContext` summary.
3. The operator can:
   - **Continue**: transition the step to `running`.
   - **Edit config**: modify the step's config before running (e.g., change sample size, switch model). This creates a config override stored in the step execution, not modifying the workflow YAML.
   - **Skip**: skip the step.
   - **Cancel**: cancel the workflow.

A workflow can also be configured with `pause_on_every_step: true`, which implicitly adds `breakpoint: true` to every step. This gives full manual control for debugging or high-stakes workflows.

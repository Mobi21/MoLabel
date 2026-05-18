---
name: 'molabel-cli'
description: 'Use when Claude Code should operate a MoLabel workspace through the public molabel CLI and installed MoLabel skill only.'
---

# MoLabel Claude Code Skill

Use this skill when Claude Code is operating a MoLabel workspace through the public CLI.

## Workflow

1. Run `molabel workspace detect`.
2. Run `molabel doctor --json` or `molabel status --json`.
3. Run `molabel manifest --json` before assuming command behavior.
4. Read canonical artifacts before attempting to change them.
5. Prefer `--json` output and explicit paths for any mutating flow.
6. Treat raw backend APIs as unavailable for operator work.
7. Use the installed MoLabel skill and CLI only; do not substitute `curl` or direct HTTP requests.

## Grounded Benchmark Workflow

When operating a grounded benchmark, read only the operator-visible workspace
files first: `AGENTS.md`, `workbench.project.yaml`, the task schema under
`workbench/config/task-schemas/`, and the workflow YAML under
`workbench/workflows/`. Do not read hidden authority-pack files unless the
benchmark prompt explicitly allows them.

### Phase 1: Discover

1. Read `AGENTS.md` in the workspace root for rules, artifact output paths, and constraints.
2. Read `workbench.project.yaml` to learn dataset IDs, task schema paths, and source paths.
3. Read the task schema YAML under `workbench/config/task-schemas/` to learn label fields and options. **You MUST only submit label values that appear exactly in the `options` list — copy the exact string, do not paraphrase or reformat.** For example, if the options include `book_flight`, submit `"book_flight"` — never `"Book Flight"`, `"book a flight"`, or `"booking_flight"`.
4. Read the workflow YAML under `workbench/workflows/` to learn step definitions.
5. Infer the required model profile and artifact path rules from the visible benchmark notes and the operator prompt.

### Phase 2: Setup

Run these commands in order. Always append `--json` and capture the returned IDs.

```
molabel workspace bootstrap <workspace-path> --workspace-name "<name>"
```

Immediately create a reviewer session after bootstrap. This is required before
`queue claim` or `review submit`:

```
molabel session list-reviewers --json
```

```
molabel session select <reviewer-id> --json
```

```
molabel dataset create \
  --name <dataset-name> \
  --source-type file \
  --loader-plugin jsonl \
  --record-kind text \
  --canonical-id-strategy source_record_id \
  --indexing-mode projection \
  --json
```

```
molabel dataset import <dataset-id> --source-uri <relative-path-to-jsonl> --json
```

```
molabel task-schema create --file <path-to-task-schema.yaml> --json
```

Create a prompt that matches the task schema's instructions and label field descriptions:

```
molabel prompt create \
  --name "<prompt-name>" \
  --agent-role proposer \
  --task-schema-id <task-schema-id> \
  --system-instructions "<instructions-from-task-schema>" \
  --task-rubric "<label-field-descriptions-as-rubric>" \
  --json
```

Register the model profile. Build the JSON body from `operator.yaml` fields (`current_labeling_engine`) and known provider configuration. The `auth_ref` is typically `ANTHROPIC_API_KEY`:

```
molabel model-profile create --body-text '{
  "model_profile_slug": "<slug>",
  "provider_type": "anthropic",
  "provider_name": "<provider-name>",
  "model_identifier": "<model-id>",
  "auth_ref": "ANTHROPIC_API_KEY",
  "supports_structured_output": true
}' --json
```

For the grounded operator benchmark, use `model_identifier: "MiniMax-M2.7-highspeed"` exactly. Do not substitute Ollama, local models, or heuristic/builtin profiles. Before running the workflow, verify the chosen profile resolves to MiniMax 2.7 highspeed via `molabel model-profile list --json`.

### Phase 3: Run workflow

```
molabel workflow create --file <path-to-workflow.yaml> --json
```

```
molabel workflow run <workflow-slug-or-id> --json
```

### Phase 4: Monitor and advance

Poll the execution until the review step reaches a breakpoint:

```
molabel workflow execution <workflow-slug-or-id> <execution-id> --json
```

Look for `queue_id` in the execution context or step outputs. If a step has `breakpoint: true`, the workflow pauses before that step. Use `workflow advance` to continue past breakpoints when ready:

```
molabel workflow advance <workflow-slug-or-id> <execution-id> <step-id> --json
```

For grounded benchmarks with a human-review queue, do not treat the workflow as
done when it first reaches `waiting_for_human`. The run is only complete after:

1. you found the review `queue_id`,
2. the queue is fully reviewed,
3. the persisted review count matches the benchmark record count,
4. and the required benchmark artifacts are written.

### Phase 5: Review

Claim exactly one review task, inspect it, submit it, then claim the next:

```
molabel queue claim <queue-id> --json
```

Treat the claim response as the only authoritative binding between the current `task.id` and the record being reviewed. Use the returned `record_external_id`, `record_text`, and `record_view` fields to identify the example. Do not bulk-claim tasks, do not build a separate task-id list, do not nest `queue claim` inside another shell command, and do not assume queue order matches dataset order.

If the task uses blind review and you need to inspect the AI proposal, reveal it for the currently claimed task only:

```
molabel review reveal-ai <task-id> --json
```

For the currently claimed task, read the record content from `record_text` (or from `record_view` if the task is not pure text), determine the correct labels by selecting from the task schema's `options` list (use the exact canonical strings), and submit. Prefer the default auto-claim behavior so the submit response returns `next_task` for the next loop iteration:

```
molabel review submit <task-id> \
  --labels-json '{"intent_label": "<value>", "is_out_of_scope": false, "notes": "..."}' \
  --decision accept \
  --rationale "<brief-rationale>" \
  --json
```

If the task exposes tokenized text instead of a plain string, use the joined
token text from `record_text` as the human-readable source, preserve any
required token-aligned structures, and keep array lengths aligned to the source
tokens. For rationale-mask tasks:

- `rationale_token_mask` must be a JSON array of `0`/`1` integers,
- its length must exactly match the visible token sequence length,
- and multi-select labels must use only task-schema options, excluding values
  that are not in the schema such as `"None"`.

Review loop:

1. Call `queue claim` once to get the first `task`.
2. Submit that exact `task.id`.
3. If the submit response contains `next_task`, continue with that object directly.
4. Only call `queue claim` again when there is no current task and the queue is not empty.
5. Stop only when the queue is empty and there is no `next_task`.

Never issue two `queue claim` calls for a single review submission.

For benchmark runs, assume the workspace is intentionally redacted. Do not try to reconstruct gold labels or hidden authority artifacts from file reads or shell tricks; if a field is not present in the claim/reveal responses or the public `molabel` CLI, treat it as unavailable.

Never read, list, or grep any path containing `authority`, `gold`, `human-labels`, `reviews`, `label-map.yaml`, `metrics.yaml`, `baselines.yaml`, `operator.yaml`, `paper.yaml`, or `scenario.yaml`. Those are hidden benchmark-authority surfaces and touching them is a blocking failure.

**Do NOT run adjudication commands** (`adjudication queue`, `adjudication detect`, `adjudication build`, `adjudication resolve`). Adjudication is a separate post-benchmark process and is not part of this workflow. If the workflow status shows steps like `adjudicate`, `score`, or `snapshot` as pending/blocked, IGNORE them — proceed directly to Phase 6 (write artifacts).

**NEVER use curl, wget, httpx, requests, or any HTTP client to call MoLabel's API.** This is a blocking benchmark gate. Only use the `molabel` CLI. If a CLI command doesn't exist for what you need, skip that action — do not work around it with HTTP calls.

### Phase 6: Write run artifacts (mandatory)

The workspace `AGENTS.md` specifies the output directory (typically `workbench/benchmarks/runs/live-operator/`). Write two files there:

- `summary.json` — JSON object with run metadata: benchmark_id, runner, timestamp, record_count, submitted_count.
- `report.md` — Markdown summary of the run: what was done, how many records, any issues.

Before writing either file, call:

```
molabel benchmark facts <workflow-execution-id> --json
```

Use that persisted payload as the source of truth for artifact counts and
rates, not pre-review workflow placeholders. Prefer
`semantic_decision_counts` for accept/edit/reject-style review outcome counts.
**You must write both files before exiting.** This phase is required even if
earlier phases had issues.

### Timing

Target total wall-clock time under 15 minutes. Avoid unnecessary reads or retries. Pipeline the setup phase (commands 1-6 depend on each other's IDs but should execute without delays between them). The review loop is the longest phase; process tasks sequentially without pausing.

## Notes

- The CLI preserves MoLabel's local-first file ownership rules.
- The GUI is the manual control room, not the primary automation surface.
- Backend URLs and API routes are implementation details, not part of the operator contract.
- Use `molabel skill install` to sync this skill bundle into the agent environment.

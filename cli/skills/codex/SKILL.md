---
name: 'molabel-cli'
description: 'Use when Codex should operate a MoLabel workspace through the public molabel CLI and installed MoLabel skill only.'
---

# MoLabel Codex Skill

Use this skill when Codex is operating a MoLabel workspace through the public CLI.

## Operating Rules

1. Treat `molabel` as the primary public interface.
2. Assume raw backend APIs are unavailable for operator work.
3. Do not use `curl`, handwritten HTTP requests, or direct SDK calls as substitutes for `molabel`.
4. Detect the workspace before mutating anything.
5. Inspect the command manifest before assuming a command shape.
6. Prefer machine-readable output over prose or terminal scraping.
7. Read canonical artifacts before attempting to change them.
8. Use safe write flows with explicit expected hashes whenever possible.

## Recommended Workflow

1. Run `molabel workspace detect`.
2. Run `molabel doctor --json`.
3. Run `molabel manifest --json`.
4. Use `molabel session ...` to confirm or switch reviewer identity.
5. Use `molabel dataset ...`, `molabel task-schema ...`, and `molabel prompt ...` to prepare the project.
6. Use `molabel workflow ...` and `molabel agent-run ...` to execute agent work.
7. Use `molabel queue ...`, `molabel review ...`, and `molabel adjudication ...` for human-in-review and disagreement handling.
8. Use `molabel quality ...`, `molabel export ...`, and `molabel release ...` to finish the governed delivery flow.
9. Use `molabel artifact ...` only when working with canonical files directly.

## Review And Benchmark Work

When operating benchmark or evaluation workspaces:

- compare outputs against gold labels where available,
- inspect disagreement rather than flattening it,
- pay special attention to intentionally bad human labels or reviews,
- stay on the CLI-and-skill surface even if you suspect a backend shortcut exists,
- and summarize whether the agent, the human, or both appear wrong.

For grounded benchmark operator runs:

1. Read only operator-visible workspace files first:
   - `AGENTS.md`
   - `workbench.project.yaml`
   - `workbench/config/task-schemas/*.yaml`
   - `workbench/workflows/*.yaml`
2. Do not read hidden benchmark-authority paths such as `authority/`,
   `workbench/benchmarks/gold/`, `workbench/benchmarks/human-labels/`,
   `workbench/benchmarks/reviews/`, `label-map.yaml`, `metrics.yaml`,
   `baselines.yaml`, `operator.yaml`, `paper.yaml`, or `scenario.yaml` unless
   the prompt explicitly allows them.
3. After `workspace bootstrap`, create or confirm a reviewer session before any
   queue action:
   - `molabel session list-reviewers --json`
   - `molabel session select <reviewer-id> --json`
4. Treat `workflow execution ... --json` as the source of truth for
   `queue_id`. A grounded operator run is not complete when the workflow first
   pauses; it is complete only when the review queue is empty, the persisted
   review count matches the record count, and the required run artifacts are
   written.
5. Review sequentially:
   - claim one task,
   - optionally reveal AI for that task only,
   - submit that task,
   - continue with `next_task` when present,
   - stop only when the queue is empty.
6. For tokenized records, use the joined token text from `record_text` as the
   reviewer-facing source text. Keep required arrays aligned to the visible
   token sequence and use only exact task-schema option strings.
7. Write `summary.json` and `report.md` under the benchmark run artifact
   directory. Before writing them, call
   `molabel benchmark facts <workflow-execution-id> --json` and use that
   persisted payload as the source of truth for counts/rates. Prefer
   `semantic_decision_counts` for accept/edit/reject-style outcome counts.

## Notes

- The CLI is local-first and file-aware.
- Benchmark operators should treat backend URLs and API routes as hidden implementation details.
- Stable JSON output is the default operating mode for Codex.
- The expected steady state is CLI-and-skill-only operation, not ad hoc `curl` or direct HTTP calls.

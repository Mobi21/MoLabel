# Evidence Loss Investigation

Date: 2026-04-12
Related: `docs/research/2026-04-12-molabel-improvement-spec.md` §7.1

## Question

Where does evidence disappear between `molabel_model` and `workflow_autorun`
for FEVEROUS and SciFact?

## Findings

1. The loss is not in `review_events` persistence.
   - `packages/molabel-app/src/molabel/app/services/claims.py`
     preserves JSON values for review submissions.
   - `tests/e2e/infrastructure/grounded_operator.py`
     reads back `review_events.labels` and `agent_outputs.labels` without
     flattening arrays.
2. The loss is not in the scorer.
   - The historical reports already show the wrong evidence representation at
     `workflow_autorun`, before review changes anything.
3. The first lossy step is proposer output generation inside the workflow path.
   - `packages/molabel-app/src/molabel/app/api/v1/workflows.py`
     `_build_output_schema()` treated every `field_type: json` field as a
     plain string.
   - For grounded evidence benchmarks, that meant `evidence_atoms` was
     requested as a string instead of an array of stable IDs.
   - This exactly matches the 2026-04-12 report artifacts:
     - SciFact `workflow_autorun` stored stringified arrays like
       `"[\"doc_1001_sentence_2\"]"`.
     - FEVEROUS `workflow_autorun` stored prose strings and nested objects
       rendered as strings instead of stable atom IDs.

## Root Cause

The workflow proposer path had a schema bug, not a DB write/read bug.

- File: `packages/molabel-app/src/molabel/app/api/v1/workflows.py`
- Function: `_LlmAgentRunner._build_output_schema`
- Bug: grounded `json` label fields were modeled as `"type": "string"`
  instead of benchmark-appropriate arrays.

The FEVEROUS workflow fixture also amplified the problem by using a legacy
`agent_run` step without explicit `task_schema_id` or `prompt_ref`, making the
proposer path more brittle than the working SciFact flow.

## Fix Direction

1. Model `evidence_atoms` as `array[string]` and `rationale_token_mask` as
   `array[int]` in the workflow proposer schema builder.
2. Make FEVEROUS and HateXplain workflow fixtures explicit about
   `task_schema_id`, `prompt_ref`, `model`, and review breakpoint behavior.
3. Add submission-time structural validation so stringified or prose evidence
   cannot be silently accepted downstream.

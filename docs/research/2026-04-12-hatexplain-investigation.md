# HateXplain Investigation

Date: 2026-04-12
Related: `docs/research/2026-04-12-molabel-improvement-spec.md` §7.2

## Question

Why did the 2026-04-12 hatexplain run fail after ~121 seconds with zero scored
output?

## Reproduction Work

1. Direct paper-baseline repros were run against live MiniMax 2.7 highspeed using the
   grounded structured schema on multiple historical slice records.
2. Those direct calls returned valid structured output quickly
   (single-attempt successes, ~7-12 seconds per call), so the raw paper-direct
   schema is not permanently invalid.
3. A fresh isolated benchmark run was started to compare against the historical
   failure signature. That run no longer reproduced the exact
   `121s + 0 scored output` pattern while this note was written.
4. After the product fixes in this implementation pass, a fresh isolated live
   operator run still failed, but with a materially different signature:
   `~76s + 2 API calls + no review submissions`. That confirms the original
   `0 API call / custom-provider` path moved, but there is still a live
   operator-side no-submission failure to finish debugging.

## Findings

The investigation converged on four concrete product issues:

1. The hatexplain workflow fixture was underspecified.
   - `fixtures/benchmarks-grounded/hatexplain/workbench/workflows/grounded-cli-hatexplain.yaml`
     used the wrong ingest path (`dataset.json` instead of `dataset.jsonl`).
   - The proposer step had no explicit `model`, `prompt_ref`, or `agent_role`.
   - The review step had no explicit `task_schema_id`, `sample_strategy`, or
     breakpoint configuration.
2. The workflow proposer path shared the same JSON-field schema bug identified
   in the evidence investigation, so `rationale_token_mask` was being requested
   through a lossy schema in the product path.
3. The workflow ingest path did not respect benchmark `record_id_field`
   metadata, so the workflow-created dataset fell back to synthetic external IDs
   such as `dataset-1` instead of preserving `post_id`. That broke operator
   coverage alignment and made otherwise valid submissions look incomplete.
4. When no usable model profile survived into workflow execution,
   `_ensure_model_profile()` synthesized a `provider_type=custom` fallback.
   `_LlmAgentRunner` cannot execute custom providers, so the workflow crashed
   before producing reviewable outputs. The correct fallback for `MiniMax-M2.7-highspeed`
   is an Anthropic-compatible profile with the MiniMax base URL, not a custom
   heuristic profile.

## Root-Cause Attribution

Strict root-cause attribution to "adapter latency" or "enforcer retry loop"
is not justified from current evidence because the direct reproductions did not
recreate the historical timeout today.

The honest conclusion is:
- the historical failure was real,
- it is not reproducibly explained by the paper-direct schema alone,
- and the operator path had multiple independent product bugs that could each
  produce an incomplete run: malformed workflow fixture, lossy rationale schema,
  source-ID loss, and custom-provider fallback during execution.

## Fix Direction

1. Harden the hatexplain workflow fixture so the proposer path is explicit and
   runnable.
2. Preserve `rationale_token_mask` as a true integer array in the live workflow
   schema builder.
3. Preserve `post_id` through workflow ingest and submission scoring.
4. Infer a real Anthropic-compatible MiniMax profile at workflow execution time
   instead of synthesizing `provider_type=custom`.
5. Keep provider/enforcer diagnostics on failed runs so any future timeout can
   be classified without guessing.

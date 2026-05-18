# CLINC150 Artifact Truthfulness Investigation

Date: 2026-04-12
Related: `docs/research/2026-04-12-molabel-improvement-spec.md` §7.3

## Question

Which field caused the clinc150 artifact truthfulness failure?

## Finding

The mismatch was in the validator, not in the operator's underlying count data.

- Historical `summary.json`:
  - `record_count: 16`
  - `submitted_count: 16`
  - `proposal_coverage: 1.0`
  - `review_coverage: 1.0`
- Historical validator expectation in
  `packages/molabel-core/src/molabel/core/quality/grounded_benchmarks.py`
  treated `proposal_coverage` as a count and expected `16`, not `1.0`.

`proposal_coverage` and `review_coverage` were written as rates, which is
truthful for fields named "coverage". The false negative came from the audit
checker comparing them to raw counts.

## Root Cause

- File: `packages/molabel-core/src/molabel/core/quality/grounded_benchmarks.py`
- Function: `build_operator_diagnostics`
- Bug: summary truthfulness checks assumed count semantics for `proposal_coverage`
  and ignored the existing `accept_rate` alias.

## Fix Direction

1. Treat `proposal_coverage` and `review_coverage` as truthful if they match
   either the raw count or the normalized rate over total records.
2. Accept both `accept_ai_rate` and `accept_rate` when validating summary
   artifacts.
3. Continue blocking genuinely inconsistent fields at write time.

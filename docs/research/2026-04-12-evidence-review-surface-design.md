# Evidence Review Surface Design

Date: 2026-04-12
Related: `docs/research/2026-04-12-molabel-improvement-spec.md` §7.5

## Current Surface

The real review surface today is the API + CLI-backed queue flow.

- Backend persistence: `packages/molabel-app/src/molabel/app/services/claims.py`
- Review endpoints: `packages/molabel-app/src/molabel/app/api/v1/queue.py`
- Frontend review page: `frontend/src/pages/review.tsx`

The frontend page is currently mock/demo code, not the production review path.

## Decisions

1. Immediate target surface: backend + CLI-backed queue flow.
   - This is the system boundary where review submissions are persisted.
   - Frontend rendering can only become authoritative after the live queue path
     moves off the current mock page.
2. Stable anchor IDs already exist for the current grounded evidence families.
   - SciFact uses stable sentence IDs shaped like `{doc_id}_sentence_{index}`.
   - FEVEROUS uses stable sentence/table/header cell IDs.
   - No schema migration is required for the current P0 band.
3. Structural validation belongs in backend persistence.
   - Client-side UX can mirror it later, but the backend must block invalid
     evidence/rationale payloads.
4. Complete-support-path policy for the current benchmarks:
   - SciFact / FEVEROUS: when verdict is not `nei`, `evidence_atoms` must be a
     non-empty list of stable atom IDs.
   - HateXplain: `rationale_token_mask` must be a binary array aligned to the
     record token sequence.

## Scope For Implementation

Immediate P0 scope:

1. Preserve structured arrays in the workflow proposer path.
2. Reject invalid evidence/rationale submissions at persistence time.
3. Surface the preserved structured labels through the existing queue payloads.

Deferred scope:

- a first-class frontend evidence editor,
- grouped evidence visualization in React,
- table/sentence anchor rendering,
- and richer inline validation UX.

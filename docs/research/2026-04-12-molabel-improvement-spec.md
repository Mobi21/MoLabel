# MoLabel Improvement Spec

Date: 2026-04-12
Status: Action-ready spec derived from the 2026-04-11 audit and a fresh live operator batch
Related:

- `docs/research/2026-04-11-live-benchmark-and-quality-audit.md`
- `reports/bench-20260412-124841/summary.md`
- `reports/bench-20260412-124841/summary.json`
- `reports/bench-20260412-124841/{clinc150,banking77,feverous,goemotions,hatexplain,scifact}.json`

## 1. Purpose

This document is the prescriptive follow-up to the 2026-04-11 audit. It
incorporates both:

1. the audit's analysis and the decisions taken during the interactive review,
2. fresh evidence from the 2026-04-12 operator benchmark batch run under the
   new conservative worker default (1 worker, sequential).

The new data changed several of the audit's conclusions. This spec reflects
what the evidence actually shows, not what the audit assumed.

## 2. Fresh Evidence (2026-04-12 Batch)

Run: `reports/bench-20260412-124841/` — 1 worker, wall time 2731.72s, 5/6 passed.

### 2.1 Per-Benchmark Stage Scores

| Benchmark  | Slice | Paper  | Model  | WF Autorun | WF Reviewed | Operator Label | Checklist | Operator Overall |
|------------|------:|-------:|-------:|-----------:|------------:|---------------:|----------:|-----------------:|
| clinc150   |    16 | 1.0000 | 1.0000 |     1.0000 |      1.0000 |         1.0000 |    0.8750 |           0.9625 |
| banking77  |    16 | 0.7292 | 0.7292 |     0.9323 |      0.9323 |         0.9323 |    1.0000 |           0.9526 |
| goemotions |    12 | 1.0000 | 1.0000 |     0.7741 |      1.0000 |         1.0000 |    1.0000 |           1.0000 |
| scifact    |     8 | 0.8750 | 0.8750 |     0.1250 |      0.1250 |         0.1250 |    1.0000 |           0.3875 |
| feverous   |     6 | 0.3333 | 0.3333 |     0.0000 |      0.0000 |         0.0000 |    1.0000 |           0.3000 |
| hatexplain |     — |      — |      — |          — |           — |              — |         — |         **FAIL** |

### 2.2 Stage Transitions (Tax And Lift)

Tax convention in the reports: **positive tax = the stage LOST quality, negative tax = the stage GAINED quality**.

The "Verdict component delta" and "Evidence component delta" columns below
decompose the `workflow_tax` transition into its underlying per-metric
components. Values in these two columns are expressed in **intuitive sign
convention** (positive = gain, negative = loss), which is the inverse of the
tax convention used in the `*_tax` columns to the left. Each cell is
prefixed with "gained" or "lost" to make the semantics unambiguous. These
component deltas are NOT attributable to the review stage alone — see §3.2
for why.

| Benchmark  | model_tax | workflow_tax [1] | operator_tax | Verdict component delta (intuitive sign) | Evidence component delta (intuitive sign) |
|------------|----------:|-----------------:|-------------:|:-----------------------------------------:|:------------------------------------------:|
| clinc150 † |   +0.0000 |          +0.0000 |      +0.0000 | n/a                                       | n/a                                        |
| banking77  |   +0.0000 |          -0.2031 |      +0.0000 | n/a                                       | n/a                                        |
| goemotions |   +0.0000 |          +0.0000 |      +0.0000 | n/a                                       | n/a                                        |
| scifact    |   +0.0000 |          +0.7500 |      +0.0000 | gained +0.1250                            | lost -1.0000                               |
| feverous   |   +0.0000 |          +0.3333 |      +0.0000 | gained +0.6667                            | lost -0.9565                               |

Negative `workflow_tax` (banking77) means the combined two-hop transition
`molabel_model → workflow_reviewed` gained quality. It does **not** tell you
whether that gain came from the autorun (workflow structuring improving model
output) or from the reviewer (edits). In the 2026-04-12 data, banking77's
`workflow_autorun` score equals its `workflow_reviewed` score (both 0.9323),
so the full +0.2031 gain happened at the autorun step, not at review. §6.4
names this `autorun_lift_vs_model`, not a review lift.

Positive `workflow_tax` on the evidence benchmarks does **not** mean review is
bad overall — it means one component (evidence) collapses harder than the
other component (verdict) improves, both of which happen by the
`workflow_autorun` stage. The review stage is demonstrably zero-delta on this
data because the reviewer accepted every record unedited (§3.2).

**[1] Tax schema is inconsistent across benchmarks and this table conflates two
transitions that the raw reports do not treat identically:**

- `clinc150` (marked †) reports `workflow_tax` as the `molabel_model →
  workflow_autorun` delta AND emits a separate `review_lift (workflow_reviewed
  → workflow_autorun)` line. Two hops, reported separately.
- `banking77`, `goemotions`, `feverous`, and `scifact` report a single
  `workflow_tax` as the full `molabel_model → workflow_reviewed` delta (two
  hops folded into one number), with no separate `review_lift` line.

The values in the table row for clinc150 are therefore **not directly
comparable** to the other rows. They only coincidentally agree (all zeros on
clinc150) because every stage scores perfectly on clinc150. On any benchmark
where the stages differ, the clinc150-style schema and the banking77-style
schema would produce different numbers that look superficially identical in
this table.

This inconsistency is a real blocker for §6.4 (named lift metrics) and must
be resolved as a prerequisite work item — see §6.7.

### 2.3 Checklist Item Pass / Fail By Benchmark

All benchmarks run the same 8 checklist items. Here is the full picture:

| Check                                      | clinc150 | banking77 | goemotions | feverous | scifact |
|---------------------------------------------|:--------:|:---------:|:----------:|:--------:|:-------:|
| uses_public_cli_and_skill_only              | PASS     | PASS      | PASS       | PASS     | PASS    |
| configures_minimax_2_7_profile              | PASS     | PASS      | PASS       | PASS     | PASS    |
| bootstraps_workspace_and_dataset            | PASS     | PASS      | PASS       | PASS     | PASS    |
| uses_real_minimax_proposals                 | PASS     | PASS      | PASS       | PASS     | PASS    |
| preserves_valid_labels                      | PASS     | PASS      | PASS       | PASS     | PASS    |
| writes_benchmark_run_artifacts              | PASS     | PASS      | PASS       | PASS     | PASS    |
| **writes_truthful_benchmark_run_artifacts** | **FAIL** | PASS      | PASS       | PASS     | PASS    |
| preserves_artifact_integrity                | PASS     | PASS      | PASS       | PASS     | PASS    |

## 3. What The New Data Changes

Three of the audit's claims need correction.

### 3.1 The Audit Misidentified The Artifact Problem

**Audit claim:** "the current product keeps missing the
`writes_benchmark_run_artifacts` check on otherwise strong runs."

**Actual:** Every benchmark in the 2026-04-12 batch passes
`writes_benchmark_run_artifacts`. The failing check is
`writes_truthful_benchmark_run_artifacts`, and it only fails on clinc150 in
this run. Banking77 and goemotions now score 1.0 on the full checklist.

The operator is writing artifacts. On clinc150 the written artifacts are not
truthful — they contain claims that do not match what actually happened. The
fix is not "teach the operator to write artifacts," it is "make truthfulness
enforcement visible at write time so the operator cannot silently emit
inaccurate artifacts."

### 3.2 The Evidence Collapse Happens Upstream Of Review, Not Inside It

**Audit claim:** "the review flow likely optimizes for label correction more
than structured evidence repair."

**Actual:** On both feverous and scifact the per-stage evidence_f1 values are:

| Stage                | feverous evidence_f1 | scifact evidence_f1 |
|----------------------|---------------------:|--------------------:|
| `molabel_model`      |               0.9565 |              1.0000 |
| `workflow_autorun`   |               0.0000 |              0.0000 |
| `workflow_reviewed`  |               0.0000 |              0.0000 |
| `operator_reviewed`  |               0.0000 |              0.0000 |

The breaking hop is `molabel_model → workflow_autorun`. Evidence is already
zero by the time the review stage sees it. Every downstream stage is
trivially zero-delta because there is nothing left to lose.

**What we can and cannot conclude from this data:**

- We **can** conclude the workflow stage that stores the model's proposal
  does not preserve structured evidence atoms. The same underlying model
  call produces `evidence_f1 = 0.9565` (feverous) and `1.0` (scifact) when
  scored directly at `molabel_model`, but `0.0` when scored after workflow
  storage at `workflow_autorun`. Something in the proposal-storage path is
  dropping or flattening evidence structure.
- We **cannot** conclude that a reviewer who edits evidence would preserve
  it correctly. On the two evidence benchmarks, the reviewer accepted
  every record unedited: feverous `Accept AI / edit AI / correct / reject
  AI / skip: 6 / 0 / 0 / 0 / 0`, scifact `8 / 0 / 0 / 0 / 0`. An
  accept-only reviewer is trivially zero-delta on every metric; we have
  no data point on feverous or scifact where a reviewer tried to edit
  structured evidence and we observed whether that edit survived.
- We **cannot** conclude that `operator_tax = 0` on feverous and
  scifact proves "the reviewer is not lossy on evidence." For those
  two benchmarks, it proves "the reviewer made no edits, so no
  editing-related loss can be measured on evidence." Goemotions is a
  separate data point where the reviewer DID make edits (5 edit AI
  actions) and still preserved full label quality — that is weak
  positive evidence that review can preserve classification labels,
  but it says nothing about structured evidence atoms.

**Implication for §5:** The audit's "build evidence review surfaces"
recommendation and the spec's "preserve evidence through the pipeline"
recommendation are **two layers of the same bug**, not clearly separable
concerns. In today's state:

1. The workflow_autorun storage path is demonstrably dropping evidence
   (5.1 addresses this directly).
2. The review surface may or may not preserve edits once storage is fixed;
   that cannot be tested until 5.1 lands. 5.2 builds the surface in
   parallel so that when 5.1 unblocks evidence in review, the reviewer
   has tools to work with it.

Neither 5.1 alone nor 5.2 alone is sufficient. They ship together not as a
phased rollout but as two coupled fixes to one coupled bug.

### 3.3 Hatexplain's Failure Is Not Rate Limiting

**Audit claim:** "batch failure on goemotions aligned with provider 429
retries ... the latest failure was not fundamentally a task-semantics failure"
(attributed primarily to overparallelization).

**Actual:** In the new 1-worker batch, goemotions and scifact both completed
cleanly. Goemotions passed in 576.8s (`12 agent API calls`, `58 total API
calls` including paper-direct baseline per the e2e teardown log), scifact in
433.3s. The concurrency fix worked for those two. But hatexplain failed in
exactly **121,211 ms with 0 API calls**, at 1 worker, with 5 other
benchmarks in the same batch succeeding.

The visible failure pattern has two candidate explanations that the raw
data does not cleanly disambiguate:

1. **Latency explanation:** The paper-direct baseline's first
   structured-output call stays in flight for the full 120s per-call
   timeout, raises `TimeoutError`, is caught by the except block, and
   control falls through to the single-prompt operator run. The agent then
   exits with code 0 but submits zero review records.

2. **Validation-retry explanation:** The same raw stdout shows
   `attempts=3, used_native=True` on the structured-output enforcer and a
   `validation_errors` list containing target-community enums (`Men`,
   `Minority`, `Nonreligious`, `Refugee`, `Women`, `Other`). This is a
   retry-until-schema-valid signature, not a latency signature. The
   enforcer could have spent the 120s burning retries against a hatexplain
   schema the model keeps emitting slightly off, eventually timing out.

Either way, **this is not provider pressure**: 1 worker, 5 sibling
benchmarks succeeding, no 429 indicators. The spec does not pre-commit to
one root cause. §7.2 requires the investigation to check both.

Attributing the failure to infrastructure would be a mis-diagnosis and
would cause the real bug to sit unfixed through future batches.

## 4. Decisions Taken During The Audit Review

These decisions were made during the interactive walkthrough of the audit and
are binding commitments this spec implements. They are listed here verbatim
for traceability.

1. **Evidence Collapse:** Build full evidence review surfaces now. Evidence
   groups as first-class in review UX. Maximum investment, no phasing, no
   intermediate scaffolding. Implemented by §5.1 + §5.2, with §3.2 adding
   the upstream-preservation corollary the original decision did not
   anticipate.
2. **Headline Number Problem:** Adopt a four-way outcome taxonomy
   (`infra-failed`, `operator-incomplete`, `scored-low-quality`,
   `scored-acceptable-quality`). Each benchmark defines its own
   per-benchmark threshold for acceptable vs. low quality. Implemented
   by §6.1.
3. **Infrastructure Contamination:** Provider-pressure diagnostics in
   both per-benchmark JSONs and batch summary. Rate-limit retries,
   timeout counts, budget consumed, no-submission exits, plus
   enforcer-level signals added in §6.3 after the new data surfaced
   them. Implemented by §6.3.
4. **Artifact Writing Drag:** Investigate operator logs before building
   a fix. **The investigation is partially discharged** — §3.1 shows the
   failing check is `writes_truthful_benchmark_run_artifacts` (not
   `writes_benchmark_run_artifacts` as the audit assumed) and that it
   only fails on clinc150. The specific mismatched field and root cause
   are still unknown and are tracked in §7.3. Implemented by §5.3.
5. **Review Lift As Primary Metric:** Both: report lift explicitly AND
   make reviewed quality the primary product optimization target.
   "Workflow lift" as a phrase is replaced by the named fields in §6.4
   (`review_lift_in_workflow`, `workflow_pipeline_delta`, etc.) so
   different stage transitions are never conflated. Implemented by
   §5.6 (process) and §6.4 (reporting).
6. **Slice Overread Risk:** Hard slices for all 6 benchmarks AND
   increase base slice sizes. Current sizes (16 for clinc150/banking77,
   12 for goemotions, 8 for scifact, 6 for feverous) are too small for
   statistical meaning. Implemented by §6.5.
7. **Missing Operator Scores:** Re-run the full batch under
   conservative workers. (Done — see §2. 5/6 benchmarks now scored.
   Hatexplain still unscored and is now a dedicated P0 fix requiring
   investigation before implementation, not just another rerun.)
   Implemented by §5.4 + §7.2.
8. **Statistical Rigor:** 5 repeated runs per benchmark in full
   evaluation mode. Runner gets a `--repeats` flag, default 1 for
   quick mode, 5 for full evaluation. Implemented by §6.6.
9. **Workflow Scaffolds:** Two evaluation modes. Preset workflow mode
   tests product quality; open workflow mode tests operator autonomy.
   Both are first-class. Implemented by §5.7 (modes) and §5.5
   (templates as standalone product surface).
10. **Label vs. Audit Quality:** Always show label score and checklist
    score side-by-side in summary tables. Never show combined score
    alone. Implemented by §6.2.

## 5. Product Improvements

These are the product changes MoLabel needs to make. Each has a primary goal,
a clear definition of done, and the specific benchmarks it is expected to
move.

### 5.1 P0 — Evidence Preservation Through workflow_autorun Storage

**Goal:** Structured evidence emitted by the model must survive the
`molabel_model → workflow_autorun` transition — the stage that stores the
model's proposal as a workflow record. When the model emits evidence groups
or atoms, those groups must still be present, structurally intact, and
scoreable at `workflow_autorun` and every downstream stage.

**Evidence this is needed:**
- feverous `molabel_model` evidence_f1 = 0.9565 →
  `workflow_autorun` evidence_f1 = 0.0000. Loss of 0.9565 in a single hop.
- scifact `molabel_model` evidence_f1 = 1.0000 →
  `workflow_autorun` evidence_f1 = 0.0000. Total collapse in a single hop.
- In both cases `workflow_reviewed` and `operator_reviewed` remain at
  0.0 — not because review is lossless, but because there is nothing left
  to lose. On this data every reviewer accepted every record unedited
  (feverous 6/6, scifact 8/8), so reviewer behavior is unobservable.
- The evidence values at `molabel_model` come from the same underlying
  structured-output call that the workflow invokes. The delta across that
  hop must therefore be caused by something in the workflow's proposal-
  storage path, not by the model.

**Definition of done:**

Two independent gates must hold on both feverous and scifact at the
stability slice:

1. **Preservation gate (primary):**
   `workflow_autorun.evidence_f1 >= molabel_model.evidence_f1 - 0.10`.
   The workflow-stored proposal must not lose more than 10 evidence
   points relative to the same model call scored directly at
   `molabel_model`. This is the bug localized by §3.2 and §7.1.
2. **Review non-regression gate:**
   `workflow_reviewed.evidence_f1 >= workflow_autorun.evidence_f1 - 0.05`.
   The review step must not silently degrade evidence structure
   regardless of whether the reviewer edited anything.

Plus two joint-score targets:

3. `feverous_score_proxy` at `workflow_reviewed` ≥ `0.3333`
   (paper-direct parity) on the stability slice.
4. `scifact_joint_score_proxy` at `workflow_reviewed` ≥ `0.5` on the
   stability slice.

Plus a test-the-test requirement:

5. An integration test in `tests/e2e/` runs both benchmarks and
   asserts the preservation gate on the stability slice. The test
   must **fail today** against unfixed code — on current data,
   `0.0 >= 0.9565 - 0.10 = 0.8565` is false for feverous and
   `0.0 >= 1.0 - 0.10 = 0.9` is false for scifact, so both assertions
   fail. If the gate passes against unfixed code, the test is
   malformed and does not satisfy this DoD.

**Owner files to touch (likely — verify before editing):**
- The `workflow_autorun` storage path. Trace from the harness's
  `harness.run_agent_prompt` call in
  `tests/e2e/tier1_pipeline/test_live_grounded_operator_benchmarks_real_llm.py`
  into the code that accepts structured-output JSON and persists it as a
  workflow record. The lossy hop is somewhere in that persistence step.
- The review submission serializer in `packages/molabel-core` (where
  `harness.load_latest_review_submissions()` reads from). Evidence atoms
  must round-trip through this serializer without being flattened.
- Any workflow-template default used by the grounded operator harness for
  evidence-shaped benchmarks — if the template strips or re-shapes fields
  on write, that would explain the collapse.

**Investigation required before implementation: §7.1.** Do not begin
implementation without the investigation output.

**Why this is P0:** The audit's top-priority concern was evidence handling.
The fresh data localizes the bug to the proposal-storage step, not the
review step. A fix here unlocks every future evidence-shaped benchmark.
Without it, any investment in evidence review UX is building on a
foundation that discards its inputs.

### 5.2 P0 — Evidence Review Surfaces (Groups As First-Class)

**Goal:** Evidence groups are first-class entities in the review experience.
The operator can see, edit, validate, and submit structured evidence with
the same ergonomics that label editing has today. Structural validation
blocks submission when a required group is incomplete.

**Decision taken:** Build the full review surface now. No phasing. No
intermediate templates or validation-only gates that delay the UX work.

**Scope decision required up front (output of §7.5 investigation):**
- Does the review surface land in the React frontend (`frontend/`), in the
  CLI review flow (`packages/molabel-core` / `packages/molabel-app`), or in
  both? The answer determines whether "review UI" in this section means
  the Tauri desktop shell, the CLI, or both.
- Does the current evidence atom schema already carry stable anchor ids
  for sentence anchors and table-cell anchors? If yes, the work is
  rendering; if no, the work includes schema extension and a migration.
- Where does structural validation run — CLI submit, backend API handler,
  frontend form, or all three? Policy: at the system boundary where the
  review submission is persisted (backend), with mirrored client-side
  feedback for UX only.
- What is the formal definition of "complete support path" per benchmark
  family? For feverous and scifact, this must be derived from each
  benchmark's authority pack gold schema, not invented in the UI layer.

**Definition of done:**
- Review surface (CLI and/or frontend per scope decision above) renders
  grouped evidence sets explicitly, not as a flat bag.
- Evidence atom editing with stable anchor ids; sentence and table-cell
  anchors visually and structurally distinct where the benchmark family
  requires.
- Structural validation lives at the review submission persistence layer.
  If a task's authority pack requires a complete support path and the
  submitted evidence has no complete path, the submission is rejected with
  an actionable error that names the missing atoms.
- Workflow defaults are benchmark-family-aware: evidence benchmarks
  default to evidence-first workflow templates, not classification
  defaults.
- feverous and scifact reviewer workflow templates live in the product,
  are referenced by the grounded benchmark harness, and are documented in
  the grounded benchmark catalog.
- A reviewer integration test exists in which a record with a
  structurally incomplete evidence set fails to submit, and the same
  record with a complete set submits successfully.

**Investigation required before implementation: §7.5.** Do not begin
implementation without the investigation output.

**Why this is P0 alongside 5.1:** 5.1 localizes where evidence is dropped
in the pipeline and fixes storage. 5.2 gives the reviewer the tools to
repair imperfect proposals after storage is fixed. Shipped together, they
address both layers of the evidence failure. Shipped separately, either
would appear to "succeed" while leaving evidence benchmarks still broken
(5.1 alone has no editing UX; 5.2 alone builds on a foundation that
discards its inputs).

### 5.3 P0 — Truthfulness Enforcement For Benchmark Run Artifacts

**Goal:** The operator cannot submit a benchmark run artifact that makes
claims inconsistent with what actually happened in the run.

**Evidence this is needed:**
- clinc150 `writes_benchmark_run_artifacts = PASS` but
  `writes_truthful_benchmark_run_artifacts = FAIL`, on a run where the
  label score is a perfect 1.0.
- Banking77 and goemotions pass both checks in the same batch, so this is
  a clinc150-specific artifact-truth problem — not a generic artifact
  schema problem.

**Definition of done:**
- When the operator writes a benchmark run artifact, a validator compares
  claimed values (scores, counts, status) against the actual run data
  tracked by the harness. Inconsistencies produce actionable CLI errors
  and block the checklist item from passing silently.
- A new helper (or existing helper, if one exists) exposes
  run-truth-values directly to the operator so there is no path where the
  operator has to invent numbers.
- clinc150 passes `writes_truthful_benchmark_run_artifacts` on the next
  full batch.

**Investigation required before implementation: §7.3.** Do not begin
implementation without the investigation output.

**Why this is P0:** Truthfulness failures erode the audit value of the
entire checklist. A benchmark that silently tolerates inaccurate operator
self-reports is not measuring what it claims to measure.

### 5.4 P0 — Hatexplain Paper-Direct And Agent-Exit Bug

**Goal:** Hatexplain produces a scored operator run under 1 worker without
dedicated rescue measures.

**Evidence this is needed:**
- 2026-04-12 batch: hatexplain FAIL in 121,211 ms with 0 API calls at
  1 worker, while 5 other benchmarks in the same sequential batch
  completed cleanly.
- Observed failure surface: agent exits code 0, no review submissions,
  test fails on `assert review_submissions`.
- Two candidate root causes visible in the raw data, not yet
  disambiguated: (a) paper-direct baseline's first call hits the 120s
  per-call timeout in the adapter, (b) the structured-output enforcer
  burns attempts against a rationale schema the model keeps emitting
  slightly off (raw output shows `attempts=3, used_native=True` and a
  `validation_errors` list containing target-community enums).
- This is **not** rate limiting: 1 worker, 5 sibling benchmarks
  succeeding, no 429 indicators.

**Definition of done:**
- Hatexplain's paper-direct baseline either completes under the budget
  or explicitly skips with a clear diagnostic that propagates into the
  provider-pressure block (§6.3), rather than silently eating the agent
  budget.
- The single-prompt operator run for hatexplain loads the scenario,
  makes at least one API call, and submits at least one review record
  in **5 out of 5** repeats under `--repeats 5` (§6.6). Zero of five
  is a failure; anything less than 5/5 is a failure.
- Hatexplain appears in the next full-evaluation batch with a scored
  outcome under the four-way taxonomy (§6.1) — specifically NOT
  `infra-failed` or `operator-incomplete`. The actual label score may
  be low; the exit bar here is that hatexplain is producing a
  trustworthy score at all.
- The root cause is documented in a short note in `docs/research/`
  alongside this spec. A one-off fix that does not explain why the
  failure happened does not satisfy DoD.

**Reproducibility gate:** The current diagnosis is based on a single
failing run. §7.2 must reproduce the failure in isolation **at least
twice** before attributing it to a specific root cause. If reproduction
produces different failure signatures across attempts, the investigation
must enumerate each and the fix must address all observed modes, not
only the one seen on 2026-04-12.

**Investigation required before implementation: §7.2.** Do not begin
implementation without the investigation output.

**Why this is P0:** Two benchmarks in the suite test structured output
patterns (rationale spans for hatexplain, grouped evidence for
feverous/scifact) that are strategically critical. Having one of them
consistently fail means every product decision is informed by 5/6
benchmarks, and the missing one is exactly the one covering moderation
with rationales — a target application family.

### 5.5 P1 — Workflow Templates As A Standalone Product Surface

**Goal:** Extract the workflow scaffolds built inside 5.1/5.2/5.4 into a
user-facing, documented, discoverable product surface — not only as
benchmark harness presets but as templates that a product user can pick
when starting a workflow for their own data.

**Scope:**
1. Classification + multi-label review templates (already working in the
   benchmark data for clinc150, banking77, goemotions; this item extracts
   those defaults into a named, documented product surface).
2. Evidence verification with grouped sets — **the template itself is
   built as part of 5.2**; this item is the product packaging, discovery,
   and documentation layer on top of that work.
3. Rationale-bearing moderation — **built as part of 5.4**; same
   relationship.

**What 5.5 adds beyond 5.1/5.2/5.4:** Those items build the scaffolds as
benchmark-facing infrastructure. 5.5 is the work to make those scaffolds
first-class product features:
- Named template identifiers exposed through the public CLI (`molabel
  workflow new --template evidence-verification`, etc.).
- User-facing documentation in the product docs (not only the benchmark
  catalog).
- Template metadata: what task family, which MoLabel capabilities the
  template relies on, which benchmark validates it.
- Template versioning so benchmark harness and product users cannot drift
  out of sync.

**Why P1 and not P0:** The scaffolds themselves are P0 work inside
5.1/5.2/5.4. The product packaging can ship after the scaffolds are
validated by benchmark runs.

### 5.6 P1 — Reviewed Quality As The Primary Internal Metric

**Goal:** MoLabel's internal dashboards, roadmap priorities, and benchmark
goal-setting all use `operator_reviewed` as the headline quality metric,
not `workflow_autorun` or `molabel_model`.

**Definition of done:**
- Every benchmark report exposes the six named lift metrics from §6.4
  (`model_lift_vs_paper`, `autorun_lift_vs_model`, `review_lift_in_workflow`,
  `operator_review_delta`, `workflow_pipeline_delta`, and
  `headline_review_lift`). The internal "headline lift" reported in
  product dashboards is `headline_review_lift = review_lift_in_workflow =
  workflow_reviewed - workflow_autorun`, because that is the delta
  attributable to MoLabel's review step in isolation of the model and
  workflow-setup quality.
- Product goal setting is phrased in terms of `operator_reviewed`
  quality. No ship-it-because-the-model-looks-good paths.
- The audit's current blind spot — that the most product-relevant signal
  is currently implicit — is closed.

**Terminology note:** §2.2 and earlier informal language called banking77's
`molabel_model → workflow_reviewed` delta of +0.2031 a "workflow lift."
That delta combines two hops (model proposal improvement inside the
workflow, then reviewer edits) and is NOT the same as
`review_lift_in_workflow` defined here. Readers of this spec should use
the §6.4 names going forward; informal mentions of the +0.2031 number
refer to the combined `molabel_model → workflow_reviewed` delta, which
§6.4 names `workflow_pipeline_delta`.

### 5.7 P2 — Two Evaluation Modes: Preset Workflow And Open Workflow

**Goal:** Make the existing "open" mode (agent infers workflow from one
short prompt) live alongside a new "preset" mode (agent receives a
benchmark-family workflow scaffold).

**Why both:**
- Open mode measures operator autonomy: can the agent figure out how to
  work the product with minimal guidance?
- Preset mode isolates product quality from operator capability: given
  the right workflow, how good is MoLabel?
- The current benchmark only runs open mode. Adding preset mode does not
  weaken the existing benchmark; it adds a second comparable axis.

**Definition of done:**
- The benchmark harness supports a `--mode preset|open` flag (or
  equivalent), defaulting to `open` for continuity with today's runs.
- In `preset` mode, each benchmark's scenario loads a benchmark-family
  workflow template (from the templates built in §5.1/§5.2/§5.4/§5.5)
  and the agent starts from that template instead of inferring one
  from a single short prompt.
- A full evaluation batch can run both modes and produce two
  independently-reported sets of scores in the summary. The outcome
  taxonomy (§6.1) and lift metrics (§6.4) apply to each mode
  separately.
- At least one published evaluation run demonstrates a measurable
  score difference between the two modes on at least one benchmark
  (otherwise the new axis is not providing signal).

**Why P2:** The existing open mode gives enough signal for current
product decisions. Adding preset mode is a net improvement in benchmark
informativeness but does not block any of the product fixes above.

## 6. Benchmark Program Improvements

These are changes to the benchmark system itself, independent of the
product changes in §5.

### 6.1 P0 — Four-Way Outcome Taxonomy With Per-Benchmark Thresholds

**Goal:** Every live benchmark run ends in one of four named outcomes.
The outcome is the primary headline, not pass/fail.

- `infra-failed`: provider, network, budget, adapter, or enforcer error
  prevented a scored result from being produced. Must be justified by at
  least one non-zero signal in the provider-pressure block (§6.3).
- `operator-incomplete`: the run reached the agent cleanly but the agent
  produced no review submissions or partial submissions; no meaningful
  label score. The distinguishing feature is agent-side empty output,
  not infrastructure failure.
- `scored-low-quality`: a scored result exists but falls below the
  benchmark's acceptable threshold.
- `scored-acceptable-quality`: a scored result at or above the
  benchmark's acceptable threshold.

**What counts as an "infra" signal for `infra-failed`:** Any non-zero
value in these provider-pressure fields from §6.3:
- `api_calls_total == 0` combined with at least one of
  `timeout_count > 0`, `rate_limit_retries > 0`, `budget_exhausted`, OR
- `enforcer_timeout_count > 0` (structured-output enforcer exhausted
  its internal retry/timeout budget), OR
- `adapter_error_count > 0` (adapter returned an error code).

The hatexplain 2026-04-12 failure must classify as `infra-failed` under
this definition because the enforcer-internal failure is precisely the
kind of infrastructure pressure the taxonomy is meant to name. If
`enforcer_timeout_count` is not wired yet, §6.3's DoD requires it to be
wired as part of that work item — §6.1 and §6.3 ship coherent or not
at all.

**Disambiguation rules when multiple conditions are true:**
- If both infra signals and a scored result are present, classify as
  the scored outcome (the run produced something usable despite
  pressure). Record the infra signals as a warning in the report.
- If no infra signals AND the agent exited code 0 AND
  `review_submissions` is empty, classify as `operator-incomplete`.
- Threshold is applied to the MEAN over repeats (see §6.6), not any
  single repeat.

**Threshold ownership:** Each benchmark's authority pack defines its own
`acceptable_operator_label_score` and optional
`acceptable_checklist_score`. The thresholds are part of the benchmark
definition, not universal constants. Easy benchmarks (clinc150) can
demand near-perfect. Hard benchmarks (feverous) set a lower but
meaningful bar.

**Definition of done:**
- Every per-benchmark JSON includes an `outcome` field with one of the
  four values.
- The batch `summary.md` header reports counts by outcome, not just
  passed/failed.
- Each benchmark authority pack has a threshold block. A run below the
  threshold classifies as `scored-low-quality` even if pytest returned 0.
- feverous in the 2026-04-12 batch retroactively classifies as
  `scored-low-quality`, not `pass`.
- Hatexplain in the 2026-04-12 batch retroactively classifies as
  `infra-failed`, not ambiguous.
- Goemotions's prior (pre-2026-04-12) batch failure retroactively
  classifies as `infra-failed`.

### 6.2 P0 — Label Score And Checklist Score Side-By-Side Everywhere

**Goal:** Readers never see a combined operator score alone. The label
score and checklist score are always visible next to it.

**Definition of done:**
- `summary.md` table columns: benchmark, slice size, label score,
  checklist score, combined, outcome.
- Per-benchmark JSON reports include label and checklist as top-level
  fields (not only inside a nested structure).
- No report reduces a run to a single number.

### 6.3 P0 — Provider-Pressure And Infrastructure Diagnostics

**Goal:** Every benchmark run carries structured data on provider-level
pressure, enforcer-level pressure, and infrastructure events. These live
in both the per-benchmark JSON and an aggregated block in the batch
summary.

**Fields required (all mandatory, populated on every run including
failed runs):**

Provider-side:
- `api_calls_total` — all API calls attributed to the run
- `api_calls_agent` — calls from the agent-driven operator run
- `api_calls_paper_direct` — calls from the paper-direct baseline
- `rate_limit_retries` — count of 429 retries
- `timeout_count` — count of calls that timed out at the adapter layer
- `adapter_error_count` — non-429, non-timeout adapter errors
- `budget_spent_usd`
- `budget_exhausted` (bool)

Enforcer-side (structured-output layer):
- `enforcer_attempts_total` — total schema-validation retry attempts
  across all calls
- `enforcer_attempts_max` — max attempts observed on any single call
- `enforcer_validation_failures` — count of calls that exhausted
  enforcer attempts without producing valid output
- `enforcer_timeout_count` — count of enforcer runs that exhausted
  their internal timeout budget (distinct from `timeout_count` above;
  adapter vs enforcer layer)

Run-level:
- `no_submission_exit` (bool) — agent exited with empty
  `review_submissions`
- Optional per-stage breakdown where available

**Data collection path:**
- Provider-side fields: the Anthropic/MinMax adapter already exposes
  retry and error counts; the harness must aggregate them into the
  report block. Confirm collection path before implementation.
- Enforcer-side fields: `StructuredOutputEnforcer` already tracks
  attempt counts and validation errors internally (visible in raw
  output as `attempts=N, used_native=True, validation_errors=[...]`);
  the harness must capture the final values into the report block.

**Definition of done:**
- These fields populate for every run, including failed runs. Zero
  values are explicit zeros, not missing keys.
- The four-way taxonomy (§6.1) uses these fields to justify
  `infra-failed` classification. A run cannot be marked `infra-failed`
  without at least one of: `rate_limit_retries > 0`, `timeout_count >
  0`, `adapter_error_count > 0`, `enforcer_timeout_count > 0`,
  `enforcer_validation_failures > 0`, or `budget_exhausted == true`.
- Hatexplain's 2026-04-12 failure, replayed against this schema,
  populates at least one non-zero infra signal (expected:
  `enforcer_timeout_count > 0` OR `timeout_count > 0` depending on
  which layer the 120s actually fired in).
- The batch summary has a "Provider And Enforcer Pressure" section
  aggregating all benchmarks.

### 6.4 P0 — Named Lift And Delta Metrics Per Stage Transition

**Goal:** Every per-benchmark report includes named, consistently-defined
deltas for each stage transition, not just raw stage scores. This closes
both the reporting gap (audit §7.2) and the audit's own inability to
compute review lift without a consistent tax schema (§2.2 footnote [1]).

**Dependency:** §6.7 (tax schema unification) must land first so that all
benchmarks emit a consistent stage-transition record. The audit's raw
reports currently use two different schemas.

**Fields required (all positive sign = stage gained quality; negative =
stage lost quality; this is the **opposite** sign of `workflow_tax` so
that reading the value directly matches intuition):**

- `model_lift_vs_paper = molabel_model - paper_model`
- `autorun_lift_vs_model = workflow_autorun - molabel_model`
- `review_lift_in_workflow = workflow_reviewed - workflow_autorun`
- `operator_review_delta = operator_reviewed - workflow_reviewed`
- `workflow_pipeline_delta = workflow_reviewed - molabel_model` —
  two-hop combined delta, provided for continuity with today's
  `workflow_tax` readings. The spec's earlier informal use of "+0.2031
  workflow lift" for banking77 refers to this field.
- `headline_review_lift = review_lift_in_workflow` — duplicated under
  a named alias so product dashboards can depend on one field name.

**Why these names matter:** The audit and earlier drafts of this spec
used "workflow lift" and "review lift" interchangeably for different
transitions. §6.4's naming is chosen so each field corresponds to exactly
one stage hop, except the two explicitly labeled combined deltas.
Informal language in §2, §3, §5 should be read through these names
going forward.

**Definition of done:**
- All six fields (`model_lift_vs_paper`, `autorun_lift_vs_model`,
  `review_lift_in_workflow`, `operator_review_delta`,
  `workflow_pipeline_delta`, `headline_review_lift`) appear in every
  per-benchmark JSON.
- `summary.md` includes a lift column labeled `headline_review_lift`.
- Banking77's `workflow_pipeline_delta = +0.2031` and
  `headline_review_lift = +0.0000` (because workflow_autorun =
  workflow_reviewed = 0.9323) both appear in the report. Readers can
  immediately see that banking77's two-hop gain is driven by model
  correction at autorun, NOT by review edits — a fact the current
  reports do not surface.
- Goemotions's `autorun_lift_vs_model = -0.2259` (drop) and
  `headline_review_lift = +0.2259` (recovery) both appear, making
  visible that the review step is where goemotions gains quality.

### 6.5 P0 — Slice Size Increase And Hard-Slice Variants For All Six

**Goal:** Every benchmark has two slices: a stability slice and a hard
slice. Both grow from current sizes to at least statistically meaningful
sizes.

**Current sizes to replace:**
- clinc150: 16 → stability 40, hard 40
- banking77: 16 → stability 40, hard 40
- goemotions: 12 → stability 40, hard 40
- feverous: 6 → stability 20, hard 20
- scifact: 8 → stability 20, hard 20
- hatexplain: — → stability 40, hard 40

Sizes above are floors, not ceilings. They are chosen to (a) give scores
at least one significant figure of statistical meaning and (b) not
explode wall time under 5-repeat evaluation mode.

**Hard slice curation direction (from audit):**
- clinc150: confusion-rich intents including near-duplicates and
  OOS edge cases.
- banking77: confusion-heavy fine-grained intent pairs.
- goemotions: high-overlap emotion combinations, valid empty sets,
  duplicate labels.
- feverous: multi-hop evidence across table and text anchors.
- scifact: grouped sentence evidence with partial supports.
- hatexplain: rationale spans that disagree with category labels,
  target-community edge cases.

**Definition of done:**
- Each benchmark authority pack exposes `stability_slice` and
  `hard_slice` selectors.
- The batch runner runs both slices by default in evaluation mode.
- Report layouts separate stability and hard scores and never average
  them into a single benchmark number.

**Investigation required before implementation: §7.4.** Do not begin
implementation without the investigation output.

### 6.6 P0 — Repeated Runs And Variance Reporting

**Goal:** The runner supports a `--repeats` flag. In quick mode (default
1) the current behavior is preserved. In evaluation mode (5) each
benchmark runs five times and the report aggregates mean, min, max,
standard deviation, and infra-invalid count.

**Definition of done:**
- `scripts/run_all_benchmarks.py` accepts `--repeats N` where N defaults
  to 1.
- At `--repeats 5`, reports include a `distribution` block per benchmark
  with the five raw scores plus aggregates (mean, min, max, stdev,
  infra-invalid count).
- The four-way taxonomy (§6.1) uses repeat-level data: a benchmark is
  only `scored-acceptable-quality` if the MEAN over repeats clears the
  threshold, and the standard deviation is reported alongside.
- Each repeat is an independent test invocation that re-fetches the
  slice records and re-invokes the agent. No state is shared across
  repeats within the runner.

**Paper-direct baseline handling across repeats:** The paper-direct
baseline is deterministic for a fixed model and temperature, and
represents a non-trivial fraction of per-run cost. The baseline is
**cached at the batch level**, not per-repeat: the runner executes the
paper-direct baseline once per benchmark per batch and scores every
repeat's workflow/operator stages against the same cached baseline.
- If a benchmark's model profile or slice selection changes between
  batches, the cache is invalidated and re-run.
- If a repeat's paper-direct cache entry is missing (e.g., first run of
  a new slice), the runner executes it lazily and caches for the
  remaining repeats.
- This halves the effective cost of evaluation mode relative to a naive
  "re-run everything" implementation.

**Cost note:** At current benchmark durations (~400s–600s per benchmark
at 1 worker), with paper-direct caching, five repeats of all six
benchmarks is approximately 2–3 hours of wall time per full evaluation.
This is acceptable as a full-evaluation mode, not as a CI default.

### 6.7 P0 — Tax Schema Unification And Structured Per-Benchmark JSON

**Goal:** All benchmarks emit stage transitions on a single consistent
schema, and per-benchmark JSON reports contain structured score data
alongside (or instead of) the current pytest stdout captures.

**Evidence this is needed:**
- §2.2 footnote [1]: `clinc150` reports
  `workflow_tax (molabel_model → workflow_autorun)` plus a separate
  `review_lift (workflow_reviewed → workflow_autorun)` line, while
  `banking77`, `goemotions`, `feverous`, `scifact` fold the two hops
  into a single `workflow_tax (molabel_model → workflow_reviewed)`.
  The values look comparable in a table but are defined over different
  stage transitions. This is a real schema bug in the benchmark
  harness, not just a reporting quirk.
- Current per-benchmark JSONs (see
  `reports/bench-20260412-124841/{benchmark}.json`) contain keys
  `benchmark, test_file, k_filter, command, exit_code, passed,
  duration_seconds, stdout, stderr`. All score, checklist, and tax
  data live inside free-text pytest stdout. Every §6 item that says
  "the per-benchmark JSON includes field X" is currently impossible to
  implement without either parsing stdout or changing the writer.

**Definition of done:**

1. Every scored stage emits all four transition deltas in the same
   named form:
   - `model_tax` — always `paper_model → molabel_model`
   - `autorun_tax` — always `molabel_model → workflow_autorun`
   - `review_tax` — always `workflow_autorun → workflow_reviewed`
   - `operator_tax` — always `workflow_reviewed → operator_reviewed`
   Sign convention matches the current raw reports (positive = loss)
   but §6.4's `*_lift_*` fields expose the inverse sign for readability.
2. The separate `workflow_tax` and `review_lift` lines that clinc150
   currently emits are replaced by the four-field schema above. No
   benchmark emits a bespoke variant.
3. Per-benchmark JSON reports include a top-level `scores` block with
   structured fields (stage scores, tax fields, lift fields, checklist
   items pass/fail, outcome, distribution, provider-pressure block).
   Stdout and stderr may remain alongside as debug aids but must not be
   the only source of truth for any downstream consumer.
4. `scripts/run_all_benchmarks.py` either reads a structured artifact
   the test emits during run (preferred) or parses stdout once into
   structured JSON. The structured JSON is the report contract; raw
   stdout is a debug aid.
5. The 2026-04-12 batch's data can be backfilled onto the new schema
   so historical comparisons remain possible. Backfill may be partial
   (e.g., provider-pressure block may be zero-filled for pre-schema
   runs) but the outcome classification and scores must survive.

**Why this is P0:** §6.1, §6.2, §6.3, and §6.4 all assume structured
per-benchmark data and a consistent tax schema. None of them are
buildable without this item. Treating this as implicit scope risk
guarantees the §6 band blows its definition of done.

## 7. Investigation Tasks Before Implementation

These are research tasks that must land before the corresponding product
fix is implemented. Each one is a standalone investigation with a
specific question and a specific artifact output.

### 7.1 Trace Evidence Loss In The workflow_autorun Storage Path

**Question:** Exactly where does evidence atom data disappear between
the `molabel_model` stage (which scores feverous at evidence_f1 =
0.9565 and scifact at 1.0000) and the `workflow_autorun` stage (which
scores both at 0.0000)?

**The evidence already shows this is NOT a review-stage problem.**
`workflow_autorun` is already at zero on both benchmarks. Every
downstream stage is trivially zero-delta. The lossy hop is
specifically the step that takes the structured model output and
stores it as a workflow proposal record.

**Method:**
- Run feverous in isolation with verbose logging.
- Capture four artifacts per record:
  1. Raw structured-output JSON returned by the adapter at the
     `molabel_model` stage (same data that scores 0.9565 on
     evidence_f1 directly).
  2. The workflow proposal record after it has been stored as
     `workflow_autorun` output (inspect whatever in-memory or
     on-disk representation the harness uses).
  3. The review submission payload loaded by
     `harness.load_latest_review_submissions()`.
  4. The scored artifact passed into `score_grounded_stage`.
- Diff artifact 1 → artifact 2: the first place evidence is dropped
  is the primary bug site. If evidence atoms are absent in artifact 2
  but present in artifact 1, the store step is lossy.
- Verify with scifact (independent reproduction with different
  evidence shape).
- Confirm the reviewer accept/edit breakdown matches the current
  data (6/6 unedited on feverous, 8/8 on scifact) and note that this
  means the review step currently has no observable edit behavior.

**Output:** A short note in `docs/research/` identifying the lossy
step with the specific file/function where evidence is dropped.
The note must also identify whether the issue is:
- the workflow storage schema flattening evidence atoms, OR
- the workflow template defaults not carrying evidence through on
  submit, OR
- the scorer's view of the workflow record vs the underlying storage
  format (could be a read-side issue rather than a write-side issue).

**Blocks:** 5.1 (Evidence Preservation).

### 7.2 Diagnose Hatexplain's Paper-Direct And Agent-Exit Failure

**Question:** Why does hatexplain's first paper-direct structured-output
call fail within the 120s per-call budget, and why does the agent
subsequently exit code 0 without submitting any review records?

**Reproducibility gate:** The failure must be reproduced **at least
twice** in isolated hatexplain-only runs before attributing it to any
specific root cause. If different failure signatures appear across
reproductions, enumerate all of them and ensure the fix addresses each.

**Method:**
- Run hatexplain in isolation at least twice with verbose logging.
- For each reproduction, capture:
  - per-call adapter timing (did the call return quickly with a
    validation failure, or did it hang until the 120s timeout?)
  - full `StructuredOutputEnforcer` trace: `attempts` counter,
    `used_native` flag, per-attempt `validation_errors` payloads,
    final `is_valid` status
  - prompt token counts, schema JSON, adapter configuration
  - agent stdout/stderr during the single-prompt operator run (why
    does it exit with code 0 and no submissions?)
  - agent-side transcript of what the agent saw after the paper-direct
    baseline warning was added to `ctx.warnings`
- Test both hypotheses explicitly:
  1. **Latency:** Does the adapter actually take the full 120s, or is
     the time spent in enforcer retry loops? Measure wall-clock time
     per adapter call.
  2. **Validation retries:** Does the enforcer exhaust its attempt
     budget on schema validation failures? The 2026-04-12 raw output
     contains `attempts=3, used_native=True` and a `validation_errors`
     list with target-community enums (`Men`, `Minority`,
     `Nonreligious`, `Refugee`, `Women`, `Other`). If enforcer retries
     are burning the time, the fix is schema-side or prompt-side, not
     adapter-side.
- Compare against feverous and scifact (which succeeded in the same
  batch) to isolate what is structurally different about hatexplain.

**Output:** A short note identifying the root cause(s) for each
reproduction, which hypothesis each confirms or refutes, and a
specific fix recommendation. If the enforcer-retries hypothesis is
correct, the fix lives in the hatexplain schema or prompt, not in
the adapter. If the latency hypothesis is correct, the fix is a
retry/fallback policy in the adapter. The note must state which.

**Blocks:** 5.4 (Hatexplain Bug).

### 7.3 Diagnose The Clinc150 Artifact Truthfulness Failure

**Question:** Which specific field in the clinc150 benchmark run artifact
is not truthful, and how does the operator arrive at the wrong value?

**Method:**
- Read the clinc150 operator logs and the artifact the operator wrote.
- Run the `writes_truthful_benchmark_run_artifacts` check against that
  artifact and surface the exact mismatch.
- Determine whether the operator had the correct data and miscopied it,
  or did not have access to the correct data at all.

**Output:** A short note identifying the mismatch and the fix path
(expose the right data, enforce at write time, or both).

**Blocks:** 5.3 (Truthfulness Enforcement).

### 7.4 Identify The Minimum Safe Slice Sizes

**Question:** For each benchmark, what is the smallest slice size that
preserves representativeness and gives a single-repeat score at least
one significant figure of statistical meaning?

**Method:**
- For each benchmark, look at the paper-reported evaluation set size and
  the stratification criteria.
- Propose slice sizes that respect those criteria and do not explode
  wall time beyond the three-hour full-evaluation target.
- Confirm size choices against §6.5's floors.

**Output:** Final slice sizes, committed to each benchmark's authority
pack. If any benchmark justifies a smaller size than §6.5's floor, it
is documented in the authority pack with rationale.

**Blocks:** 6.5 (Slice Size Increase).

### 7.5 Evidence Review Surface Design Decisions

**Question:** Before building §5.2, what are the concrete scope
boundaries?

**Decisions needed as output:**
- Target surface: CLI only, frontend only, or both. Recommendation
  expected to be "both," but the investigation must confirm and scope
  what each surface actually owns.
- Current state of evidence atom schema: does it already carry stable
  anchor ids for sentence anchors and table-cell anchors? If not, the
  §5.2 work includes schema extension and a migration, and the spec
  must be updated to reflect that.
- Authority-pack definition of "complete support path" per benchmark
  family. Read feverous and scifact authority packs directly and
  document what structural validity means for each.
- Where structural validation runs: backend persistence layer
  (preferred) with mirrored client-side feedback, or alternative.
- Relationship to the existing MoLabel review flow: extend, replace,
  or build alongside? This decision should minimize new surface area
  while supporting evidence-first review.

**Method:**
- Read the existing review flow in `packages/molabel-core` and
  `packages/molabel-app`, and the frontend review components in
  `frontend/`.
- Read feverous and scifact authority packs (gold schema, task
  schema).
- Read the e2e test harness to understand how review submissions are
  constructed for evidence benchmarks today.

**Output:** A short design note in `docs/research/` with each decision
above resolved. The note becomes the immediate scope document for
§5.2 implementation.

**Blocks:** 5.2 (Evidence Review Surfaces).

## 8. Sequencing

All §5 P0 items and all §6 P0 items are intended to land together as
one coordinated investment, because they are mutually dependent:

- **§6.7 tax schema unification and structured JSON is a strict
  prerequisite for §6.1, §6.2, §6.3, §6.4.** Those four items all
  assume structured per-benchmark fields and a consistent stage
  transition schema that §6.7 establishes. None are buildable
  without 6.7 first.
- 5.1 Evidence Preservation and 5.2 Evidence Review Surfaces must
  ship together. 5.1 alone leaves the reviewer without tools; 5.2
  alone builds on a foundation that silently drops evidence.
- 6.1 Four-way taxonomy requires 6.3 Provider diagnostics (infra
  classification needs infra metrics, including the enforcer-level
  signals §6.3 adds) and 6.2 label/checklist separation (the
  taxonomy references both).
- 6.5 Slice resizing requires 7.4 Investigation first.
- 5.1 Evidence Preservation requires 7.1 Investigation first.
- 5.2 Evidence Review Surfaces requires 7.5 Investigation first.
- 5.3 Truthfulness Enforcement requires 7.3 Investigation first.
- 5.4 Hatexplain Bug requires 7.2 Investigation first.

Recommended sequence within the P0 band:

1. **Investigation wave.** All five investigation tasks (§7.1, §7.2,
   §7.3, §7.4, §7.5) run in parallel. Each produces a short note
   unblocking one or more P0 fixes. None depend on each other.
2. **Benchmark infrastructure wave.** §6.7 tax schema unification and
   structured JSON lands first. This is a prerequisite for
   everything else in §6.
3. **Benchmark reporting wave.** §6.1 four-way taxonomy, §6.2
   label/checklist separation, §6.3 provider-and-enforcer
   diagnostics, and §6.4 named lift metrics land together. They do
   not depend on §5 fixes and make every subsequent §5 fix easier to
   measure.
4. **Benchmark design wave.** §6.5 slice resizing (depends on §7.4)
   and §6.6 repeated runs land. §6.5 also depends on §6.7's
   structured reporting because hard slices and stability slices
   need to be reported as separate fields, not averaged.
5. **Product fix wave.** §5.3 truthfulness (depends on §7.3), §5.4
   hatexplain (depends on §7.2), and §5.1 + §5.2 evidence
   preservation and review surfaces landing together (depend on
   §7.1 and §7.5).
6. §5 P1 and P2 items afterward.

The benchmark infrastructure and reporting waves (steps 2–4) should
land before the product fix wave (step 5), because the reporting
layer is how the product fix wave's success is measured. Shipping
product fixes first against broken reporting produces untrustworthy
score movement.

## 9. Exit Criteria

This spec is considered successfully executed when **all** of the
following are true on a fresh full-evaluation batch (6 benchmarks × 5
repeats × both stability slice and hard slice):

**Coverage and classification:**
- 6/6 benchmarks produce a scored outcome on both the stability slice
  and the hard slice. Zero are `infra-failed`. Zero are
  `operator-incomplete`.
- Hatexplain appears with a real operator label score on at least the
  stability slice (score may be low; the exit bar here is that
  hatexplain no longer classifies as `infra-failed` or
  `operator-incomplete`).

**Evidence benchmarks:**
- feverous `workflow_autorun.evidence_f1 >= molabel_model.evidence_f1 - 0.10`
  (preservation gate from §5.1) on the stability slice. Additive, not
  multiplicative — same formulation as §5.1 DoD.
- scifact `workflow_autorun.evidence_f1 >= molabel_model.evidence_f1 - 0.10`
  (same preservation gate) on the stability slice.
- feverous `workflow_reviewed.evidence_f1 >= workflow_autorun.evidence_f1 - 0.05`
  (review non-regression gate from §5.1).
- scifact `workflow_reviewed.evidence_f1 >= workflow_autorun.evidence_f1 - 0.05`
  (same review non-regression gate).
- feverous `feverous_score_proxy` at `workflow_reviewed` ≥ `0.3333` on
  the stability slice (paper-direct parity).
- scifact `scifact_joint_score_proxy` at `workflow_reviewed` ≥ `0.5`
  on the stability slice.
- A reviewer integration test for each exists in which a record with
  structurally incomplete evidence fails to submit (§5.2).

**Checklist and truthfulness:**
- All 6 benchmarks pass all 8 checklist items, including
  `writes_truthful_benchmark_run_artifacts`, on the stability slice.
- Clinc150's truthfulness failure is resolved with a documented root
  cause (§7.3).

**Reporting layer:**
- The batch summary classifies each benchmark with a four-way outcome
  (§6.1).
- Every per-benchmark report shows `operator_label_score`,
  `operator_checklist_score`, and `operator_overall_score` as
  explicit top-level fields (§6.2).
- Every per-benchmark report includes the full provider-and-enforcer
  pressure block (§6.3) with all required fields populated. Any
  `infra-failed` classification is justified by at least one
  non-zero signal from that block.
- Every per-benchmark report includes all six named lift/tax fields
  from §6.4 (`model_lift_vs_paper`, `autorun_lift_vs_model`,
  `review_lift_in_workflow`, `operator_review_delta`,
  `workflow_pipeline_delta`, and the `headline_review_lift` alias)
  on the unified schema defined in §6.7. No benchmark still emits the
  bespoke clinc150-style schema.
- `headline_review_lift` is a visible column in the batch summary.

**Statistical rigor:**
- Each benchmark is reported with a `distribution` block containing
  5 raw repeat scores plus `mean`, `min`, `max`, `stdev`, and
  `infra_invalid_count` (§6.6).
- Outcome classification uses the MEAN over repeats, not any single
  run.
- Paper-direct baselines are cached at the batch level (§6.6), not
  re-run per repeat.

**Slices:**
- Both the stability slice and hard slice run to completion and are
  reported separately (not averaged into a single per-benchmark
  number).
- Slice sizes in each authority pack match the sizes determined by
  §7.4 (not smaller, not unjustified).

Until **every** criterion above is met, the spec is in progress. Any
benchmark movement claimed under weaker evidence is to be treated as
provisional.

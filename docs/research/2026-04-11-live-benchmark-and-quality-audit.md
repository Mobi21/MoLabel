# Live Benchmark And Quality Audit

Date: 2026-04-11
Status: Research audit based on latest live real-LLM benchmark evidence
Related:

- `docs/guides/grounded-benchmark-framework.md`
- `docs/guides/grounded-benchmark-catalog.md`
- `docs/guides/grounded-benchmark-authoring-checklist.md`
- `docs/guides/grounded-benchmark-expansion-plan.md`
- `reports/bench-20260411-120747/summary.md`
- `reports/bench-20260411-120747/clinc150.json`
- `reports/bench-20260411-120747/banking77.json`
- `reports/bench-20260411-120747/feverous.json`

## 1. Purpose

This document records a detailed audit of two things:

1. what MoLabel itself most needs to improve in order to improve benchmark
   outcomes honestly,
2. whether the grounded benchmark system is itself a good benchmark program,
   and what should change inside the benchmark system so it measures product
   quality more clearly and more truthfully.

This is not a rewrite of the benchmark framework. It is an audit of the current
live evidence.

## 2. Scope Of Evidence

This audit is grounded in the latest live real-LLM runs completed on
2026-04-11, plus the benchmark framework documents already committed in the
repo.

### 2.1 Live Run Evidence Used

- operator batch summary:
  - `reports/bench-20260411-120747/summary.md`
- operator batch per-benchmark reports:
  - `reports/bench-20260411-120747/clinc150.json`
  - `reports/bench-20260411-120747/banking77.json`
  - `reports/bench-20260411-120747/feverous.json`
  - `reports/bench-20260411-120747/goemotions.json`
  - `reports/bench-20260411-120747/hatexplain.json`
  - `reports/bench-20260411-120747/scifact.json`
- live operator e2e logs from the same session:
  - `tests/e2e/logs/e2e_run_20260411_120749_a0cc5f.jsonl`
  - `tests/e2e/logs/e2e_run_20260411_120749_41391e.jsonl`
  - `tests/e2e/logs/e2e_run_20260411_120749_ae655b.jsonl`
- direct live model-mode result from the same session:
  - `tests/e2e/tier1_pipeline/test_live_grounded_benchmarks_real_llm.py`
  - observed outcome: all six model-mode runs passed
- isolated operator rerun performed after the batch:
  - `goemotions` rerun on the same `claude` path passed end to end

### 2.2 Framework Documents Used

- `docs/guides/grounded-benchmark-framework.md`
- `docs/guides/grounded-benchmark-catalog.md`
- `docs/guides/grounded-benchmark-authoring-checklist.md`
- `docs/guides/grounded-benchmark-expansion-plan.md`

## 3. Executive Verdict

The grounded benchmark system is directionally strong and mostly measuring the
right things.

The product-level conclusion is:

- MoLabel is already operationally credible for live agent-first labeling work.
- MoLabel is strong today on classification-style benchmark families.
- MoLabel is materially weaker on evidence-heavy benchmark families.
- The benchmark program itself is good enough to trust for direction-setting,
  but its current live reporting mixes infrastructure reliability, workflow
  quality, and benchmark semantics too aggressively.

The most important product fact from the latest evidence is not “3/6 operator
benchmarks passed.” That number is too coarse. The more useful reading is:

- direct model-mode live benchmarks passed `6/6`,
- operator-mode live benchmarks produced three clean scored passes in the batch,
- one of the batch failures, `goemotions`, passed immediately when rerun in
  isolation,
- therefore at least part of the observed operator failure surface is benchmark
  infrastructure pressure rather than product semantics,
- while at the same time the scored `feverous` pass proves there is a real
  semantic weakness in evidence handling even when the infrastructure works.

That combination matters:

- classification-style product quality is genuinely strong,
- evidence-heavy product quality is genuinely weak,
- operator-batch reliability was made to look worse than it should have because
  the batch runner was overparallelized.

## 4. Current Scoring Snapshot

### 4.1 Direct Live Model Mode

Latest live model-mode result:

- `clinc150`: pass
- `hatexplain`: pass
- `feverous`: pass
- `banking77`: pass
- `goemotions`: pass
- `scifact`: pass

Interpretation:

- the provider path, structured output path, benchmark loading path, and core
  scorer path are all operationally usable across the current benchmark mix,
- the current bottleneck is not “can MoLabel run live benchmarks at all,”
  because it clearly can.

### 4.2 Latest Operator Batch

Latest operator batch result from `reports/bench-20260411-120747/summary.md`:

- `clinc150`: pass
- `banking77`: pass
- `feverous`: pass
- `goemotions`: fail
- `hatexplain`: fail
- `scifact`: fail

Batch summary:

- `3/6 passed`
- wall time: `577.73s`

### 4.3 Scored Operator Runs Available Now

These are the latest trustworthy operator-stage scores available now. For
`goemotions`, the score comes from the isolated rerun done after the batch,
because the batch failure was infrastructure-driven and did not produce a
scored review artifact.

| Benchmark | Paper / Model | Workflow Autorun | Workflow Reviewed | Operator Label | Operator Overall | Checklist |
|---|---:|---:|---:|---:|---:|---:|
| `clinc150` | `1.0000` | `1.0000` | `1.0000` | `1.0000` | `0.9625` | `0.8750` |
| `banking77` | `0.7917` | `0.8646` | `0.9323` | `0.9323` | `0.9151` | `0.8750` |
| `feverous` | `0.1667` | `0.0000` | `0.0000` | `0.0000` | `0.3000` | `1.0000` |
| `goemotions` | `1.0000` | `0.7966` | `1.0000` | `1.0000` | `0.9625` | `0.8750` |

Benchmarks lacking fresh scored operator outcomes from the latest batch:

- `hatexplain`
- `scifact`

Those two remain live benchmark targets, but the latest batch did not produce a
current high-confidence operator quality score for them.

## 5. What The Scores Actually Mean

### 5.1 `clinc150`

Current reading:

- paper/model is perfect,
- workflow is perfect,
- operator-reviewed labels are perfect,
- only the checklist score drags the overall score below `1.0`.

Implication:

- MoLabel is already production-credible for this benchmark family,
- further work on this family should mostly be about preserving quality,
  reducing operational drag, and preventing regressions,
- this benchmark is now more valuable as a stability sentinel than as a
  frontier-improvement target.

### 5.2 `banking77`

Current reading:

- the raw model baseline is good but not great,
- workflow review improves the result materially,
- operator-reviewed quality remains high,
- the benchmark demonstrates real workflow lift.

Implication:

- this is one of the strongest arguments in favor of MoLabel’s workflow value,
- it shows the product is not only executing model calls, but actually helping
  move output quality upward.

### 5.3 `goemotions`

Current reading from isolated rerun:

- paper/model is perfect,
- raw workflow autorun is imperfect,
- reviewed/operator output reaches perfect label quality,
- checklist is still below perfect due to artifact-writing issues,
- the batch failure was not a benchmark-semantic failure.

Implication:

- this benchmark validates that MoLabel’s review layer can repair imperfect
  multi-label proposals,
- it is also strong evidence that some apparent operator failures were actually
  infrastructure pressure, not product weakness.

### 5.4 `feverous`

Current reading:

- paper/model score is already low,
- verdict accuracy improves during review,
- evidence quality collapses completely in reviewed/operator stages,
- operator checklist remains perfect.

Implication:

- the operational path is not the problem here,
- the product is failing at the exact thing the benchmark is supposed to make
  hard: preserving evidence completeness and grouped evidence semantics,
- this is the single highest-value benchmark family for product improvement.

### 5.5 `hatexplain`

Current reading:

- no fresh final operator score from the latest batch,
- this benchmark is structurally important because it mixes class labels,
  target communities, and token-level rationales,
- it is a good benchmark family in principle because it prevents the system
  from pretending moderation is just one categorical label.

Implication:

- this benchmark should stay,
- but the live operator path for it needs reliability work before its current
  score signal should drive product decisions aggressively.

### 5.6 `scifact`

Current reading:

- no fresh final operator score from the latest batch,
- the benchmark family is extremely valuable because it tests scientific
  claim-verification semantics and grouped sentence evidence,
- the benchmark remains a good benchmark even if the latest run failed early.

Implication:

- this benchmark should stay,
- it is one of the best truthfulness checks in the current suite,
- but the live operator harness needs more reliable execution and more
  benchmark-specific operator support before the batch result should be read as
  a clean product-quality score.

## 6. Product Audit: What MoLabel Most Needs To Improve

This section is about improving MoLabel itself, not changing the benchmark to
be easier.

### 6.1 Highest Priority: Evidence Review And Evidence Editing

This is the clearest real product gap.

Why this is the highest priority:

- `feverous` shows the system can preserve operational discipline and still
  fail semantically on evidence,
- reviewed verdicts can become correct while evidence remains unusable,
- that means the product is letting the reviewer fix the decision without
  making it practical to fix the evidence contract.

Most likely root causes:

- evidence atoms or grouped evidence sets are not ergonomic enough to inspect,
  edit, and submit,
- the review flow likely optimizes for label correction more than structured
  evidence repair,
- the CLI/operator path may make evidence editing too implicit or too verbose,
- grouped evidence semantics remain too easy to flatten during workflow review.

Best product changes:

1. Make evidence groups first-class in review surfaces.
   - Present grouped evidence sets explicitly, not as a flat bag.
   - Show whether at least one complete gold-like support path has been
     reconstructed.

2. Add stricter evidence validation before submit.
   - If a task requires grouped evidence, do not let a reviewed record look
     “done” when the group is structurally incomplete.
   - Surface clear validation errors instead of silently accepting structurally
     invalid evidence output.

3. Improve operator-visible evidence context.
   - Show stable anchor previews.
   - Support editing evidence with clearer anchor ids and grouped structure.
   - Distinguish sentence anchors from table-cell anchors explicitly where the
     benchmark family requires it.

4. Make workflow templates benchmark-family-aware.
   - Evidence-heavy benchmarks should not use the same ergonomic defaults as
     simple classification tasks.
   - The product should ship better default reviewer prompts and better review
     affordances for verification tasks.

Expected benchmark impact:

- strongest impact on `feverous`,
- likely strong impact on `scifact`,
- likely reusable impact on `evidence-inference`, `hotpotqa`, `qasper`, and
  `tabfact`.

### 6.2 High Priority: Review Lift As A Product Objective

The benchmark results say MoLabel’s real value is not always in the first model
output. It is often in what the review workflow allows the human or operator to
correct.

Evidence:

- `banking77` shows meaningful lift from model baseline to reviewed result,
- `goemotions` shows raw workflow proposals are imperfect, but reviewed output
  reaches full quality,
- `clinc150` shows no lift is needed when the task is already easy for the
  current model,
- `feverous` shows verdict-only lift is not enough when the review artifact
  contract is harder.

Best product changes:

1. Treat `workflow_reviewed` as a first-class optimization target.
   - Make this a top-line internal metric.
   - Stop optimizing only for proposal quality.

2. Improve reveal-and-edit ergonomics.
   - The system should minimize friction between “AI proposal seen” and
     “correct reviewed artifact persisted.”

3. Capture structured review corrections as reusable signals.
   - The kinds of corrections seen in `banking77` and `goemotions` should feed
     future prompt or workflow refinement.

Expected benchmark impact:

- strongest on `banking77` and `goemotions`,
- moderate on `hatexplain`,
- only partial on evidence-heavy families unless evidence editing itself is
  improved.

### 6.3 High Priority: Artifact Writing And Benchmark Run Output Ergonomics

The current product keeps missing the `writes_benchmark_run_artifacts` check on
otherwise strong runs.

Why this matters:

- this is not the highest semantic problem,
- but it reduces operator overall score on otherwise excellent runs,
- and it creates unnecessary friction in the benchmark story.

Observed pattern:

- `clinc150`, `banking77`, and isolated `goemotions` all show strong or perfect
  label quality with checklist score only `0.8750`.

Best product changes:

1. Provide a dedicated benchmark artifact write command.
   - Do not require the operator to infer JSON shape and file paths from
     prompt text alone.

2. Provide benchmark-family-specific artifact templates.
   - Artifact-writing should be easy to do correctly for classification,
     evidence, and span tasks without bespoke prompting.

3. Validate artifacts immediately after write.
   - Surface missing fields or wrong locations as actionable CLI feedback.

Expected benchmark impact:

- improves operator overall score on already-strong runs,
- reduces benchmark noise,
- improves trust in the operator story without gaming label quality.

### 6.4 High Priority: Operator Reliability Under Live Load

This was partially a benchmark-runner issue, but it still matters for the
product story because external-agent operation should be robust under practical
conditions.

What the latest evidence shows:

- batch failure on `goemotions` aligned with provider `429` retries,
- isolated rerun of `goemotions` passed on the same runner,
- therefore the latest failure was not fundamentally a task-semantics failure.

Best product and harness changes:

1. Keep live operator batches conservative by default.
   - This was already fixed in the batch runner default.

2. Distinguish reliability failures from semantic failures in user-facing
   reports.

3. Add explicit provider-pressure diagnostics into benchmark summaries.
   - Rate-limit retries,
   - budget exhaustion,
   - timeout counts,
   - no-review-submission exits.

Expected benchmark impact:

- improves trustworthiness of benchmark reporting,
- reduces false negatives,
- especially important for `goemotions`, `hatexplain`, and `scifact`.

### 6.5 Medium Priority: Better Benchmark-Family Workflow Scaffolds

The current benchmark design expects the agent to do a lot correctly from one
short prompt and the public CLI. That is a valid benchmark shape. But product
quality will improve faster if the product ships better reusable workflow
scaffolds for different task families.

Best product changes:

- classification workflow templates,
- multi-label review templates,
- evidence-verification workflow templates,
- rationale-bearing moderation templates,
- artifact-writing helpers attached to those workflows.

Why this is honest:

- it is not adding hidden benchmark logic,
- it is improving the public product surface in the exact way the benchmark is
  supposed to evaluate.

### 6.6 Medium Priority: Better Distinction Between Label Quality And Audit Quality

Right now the benchmark already models this distinction internally, but the
headline reading is still too easy to flatten into a single number.

Best product and report changes:

- label quality should stay separate from checklist quality,
- artifact truthfulness should stay separate from operator label quality,
- benchmark summaries should explicitly tell the reader what kind of failure
  happened.

This is especially important because:

- `feverous` can pass operationally while still being semantically poor,
- `goemotions` can fail operationally in a batch while being semantically
  strong when rerun.

## 7. Benchmark Audit: Are The Benchmarks Good?

Overall verdict:

- yes, mostly,
- the benchmark architecture is fundamentally strong,
- but the live benchmark reporting layer still needs refinement so it separates
  measurement categories more clearly.

### 7.1 What The Current Benchmark System Gets Right

#### 7.1.1 Authority-Pack-First Contract

This is the right design.

Why it is good:

- it keeps benchmark truth canonical,
- it separates operator-visible surfaces from scorer truth,
- it makes contamination protection explicit,
- it makes benchmark authoring reproducible.

This should not be weakened.

#### 7.1.2 Two Gold Views

The distinction between `paper_direct` and `molabel_operated` is one of the
best parts of the framework.

Why it is good:

- it prevents MoLabel from overclaiming paper-faithful performance after a
  lossy normalization,
- it makes normalization tax visible,
- it lets the benchmark honestly answer whether MoLabel preserved or changed
  task semantics.

This is especially important for:

- evidence tasks,
- span tasks,
- grounded generation,
- multi-label tasks.

#### 7.1.3 Stage-Aware Scoring

The five-stage model is excellent:

- `paper_model`
- `molabel_model`
- `workflow_autorun`
- `workflow_reviewed`
- `operator_reviewed`

Why it is good:

- it localizes where quality improved or degraded,
- it prevents “one final score” thinking,
- it helps distinguish model weakness from workflow weakness.

This is the right benchmark structure and should stay.

#### 7.1.4 Operator Audit Checks

Treating shell audit and artifact truthfulness as first-class benchmark outputs
is correct.

Why it is good:

- it evaluates whether the operator used the intended public surface,
- it protects against hidden-truth touching,
- it evaluates trustworthiness of operator-authored reports,
- it aligns with MoLabel’s file-ownership and auditability goals.

#### 7.1.5 Benchmark Family Coverage

The implemented benchmark families described in
`docs/guides/grounded-benchmark-catalog.md` are well chosen.

Why they are good:

- they cover the main artifact shapes MoLabel claims to support,
- they prevent overfitting to one easy task family,
- they make it possible to see whether MoLabel is a real data-operations
  workbench or only a text-classification wrapper.

### 7.2 What The Current Benchmark System Does Poorly Or Ambiguously

#### 7.2.1 Headline Pass / Fail Is Too Crude

This is the biggest reporting weakness.

Examples:

- `feverous` passed the operator test but had operator label quality `0.0000`,
- `goemotions` failed in the batch even though isolated rerun quality was
  excellent,
- `hatexplain` and `scifact` failed before producing current operator scores.

Problem:

- a top-level pytest result is mixing operational validity and semantic quality,
- this makes the benchmark harder to reason about than it needs to be.

Required benchmark-system improvement:

- every live report should expose:
  - `run_status`
  - `score_status`
  - `semantic_quality_status`
  - `operator_audit_status`

#### 7.2.2 Some Report Readers Can Overread Small Slices

The benchmark slices are intentionally small so they stay runnable. That is
good operationally, but it means perfect scores can be overread.

Risk:

- a perfect `clinc150` or `goemotions` slice can sound like full product
  validation when it is really repeatable slice validation.

Required benchmark-system improvement:

- explicitly label slice size and benchmark intent in summary reports,
- add repeated-run summaries and variance for live runs,
- add hard-slice variants for the most important benchmark families.

#### 7.2.3 Infrastructure Failures Are Currently Too Entangled With Product Scores

This is partly fixed by the batch-runner change, but the benchmark system still
needs clearer semantics.

Problem:

- provider pressure can erase a benchmark outcome before any reviewed artifact
  exists,
- and the current top-level story then makes that look like product weakness
  rather than evaluation unreliability.

Required benchmark-system improvement:

- classify failures as:
  - infra-failed,
  - operator-incomplete,
  - scored-low-quality,
  - scored-high-quality.

#### 7.2.4 Artifact Checks Need Better Reader Framing

Artifact-writing checks are useful, but the current reporting can make them
look like equivalent failures to semantic label failures.

Problem:

- a run with perfect labels but bad artifact writing is not the same failure as
  a run with incorrect reviewed labels,
- the current combined operator overall score can hide that distinction.

Required benchmark-system improvement:

- show label score and checklist score side by side in all top-level summary
  views,
- do not let readers miss that distinction.

### 7.3 Benchmark-By-Benchmark Audit

#### 7.3.1 `clinc150`

Benchmark quality:

- good,
- but now relatively saturated.

Why it is still useful:

- it is a low-noise regression sentinel,
- it validates OOS handling and exact-match classification behavior,
- it checks whether the operator path can stay disciplined on a simple task.

What can improve:

- make sure it stays confusion-rich enough to remain meaningful,
- keep it small and stable,
- use it more as a reliability benchmark than as a frontier challenge.

#### 7.3.2 `banking77`

Benchmark quality:

- very good.

Why it is strong:

- it is harder than `clinc150`,
- it measures real workflow lift,
- it stresses fine-grained intent confusion rather than generic classification.

What can improve:

- preserve confusion-heavy slices,
- expand with a harder slice once the current slice stops being discriminative.

#### 7.3.3 `goemotions`

Benchmark quality:

- very good.

Why it is strong:

- it proves MoLabel is not collapsing multi-label tasks into one-label
  shortcuts,
- it tests set-valued artifact preservation honestly,
- it rewards meaningful review improvement.

What can improve:

- keep duplicate-label and valid-empty-set behaviors explicit,
- consider adding a harder slice emphasizing high-overlap emotions.

#### 7.3.4 `hatexplain`

Benchmark quality:

- good in principle and important strategically.

Why it matters:

- it prevents moderation evaluation from degenerating into single-label
  classification,
- it forces target-community and rationale preservation.

Current limitation:

- live operator reliability for it is not yet stable enough to treat the latest
  batch result as a clean semantic measurement.

What can improve:

- keep the benchmark,
- improve operator support and reporting around rationale-mask tasks,
- ensure the slice is not too operationally expensive for live runs.

#### 7.3.5 `feverous`

Benchmark quality:

- extremely good and extremely valuable.

Why it is strong:

- it forces verdict plus evidence completeness,
- it is hard in exactly the way that catches shallow systems,
- it exposed a real product weakness immediately.

What can improve:

- keep it exactly because it is painful,
- but consider clearer reporting to distinguish verdict recovery from evidence
  collapse.

#### 7.3.6 `scifact`

Benchmark quality:

- very good.

Why it is strong:

- it is one of the best medium-complexity evidence benchmarks in the suite,
- it exercises grouped sentence evidence in a scientific domain,
- it should be one of the primary evidence-family targets after `feverous`.

What can improve:

- improve live operator reliability,
- possibly add slightly different slice difficulties,
- make it easier to see whether failures are verdict failures, evidence
  failures, or operator-process failures.

## 8. Best Ways To Improve The Benchmark System

These are benchmark-program improvements, not MoLabel product changes.

### 8.1 Add A Four-Way Outcome Taxonomy

Every live benchmark run should end in one of:

- infra failed,
- operator incomplete,
- scored low quality,
- scored acceptable quality.

This change would improve interpretability immediately.

### 8.2 Publish Repeated-Run Statistics

For stochastic live runs, publish:

- mean,
- min,
- max,
- standard deviation,
- count of infra-invalid runs.

This matters especially for operator-mode live benchmarks.

### 8.3 Add Hard Slices And Stability Slices

For core benchmark families, maintain two slices:

- a small repeatable stability slice,
- a harder discriminative slice.

This avoids the current tension between fast reruns and meaningful difficulty.

### 8.4 Make Workflow Lift A First-Class Benchmark Output

The benchmark should explicitly summarize:

- model baseline,
- workflow autorun,
- workflow reviewed,
- operator reviewed,
- and net workflow lift.

That is one of the most product-relevant outputs the framework can provide.

### 8.5 Distinguish Checklist Penalties From Label Penalties More Clearly

Do not remove the combined score, but always show:

- label score,
- checklist score,
- combined operator score,
- and whether the checklist penalty is the main reason the combined score is
  lower.

### 8.6 Add Provider-Pressure Diagnostics Into Summary Reports

For live runs, report:

- rate-limit retries,
- timeout counts,
- budget exhaustion,
- no-submission exits,
- per-stage API pressure where available.

This will make the benchmark program more debuggable and more honest.

## 9. Prioritized Action Plan

### 9.1 Immediate

1. Re-run the full operator benchmark batch under the new conservative worker
   default.
2. Refresh live operator results for:
   - `goemotions`
   - `hatexplain`
   - `scifact`
3. Update reporting to separate:
   - infra validity,
   - semantic quality,
   - audit quality.

### 9.2 Near-Term

1. Improve evidence review and evidence editing for verification benchmarks.
2. Add benchmark artifact-writing helpers to the public product surface.
3. Add clearer benchmark-family workflow scaffolds for:
   - evidence verification,
   - moderation with rationales,
   - multi-label review.

### 9.3 Medium-Term

1. Add repeated-run reporting for live operator benchmarks.
2. Add hard-slice variants for:
   - `banking77`
   - `goemotions`
   - `scifact`
   - `feverous`
3. Add explicit workflow-lift summaries to all benchmark reports.

## 10. Final Assessment

MoLabel should not respond to the current evidence by weakening the benchmarks.

The right response is:

- keep the strong benchmark semantics,
- improve the product where the benchmarks are exposing real weakness,
- improve live-run reporting where the benchmark program is currently mixing
  together different failure classes.

The most important product truth revealed by this audit is:

- MoLabel is already strong on classification-style reviewed workflows,
- MoLabel is not yet strong enough on evidence-preserving reviewed workflows,
- and the benchmark system is doing its job by making that impossible to hide.

The most important benchmark-program truth revealed by this audit is:

- the benchmark framework design is good,
- but the reporting layer still needs to separate reliability, audit, and
  semantic quality more clearly so the benchmark story is easier to trust.

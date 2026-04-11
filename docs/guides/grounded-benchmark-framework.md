# Grounded Benchmark Framework

This document explains how the current grounded benchmark works in MoLabel.

It is the current-state guide for benchmark execution, scoring, diagnostics, and
evidence inspection. Older files under `docs/research/` remain useful for
design intent, but this guide is meant to explain what the code and live
harness actually do now.

For benchmark-by-benchmark task semantics, see
`docs/guides/grounded-benchmark-catalog.md`.

## 1. Purpose

The grounded benchmark is the paper-backed evaluation track. It exists to
measure not only raw model quality, but also the MoLabel workflow and
Codex-or-Claude-as-operator behavior on a real task slice.

For the current CLINC slice, the framework is designed to answer questions
such as:

- how good is the paper-direct model baseline,
- how much quality is lost or preserved after MoLabel normalization,
- how good are raw workflow proposals,
- how much review improves or harms those proposals,
- how much operator behavior helps, hurts, or simply preserves the result,
- whether the operator used only allowed surfaces,
- whether the operator-written report matches the persisted facts.

## 2. Current Scope

The framework is no longer CLINC-only. The committed grounded fixtures now
cover:

- `fixtures/benchmarks-grounded/clinc150`
- `fixtures/benchmarks-grounded/banking77`
- `fixtures/benchmarks-grounded/goemotions`
- `fixtures/benchmarks-grounded/hatexplain`
- `fixtures/benchmarks-grounded/feverous`
- `fixtures/benchmarks-grounded/scifact`
- `fixtures/benchmarks-grounded/evidence-inference`
- `fixtures/benchmarks-grounded/tabfact`
- `fixtures/benchmarks-grounded/hotpotqa`
- `fixtures/benchmarks-grounded/qasper`
- `fixtures/benchmarks-grounded/docvqa`
- `fixtures/benchmarks-grounded/beir`
- `fixtures/benchmarks-grounded/msmarco`
- `fixtures/benchmarks-grounded/cuad`
- `fixtures/benchmarks-grounded/multispanqa`
- `fixtures/benchmarks-grounded/toxic-spans`
- `fixtures/benchmarks-grounded/totto`
- `fixtures/benchmarks-grounded/webnlg`

Three files define the benchmark contract:

- `authority/scenario.yaml`
- `authority/metrics.yaml`
- `authority/operator.yaml`

The harness and scorer are implemented in:

- `packages/molabel-core/src/molabel/core/quality/grounded_benchmarks.py`
- `packages/molabel-core/src/molabel/core/quality/grounded_benchmark_primitives.py`
- `tests/e2e/tier1_pipeline/test_live_grounded_benchmarks_real_llm.py`
- `tests/e2e/tier1_pipeline/test_live_grounded_operator_benchmarks_real_llm.py`
- `tests/e2e/infrastructure/grounded_operator.py`

The important scope expansion is reusable primitive support, not just more
fixture directories. The scorer now has first-class contracts for:

- calibration, abstention, and review-routing diagnostics for classification,
- score-to-label thresholding and micro-F1 for multi-label tasks,
- grouped evidence annotations with multiple acceptable gold groups,
- QA answer-plus-support bundles,
- ranked retrieval outputs plus qrels,
- span-native extraction outputs,
- grounded generation outputs,
- and document/table anchors.

Those fixtures now span the major benchmark families MoLabel needs to support:

- single-label classification with abstention or OOS semantics,
- multi-label classification,
- moderation with rationale evidence,
- evidence-backed verification,
- QA with supporting evidence,
- retrieval and ranking,
- span extraction,
- and grounded generation.

## 3. Key Terms

### 3.1 Authority Pack

The authority pack is the canonical benchmark contract. It carries:

- scenario metadata,
- paper and dataset provenance,
- label mapping,
- scoring metrics,
- operator checks,
- gold and benchmark artifact references.

### 3.2 Reference Workspace

The CLINC fixture still includes a `workbench/` tree. In the long-term design,
that tree is transitional reference material, not the canonical authority. In
current execution, parts of that tree are still used as runnable input.

### 3.3 Stage

A stage is the thing being measured. The current scorer supports five stages:

- `paper_model`
- `molabel_model`
- `workflow_autorun`
- `workflow_reviewed`
- `operator_reviewed`

### 3.4 Mode And Variant

Legacy YAML still refers to `mode` and `variant`.

- mode: `model`, `workflow`, `operator`
- variant: `paper_direct`, `molabel_operated`

The scorer supports both the older mode/variant semantics and the newer
stage-oriented view. For CLINC today, the report renders both.

## 4. Fixture Contract

The CLINC authority pack defines:

- source records under `workbench/benchmarks/splits/*.jsonl`,
- task schema and workflow references,
- paper-direct and MoLabel-operated gold views,
- benchmark human-label and review artifacts,
- evaluation fields:
  - `intent_label`
  - `is_out_of_scope`

The primary metric configuration is a weighted mean over:

- `intent_accuracy`
- `oos_recall`
- `intent_exact_match`

The operator specification defines:

- `label_quality_weight = 0.7`
- `checklist_weight = 0.3`
- blocking checks such as:
  - `uses_public_cli_and_skill_only`
  - `configures_minimax_2_7_profile`
  - `preserves_artifact_integrity`

If blocking checks fail, the combined operator score is capped so the run does
not overclaim quality from labels alone.

## 5. End-To-End Execution

There are two live benchmark paths.

### 5.1 Live Model Baseline

The model benchmark path:

1. copies a grounded fixture workspace into a temporary workspace,
2. loads the authority/scenario bundle,
3. loads the task schema and raw records,
4. builds a structured output schema,
5. runs the current labeling engine, MiniMax 2.7, through the
   Anthropic-compatible adapter,
6. scores predictions against the gold rows,
7. writes `summary.json`, `report.md`, and the evidence bundle.

This path is maintainer-side baseline measurement. It is not the external
operator benchmark.

### 5.2 Live Operator Benchmark

The operator benchmark path:

1. prepares a temporary operator-visible workspace,
2. strips authority and hidden truth-bearing assets from the copy,
3. gives the runner only:
   - the temporary workspace,
   - the public `molabel` command,
   - the installed MoLabel skill,
   - one short prompt,
4. lets the runner create the model profile, import data, run the workflow, and
   persist review outputs,
5. reconstructs persisted outputs after the agent exits,
6. scores those persisted artifacts externally against the authority-side gold
   copy,
7. audits shell usage and validates operator-written run artifacts,
8. writes a full evidence bundle.

This path measures Codex or Claude as an external MoLabel operator, not a
maintainer-side scripted replay.

## 6. Contamination Protection

The operator benchmark is explicitly hardened against contamination.

The operator-visible workspace must not expose:

- authority files,
- gold labels,
- benchmark human-label or review artifacts,
- scoring configs,
- hidden truth-bearing fields such as `source_label`.

The harness enforces this by preparing a stripped temporary workspace before the
run and then scoring externally against the authority-side copy. That is why a
perfect operator score can still coexist with strict audit failures if the
runner touched forbidden surfaces.

## 7. Stages And What They Measure

### 7.1 `paper_model`

Direct model score against the paper-faithful gold view.

### 7.2 `molabel_model`

Model score after MoLabel normalization into the operational label view.

### 7.3 `workflow_autorun`

Raw proposal quality before human/operator review.

### 7.4 `workflow_reviewed`

Quality after the workflow’s review stage.

### 7.5 `operator_reviewed`

The final external-operator result after combining:

- reviewed label quality,
- operator checklist quality.

These stage splits are important because final accuracy alone can hide whether
quality came from the proposal stage, the review stage, or the operator simply
preserving an already-correct proposal.

## 8. Scoring Model

Metrics are defined in `authority/metrics.yaml`.

The original grounded scorer supported CLINC-style classification, set metrics,
token-mask rationale scoring, and FEVEROUS paper-direct scoring. The framework
now additionally supports reusable metrics for the previously blocked families:

- classification:
  - `abstain_precision`
  - `abstain_recall`
  - calibration and selective-prediction diagnostics in stage summaries
- multi-label:
  - `micro_f1`
  - threshold sweeps and hierarchy validation via `metric_options`
- evidence attribution:
  - `evidence_group_precision`
  - `evidence_group_recall`
  - `evidence_group_f1`
  - `evidence_group_exact_match`
  - `joint_evidence_decision`
- QA with evidence:
  - `answer_exact_match`
  - `answer_token_f1`
  - `supporting_fact_exact_match`
  - `supporting_fact_f1`
  - `joint_answer_support`
- retrieval / ranking:
  - `mrr`
  - `ndcg_at_k`
  - `recall_at_k`
  - `precision_at_k`
  - `map`
- spans / extraction:
  - `span_exact_match`
  - `span_overlap_f1`
- grounded generation:
  - `source_coverage`
  - `unsupported_content_rate`
  - `grounded_generation_score`
- document QA / grounding:
  - `anls`

The scorer computes:

- per-metric values,
- overall weighted score,
- per-field accuracy,
- exact-match rates,
- coverage integrity diagnostics,
- confusion data and subset breakdowns.

Where a metric family needs more than a scalar, the scorer now also attaches
report-friendly structured details:

- classification routing summaries show abstain rate, abstain precision/recall,
  expected calibration error, and selective-prediction curve size,
- ranking metrics include duplicate/depth validation and missing-qrels counts,
- span metrics include offset validation details,
- evidence and QA metrics keep decision quality, evidence quality, and joint
  quality separate,
- grounded generation metrics surface source coverage, unsupported-content
  rate, and structure-validation results,
- and stage diagnostics expose `metric_family_summaries` so benchmark reports
  stay readable across heterogeneous task families.

Coverage is not treated as an invisible implementation detail. Missing rows,
duplicate record IDs, extra submissions, and related integrity issues are
surfaced in diagnostics rather than silently collapsed away.

## 9. Tax Breakdown

Tax definitions are also configured in `authority/metrics.yaml`.

The CLINC bundle currently defines:

- `model_tax`
  paper-direct model score minus MoLabel-operated model score
- `workflow_tax`
  MoLabel-operated model score minus workflow-reviewed score
- `review_lift`
  `workflow_reviewed` minus `workflow_autorun`
- `operator_tax`
  workflow-reviewed score minus operator-reviewed score

Each tax result now carries per-metric deltas in addition to the blended delta.
That matters because one aggregate score can hide whether the loss came from
intent classification, OOS handling, or exact-match behavior.

## 10. Proposal, Review, And Operator Diagnostics

The operator diagnostics layer is intentionally stage-aware.

It measures:

- `proposal_exact_match_rate`
- `review_exact_match_rate`
- `proposal_to_review_delta`
- `corrected_count`
- `regressed_count`
- `operator_lift_count`
- `preserved_correct_count`
- `preserved_wrong_count`
- `changed_wrong_to_wrong_count`

This means the framework can distinguish:

- a perfect proposal that review simply preserved,
- a wrong proposal that review corrected,
- a correct proposal that review regressed,
- a wrong proposal that changed but stayed wrong.

Those distinctions were missing from the earlier, coarser score model.

## 11. Decision And Accept/Edit Behavior

The benchmark does not infer accept/edit behavior from prose. It derives it from
the final persisted review decisions.

It records:

- `accept_ai_count` and `accept_ai_rate`
- `edit_ai_count` and `edit_ai_rate`
- `correct_count` and `correct_rate`
- `reject_ai_count` and `reject_ai_rate`
- `skip_count` and `skip_rate`

It also computes decision-quality summaries that condition quality on the final
decision. That lets you answer questions such as:

- when the operator accepts AI proposals, are those proposals actually correct,
- when the operator edits, do those edits fix or regress the record,
- how often does the operator reject or skip hard cases.

## 12. Hard-Case And Confidence Diagnostics

The scorer isolates several difficult subsets:

- records where the proposal was wrong,
- low-confidence proposals when confidence exists,
- benchmark disagreement cases,
- intentionally wrong benchmark artifacts,
- out-of-scope rows.

Each subset gets its own delta summary. Confidence diagnostics are emitted as
structured data when proposal confidence exists; when it does not, the report
marks that explicitly instead of inventing a calibration story.

## 13. Confusion And Difficulty Stratification

Stage diagnostics include more than one blended score. They expose:

- per-label confusion information,
- per-field accuracy,
- subset breakdowns,
- coverage integrity signals,
- machine-readable row-level deltas.

This is necessary for grounded evaluation because a single overall score can
hide near-neighbor intent confusions or overstate performance on an imbalanced
slice.

## 14. Shell Audit And Workflow Hygiene

The operator benchmark treats command audit as first-class output.

The shell audit tracks categories such as:

- non-CLI surface usage,
- hidden benchmark path touches,
- truth-probe attempts,
- `queue claim` usage,
- `reveal-ai` usage,
- status polling,
- repeated polling,
- duplicate shell commands,
- redundant reads.

Some of these are blocking or checklist-relevant. Others are audit-only and are
meant to make behavior diagnosable without turning every inefficiency into a
hard failure.

## 15. Artifact Truthfulness

The framework now checks whether the operator-written report and summary match
persisted benchmark facts.

Examples of truthfulness checks include:

- benchmark ID,
- record and submission counts,
- agent output counts,
- proposal coverage and failure counts,
- accept/edit counts or rates derived from persisted decisions,
- audit counts such as hidden path touches and truth probes.

This prevents the benchmark from crediting a clean or perfect run when the
operator-written narrative does not match what was actually persisted.

## 16. Repeated-Run Stability

The scorer can compute stage stability summaries across repeated runs of the
same stage. It reports:

- run count,
- overall mean,
- standard deviation,
- score span,
- per-metric spans.

The current CLINC slice is often exercised as a single live run, so stability
only appears once repeated runs are available. The framework supports it even
when a given report has only one run.

## 17. Run Output Layout

Every scored run can emit a bundle like this:

```text
workbench/benchmarks/runs/<run-id>/
  summary.json
  report.md
  evidence_manifest.json
  evidence/
    inputs/
    outputs/
    logs/
    scoring/
    runtime/
    artifacts/
```

Typical contents:

- `summary.json`
  machine-readable top-level result
- `report.md`
  human-readable report
- `evidence_manifest.json`
  index of bundle artifacts
- `evidence/inputs/*`
  raw records, gold rows, benchmark human/review inputs
- `evidence/outputs/*`
  predictions, review submissions, review events
- `evidence/logs/*`
  shell commands, shell audit, runner logs
- `evidence/scoring/*`
  stage diagnostics, tax breakdowns, operator diagnostics
- `evidence/runtime/*`
  output schema and test context
- `evidence/artifacts/*`
  operator-authored summary/report payloads

## 18. How To Verify A Score From Logs

When a score looks suspicious, inspect the bundle in this order.

1. Open `summary.json`.
   Confirm the benchmark ID, run ID, stage, overall score, metric values, and
   whether `truthfulness_ok` is true.

2. Open `evidence/outputs/review_submissions.json` and
   `evidence/outputs/review_events.json`.
   Confirm coverage and the final persisted decisions.

3. Open `evidence/outputs/agent_outputs.json`.
   Confirm proposal coverage and row count.

4. Open `evidence/scoring/operator_diagnostics.json` or the stage diagnostics
   files.
   Confirm corrected, regressed, accept/edit/reject, and hard-case metrics.

5. Open `evidence/logs/shell_audit.json`.
   Confirm whether there were forbidden touches, truth probes, or avoidable
   command patterns.

6. Open the operator-authored artifacts under `evidence/artifacts/`.
   Confirm the written summary/report actually match the persisted counts.

If the human-readable `report.md` and the evidence disagree, trust the persisted
artifacts plus the machine-readable diagnostics, not the prose alone.

## 19. Current Rerun Commands

Current live rerun entrypoints:

```bash
uv run pytest tests/e2e/tier1_pipeline/test_live_grounded_benchmarks_real_llm.py -k clinc150 -vv -s
uv run pytest tests/e2e/tier1_pipeline/test_live_grounded_operator_benchmarks_real_llm.py -k clinc150 -vv -s
```

These require valid MiniMax or Anthropic-compatible credentials in the
environment.

## 20. Current Limitations

- The current CLINC fixture still carries transitional `workbench/` scaffolding
  even though the scoring model is authority-pack-first.
- Confidence diagnostics are only populated when proposal confidence is
  available.
- Stability reporting is structural but only useful once repeated runs exist.
- This guide only covers the current grounded slice and framework behavior, not
  cross-paper benchmark expansion.

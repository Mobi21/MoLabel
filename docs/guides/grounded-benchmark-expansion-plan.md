# Grounded Benchmark Expansion Plan

Date: 2026-04-05
Status: Implementation planning guide with historical rollout notes
Related:

- `docs/guides/grounded-benchmark-framework.md`
- `docs/guides/grounded-benchmark-catalog.md`
- `docs/research/paper-backed-benchmark-candidates.md`
- `docs/research/grounded-benchmark-paper-map.md`
- `packages/molabel-core/src/molabel/core/quality/grounded_benchmarks.py`

## 1. Current State

The repo is already past a CLINC150-only benchmark system.

Implemented grounded benchmark fixtures:

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

See `docs/guides/grounded-benchmark-catalog.md` for the benchmark-by-benchmark
task contract and current metric semantics.

Historical note:

- sections below still describe how benchmark families were expected to roll
  out and which reusable primitives they depended on,
- but many of the benchmark families discussed there are now implemented,
- so treat this file as a planning and sequencing reference, not as the live
  source of truth for which fixtures currently exist.

These grounded fixtures prove that the current harness can already support:

- single-label classification with exact-match and binary recall,
- macro-F1 scoring for categorical labels,
- set-valued artifact scoring with precision, recall, F1, and Jaccard,
- token-mask rationale scoring,
- FEVEROUS-style joint verdict-plus-evidence scoring,
- stage-aware benchmark reporting across `paper_model`, `molabel_model`,
  `workflow_autorun`, `workflow_reviewed`, and `operator_reviewed`,
- operator diagnostics, audit checks, and report-truthfulness checks,
- authority-pack-first fixture loading with transitional `workbench/`
  compatibility,
- retrieval/ranking fixtures with qrels,
- span-native extraction fixtures,
- QA bundles with supporting evidence,
- and grounded generation with explicit unsupported-content diagnostics.

This means the next benchmark work should not start by inventing a new framework
from scratch. It should split into:

- benchmarks that can be added now with existing scorer primitives,
- and benchmarks that are blocked on new artifact or metric support.

## 2. Current Harness Capabilities

The grounded scorer currently supports these metric types:

- `accuracy`
- `abstain_precision`
- `abstain_recall`
- `answer_exact_match`
- `answer_token_f1`
- `anls`
- `binary_recall`
- `evidence_group_exact_match`
- `evidence_group_f1`
- `evidence_group_precision`
- `evidence_group_recall`
- `macro_f1`
- `micro_f1`
- `exact_match`
- `jaccard`
- `joint_answer_support`
- `joint_evidence_decision`
- `map`
- `mrr`
- `ndcg_at_k`
- `precision_at_k`
- `recall_at_k`
- `set_precision`
- `set_recall`
- `set_f1`
- `source_coverage`
- `span_exact_match`
- `span_overlap_f1`
- `supporting_fact_exact_match`
- `supporting_fact_f1`
- `token_mask_f1`
- `unsupported_content_rate`
- `feverous_score`

The scorer also has reusable artifact contracts and validators for:

- abstention-aware classification outputs,
- multi-label score thresholding and hierarchy validation,
- grouped evidence outputs and faithfulness hooks,
- QA answer-plus-support bundles,
- ranked retrieval outputs and qrels,
- span-native extraction outputs,
- grounded generation outputs,
- and document/table anchors.

That means the previously partial or blocked families are now framework-ready.
What remains after this work is fixture authoring, paper-direct packaging, and
benchmark-specific subset curation rather than missing scorer primitives.

### 2.1 Ready Now

These benchmark families can be added without changing the core metric engine.

| Family | Candidate | Why it fits now |
|---|---|---|
| Single-label classification | `BANKING77` | Same basic contract as `clinc150`: one label per record, closed label set, accuracy plus macro-F1, exact-match, confusion analysis. |
| Multi-label classification | `GoEmotions` | The scorer already supports set-valued outputs, Jaccard, set F1, and exact-match over normalized MoLabel labels. |
| Verification close to FEVEROUS | `SciFact` | Reuses verdict-plus-evidence patterns already present in `feverous`, with simpler evidence structure than table-aware FEVEROUS. |
| Moderation variants | `Social Bias Frames` | Operationally close to `hatexplain` if the first slice stays text-only and treats structured fields as normalized labels instead of adding new anchor types. |

### 2.2 Framework-Unblocked Families

These families no longer need scorer work before packaging. They still need
honest fixture construction and paper-direct mapping.

| Family | Candidate | Reusable support now available |
|---|---|---|
| Classification with abstention | `BANKING77` plus abstain routing | Calibration reporting, selective-prediction summaries, explicit abstain handling, abstain precision/recall, review-routing diagnostics. |
| Multi-label classification | `GoEmotions`, `EURLEX57K` | `micro_f1`, threshold sweeps, hierarchy-aware validation, parser-failure versus valid-empty diagnostics. |
| Evidence attribution | `Evidence Inference 2.0`, `ERASER` | Grouped evidence outputs, multiple acceptable gold groups, completeness/integrity checks, faithfulness hooks, separate evidence-versus-decision reporting. |
| QA with evidence | `HotpotQA`, `QASPER` | Answer normalization, answer EM/F1, supporting-facts EM/F1, joint answer-plus-evidence scoring, null handling. |
| Retrieval / ranking | `BEIR`, `MS MARCO` | Ranked-result artifacts, qrels ingestion, `MRR`, `nDCG@K`, `Recall@K`, `Precision@K`, `MAP`, duplicate/depth validation, corpus metadata. |
| Span extraction | `CUAD`, `MultiSpanQA`, `Toxic Spans` | Span-native artifacts, stable offsets, discontiguous spans, exact and overlap scoring, normalization-aware comparison, offset validation. |
| Structured generation | `ToTTo`, `WebNLG` | Grounded-generation artifacts, source coverage checks, unsupported-content checks, structure-aware validation, report diagnostics. |
| Table / document grounding | `TabFact`, `DocVQA`, `doc2dial` | Table-cell anchors, hierarchical document anchors, ANLS, page/section/cell grounding, lossy-grounding warnings. |

## 3. Recommended Sequence

The research note recommends `BANKING77`, then `GoEmotions`, then an
evidence-heavy benchmark. The codebase supports that, but the harness suggests a
slightly more operational sequence.

### Phase 1: Add What The Current Harness Already Supports

1. `BANKING77`
2. `GoEmotions`
3. `SciFact`

Rationale:

- `BANKING77` is the cleanest next benchmark because it is almost a direct
  sibling of `clinc150`.
- `GoEmotions` is the first benchmark that proves the current set-metric support
  is real, not incidental.
- `SciFact` is a lower-risk next evidence benchmark than `HotpotQA` because it
  extends the existing FEVEROUS-style verdict-and-evidence machinery instead of
  requiring answer normalization.

### Phase 2: Package The Newly Unblocked Families

1. `SciFact`
2. `BEIR`
3. `HotpotQA`

Rationale:

- the scorer work is now in place,
- these additions would validate the new ranking, evidence, and QA bundles with
  real authority packs,
- and they would prove the framework changes against paper-direct packaging
  rather than only unit-level primitive tests.

### Phase 3: Add Harder Benchmark Families

1. `BEIR`
2. `CUAD`
3. `HotpotQA`
4. `ToTTo`
5. `TabFact`
6. `DocVQA`

## 4. Benchmark-By-Benchmark Build Plan

## 4.1 `BANKING77`

Implementation class: ready now

Expected fixture shape:

- one utterance per record,
- one normalized `intent_label`,
- optional `banking77_label` paper-direct field if label names are normalized,
- no span or evidence anchors,
- one small redistributable slice with confusion-heavy intents.

Recommended metrics:

- `intent_accuracy`
- `intent_macro_f1`
- `intent_exact_match`

Recommended operator checks:

- same baseline checks as `clinc150`,
- explicit check that invalid labels are not used as implicit abstentions,
- report truthfulness and artifact integrity checks.

Expected files:

- `fixtures/benchmarks-grounded/banking77/authority/*`
- `fixtures/benchmarks-grounded/banking77/workbench/benchmarks/splits/*.jsonl`
- `fixtures/benchmarks-grounded/banking77/workbench/benchmarks/gold/*`
- `tests/unit/test_grounded_benchmark_banking77.py`

Core-code changes expected:

- none required in `grounded_benchmarks.py`

## 4.2 `GoEmotions`

Implementation class: ready now

Expected fixture shape:

- one text field per record,
- one label set field such as `emotion_labels`,
- optional metadata for disagreement and group slices,
- optional empty-set cases if the subset includes them.

Recommended metrics:

- `emotion_macro_f1`
- `emotion_micro_f1` if added later, otherwise `set_f1` as the current proxy
- `emotion_jaccard`
- `emotion_exact_match`

Recommended operator checks:

- duplicate-label rejection,
- authority-vocabulary enforcement,
- explicit distinction between empty prediction set and parser failure,
- disagreement-preservation checks where the subset includes ambiguous cases.

Core-code changes expected:

- optional, not required: add `micro_f1` if exact paper-faithful reporting is
  required instead of relying on `set_f1` and diagnostics

## 4.3 `SciFact`

Implementation class: ready now with light fixture-specific mapping

Expected fixture shape:

- one claim per record,
- one verdict label,
- one or more evidence sentence ids,
- paper-direct gold plus MoLabel-operated flattened evidence atoms.

Recommended metrics:

- `scifact_joint_score`
- `verdict_accuracy`
- `evidence_precision`
- `evidence_recall`
- `evidence_f1`

Core-code changes expected:

- probably none if the fixture maps cleanly onto the existing FEVEROUS-style
  joint scorer

## 4.4 `BEIR`

Implementation class: blocked

Required new work before packaging:

- add ranked-list prediction artifact support,
- add qrels loading helpers,
- add `mrr`, `ndcg_at_k`, `recall_at_k`, and `map`,
- add duplicate-id and fixed-depth validation.

## 4.5 `CUAD`

Implementation class: blocked

Required new work before packaging:

- add span artifact schema with stable offsets,
- add exact and overlap span scoring,
- add multi-span support,
- add offset-to-source validation.

## 4.6 `HotpotQA`

Implementation class: blocked

Required new work before packaging:

- add answer normalization helpers,
- add answer EM/F1 metrics,
- add supporting-facts EM/F1,
- add joint answer-plus-support scoring.

## 5. Practical Rule For New Benchmarks

Do not add a benchmark fixture just because the paper is attractive.

Add the fixture only if one of the following is true:

- the current scorer already measures the task contract faithfully enough to be
  honest in reports,
- or the harness change being introduced is reusable across a benchmark family,
  not a one-off patch for a single dataset.

That rule keeps grounded benchmarks from becoming a pile of special cases.

## 6. Immediate Next Work

The most productive next milestone is:

1. land `BANKING77`,
2. land `GoEmotions`,
3. then decide whether to add `SciFact` or first build the ranking/span/QA
   primitives.

If the goal is to maximize benchmark count quickly, do:

- `BANKING77`
- `GoEmotions`
- `SciFact`

If the goal is to maximize framework leverage, do:

- ranked retrieval artifacts and metrics,
- span-native scoring,
- joint answer-plus-evidence scoring,
- then add benchmark families unlocked by those primitives.

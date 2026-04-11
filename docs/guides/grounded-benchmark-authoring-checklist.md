# Grounded Benchmark Authoring Checklist

Date: 2026-04-05
Status: Authoring checklist
Related:

- `docs/guides/grounded-benchmark-framework.md`
- `docs/guides/grounded-benchmark-expansion-plan.md`
- `packages/molabel-core/src/molabel/core/quality/grounded_benchmarks.py`

Use this checklist when adding a new grounded benchmark under
`fixtures/benchmarks-grounded/<benchmark-id>/`.

## 1. Decide Whether The Benchmark Is Ready

Before creating files, classify the benchmark into one of these buckets:

- ready now: current metric and artifact primitives already fit the paper task,
- partially ready: the fixture can ship, but paper-faithful reporting needs a
  small shared scorer addition,
- blocked: the benchmark needs a new reusable artifact type or metric family.

Do not proceed if the benchmark is blocked unless the same change unlocks a
benchmark family.

## 2. Create The Standard Fixture Layout

Each grounded benchmark should follow this shape:

```text
fixtures/benchmarks-grounded/<benchmark-id>/
  README.md
  AGENTS.md
  workbench.project.yaml
  authority/
    README.md
    manifest.yaml
    scenario.yaml
    paper.yaml
    label-map.yaml
    metrics.yaml
    baselines.yaml
    operator.yaml
    packaging.yaml
    provenance.lock
  workbench/
    benchmarks/
      splits/
      gold/
      human-labels/
      reviews/
      runs/
    config/task-schemas/
    workflows/
  reference-workspace/
```

Optional raw data can live outside `workbench/` when that keeps provenance and
redistribution clearer, as `hatexplain` does under `data/raw/`.

## 3. Fill The Authority Pack In This Order

### 3.1 `manifest.yaml`

Define:

- `benchmark_id`
- `layout: authority`
- profile ids
- canonical file paths
- source manifest paths
- reference workspace path

### 3.2 `scenario.yaml`

Define:

- `benchmark_id`
- `track: grounded`
- `name`
- `description`
- `raw_format`
- `source_path`
- `loader_plugin`
- `record_id_field`
- task schema and workflow paths
- paper, label-map, metrics, baselines, and operator paths
- gold paths for paper-direct and MoLabel-operated views
- split, human-label, and review artifact paths
- `evaluation_modes`
- `scoring_variants`
- `evaluation_fields`
- `default_model_profile`
- redistribution notes and subset policy

Use the existing stage model implicitly supported by the scorer:

- `paper_model`
- `molabel_model`
- `workflow_autorun`
- `workflow_reviewed`
- `operator_reviewed`

### 3.3 `paper.yaml`

Capture paper and dataset provenance:

- paper title and citation
- dataset URL
- source repository URL if relevant
- dataset and repository licenses
- redistribution status
- original task definition
- original metrics

### 3.4 `label-map.yaml`

Define a strict mapping from dataset-native labels into MoLabel fields.

The label map must make these things explicit:

- record id field,
- dataset label fields,
- target label fields,
- lossy vs lossless mappings,
- paper-direct vs MoLabel-operated normalization decisions.

### 3.5 `metrics.yaml`

Stay inside the current supported metric types unless the benchmark is also
introducing a new reusable primitive.

Current supported metric types:

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

Important `metric_options` patterns now supported:

- classification:
  - `classification_diagnostics`
  - `abstain_field`
  - `abstain_gold_field`
  - `review_route_field`
  - `review_required_field`
  - `abstain_values`
- multi-label:
  - `threshold`
  - `thresholds`
  - `hierarchy`
  - `vocabulary`
- retrieval:
  - `qrels_field`
  - `k`
  - `fixed_depth`
  - `require_corpus_metadata`
- QA and evidence:
  - `joint_mode`
  - `decision_field`
- grounded generation:
  - `required_fields`

Every benchmark should define:

- one `primary_metric_id`,
- weighted metrics used in the overall score,
- zero-weight diagnostic metrics where needed,
- tax definitions for model, workflow, review, and operator deltas when those
  stages are meaningful.

### 3.6 `baselines.yaml`

Include at least:

- one paper or oracle baseline,
- one weak but interpretable floor baseline.

The floor should be deliberately simple and auditable, not tuned.

### 3.7 `operator.yaml`

Specify:

- operator scoring weights,
- blocking checks,
- non-blocking checks,
- benchmark-specific artifact-truthfulness rules.

Operator checks should validate product behavior, not just label quality.

### 3.8 `packaging.yaml` and `provenance.lock`

Use these to keep the pack reproducible:

- exactly which files are canonical,
- what subset policy was used,
- what raw paths or upstream materials were referenced,
- and whether redistribution constraints apply.

## 4. Build The Data Artifacts

At minimum, add:

- one scored split under `workbench/benchmarks/splits/`
- one paper-direct gold view
- one MoLabel-operated gold view
- one intentionally imperfect human-label artifact
- one intentionally imperfect review artifact

The committed slice should be:

- small enough for repeatable operator runs,
- paper-faithful enough that the benchmark report is honest,
- and difficult enough to expose review and adjudication behavior.

## 5. Keep The Two Gold Views Honest

Every benchmark should make the distinction explicit:

- paper-direct gold preserves the paper task contract as closely as possible,
- MoLabel-operated gold preserves the normalized MoLabel artifact contract.

Do not silently flatten or normalize paper artifacts without documenting the
loss in `label-map.yaml`, `paper.yaml`, or benchmark notes.

## 6. Write The Fixture Test

Add a focused unit test at:

- `tests/unit/test_grounded_benchmark_<benchmark-id>.py`

Each benchmark test should verify:

- the authority bundle loads,
- key scenario fields align,
- paper and redistribution metadata are correct,
- metrics and operator checks are present,
- split ids match gold ids,
- intentionally wrong human or review artifacts exist,
- committed reference run artifacts exist when the fixture ships with them.

## 7. Only Add Harness Code For Reusable Needs

If the benchmark needs new core support, add it only when it is reusable across
more than one benchmark family.

Good core additions:

- ranked retrieval metrics,
- span overlap scoring,
- answer normalization helpers,
- stable table or document anchors.

Bad core additions:

- one metric or parser branch that exists only for one dataset name,
- fixture-specific field assumptions in `grounded_benchmarks.py`,
- one-off report logic that cannot generalize.

## 8. Benchmark Family Mapping

Use this quick map when choosing metrics.

| Benchmark family | Existing metric types that fit |
|---|---|
| Single-label classification | `accuracy`, `macro_f1`, `exact_match`, `binary_recall`, `abstain_precision`, `abstain_recall` |
| Multi-label classification | `set_precision`, `set_recall`, `set_f1`, `jaccard`, `exact_match`, `micro_f1` |
| Moderation with rationales | `macro_f1`, `jaccard`, `token_mask_f1`, `exact_match` |
| FEVER-style verification | `feverous_score`, `accuracy`, `set_precision`, `set_recall`, `set_f1`, `exact_match`, `evidence_group_*`, `joint_evidence_decision` |
| QA with evidence | `answer_exact_match`, `answer_token_f1`, `supporting_fact_exact_match`, `supporting_fact_f1`, `joint_answer_support`, `anls` |
| Retrieval / ranking | `mrr`, `ndcg_at_k`, `recall_at_k`, `precision_at_k`, `map` |
| Span / extraction | `span_exact_match`, `span_overlap_f1` |
| Grounded generation | `source_coverage`, `unsupported_content_rate`, `grounded_generation_score` |

If the benchmark family is not covered by this table, treat it as a likely
framework task first and a fixture task second.

## 9. Default Next Benchmarks

If no other prioritization exists, use this order:

1. `BANKING77`
2. `GoEmotions`
3. `SciFact`

Those three give the best ratio of benchmark coverage gained to new framework
surface required.

# Grounded Benchmark Fixtures

This directory contains the grounded benchmark track.

For the canonical docs, use:

- `docs/guides/grounded-benchmark-framework.md` for harness behavior, stage
  semantics, scoring, and operator audit rules,
- `docs/guides/grounded-benchmark-catalog.md` for the benchmark-by-benchmark
  explanation of what each fixture measures and how it works.

Current engine note:

- The current labeling engine used by MoLabel benchmark runs is `MiniMax 2.7`
  through the Anthropic-compatible adapter path.

Grounded is different from `fixtures/benchmarks/`.

- `fixtures/benchmarks/` stays stress-first and workspace-first.
- `fixtures/benchmarks-grounded/` should be authority-pack-first.

## Canonical Rule

The canonical input for a grounded benchmark is the authority pack.

It should contain:

- paper and dataset provenance,
- licensing and redistribution rules,
- source acquisition or bundled raw slices where allowed,
- split definitions,
- paper-faithful gold artifacts,
- MoLabel-operational gold artifacts,
- simulated human artifacts,
- and benchmark scoring and operator checks.

It should not require:

- `workbench.project.yaml`,
- a pre-authored task schema,
- a pre-authored prompt,
- or a pre-authored workflow.

Those are optional `reference-workspace/` artifacts, not the operator starting
point.

## Recommended Layout

```text
<benchmark-id>/
  README.md
  authority/
    manifest.yaml
    paper.yaml
    packaging.yaml
    scenario.yaml
    label-map.yaml
    metrics.yaml
    baselines.yaml
    operator.yaml
    provenance.lock
    bootstrap/
    splits/
    gold/
    humans/
  source/
    raw/        # only if redistribution is acceptable
    notices/
  reference-workspace/  # optional
```

## Benchmark Intent

Grounded operator benchmarks should answer:

- can the agent runner (Claude Code or Codex) read the paper and authority materials,
- inspect the raw dataset,
- use the public `molabel` CLI as the main interface,
- build the project from scratch,
- handle data preparation,
- design schema, prompts, and workflow,
- run review and adjudication correctly,
- and produce paper-faithful evaluation outputs?

If a needed operator step cannot be done through public CLI surfaces, that is a
product gap and should be reported as such.

## Implemented Benchmarks

| Benchmark | Family | Primary metric | Notes |
|---|---|---|---|
| `clinc150` | single-label classification | `intent_accuracy` | intent plus explicit out-of-scope handling |
| `banking77` | single-label classification | `intent_accuracy` | closed-set fine-grained banking intents |
| `goemotions` | multi-label classification | `emotion_set_f1` | set-valued emotion labels |
| `hatexplain` | moderation with rationales | `stance_macro_f1` | label, community targets, token rationale mask |
| `feverous` | evidence-backed verification | `feverous_score` | sentence and table-cell evidence sets |
| `scifact` | evidence-backed verification | `scifact_joint_score` | scientific claim verdict plus evidence |
| `evidence-inference` | evidence-backed verification | `joint_effect_evidence` | intervention effect plus grouped evidence |
| `tabfact` | evidence-backed verification | `decision_accuracy` | table-grounded verdicts with evidence cells |
| `hotpotqa` | QA with evidence | `joint_answer_support` | answer text plus supporting facts |
| `qasper` | QA with evidence | `joint_answer_support` | scientific QA plus evidence and null handling |
| `docvqa` | QA with evidence | `anls` | document QA with OCR-noisy answer matching |
| `beir` | retrieval / ranking | `ndcg_at_5` | ranked retrieval against qrels |
| `msmarco` | retrieval / ranking | `mrr_at_5` | early-rank precision pressure |
| `cuad` | span extraction | `span_overlap_f1` | legal clause spans |
| `multispanqa` | span extraction | `span_overlap_f1` | discontiguous answer spans |
| `toxic-spans` | span extraction | `span_overlap_f1` | character-grounded toxicity spans |
| `totto` | grounded generation | `grounded_generation_score` | highlighted-cell-faithful generation |
| `webnlg` | grounded generation | `grounded_generation_score` | triple-faithful data-to-text generation |

## Transitional Status

Some current grounded directories still carry workspace-first scaffolding under
`workbench/`. Treat those as transitional or `reference-workspace/` material,
not as the long-term grounded contract.

## Packaging Rules

- `CLINC150`: vendorable with attribution.
- `FEVEROUS`: only small provenance-heavy slices should be vendored; preserve
  Wikipedia-derived notices.
- `HateXplain`: fetch-first until licensing is reconciled clearly.
- `FUNSD`: download-only; do not check raw payload into the repo.

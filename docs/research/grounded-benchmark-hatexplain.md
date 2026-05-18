# Grounded HateXplain Benchmark Note

This benchmark is the first grounded explainability fixture for MoLabel. It
now has a canonical authority pack plus a transitional reference workspace.

The current MoLabel labeling engine used when this benchmark is run live is
`MiniMax 2.7 highspeed` through the Anthropic-compatible adapter path.

## Why This Shape

- The dataset already provides majority-vote labels, target communities, and
  token-level rationales.
- A small subset is enough to verify the benchmark contract and keep the repo
  maintainable.
- The benchmark needs two different truths:
  - `paper-direct` for label and rationale fidelity
  - `molabel-operated` for workflow, review, and adjudication behavior

Authority files:

- `authority/manifest.yaml`
- `authority/packaging.yaml`
- `authority/provenance.lock`
- `authority/scenario.yaml`
- `authority/paper.yaml`
- `authority/label-map.yaml`
- `authority/metrics.yaml`
- `authority/baselines.yaml`
- `authority/operator.yaml`

Reference workspace:

- `workbench.project.yaml`
- `workbench/benchmarks/...`
- `workbench/config/task-schemas/...`
- `workbench/workflows/...`

## Selection Strategy

- source split: official test split
- subset size: 8 records
- balance: normal, offensive, and hatespeech examples
- rationale coverage: includes both empty and non-empty rationale masks

The subset is intentionally small, but it still exercises disagreement handling
and token-level rationale scoring.

## Evaluation Split

- `model`: compare raw predicted labels and rationale masks against the
  paper-direct gold view
- `workflow`: compare route/edit/adjudication decisions against the operational
  gold view
- `operator`: compare the external agent's CLI-and-skill behavior and artifact
  integrity against the operational workflow contract

## Licensing Note

The upstream repository is MIT licensed for code, but the dataset content still
requires careful provenance handling because it is social-media text. The
authority pack records the packaging policy explicitly so the benchmark can
distinguish canonical slices from the legacy workspace layout.

# HateXplain Grounded Benchmark

This benchmark now has a canonical authority pack plus a transitional
reference workspace.

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

The current MoLabel labeling engine for live benchmark runs is `MiniMax 2.7`
through the Anthropic-compatible adapter path.

The benchmark is organized around three evaluation modes:

- `model`: score raw label quality against the paper-aligned gold view
- `workflow`: score MoLabel review/adjudication behavior against the
  operational gold view
- `operator`: score an external agent operating MoLabel through the CLI and benchmark skill

Licensing note:

The upstream HateXplain repository is MIT licensed for code, but the dataset
content still requires careful review because it is social-media text. This
benchmark keeps the subset small and explicit so the provenance is visible and
the authority pack can record the license ambiguity separately from the legacy
workspace layout.

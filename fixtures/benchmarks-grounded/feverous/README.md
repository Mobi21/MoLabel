# FEVEROUS Grounded Benchmark

This benchmark uses a canonical authority pack plus a transitional reference
workspace.

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

This benchmark is a small grounded slice of the public FEVEROUS development
set. It is designed to measure:

- raw claim-verification quality,
- MoLabel workflow quality,
- external operator quality through the CLI-and-skill surface,
- and review/adjudication behavior against paper-faithful evidence rules.

The current MoLabel labeling engine for live benchmark runs is `MiniMax 2.7 highspeed`
through the Anthropic-compatible adapter path.

The committed slice keeps the benchmark redistributable while preserving the
official FEVEROUS structure:

- claims are verified against Wikipedia sentences and table cells,
- verdicts are `SUPPORTS`, `REFUTES`, or `NOT ENOUGH INFO`,
- and paper-direct success requires the verdict plus at least one complete
  gold evidence set.

The FEVEROUS paper and repository are cited in the benchmark metadata. The
dataset annotations are redistributed only as a small curated subset under the
official Wikipedia-derived license terms, and the authority pack separates that
policy from the legacy workspace layout.

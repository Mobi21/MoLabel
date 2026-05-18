# Grounded CLINC150 Benchmark Note

Current executable behavior is documented in
`docs/guides/grounded-benchmark-framework.md`.

This file remains useful as benchmark background and packaging context, but it
is not the primary current-state guide.

## Why This Shape

This fixture is a grounded micro-benchmark built from the official CLINC/OOS release rather than a synthetic reconstruction. The upstream repository says the dataset is English-only, single-intent, and includes 150 in-scope intents plus out-of-scope queries. The repo README also documents the canonical split structure and points to `data/data_full.json`.

The current MoLabel labeling engine used when this benchmark is run live is
`MiniMax 2.7 highspeed` through the Anthropic-compatible adapter path.

The benchmark is intentionally small:

- 16 test records,
- 4 support records for train,
- 4 support records for validation,
- 12 in-scope intent labels plus `oos`,
- and explicit human-label / review artifacts with intentional mistakes.

That keeps the benchmark useful for repeated CLI-driven runs while still preserving the original paper task structure.

## Files And Contract

The grounded CLINC150 pack is now organized as an authority pack plus a
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

The authority pack is the canonical contract. The current workspace tree is
retained as transitional reference material and executable test input until the
new CLI and scorer phases land.

The score layers are currently still implemented in the transitional workspace
shape:

- `paper_direct`: direct score against the subset gold labels from the upstream CLINC/OOS task.
- `model`: raw model labeling quality after MoLabel label normalization.
- `workflow`: quality after review and adjudication.
- `operator`: quality when an external agent drives the CLI-and-skill flow.

The new benchmark contract will move this into the five-stage authority model,
but that code path is not landed yet. The pack metadata is the migrated piece in
this phase.

The current live CLINC slice is also the smoke validation target for the shared
diagnostics layer:

- proposal-vs-review deltas,
- operator lift and regression counts,
- command-audit counters,
- artifact truthfulness checks,
- and report-vs-persisted-state consistency.

For the broader benchmark expansion plan, see
`docs/research/grounded-benchmark-paper-map.md` and
`docs/research/paper-backed-benchmark-candidates.md`.

## Licensing And Redistribution

Primary-source references:

- [CLINC/OOS repository](https://github.com/clinc/oos-eval)
- [Upstream LICENSE](https://raw.githubusercontent.com/clinc/oos-eval/master/LICENSE)
- [Paper at ACL Anthology](https://aclanthology.org/D19-1131/)

The upstream repo license is CC BY 3.0. This fixture ships only a small subset
of upstream examples. The authority pack records the provenance and packaging
rules separately from the reference workspace, so the benchmark can later
distinguish canonical slices from transitional scaffolding.

## Open Follow-Ups

- The grounded benchmark harness now has shared loading and scoring helpers in
  `molabel.core.quality.grounded_benchmarks`, but it still needs CLI entrypoints
  that can execute full paper-direct and MoLabel-operated runs automatically.
- Add a CLI entrypoint that can execute the grounded benchmark summary/report generation.
- If we later package more of CLINC150, verify whether the subset remains the right legal and practical cutoff.

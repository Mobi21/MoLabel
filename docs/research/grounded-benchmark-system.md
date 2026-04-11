# Grounded Benchmark System

Date: 2026-03-29
Status: Proposed rebuild blueprint
Related:

- `docs/research/paper-backed-benchmark-candidates.md`
- `docs/research/grounded-benchmark-paper-map.md`

Current executable behavior is documented in
`docs/guides/grounded-benchmark-framework.md`.

This file remains a design-history and rebuild-direction document rather than
the authoritative description of the current live harness.

## 1. Decision

MoLabel should rebuild the grounded benchmark harness contract from scratch.

This is not a recommendation to discard every existing grounded asset. It is a
recommendation to replace the current canonical shape, because the current
shape measures the wrong thing.

What should be reused:

- paper and dataset research already gathered,
- parts of the shared metric and report code,
- some curated source slices where licensing is acceptable,
- and some reference workspace content for maintainer baselines.

What should be replaced:

- the canonical grounded fixture contract,
- the operator harness,
- the grounded test entrypoints,
- and the assumption that a grounded benchmark starts from a solved workspace.

Current engine note:

- MoLabel currently uses `MiniMax 2.7` as the labeling engine in benchmark and
  real-LLM paths through the Anthropic-compatible adapter path. Grounded
  benchmark docs and harness outputs should keep naming `MiniMax 2.7`
  explicitly until the live engine changes.

## 2. Current Repo Contract

The repo currently has a split between:

- `fixtures/benchmarks/` for synthetic or stress fixtures,
- `fixtures/benchmarks-grounded/` for real-paper grounded fixtures,
- `packages/molabel-core/src/molabel/core/quality/grounded_benchmarks.py` for
  shared grounded contracts and scoring,
- `tests/e2e/tier1_pipeline/test_live_grounded_benchmarks_real_llm.py` for
  paper-direct model runs,
- `tests/e2e/tier1_pipeline/test_live_grounded_operator_benchmarks_real_llm.py`
  for operator-oriented runs,
- and `tests/e2e/infrastructure/grounded_operator.py` for operator fixture
  preparation.

The intended public product contract is also already clear in the repo:

- agents use the public `molabel` CLI as the primary interface,
- the backend stays behind that CLI,
- the GUI is the manual control room.

The CLI is already capable of substantial project authoring and operation:

- workspace bootstrap,
- dataset create and import,
- task-schema create,
- prompt create,
- workflow create and run,
- queue claim and status,
- review submit, draft, reveal, correct,
- adjudication queue and resolve,
- export create and download,
- artifact read, diff, and safe write.

But the grounded benchmark contract is still workspace-first in code and tests.

## 3. Why The Current Grounded Harness Is Wrong

The current grounded direction is not just incomplete. It is structurally
misaligned with the actual benchmark goal.

### 3.1 Docs And Code Disagree

The docs now say grounded should be authority-pack-first, but the executable
contract still requires a solved workspace.

Today the core grounded bundle requires paths like:

- `task_schema_path`
- `workflow_path`
- `workbench.project.yaml`
- `workbench/benchmarks/scenario.yaml`

That means the benchmark input already includes the schema and workflow the
operator was supposed to design.

### 3.2 The Operator Test Is An Operator Proxy

The current live grounded operator path copies a prebuilt fixture workspace,
loads the authored task schema and workflow, posts them through APIs, and then
scores the result.

That validates:

- API wiring,
- some scorer plumbing,
- and some review/adjudication behavior.

It does not validate:

- paper reading,
- raw dataset inspection,
- project design,
- schema authoring,
- prompt authoring,
- workflow design,
- or CLI-first project construction.

### 3.3 The Grounded Fixtures Hide The Hard Part

Current grounded fixtures often point `source_path` at benchmark-shaped test
splits or already-curated JSONL files, not at a raw authority surface.

That means the benchmark is silently skipping:

- dataset acquisition,
- raw format understanding,
- normalization decisions,
- split handling,
- and MoLabel project synthesis from first principles.

### 3.4 The Current Three-Layer Score Is Not Enough

`model`, `workflow`, and `operator` are not sufficient on their own to cleanly
separate:

1. raw model quality,
2. workflow quality,
3. review/adjudication quality,
4. Codex-as-operator quality.

Review and adjudication quality are currently partially buried inside
`workflow` or `operator`, which makes the resulting tax accounting too coarse.

### 3.5 Smoke Fixtures And Canonical Benchmarks Are Blended

The current grounded dataset slices are small enough to be useful as smoke
fixtures. That is good.

What is not good is letting those smoke fixtures stand in for the canonical
paper-faithful benchmark. A tiny curated slice can be operationally useful
without being sufficient to support a serious benchmark claim.

## 4. Canonical Architecture

The grounded benchmark system should have four distinct layers.

### 4.1 Authority Pack

This is the canonical benchmark input.

It contains:

- paper and dataset provenance,
- source acquisition rules,
- split definitions,
- paper-faithful gold artifacts,
- MoLabel-operational gold artifacts,
- simulated human artifacts,
- scoring definitions,
- operator checks,
- and packaging or licensing rules.

It does not contain:

- a required `workbench.project.yaml`,
- a required task schema,
- a required prompt,
- or a required workflow.

### 4.2 Reference Workspace

This is optional and derived.

It exists for:

- maintainer debugging,
- scorer validation,
- baseline regression,
- and workflow experiments.

It must not be the required input for operator evaluation.

### 4.3 Run Harness

This is the execution layer.

It should support five scored stages:

1. `paper_model`
2. `molabel_model`
3. `workflow_autorun`
4. `workflow_reviewed`
5. `operator_reviewed`

Those five stages are the minimum needed to separate the four quality classes
the benchmark must expose.

### 4.4 Report Layer

This is the durable output layer.

It should emit:

- machine-readable summaries,
- human-readable reports,
- tax breakdowns,
- stage-by-stage metrics,
- proposal-vs-review deltas,
- operator lift / regression / preserve counts,
- command-audit counters,
- artifact truthfulness checks,
- CLI transcript summaries,
- artifact integrity checks,
- and benchmark failure reasons.

## 5. Recommended Grounded Fixture Layout

Recommended canonical layout per benchmark:

```text
fixtures/benchmarks-grounded/<benchmark-id>/
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
      fetch.yaml
      transforms.py or transforms.md
    splits/
      official/
      benchmark/
    gold/
      paper-direct/
      molabel-operated/
    humans/
      gold/
      flawed/
    eval/
      scorer-notes.md
      acceptance-thresholds.yaml
  source/
    raw/                # only if redistribution is acceptable
    notices/
  reference-workspace/  # optional, derived or maintainer-authored
  reports/              # optional checked-in reference reports only
```

Rules:

- `authority/` is canonical.
- `source/raw/` is optional and only exists when redistribution is acceptable.
- `reference-workspace/` is secondary.
- benchmark outputs from real runs should not be committed back into the pack by
  default; they should go to a generated run location.

## 6. Authority Pack Contract

Every grounded authority pack should encode the following contracts explicitly.

### 6.1 Provenance Contract

- paper URL,
- dataset URL,
- source repository URL,
- license or terms URL,
- redistribution status,
- exact source files or source manifests,
- and content hashes for committed raw slices.

### 6.2 Task Contract

- original task definition,
- official label space,
- exact split semantics,
- exact primary metric,
- allowed secondary metrics,
- and any benchmark-profile caveat if the MoLabel pack uses a subset rather
  than the full official evaluation set.

### 6.3 Projection Contract

This is where paper-faithful annotations are projected into MoLabel.

It should define:

- paper-direct fields,
- MoLabel-operational fields,
- lossless projections where possible,
- explicit lossy projections where unavoidable,
- and benchmark warnings when a MoLabel projection cannot preserve the full
  paper structure.

### 6.4 Human Simulation Contract

The authority pack should carry two human layers:

- trusted human artifacts,
- intentionally flawed human artifacts.

Flawed artifacts must be explicit and labeled as flawed. They should never be
mixed into the canonical gold by implication.

## 7. Scoring Model

The current three-way score should be replaced by a five-stage model.

### 7.1 Stage Definitions

`paper_model`

- Run `MiniMax 2.7` directly against the paper-faithful task contract.
- Use the paper’s label and evidence structure.

`molabel_model`

- Run the same model through the MoLabel projection only.
- No workflow or review.

`workflow_autorun`

- Run a maintainer-authored reference workspace through MoLabel.
- No human simulation.

`workflow_reviewed`

- Run the reference workspace plus review and adjudication against the human
  simulation artifacts.

`operator_reviewed`

- Run from the authority pack only.
- Codex must build the project through the public CLI.
- Then run workflow, review, and adjudication.

### 7.2 Tax Definitions

Recommended benchmark deltas:

- `normalization_tax = paper_model - molabel_model`
- `workflow_tax = molabel_model - workflow_autorun`
- `review_lift = workflow_reviewed - workflow_autorun`
- `operator_tax = workflow_reviewed - operator_reviewed`
- `end_to_end_tax = paper_model - operator_reviewed`

This is better than the current model because it isolates review and
adjudication quality instead of smearing them into workflow or operator.

### 7.3 Reporting Rule

Do not collapse all benchmark outcomes into a single number by default.

Default reporting should show:

- per-stage paper-faithful metrics,
- per-stage operational metrics,
- review and adjudication outcomes,
- operator process score,
- blocking failures,
- and the signed tax breakdown.

A composite score can exist, but only as a secondary view.

### 7.4 Blocking Failures

The following should remain hard failures regardless of final label quality:

- bypassing public CLI surfaces for measured operator steps,
- mutating authority artifacts,
- relying on a prebuilt workspace in operator mode,
- producing incomplete benchmark outputs,
- or running with an undeclared labeling engine when the benchmark expects
  `MiniMax 2.7`.

## 8. CLI-First Operator Benchmark Loop

The operator benchmark should be measured through generic `molabel` project
commands, not through a magic benchmark command that performs the judged work
on the operator’s behalf.

The expected loop is:

1. inspect authority pack files,
2. inspect raw dataset slices or bootstrap metadata,
3. fetch or verify source material when needed,
4. `molabel workspace bootstrap`,
5. `molabel dataset create`,
6. `molabel dataset import`,
7. use `molabel artifact write` for authored files where direct file authoring
   is needed,
8. `molabel task-schema create`,
9. `molabel prompt create`,
10. `molabel workflow create`,
11. `molabel workflow run`,
12. `molabel queue status` and `molabel queue claim`,
13. `molabel review submit` or related review commands,
14. `molabel adjudication queue` and `molabel adjudication resolve`,
15. `molabel quality ...`,
16. `molabel export ...`,
17. benchmark-native scoring and report generation.

### 8.1 What Benchmark Commands Should Exist

Benchmark-native CLI support is still needed, but only for benchmark-specific
operations:

- `molabel benchmark inspect <pack>`
- `molabel benchmark fetch-source <pack>`
- `molabel benchmark verify-pack <pack>`
- `molabel benchmark score <pack> --run <run-dir>`
- `molabel benchmark report <pack> --run <run-dir>`
- `molabel benchmark compare <pack> --baseline <run-a> --candidate <run-b>`

These commands should not create the project for the operator. They should only
help with authority-pack management, scoring, and reporting.

## 9. Current CLI State And Remaining Gaps

The CLI now exposes the main grounded benchmark setup and reporting surfaces:

- benchmark inspect, fetch, verify, score, report, and compare,
- provider discovery and health,
- model-profile setup and connectivity testing,
- workflow create and execution control,
- and manifest entries for the benchmark-critical command families.

The remaining benchmark-relevant gaps are narrower:

- there is still no CLI surface for reviewer-profile creation beyond workspace
  bootstrap defaults,
- the live grounded operator test still computes a maintainer-only paper-direct
  baseline in the same file even though the operator surface is CLI-only,
- and the operator benchmark still needs a fully MoLabel-executed labeling step
  to close the gap between CLI project operation and CLI-driven label
  generation.

The harness should treat those remaining items as product gaps, not paper over
them with private API calls or hidden non-CLI operator paths.

## 10. Dataset-Specific Packaging Policy

Grounded benchmark packaging must be dataset-specific, not generic.

### 10.1 CLINC150

Primary sources:

- [paper](https://aclanthology.org/D19-1131/)
- [official repository](https://github.com/clinc/oos-eval)
- [license](https://raw.githubusercontent.com/clinc/oos-eval/master/LICENSE)

Policy:

- safe to vendor with attribution,
- preserve the original intent labels,
- preserve official split semantics,
- and keep any small MoLabel slice clearly separate from any canonical pack
  used for serious benchmark reporting.

Validation note:

- the current CLINC grounded slice is now the smoke harness for the shared
  diagnostics layer,
- its live operator run should be used to validate audit counters, operator
  lift, and truthfulness checks before expanding to other paper families,
- and the broader family map is tracked in
  `docs/research/grounded-benchmark-paper-map.md`.

### 10.2 HateXplain

Primary sources:

- [paper](https://arxiv.org/abs/2012.10289)
- [official repository](https://github.com/hate-alert/HateXplain)
- [dataset card](https://huggingface.co/datasets/Hate-speech-CNERG/hatexplain)

Policy:

- treat as fetch-first until the dataset license story is reconciled clearly,
- keep raw-source provenance explicit,
- preserve per-annotator rationale structure in authority artifacts,
- and do not describe the dataset content as cleanly MIT-licensed without
  qualification.

### 10.3 FEVEROUS

Primary sources:

- [dataset page](https://fever.ai/dataset/feverous.html)
- [license page](https://fever.ai/download/feverous/license.html)
- [NeurIPS dataset paper](https://arxiv.org/abs/2106.05707)
- [shared-task paper](https://aclanthology.org/2021.fever-1.1/)
- [official repository](https://github.com/Raldir/FEVEROUS)

Policy:

- safe to vendor only as small, provenance-heavy slices,
- keep Wikipedia-derived license notices with the pack,
- preserve nested evidence sets for paper-direct scoring,
- and treat flattened evidence atoms as an operational projection only.

### 10.4 FUNSD

Primary sources:

- [dataset site](https://guillaumejaume.github.io/FUNSD/)
- [license terms](https://guillaumejaume.github.io/FUNSD/work/)
- [paper](https://arxiv.org/abs/1905.13538)

Policy:

- do not vendor raw payload in the repo,
- keep it download-only pending explicit legal review,
- and do not use FUNSD as an initial grounded benchmark target.

## 11. Benchmark Profiles

Each grounded benchmark should define explicit profiles so that smoke testing
does not masquerade as canonical evaluation.

Recommended profiles:

- `canonical`: closest possible match to the official task and split,
- `operator-primary`: fixed-cost slice that still preserves the benchmark’s key
  task invariants,
- `smoke`: very small slice for regression and harness debugging.

Reporting rule:

- only `canonical` should be compared directly to published paper numbers,
- `operator-primary` should compare against MoLabel-maintained baselines on the
  same slice,
- and `smoke` should never be used for headline claims.

## 12. Rebuild Versus Migration

Recommendation: rebuild the grounded harness contract, migrate selected assets,
and keep the current harness only as temporary compatibility scaffolding.

This is effectively:

- contract rebuild,
- code-path migration,
- data and scorer reuse where valid.

This is not:

- a line-by-line incremental evolution of the current grounded fixture shape.

Why rebuild:

- the current canonical input is wrong,
- the current tests lock in the wrong contract,
- the current operator path is an operator proxy,
- and carrying both contracts as equal first-class shapes would create
  permanent ambiguity.

## 13. Migration Plan

### Phase 0: Freeze The Contract

- Declare `authority/` canonical for grounded.
- Declare `reference-workspace/` secondary.
- Stop expanding the old workspace-first grounded shape.

### Phase 1: Add New Authority Models

- Introduce authority-pack models alongside the current grounded bundle.
- Add pack validation.
- Add provenance, packaging, and benchmark-profile metadata.

### Phase 2: Build Benchmark-Native CLI Support

- add pack inspect, fetch, verify, score, and report commands,
- add provider and model-profile CLI surfaces,
- and fix the manifest so it accurately advertises implemented commands.

### Phase 3: Split The Scoring Pipeline

- separate paper-direct, operational, review, and operator scoring stages,
- add explicit `review_lift`,
- and make blocking failures first-class in the report format.

### Phase 4: Replace The Operator Harness

- replace API-proxy grounded operator tests with a true CLI transcript runner,
- capture command use, artifact diffs, and failure reasons,
- and require operator runs to start from the authority pack only.

### Phase 5: Migrate Dataset Packs

Recommended order:

1. CLINC150
2. FEVEROUS
3. HateXplain
4. FUNSD only after legal review

### Phase 6: Retire The Old Grounded Contract

- move solved grounded workspaces under `reference-workspace/`,
- replace old fixture-consistency tests with authority-pack validation tests,
- and retire the old operator proxy path.

## 14. Files And Directories To Deprecate, Migrate, Or Replace

Move or demote:

- `fixtures/benchmarks-grounded/*/workbench.project.yaml`
- `fixtures/benchmarks-grounded/*/workbench/config/task-schemas/*`
- `fixtures/benchmarks-grounded/*/workbench/workflows/*`

These should become optional `reference-workspace/` artifacts, not canonical
benchmark inputs.

Replace:

- `packages/molabel-core/src/molabel/core/quality/grounded_benchmarks.py`
  current top-level fixture contract
- `tests/e2e/infrastructure/grounded_operator.py`
- `tests/e2e/tier1_pipeline/test_live_grounded_benchmarks_real_llm.py`
- `tests/e2e/tier1_pipeline/test_live_grounded_operator_benchmarks_real_llm.py`
- `tests/unit/test_grounded_benchmark_fixtures.py`

Migrate carefully:

- per-dataset research docs under `docs/research/`
- per-dataset `paper.yaml`, `metrics.yaml`, and `label-map.yaml` content
- shared grounded scoring helpers that are still valid

## 15. Bottom Line

The grounded benchmark system should become first-class product infrastructure.

The canonical question is not:

- can MoLabel replay a solved benchmark workspace?

The canonical question is:

- can Codex use MoLabel, through the public CLI, to turn authority materials
  into a correct, paper-faithful, review-aware project and then run it well?

The current grounded harness is valuable only insofar as it helps us migrate to
that benchmark. It should not be mistaken for the finished benchmark system.

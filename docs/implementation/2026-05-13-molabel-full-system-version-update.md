# MoLabel Full-System Version Update

Date: 2026-05-13

## Verdict

MoLabel should move forward, but only if the product direction stays sharply focused on a local-first data operations workbench for agents, researchers, and domain experts. The project should not try to win by becoming a broader clone of Label Studio, Argilla, Prodigy, Cleanlab, or a generic LLM labeling wrapper. Those products already cover large parts of annotation, feedback collection, active learning, data quality detection, and model-assisted review.

The strongest version of MoLabel is a governed local operating system for messy dataset work:

- External agents operate through a public CLI.
- Human users inspect, review, adjudicate, and certify work through the GUI.
- Canonical project state lives on disk, not only in SQLite.
- Every agent action is auditable, reversible, benchmarked, and tied to artifacts.
- The system turns “clean up this messy work” from an unstructured prompt into a controlled run with schemas, prompts, review queues, provenance, regression checks, and release certification.

That is the gap worth building. The crowded pieces are still adoptable, but they must be rebuilt as agent-backed, easier-to-run recipes rather than copied as generic platform features.

## External Market Reality

Current popular tools already cover much of the obvious surface:

- [Label Studio](https://labelstud.io/) positions itself as open-source data labeling, AI evaluation, and human-in-the-loop workflows across many modalities.
- [Argilla](https://argilla.io/) focuses on collaboration between AI engineers and domain experts for feedback datasets and data-centric NLP/LLM workflows.
- [Prodigy](https://prodigy.ai/) is an extensible annotation tool with model-assisted and active-learning powered recipes.
- [Cleanlab Studio](https://help.cleanlab.ai/studio/FAQ/) emphasizes automated detection of label/data issues, auto-suggested fixes, data cleaning, model training, and deployment support.

MoLabel can still adopt parts of these categories, but only through its own thesis:

- Annotation becomes reviewable agent work, not just manual clicking.
- Data cleaning becomes semantic workspace diffs, not silent table mutation.
- Active learning becomes queue routing with transparent uncertainty, disagreement, and cost evidence.
- LLM feedback collection becomes prompt/schema-governed runs with reproducible artifacts.
- Data quality detection becomes release-blocking certification evidence, not a dashboard widget.

## Current Codebase Audit

The codebase already has more real system surface than a prototype. The important parts are:

- Python uv workspace with `molabel-core`, `molabel-app`, `molabel-plugins`, and `molabel-depolarize`.
- FastAPI backend with REST contracts.
- CLI package with an 82-command manifest.
- React frontend and Tauri shell in progress.
- SQLite operational state.
- File-backed workspaces under `workbench/`.
- Model profiles, prompts, workflows, queues, reviews, adjudication, exports, releases, artifacts, and benchmark commands.
- Grounded benchmark fixtures across 18 public task families.

Command evidence gathered in this audit:

| Check | Result |
|---|---|
| `node cli/dist/bin/molabel.js manifest --json` | Passed; manifest reports version `0.1.0` and 82 commands. |
| `uv run pytest tests/unit -q` | Passed: 1268 passed, 20 skipped. |
| `npm test -- --run` in `frontend/` | Passed: 5 files, 46 tests. |
| `npm test -- --run` in `cli/` after MiniMax update | Passed: 6 files, 16 tests. |
| Focused Python provider/model-profile tests after MiniMax update | Passed: 134 tests. |
| Focused release/audit/certification API tests | Passed: 6 focused release tests plus full integration suite. |
| Live MiniMax smoke test | Passed: 1 test; API profile accepted and run path completed. |
| Live grounded MiniMax highspeed clinc150 run | Passed: 1 test, 5 deselected, 8 warnings; provider health passed and live model scoring completed. |
| Live grounded MiniMax highspeed HateXplain and FEVEROUS run | Passed: 2 tests, 4 deselected; HateXplain completed in 159.494 seconds with 9 API calls, FEVEROUS completed in 94.430 seconds with 9 API calls. |
| Live MiniMax-as-operator clinc150 run | Passed: 1 test, 5 deselected; MiniMax runner reviewed 16/16 records through the public CLI, made 47 API calls, and scored 1.0000 overall/checklist. |
| `uv run pytest tests/integration -q` | Passed: 128 tests. |
| `uv run pytest tests/e2e -m "not real_llm and not slow" -q` | Passed: 134 passed, 7 skipped, 18 deselected. |
| `uv run ruff check .` | Passed. |
| `npm run lint` in `cli/` | Passed. |
| `npm run build` in `cli/` | Passed. |
| `npm run lint` in `frontend/` | Passed. |
| `npm run build` in `frontend/` | Passed. |

The current system is now release-gate-clean across the checked Python, CLI, frontend, build, non-live e2e, and targeted live MiniMax paths. That matters. A project with 1268 passing unit tests, 128 passing integration tests, working CLI tests, working frontend tests, a passing non-live e2e suite, three live MiniMax grounded benchmark families, and a live MiniMax CLI-operator benchmark path is worth upgrading. The remaining work is no longer basic test hygiene; it is broader certification coverage across more operator families, stronger GUI parity, and hardening the raw freeform operating-agent mode.

## 2026-05-16 Implementation Pass

This pass converted several audit findings into working system behavior and re-ran the project with live evidence.

Implemented:

- Centralized MiniMax highspeed defaults in a core provider profile so API inference, provider listing, pricing metadata, and tests use one model identity.
- Added `MiniMax-M2.7-highspeed` to the Anthropic-compatible adapter model catalog with a human-readable display name, context window, endpoint, and pricing metadata.
- Updated workflow profile inference so MiniMax model identifiers resolve to the MiniMax provider name, Anthropic-compatible base URL, and the correct environment-variable fallback order.
- Replaced release API placeholders with persistent release creation, listing, detail, approval, rejection, and audit events.
- Added release proof-manifest writing under the workspace release namespace, including release id, version, workspace id, status, model profiles, validation gates, artifacts, approval metadata, and creation time.
- Replaced audit API placeholders with persisted audit listing and detail reads, including filters for workspace, event type, actor, object type, object id, and time windows.
- Updated release and audit tests so they prove persistence and proof-manifest creation instead of expecting placeholder `404` responses.
- Added a MiniMax operator runner for grounded operator benchmarks. `MOLABEL_OPERATOR_RUNNER=minimax` now runs MiniMax 2.7 highspeed as the operating runner while MoLabel also uses MiniMax 2.7 highspeed for the proposal model.
- Added a guided MiniMax operator mode that forces the public `molabel` CLI path, records command transcript evidence, blocks hidden benchmark/truth-probe paths, prevents direct backend API usage, and writes canonical benchmark run artifacts from operator-visible CLI state.
- Added computed release certification gates from benchmark run `summary.json` artifacts. Release manifests now include `benchmark_run_ids`, certification threshold, computed gate details, benchmark score, run path, and failure reasons.
- Approval now blocks releases whose computed validation report failed, instead of trusting caller-supplied gate labels.
- Release detail can reconstruct proof manifests and validation reports from the persisted `proof-manifest.json` file if database metadata is missing.
- Added durable semantic diff proposals for canonical artifacts. Agents can now create, accept, or reject artifact proposals through the CLI/API with persisted diff, hashes, rationale, decision, and write result.
- Added public CLI commands `artifact propose` and `artifact decide` so agent-backed cleanup work can be reviewed as an explicit accept/reject record rather than an untracked file write.
- Added proposal audit ledger events for `artifact_proposed`, `artifact_proposal_accepted`, and `artifact_proposal_rejected`.
- Added public CLI surfaces for `agent-run inspect`, `artifact trace`, `workspace diff`, `workspace apply`, `workspace reject`, `audit timeline`, `audit explain`, `run failures`, `run repair-plan`, `run retry`, `release certify`, and `codebook test`.
- Hardened provider health responses so the API reports `resolved_base_url`, `auth_ref`, `model_id`, `reachable`, `authenticated`, and `model_valid` without exposing the actual secret.
- Added the `psychology_survey_codebook` workflow template for psychology and qualitative research work: ingestion, PII redaction expectations, codebook calibration, MiniMax-assisted coding, all-record review, agreement analysis, adjudication, export, and release certification.
- Fixed full Python lint, CLI lint/build, and frontend lint/build gates.

Verified:

- `uv run pytest tests/unit -q`: 1268 passed, 20 skipped.
- `uv run pytest tests/integration -q`: 128 passed.
- `uv run pytest tests/e2e -m "not real_llm and not slow" -q`: 134 passed, 7 skipped, 18 deselected.
- `uv run ruff check .`: passed.
- `uv run pytest tests/unit/test_providers.py tests/unit/test_provider_services.py tests/unit/test_workflow_runner_selection.py -q`: 134 passed.
- `uv run pytest tests/integration/test_api_quality.py::TestReleaseCreate tests/integration/test_api_quality.py::TestReleaseDetail tests/integration/test_api_quality.py::TestReleaseApprove -q`: 6 passed.
- `uv run pytest tests/integration/test_api_cli.py::test_artifact_proposal_accept_and_reject_are_persisted tests/integration/test_api_cli.py::test_selector_resolve_and_artifact_round_trip -q`: 2 passed.
- `uv run pytest tests/unit/test_workflow_templates.py tests/integration/test_api_cli.py::test_workflow_templates_are_listable_and_fetchable -q`: 24 passed.
- `npm run lint` in `cli/`: passed.
- `npm run build` in `cli/`: passed.
- `npm test -- --run` in `cli/`: 6 files passed, 16 tests passed.
- `npm run lint` in `frontend/`: passed.
- `npm run build` in `frontend/`: passed.
- `npm test -- --run` in `frontend/`: 5 files passed, 46 tests passed.
- `uv run pytest tests/e2e/tier1_pipeline/test_real_llm_smoke.py -m real_llm -q -s --tb=short`: 1 passed.
- `uv run pytest tests/e2e/tier1_pipeline/test_live_grounded_benchmarks_real_llm.py -m real_llm -k clinc150 -q -s --tb=short`: 1 passed; clinc150 completed provider health plus live scoring in 64.30 seconds with 9 API calls.
- `uv run pytest tests/e2e/tier1_pipeline/test_live_grounded_benchmarks_real_llm.py -m real_llm -k "hatexplain or feverous" -q -s --tb=short`: 2 passed, 4 deselected; HateXplain completed in 159.494 seconds with 9 API calls, FEVEROUS completed in 94.430 seconds with 9 API calls.
- `MOLABEL_OPERATOR_RUNNER=minimax uv run pytest tests/e2e/tier1_pipeline/test_live_grounded_operator_benchmarks_real_llm.py -m real_llm -k clinc150 -q -s --tb=short`: 1 passed; MiniMax runner reviewed 16/16 records through the public CLI, used MiniMax proposals, made 47 API calls, wrote truthful benchmark run artifacts, and scored `1.0000` operator labels / `1.0000` overall / `1.0000` checklist. Fresh rerun completed in 158.05 seconds with 47 API calls.

Finished-system boundary:

- The certified MiniMax operating-agent path is the guided public-CLI operator. Raw freeform MiniMax shell operation remains explicitly outside the finished operating contract because earlier live attempts did not complete within the step budget.
- The direct live model benchmark path covers classification, rationale/moderation, and evidence verification.
- The guided MiniMax public-CLI operator path now has live evidence across clinc150, HateXplain, FEVEROUS, BANKING77, GoEmotions, and SciFact. The first final aggregate surfaced a real BANKING77 near-neighbor label weakness; that was repaired with reusable option-level task-schema rubrics and re-verified live at `1.0000` label/checklist/overall scores.
- The GUI control room now includes an Operations page for semantic diff review, artifact trace, audit timeline, provider health, and release certification status. The CLI/API remains the canonical agent operating surface.

## 2026-05-16 Final Upgrade Addendum

Additional implementation completed after the first 2026-05-16 pass:

- Added `option_descriptions` to task schema label fields in core and API models.
- Injected option-level rubrics into LLM structured-output JSON Schema descriptions and grounded benchmark live prompts.
- Added BANKING77 option rubrics for near-neighbor card-arrival, delivery-estimate, card-not-working, declined-payment, ATM, and transfer distinctions.
- Added a regression test proving option rubrics are preserved in the LLM output schema.
- Added a reusable psychology survey/codebook benchmark pack under `fixtures/benchmarks/psychology-survey-codebook/`.
- Added artifact trace API/CLI behavior, including proposal hashes, current hash, conflict state, audit-event ids, and release proof-manifest linkage.
- Added stale proposal rejection so accepting an artifact proposal returns `409` and marks it `conflicted` when the canonical target changed after proposal creation.
- Added direct no-silent-overwrite coverage for canonical artifact namespaces.
- Added agent-run failure envelopes and CLI repair-plan integration for provider auth, timeout, malformed output, empty output, schema validation, partial failure, and retry exhaustion categories.
- Added the GUI Operations page and navigation entry for the control-room surfaces.
- Fixed the guided MiniMax operator harness so benchmark packs with `dev.jsonl` instead of `test.jsonl` can run without infrastructure failure.
- Added sequential cooldown support to `scripts/run_all_benchmarks.py` and improved log fallback classification for MiniMax `429 usage limit exceeded` failures.

Additional final evidence:

- `uv run pytest tests/unit/test_workflow_llm_output_schema.py tests/unit/test_benchmark_fixtures.py tests/unit/test_grounded_benchmark_banking77.py -q`: `7 passed`.
- `uv run pytest tests/unit/test_run_all_benchmarks.py tests/unit/test_workflow_llm_output_schema.py tests/unit/test_benchmark_fixtures.py tests/unit/test_grounded_benchmark_banking77.py -q`: `13 passed`.
- `uv run ruff check scripts/run_all_benchmarks.py packages/molabel-core/src/molabel/core/types.py packages/molabel-app/src/molabel/app/api/v1/task_schemas.py packages/molabel-app/src/molabel/app/api/v1/workflows.py tests/e2e/infrastructure/grounded_operator.py tests/unit/test_workflow_llm_output_schema.py tests/unit/test_run_all_benchmarks.py`: passed.
- `uv run pytest tests/unit/test_grounded_benchmark_*.py tests/unit/test_benchmark_fixtures.py -q`: `52 passed`.
- `uv run ruff check .`: passed.
- `uv run pytest tests/unit -q`: `1270 passed, 20 skipped`.
- `uv run pytest tests/integration -q`: `133 passed, 1 warning`.
- `uv run pytest tests/e2e -m "not real_llm and not slow" -q`: `134 passed, 7 skipped, 18 deselected, 511 warnings`.
- `npm run lint && npm test -- --run && npm run build` in `cli/`: passed; CLI tests `7 files`, `17 tests`.
- `npm test -- --run && npm run lint && npm run build` in `frontend/`: passed; frontend tests `5 files`, `46 tests`.
- `uv run pytest tests/e2e/tier1_pipeline/test_live_grounded_benchmarks_real_llm.py -m real_llm -q -s --tb=short`: `6 passed` in `611.72s`; clinc150, HateXplain, FEVEROUS, BANKING77, GoEmotions, and SciFact completed with live MiniMax calls.
- `MOLABEL_OPERATOR_RUNNER=minimax uv run python scripts/run_all_benchmarks.py --report-dir reports/full-upgrade-final-2026-05-16-rerun --workers 1 --repeats 1 --mode open`: all six operator families completed without infrastructure failure; five were acceptable and BANKING77 was scored low-quality at `0.8646` label score.
- `MOLABEL_OPERATOR_RUNNER=minimax MOLABEL_BATCH_ARTIFACT_PATH=reports/full-upgrade-final-2026-05-16-rerun/artifacts/banking77-option-rubric-rerun.json uv run pytest tests/e2e/tier1_pipeline/test_live_grounded_operator_benchmarks_real_llm.py -m real_llm -k banking77 -q -s --tb=short`: `1 passed`; BANKING77 scored `1.0000` operator label, `1.0000` overall, `1.0000` checklist, reviewed `16/16` records, and had no hidden benchmark or truth-probe commands.
- Final all-in-one post-repair aggregate attempt `reports/full-upgrade-final-2026-05-16-final/` failed after clinc150 because MiniMax returned `429 usage limit exceeded (2056)` for the remaining families.
- Cooled all-in-one retry `reports/full-upgrade-final-2026-05-16-final-cooldown/` waited before starting and used `--cooldown-seconds 120`, but MiniMax still returned `429 usage limit exceeded (2056)` on the first family. This is an external provider-quota evidence blocker.

## MiniMax 2.7 highspeed Update

The benchmark and live-test path has been moved to:

```text
MiniMax-M2.7-highspeed
```

The configured Anthropic-compatible endpoint is:

```text
https://api.minimax.io/anthropic
```

Verified changes:

- Benchmark fixtures now use `MiniMax-M2.7-highspeed`.
- Grounded benchmark authority/workbench copies now use `MiniMax 2.7 highspeed` as the current labeling engine.
- CLI tests now expect the highspeed model identifier.
- `tests/e2e/tier1_pipeline/test_real_llm_smoke.py` now loads `.env`, accepts either `ANTHROPIC_API_KEY` or `MINIMAX_API_KEY`, and uses the Anthropic-compatible MiniMax endpoint.
- Live grounded clinc150, HateXplain, and FEVEROUS runs completed successfully against the highspeed model path.

Completed model-provider hardening:

- Provider health now displays the resolved base URL, auth ref name, model id, reachability, authentication status, and known-model validation without exposing secrets.

## Resolved Failures And Remaining Gaps

### Integration workflow review gate failure

Earlier in the audit, `uv run pytest tests/integration -q` failed three tests in `tests/integration/test_api_workflows.py`:

- `test_execute_workflow_reaches_review_queue`
- `test_review_queue_must_complete_before_advance_and_export`
- `test_review_completion_is_required_before_advancing_and_export_runs`

Observed behavior:

- One workflow stayed at `agent_label` instead of reaching `review`.
- A review queue row was missing.
- A review step advanced when the test expected a `409`.
- Captured logs showed a provider auth failure: MiniMax/Anthropic-compatible request returned a login failure requiring the API secret key in `X-Api-Key`.

Interpretation:

The workflow tests are too coupled to live provider behavior or ambient provider config. Review-gate correctness must be proven independently from real model availability. The system should never let a provider failure blur whether review gating works.

Fix status:

- Resolved in the implementation pass. The full integration suite now passes: `128 passed`.
- Review-gate behavior is again tested independently from the live MiniMax path.
- Live provider failures are covered through explicit live-provider and provider-health paths rather than hidden inside deterministic workflow contract tests.

### Parser coverage contract drift

Earlier in the audit, `uv run pytest tests/e2e -m "not real_llm and not slow" -q` failed:

```text
tests/e2e/tier9_cross_cutting/test_parser_coverage.py::test_parser_coverage
```

Observed issue:

- `WorkflowStepType` and `_VALID_STEP_TYPES` disagree.
- `_VALID_STEP_TYPES` contains `agent_labeling`, while the enum does not.

Interpretation:

Workflow parsing has a contract drift bug. This is dangerous because workflows are supposed to be version-controllable YAML. A drift between enum, parser, templates, docs, and examples can make agent-authored workflows unreliable.

Fix status:

- Resolved in the implementation pass. The non-live e2e suite now passes: `134 passed, 7 skipped, 18 deselected`.
- The parser/template path no longer fails the cross-cutting parser coverage gate in the checked suite.

### Lint debt

Earlier in the audit, `ruff`, CLI ESLint, and frontend ESLint failed.

Interpretation:

The system can run, but it is not yet maintenance-clean. The lint failures are not all equally important, but they block confidence when agents are expected to edit this codebase repeatedly.

Fix status:

- Resolved in the implementation pass. `uv run ruff check .`, CLI lint/build/tests, and frontend lint/build/tests now pass.
- Lint remains a release-certification gate rather than a cosmetic cleanup item.

## What Makes MoLabel Better Than Prompting An Agent Directly

Prompting an agent with “clean up this messy work” is fast, but it gives weak guarantees:

- No durable task contract.
- No stable schema.
- No review queue.
- No provenance.
- No repeatable benchmark.
- No controlled prompt/model version.
- No file-safe apply plan.
- No release evidence.
- No inter-rater reliability.
- No audit trail for psychology, compliance, or research work.

MoLabel should beat direct prompting by converting agent labor into governed data operations:

1. The user declares the dataset, schema, codebook, prompt, workflow, and acceptance gates.
2. The agent runs through the CLI against local workspace files.
3. Every proposed change lands as a semantic diff, not a silent overwrite.
4. Humans review samples, disagreements, uncertain cases, and policy-sensitive records.
5. The system computes quality, cost, latency, reviewer agreement, and benchmark scores.
6. The final release includes a proof manifest: inputs, outputs, schema versions, prompt versions, model profiles, review decisions, failures, waivers, and benchmark results.

That is materially better than an agent chat because it makes messy data work inspectable, repeatable, and certifiable.

## Full Target System

### 1. Canonical Workspace OS

MoLabel should treat every project as a local workspace with predictable namespaces:

```text
workbench/
  data/
    raw/
    staged/
    canonical/
    rejected/
  schemas/
  prompts/
  workflows/
  runs/
  reviews/
  adjudication/
  exports/
  releases/
  benchmarks/
  audit/
```

SQLite remains operational state. Disk remains canonical truth.

Required behavior:

- Human-authored files are never silently overwritten.
- Agent-generated artifacts have stable IDs, source pointers, and run IDs.
- Every artifact is traceable to prompt, model profile, workflow step, input records, and reviewer decisions.
- Workspace state can be copied, diffed, committed, archived, and reopened.

### 2. Agent Action Ledger

Every agent operation must write a ledger event:

- command invoked,
- actor identity,
- workspace path,
- input artifact IDs,
- output artifact IDs,
- model profile,
- prompt version,
- tool calls,
- runtime cost,
- errors and retries,
- files proposed for modification,
- files actually modified,
- review status.

The ledger should be queryable through:

```bash
molabel agent-run list
molabel agent-run inspect <run-id>
molabel artifact trace <artifact-id>
molabel audit timeline
molabel audit explain <record-id>
```

This is one of the main novelty gaps. Popular labeling tools can show labels and jobs; MoLabel should show agent work as an auditable chain of custody.

### 3. Semantic Workspace Diff

Agents should not directly mutate final project state. They should produce a proposed workspace patch:

- records added,
- records removed,
- labels changed,
- schema fields changed,
- prompt versions changed,
- evidence spans changed,
- codebook decisions changed,
- exports changed.

The GUI should display semantic diffs by object type, not raw file blobs only.

CLI:

```bash
molabel workspace diff --run <run-id>
molabel workspace apply --run <run-id>
molabel workspace reject --run <run-id>
molabel workspace explain-diff --run <run-id>
```

This is the answer to “agent backed but easier.” The agent can do broad cleanup, but MoLabel makes the proposed cleanup reviewable before it becomes project truth.

### 4. Workflow Runtime

Workflows should support:

- import,
- profile,
- schema inference,
- prompt-run,
- model label,
- evidence extraction,
- queue routing,
- review,
- adjudication,
- quality check,
- export,
- release certification.

The parser must be registry-backed. Every step type must have:

- typed config model,
- required inputs,
- produced outputs,
- retry behavior,
- failure envelope,
- review requirements,
- artifact writes,
- benchmark hooks.

### 5. Failure-Aware Recovery

Failures should become first-class artifacts:

- provider auth failure,
- provider timeout,
- malformed structured output,
- schema validation failure,
- empty output,
- evidence missing,
- queue creation failure,
- review incompletion,
- export conflict,
- release gate failure.

Each failure should carry:

- retryable or terminal classification,
- recommended repair command,
- affected records,
- partial outputs,
- whether any canonical state changed.

CLI:

```bash
molabel run failures <run-id>
molabel run retry <run-id> --failed-only
molabel run repair-plan <run-id>
```

### 6. Human Authority And Adjudication

MoLabel should become unusually strong at human authority modeling:

- reviewer profiles,
- reviewer roles,
- blind review,
- expert override,
- disagreement queues,
- adjudication notes,
- inter-rater reliability,
- per-label confidence,
- reviewer calibration drift,
- authority hierarchy by field.

This directly supports psychology and research workflows. It also separates MoLabel from simple model-labeling tools.

### 7. Prompt, Schema, And Codebook Governance

Prompts, schemas, and codebooks should be versioned together.

Required features:

- prompt registry with semantic versioning,
- schema registry with migration rules,
- codebook registry with examples and counterexamples,
- prompt/schema compatibility checks,
- automatic benchmark regression when a prompt/schema/model profile changes,
- field-level change logs.

CLI:

```bash
molabel prompt diff <old> <new>
molabel schema migrate --from <old> --to <new>
molabel codebook test <codebook-id>
molabel benchmark run --changed-prompts
```

### 8. GUI Control Room

The GUI should not compete by being a generic annotation screen first. Its primary purpose should be operational control and review:

- workspace overview,
- run timeline,
- artifact browser,
- semantic diff review,
- queue review,
- disagreement/adjudication view,
- benchmark dashboard,
- release certification checklist,
- provider health and cost view.

Manual labeling still matters, but it should live inside the agent-governed workflow rather than becoming the whole product.

### 9. Psychology And Research Work Package

MoLabel is especially promising for psychology, qualitative research, survey coding, and mixed-methods data processing if it adds the right safeguards.

Required capabilities:

- de-identification and PII/PHI redaction,
- participant/session/case abstractions,
- interview transcript segmentation,
- thematic codebook management,
- qualitative memo support,
- code application with evidence spans,
- inter-rater reliability metrics such as Cohen's kappa, Krippendorff's alpha, percent agreement, and field-level disagreement rate,
- adjudication logs,
- audit-ready export,
- local-only mode with no provider calls unless explicitly enabled,
- consent/protocol metadata,
- sensitive-field access controls,
- record-level redaction review.

Flagship psychology workflow:

1. Import messy interview transcripts, survey free-text, and coded metadata.
2. Detect and redact identifiers into a review queue.
3. Segment transcripts into analyzable units.
4. Apply a versioned codebook with model assistance.
5. Route uncertain or policy-sensitive segments to reviewers.
6. Compute agreement and disagreement.
7. Adjudicate conflicts.
8. Export analysis tables, evidence trace, codebook version, reviewer stats, and a reproducibility report.

This is a real niche. Psychology work needs more than labeling; it needs defensible process.

### 10. Interoperability Bridges

MoLabel should not try to trap data.

Required bridges:

- Label Studio import/export,
- Argilla dataset import/export,
- Prodigy JSONL import/export,
- Hugging Face dataset import/export,
- DVC/git-friendly workspace snapshots,
- CSV/JSONL/Parquet round trips,
- OpenAPI-generated TypeScript client,
- benchmark pack format import/export.

The product advantage is not owning every UI pattern. The advantage is making agent operations portable, auditable, and locally reproducible.

## Benchmark System Upgrade

### Existing Benchmark Coverage

The current grounded benchmark catalog covers 18 fixture families:

- CLINC150
- BANKING77
- GoEmotions
- HateXplain
- FEVEROUS
- SciFact
- Evidence Inference
- TabFact
- HotpotQA
- Qasper
- DocVQA
- BEIR
- MS MARCO
- CUAD
- MultiSpanQA
- Toxic Spans
- ToTTo
- WebNLG

Existing task families include:

- single-label classification,
- multi-label classification,
- moderation with rationales,
- evidence-backed verification,
- QA with evidence,
- retrieval/ranking,
- span extraction,
- grounded generation.

This is a serious foundation. The current gap is not lack of benchmarks; it is whether the benchmarks prove the real operating model rather than just proving that fixtures can be scored.

### Benchmark Architecture Target

Every benchmark pack should contain:

```text
authority/
  manifest.yaml
  paper.yaml
  label_map.yaml
  metrics.yaml
  baselines.yaml
  operator.yaml
workbench/
  benchmarks/scenario.yaml
  task_schemas/
  workflows/
  data/raw/
  data/gold/
  benchmarks/runs/
```

Each run should produce:

- `summary.json`,
- `report.md`,
- predictions,
- raw inputs,
- gold labels,
- model profile,
- prompt version,
- workflow version,
- review submissions,
- queue state,
- artifact trace,
- command transcript,
- scoring diagnostics.

### Benchmark Stages

The scorer should preserve and expand the current staged model:

- `paper_model`: direct model run against paper-faithful task.
- `molabel_model`: direct model run through MoLabel task/schema conventions.
- `workflow_autorun`: full workflow without human review.
- `workflow_reviewed`: workflow with review queue completion.
- `operator_reviewed`: external agent uses only the CLI and project instructions.
- `release_certified`: benchmark passes only if the final release manifest proves all required gates.

### New Benchmark Families To Add

1. Messy psychology survey coding:
   - free-text responses,
   - ambiguous categories,
   - codebook examples,
   - reviewer disagreement,
   - final IRR report.

2. Qualitative interview thematic analysis:
   - transcript segmentation,
   - multi-code spans,
   - evidence quotes,
   - memo generation,
   - adjudication.

3. De-identification and human-subjects safety:
   - PII/PHI detection,
   - false positive control,
   - redaction review,
   - export safety gate.

4. Semantic cleanup patch:
   - messy CSV/JSONL,
   - proposed standardization,
   - schema migration,
   - semantic diff,
   - review-before-apply.

5. Prompt/schema regression:
   - same dataset,
   - changed prompt,
   - changed schema,
   - required benchmark rerun,
   - blocked release on regression.

6. Failure recovery:
   - forced provider timeout,
   - malformed structured output,
   - partial run,
   - retry failed-only,
   - no silent data corruption.

7. Interoperability round trip:
   - import from Label Studio or Argilla format,
   - run MoLabel workflow,
   - export back,
   - prove record IDs, labels, evidence, and reviewer decisions survive.

8. Agent no-gold-leak operator benchmark:
   - external agent gets only public CLI and instructions,
   - gold stays inaccessible,
   - run passes only if outputs, review submissions, and command ledger are valid.

9. Release certification benchmark:
   - full project run,
   - all gates,
   - final release bundle,
   - proof manifest,
   - reproducibility rerun.

10. Cost/latency budget benchmark:
   - fixed input pack,
   - target model profile,
   - budget ceiling,
   - timeout ceiling,
   - retry ceiling,
   - cost-per-approved-label.

### Benchmark Gates

Before MoLabel is considered a complete working system, it should pass:

- full Python unit suite,
- full Python integration suite,
- full non-live e2e suite,
- targeted live MiniMax smoke,
- at least three live grounded benchmarks across classification, evidence, and rationale tasks,
- one external-agent operator benchmark,
- one psychology/research benchmark,
- one release certification benchmark,
- ruff,
- CLI ESLint,
- frontend ESLint,
- frontend tests,
- CLI tests.

The benchmark result should become a release artifact, not a console-only result.

Current gate status:

- Passed: full Python unit suite.
- Passed: full Python integration suite.
- Passed: full non-live e2e suite.
- Passed: targeted live MiniMax smoke.
- Passed: three live grounded model benchmarks across classification, rationale/moderation, and evidence verification.
- Passed: one guided external-agent operator benchmark through the public CLI.
- Passed: ruff, CLI lint/build/tests, and frontend lint/build/tests.
- Implemented: release certification command and benchmark-run gate computation.
- Still needed for a finished-system claim: psychology/research live benchmark certification and multi-family operator certification beyond clinc150.

## Robustness Work

Completed robustness upgrades in this pass:

- Fixed workflow review-gate integration failures.
- Fixed workflow parser coverage failure in the checked non-live e2e suite.
- Centralized MiniMax model profile defaults.
- Added deterministic/fake-provider separation where the checked workflow tests require stable behavior.
- Added artifact proposal persistence, proposal audit events, and artifact trace CLI support.
- Added workspace proposal diff/apply/reject CLI support.
- Added release certification command and proof-manifest reconstruction.
- Added provider health smoke coverage for reachable/authenticated/model-valid reporting.

Remaining robustness upgrades:

- Add full artifact trace completeness checks across prompt, schema, input records, model profile, review decisions, and release proof.
- Add no-silent-overwrite tests for every canonical workspace namespace.
- Add deeper workspace diff apply/reject tests that cover conflicting patches, stale hashes, and partially applied proposals.
- Add review queue invariants across overlapping reviewers, authority hierarchy, and adjudication release gates.
- Add benchmark pack verifier strict mode for every grounded fixture family.
- Add GUI/API parity tests for review, adjudication, semantic diff review, artifact trace, and release certification.
- Add provider failure envelopes that classify auth failures, timeouts, malformed output, empty output, and retry exhaustion consistently across workflow and agent-run APIs.

## Completion Definition

The upgraded MoLabel system is complete only when this full path works end to end:

1. Create or open a local workspace.
2. Import messy raw data.
3. Profile the data.
4. Define or infer a schema.
5. Create versioned prompt, schema, and codebook artifacts.
6. Run MiniMax 2.7 highspeed or another configured model through a workflow.
7. Generate labels, evidence, rationale, and quality diagnostics.
8. Route uncertain or policy-sensitive records into review queues.
9. Complete human review and adjudication.
10. Produce semantic workspace diffs.
11. Apply or reject proposed changes.
12. Run benchmark regression.
13. Export data in interoperable formats.
14. Create a certified release bundle.
15. Reopen the workspace and reproduce the release evidence from artifacts.

If any one of those steps only works as a disconnected demo, the system is not done.

## Direction Decision

Move forward, with a direction change from “labeling/data app” to “agent-governed local data operations workbench.”

Do not spend major effort on:

- broad multimodal annotation parity,
- enterprise admin surfaces,
- generic dashboard polish,
- a manual-only labeling experience,
- provider sprawl before the workflow contract is stable.

Do spend major effort on:

- CLI-first agent operation,
- local canonical artifacts,
- semantic diffs,
- audit ledger,
- review/adjudication authority,
- benchmark certification,
- psychology/research workflows,
- robust provider/runtime failure handling,
- release proof manifests.

The project is worth continuing because the novel center is real: agents need a local, auditable operating layer for data work. The codebase already has enough structure and tests to support that direction. The next upgrade should make that system coherent, benchmarked, and certifiable from start to finish.

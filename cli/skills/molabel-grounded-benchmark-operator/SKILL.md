---
name: 'molabel-grounded-benchmark-operator'
description: 'Use when Codex should run MoLabel grounded benchmark regressions, analyze failures or score movement, localize the highest-leverage cause, and make the smallest honest fix across fixtures, reusable primitives, or product code without benchmark gaming.'
---

# MoLabel Grounded Benchmark Operator

Use this skill when benchmark improvement or grounded benchmark regression work is the task.

## Trigger

Trigger when the request is to:

- run or improve grounded benchmarks,
- diagnose benchmark failures or score regressions,
- inspect fixture or authority-pack breakage,
- improve benchmark quality honestly over repeated runs,
- or work in `fixtures/benchmarks-grounded/`, `tests/unit/test_grounded_benchmark_*.py`, `tests/unit/test_benchmark_fixtures.py`, `packages/molabel-core/src/molabel/core/quality/grounded_benchmarks.py`, or `packages/molabel-core/src/molabel/core/quality/grounded_benchmark_primitives.py`.

## First Read

Read these before changing semantics:

- `AGENTS.md`
- `docs/guides/grounded-benchmark-framework.md`
- `docs/guides/grounded-benchmark-expansion-plan.md`
- `docs/guides/grounded-benchmark-authoring-checklist.md`
- `packages/molabel-core/src/molabel/core/quality/grounded_benchmarks.py`
- `packages/molabel-core/src/molabel/core/quality/grounded_benchmark_primitives.py`

Inspect the specific failing test file and fixture directory before editing.

## Operating Loop

1. Inspect the repo first.
   - Run `git status --short`.
   - Assume the worktree is dirty until proven otherwise.
   - Do not revert unrelated user changes.
   - Respect the package boundaries in `AGENTS.md`.

2. Pick the smallest benchmark slice that can falsify the current hypothesis.
   - If one benchmark failed, start with its single test file.
   - If a shared primitive or scorer changed, start with the relevant primitive test file and one representative benchmark family.
   - If a fixture changed, start with that fixture test and any direct benchmark test.
   - Only run the whole grounded unit set after the targeted path is green.

3. Run targeted validation before broad regressions.
   - Whole grounded unit sweep:
     - `uv run pytest tests/unit/test_grounded_benchmark_*.py tests/unit/test_benchmark_fixtures.py`
   - Single benchmark:
     - `uv run pytest tests/unit/test_grounded_benchmark_scifact.py -q`
   - Single primitive family:
     - `uv run pytest tests/unit/test_grounded_benchmark_primitives_evidence_qa.py -q`
     - `uv run pytest tests/unit/test_grounded_benchmark_primitives_ranking_span_generation.py -q`
     - `uv run pytest tests/unit/test_grounded_benchmark_primitives_classification_multilabel.py -q`
   - Fixture integrity:
     - `uv run pytest tests/unit/test_grounded_benchmark_fixtures.py tests/unit/test_benchmark_fixtures.py -q`
   - Narrow further with `-k`, `::test_name`, or a single file when one assertion is enough.

4. Extract the actual failure or regression.
   - Record the failing test, benchmark id, metric ids, stages, and variant view.
   - Check whether the movement is in `paper_model`, `molabel_model`, `workflow_autorun`, `workflow_reviewed`, or `operator_reviewed`.
   - Check whether the affected view is `paper_direct`, `molabel_operated`, or both.
   - Inspect the authority pack first, then fixture data, then scorer logic, then broader product behavior.
   - Use lightweight inspection:
     - `rg -n "benchmark_id|primary_metric_id|metric_type|stage|paper_direct|molabel_operated|authority|operator" fixtures/benchmarks-grounded/<benchmark-id> tests/unit packages/molabel-core/src/molabel/core/quality`
     - `sed -n '1,220p' <path>`

5. Classify the issue before fixing it.
   - Framework bug: shared primitive, validator, scorer, report, or stage routing is wrong across benchmark families.
   - Fixture bug: authority pack, gold rows, review artifacts, provenance, or split alignment is wrong for one benchmark.
   - Scoring bug: metric wiring, field mapping, stage mapping, or variant mapping is wrong.
   - Legitimate benchmark limitation: the harness is truthful, but the benchmark requires semantics the current reusable primitives do not yet express honestly.

6. Apply the smallest honest fix.
   - First fix failing tests and broken semantics.
   - Then fix regressions in reusable primitives.
   - Then improve benchmark fixtures when provenance, authority-pack integrity, or paper-faithfulness is the problem.
   - Only then consider broader product improvements directly supported by failing evidence.
   - Avoid speculative refactors.

7. Rerun the right validation set.
   - Rerun the exact failing target first.
   - If shared logic changed, rerun the primitive family plus at least one other benchmark family that exercises the same primitive.
   - If `grounded_benchmarks.py` changed, rerun the relevant benchmark tests and the grounded fixture sweep.
   - If fixture files changed, rerun that fixture test and the benchmark-specific test.
   - End with:
     - `uv run pytest tests/unit/test_grounded_benchmark_*.py tests/unit/test_benchmark_fixtures.py`

8. Summarize the result truthfully.
   - Report what ran.
   - Report what failed or regressed.
   - State the root-cause hypothesis.
   - State what changed.
   - State what was rerun and what passed.
   - State remaining limitations, residual risk, and any paper-faithfulness compromise.

## Improvement Policy

Use this priority order:

1. broken tests and semantic regressions,
2. reusable primitive bugs,
3. fixture defects or authority-pack defects,
4. broader product fixes supported by the failing evidence.

Prefer additive fixture work over new framework work.

Only add framework code when the gap is clearly reusable across benchmark families.

Do not create a parallel benchmark path.

## Guardrails

- Do not add dataset-name branching in `grounded_benchmarks.py`.
- Do not weaken, bypass, or special-case the authority-pack system.
- Do not hide failures by editing gold data, baselines, thresholds, or reports unless the underlying authority or paper mapping is actually wrong.
- Do not claim paper-faithful improvement when the harness measures a normalized MoLabel-operated view.
- Keep `paper_direct` and `molabel_operated` distinct.
- Preserve stage-aware scoring, stage-aware deltas, and stage-aware reporting.
- Reuse primitives from `grounded_benchmark_primitives.py`; do not clone fixture-specific copies into benchmark-specific code.
- Never silently flatten paper semantics when the task requires grouped evidence, joint QA plus support, ranking depth, span offsets, or grounded generation anchors.
- Do not add one-off report logic or parser branches that only work for one benchmark id.
- Do not add DePolarize-specific logic outside `packages/molabel-depolarize`.

## Semantic Rules

- Treat the authority pack as the canonical benchmark contract.
- Preserve the meaning of `paper_direct` even when MoLabel normalization needs a separate operational view.
- Preserve the meaning of `molabel_operated` as the truthful normalized MoLabel artifact view.
- If a benchmark needs grouped evidence, multiple acceptable gold groups, joint answer plus support, retrieval ranking, span offsets, or grounded generation anchors, preserve those structures explicitly.
- If current primitives cannot represent the paper task honestly, stop calling it a fixture bug. It is a reusable framework gap or a blocked benchmark.

## When To Stop And Ask For Help

Stop and escalate instead of forcing a shortcut when:

- the only apparent fix is a benchmark-specific branch in shared framework code,
- the benchmark requires a new semantic primitive that is not obviously reusable,
- paper-direct and MoLabel-operated views cannot both remain honest under the proposed fix,
- provenance, redistribution, or authority-pack truth is unclear,
- the score can only be improved by hiding operator mistakes or relaxing audit checks,
- or the change would silently alter what the report claims to measure.

## Useful Commands

- Repo inspection:
  - `git status --short`
  - `rg --files tests/unit fixtures/benchmarks-grounded packages/molabel-core/src/molabel/core/quality`
  - `rg -n "scifact|feverous|hotpotqa|qasper|beir|msmarco|multispanqa|totto|webnlg|docvqa|tabfact|goemotions|banking77|clinc150|hatexplain|cuad|toxic-spans" tests/unit fixtures/benchmarks-grounded`
- Focused reads:
  - `sed -n '1,220p' packages/molabel-core/src/molabel/core/quality/grounded_benchmarks.py`
  - `sed -n '1,260p' packages/molabel-core/src/molabel/core/quality/grounded_benchmark_primitives.py`
  - `sed -n '1,220p' tests/unit/test_grounded_benchmark_scifact.py`
- Test commands:
  - `uv run pytest tests/unit/test_grounded_benchmark_*.py tests/unit/test_benchmark_fixtures.py`
  - `uv run pytest tests/unit/test_grounded_benchmark_scifact.py -q`
  - `uv run pytest tests/unit/test_grounded_benchmark_primitives_evidence_qa.py -q`
  - `uv run pytest tests/unit/test_grounded_benchmark_primitives_ranking_span_generation.py -q`
  - `uv run pytest tests/unit/test_grounded_benchmark_primitives_classification_multilabel.py -q`
  - `uv run pytest tests/unit/test_grounded_benchmark_fixtures.py tests/unit/test_benchmark_fixtures.py -q`

## Output Contract

The final benchmark-improvement report must include:

- what ran,
- what failed or regressed,
- the root-cause hypothesis,
- what changed,
- what was rerun,
- what passed,
- any remaining limitations or follow-up items,
- and any paper-faithfulness compromise or unresolved semantic mismatch.

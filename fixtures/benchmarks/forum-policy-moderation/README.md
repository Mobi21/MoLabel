# Forum Policy Moderation Benchmark

## Purpose

This benchmark evaluates whether MiniMax 2.7 can moderate messy markdown thread
content with evidence-backed reasoning while Codex operates the workflow in
MoLabel.

The records stress:

- harassment and dogpiling
- xenophobic speech
- leaked secret handling
- security-circumvention requests
- quoted context and moderator-note carryover

## Benchmark Question

Can the model:

1. identify the right policy category,
2. assign severity without flattening everything to the maximum,
3. decide whether content can remain visible,
4. cite evidence cleanly,
5. and correct bad human review calls when necessary?

## Files

- `data/raw/thread-*.md`
- `workbench/config/task-schemas/forum-policy-v1.yaml`
- `workbench/workflows/live-cli-forum-policy.yaml`
- `workbench/benchmarks/gold/forum-policy-gold.jsonl`
- `workbench/benchmarks/human-labels/reviewer-rin.jsonl`
- `workbench/benchmarks/reviews/reviewer-devon.jsonl`
- `AGENTS.md`

## Recommended Live Run

1. Start a reviewer session.
2. Register the markdown dataset.
3. Register the moderation schema.
4. Register the MiniMax model profile.
5. Use `AGENTS.md` as the prompt backbone.
6. Run the benchmark with real structured moderation calls.
7. Compare predictions to gold.
8. Replay simulated human labels and review decisions.
9. Note where the model correctly overrides bad human judgment.

## Evaluation Focus

Primary fields:

- `severity`
- `violation_types`
- `allow_publish`

Secondary diagnostics:

- `evidence_quotes`
- over- versus under-enforcement
- whether explicit xenophobic language is handled correctly

## Known Intentional Human Errors

- `reviewer-rin` allows the leaked-key thread to remain published
- `reviewer-devon` undercalls the xenophobic harassment thread and allows it

Those are deliberate benchmark traps.

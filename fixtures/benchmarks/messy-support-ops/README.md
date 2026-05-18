# Messy Support Ops Benchmark

## Purpose

This benchmark is for live MiniMax 2.7 highspeed runs where Codex is the operator and
MoLabel is the workbench. It is intentionally small enough to run repeatedly,
but messy enough to expose normalization, routing, and review failures.

The dataset stresses:

- HTML fragments inside otherwise plain-text tickets
- duplicated phrases from chat transcripts
- attachment mentions without attachment contents
- mixed-language customer requests
- ambiguity between bug, feature request, and documentation feedback
- escalation language that should change urgency

## Benchmark Question

Can the model:

1. clean up noisy support text without deleting important signals,
2. classify intent and urgency accurately,
3. flag when a human must intervene,
4. preserve uncertainty instead of hallucinating certainty,
5. and behave sensibly when human labelers or reviewers are wrong?

## Files

- `data/raw/support_tickets.csv`: raw messy source records
- `workbench/config/task-schemas/support-triage-v1.yaml`: label contract
- `workbench/workflows/live-cli-support-triage.yaml`: benchmark workflow
- `workbench/benchmarks/gold/support-triage-gold.jsonl`: confirmed labels
- `workbench/benchmarks/human-labels/reviewer-avery.jsonl`: simulated human labels
- `workbench/benchmarks/reviews/reviewer-jo.jsonl`: simulated review events
- `AGENTS.md`: deep operator prompt and decision rules

## Expected Operator Mode

Codex should operate this benchmark as a disciplined benchmark run, not as a
demo. That means:

- compare model output against gold labels,
- inspect disagreement instead of flattening it,
- identify whether the model or the simulated human is wrong,
- and preserve a short error taxonomy for repeat failures.

## Recommended Live Run

1. Create or detect the workspace through MoLabel.
2. Create a dataset from `support_tickets.csv`.
3. Register `support-triage-v1`.
4. Register a MiniMax model profile using the Anthropic-compatible path and the
   `.env` key.
5. Create a prompt grounded in `AGENTS.md`.
6. Run the records through MiniMax 2.7 highspeed.
7. Compare outputs against `support-triage-gold.jsonl`.
8. Replay simulated human labels and reviews.
9. Record where the model corrected bad human work and where it failed.

## Evaluation Focus

Primary fields:

- `primary_intent`
- `urgency`
- `needs_human_followup`

Secondary diagnostics:

- `cleanup_issues`
- whether the model over- or under-escalates
- whether mixed language is handled cleanly

## Known Intentional Human Errors

- `reviewer-avery` underestimates urgency on `sup-002`
- `reviewer-jo` misroutes `sup-003` as low-risk documentation feedback

These are deliberate. The benchmark is better when the model can disagree with
bad human work for the right reason.

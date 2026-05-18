# Claims Audit Extraction Benchmark

## Purpose

This benchmark evaluates whether MiniMax 2.7 highspeed can extract structured claims data
from noisy OCR packets while Codex manages the project through MoLabel.

The records are intentionally messy:

- OCR punctuation drift
- inconsistent currency formatting
- partial identifiers
- missing document references
- prior-audit context buried in narrative notes
- routing ambiguity between claims ops, utilization review, documentation
  follow-up, and special investigations

## Benchmark Question

Can the model:

1. extract provider and amount reliably from noisy packet text,
2. route each packet to the correct downstream queue,
3. assign risk flags only when there is evidence,
4. avoid inventing missing values,
5. and outperform intentionally flawed human decisions?

## Files

- `data/raw/claims_packets.jsonl`
- `workbench/config/task-schemas/claims-audit-v1.yaml`
- `workbench/workflows/live-cli-claims-audit.yaml`
- `workbench/benchmarks/gold/claims-audit-gold.jsonl`
- `workbench/benchmarks/human-labels/reviewer-mika.jsonl`
- `workbench/benchmarks/reviews/reviewer-sam.jsonl`
- `AGENTS.md`

## Recommended Live Run

1. Bootstrap the workspace and reviewer session.
2. Register a dataset from the JSONL packet file.
3. Register the task schema.
4. Register a MiniMax model profile through the Anthropic-compatible path.
5. Build the prompt from `AGENTS.md`.
6. Run real structured extraction calls against the packet text.
7. Score the outputs against gold.
8. Replay the simulated human labels and review decisions.
9. Inspect whether the model catches the deliberate human mistakes.

## Evaluation Focus

Primary fields:

- `provider_name`
- `total_amount`
- `routing_queue`

Secondary diagnostics:

- `audit_risk_flags`
- missing-document handling
- duplicate-claim handling
- preauth-gap handling

## Known Intentional Human Errors

- `reviewer-mika` routes `clm-002` to `claims_ops` instead of `utilization_review`
- `reviewer-sam` corrupts the amount on `clm-003` and fabricates a billing outlier

Those errors are deliberate. The benchmark is stronger when the model refuses
to copy bad human reasoning.

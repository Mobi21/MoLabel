# Product Requirements

This folder contains the product specification for MoLabel.

Current direction:

- agent-first,
- CLI-primary,
- GUI as manual control room and observability layer,
- no in-app assistant as the primary AI surface.

## Documents

- [`agentic-data-operations-workbench-prd.md`](./agentic-data-operations-workbench-prd.md)
  — Primary product requirements document. Source of truth for product scope, architecture, and requirements.

- [`ux-and-ai-strategy.md`](./ux-and-ai-strategy.md)
  — Companion strategy note for CLI-primary operation, GUI control-room UX, and manual fallback design.

- [`agent-benchmark-and-evaluation.md`](./agent-benchmark-and-evaluation.md)
  — Benchmark portfolio and evaluation strategy for messy data, gold labels, human simulation, and Codex-driven operation.

- Decision log and unresolved questions
  — No standalone decision-log file is checked in under `docs/prd/decisions/` at
  the moment. Treat open questions as living inside the PRD and companion notes
  until that directory is restored.

## How to use these docs

The PRD is the primary reference. The strategy and benchmark docs provide
supporting context for interface design, evaluation, and open questions.

For current executable behavior, prefer the guides in `docs/guides/`:

- `docs/guides/how-molabel-works-today.md`
- `docs/guides/grounded-benchmark-framework.md`

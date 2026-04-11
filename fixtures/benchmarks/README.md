# Benchmark Fixtures

These fixtures are designed for live `molabel` CLI runs where Codex acts as the
operator and `minimax-2.7` is the labeling model under test via the
Anthropic-compatible SDK path.

Each benchmark workspace includes:

- messy source data,
- confirmed gold labels,
- simulated human labeling artifacts,
- simulated human review artifacts with some intentionally wrong decisions,
- a benchmark-specific `README.md` with the operator runbook,
- a benchmark-specific `AGENTS.md` with deep prompting and evaluation rules,
- a task schema,
- and a workflow file for a realistic CLI-driven run.

Scenarios:

| Scenario | Raw format | Focus |
|---|---|---|
| `messy-support-ops` | CSV | cleanup + triage classification + review |
| `claims-audit-extraction` | JSONL | structured extraction + routing + review |
| `forum-policy-moderation` | Markdown | evidence-based moderation + human correction |

Canonical scenario metadata lives in each workspace under
`workbench/benchmarks/scenario.yaml`.

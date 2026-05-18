# CLINC150 Grounded Benchmark

This benchmark is a grounded micro-benchmark built from official CLINC/OOS
examples. It keeps the paper task structure intact while staying small enough
to run repeatedly.

The current MoLabel labeling engine for live benchmark runs is `MiniMax 2.7 highspeed`
through the Anthropic-compatible adapter path.

Evaluation modes:

- `paper_direct`: score against the original CLINC/OOS label decisions.
- `model`: score raw model outputs after MoLabel normalization.
- `workflow`: score workflow execution, review preservation, and adjudication behavior.
- `operator`: score the external agent operating MoLabel through the CLI and benchmark skill only.

License: CC BY 3.0 from the upstream CLINC/OOS repository.

# BANKING77 Grounded Benchmark

This benchmark is a grounded micro-benchmark built on the BANKING77 banking
intent task. It keeps the single-label classification contract intact while
staying small enough to run repeatedly.

The current MoLabel labeling engine for live benchmark runs is `MiniMax 2.7`
through the Anthropic-compatible adapter path.

Evaluation modes:

- `paper_direct`: score against the canonical BANKING77 intent labels.
- `model`: score raw model outputs after MoLabel normalization.
- `workflow`: score workflow execution, review preservation, and adjudication behavior.
- `operator`: score the external agent operating MoLabel through the CLI and benchmark skill only.

License: MIT from the upstream `PolyAI-LDN/task-specific-datasets` repository.
The committed utterances are representative synthetic examples matched to
BANKING77 intent categories; see `authority/provenance.lock` for provenance.

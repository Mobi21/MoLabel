# GoEmotions Grounded Benchmark

This benchmark is a grounded micro-benchmark built on the GoEmotions
multi-label emotion classification task. It keeps the set-valued annotation
contract intact while staying small enough to run repeatedly.

The current MoLabel labeling engine for live benchmark runs is `MiniMax 2.7 highspeed`
through the Anthropic-compatible adapter path.

Evaluation modes:

- `paper_direct`: score against the canonical GoEmotions label sets.
- `model`: score raw model outputs after MoLabel normalization.
- `workflow`: score workflow execution, review preservation, and adjudication behavior.
- `operator`: score the external agent operating MoLabel through the CLI and benchmark skill only.

License: Apache-2.0 from the upstream `google-research/google-research/goemotions`
directory. The committed utterances are representative synthetic examples
matched to GoEmotions categories; see `authority/provenance.lock` for
provenance.

Metric coverage limitation: GoEmotions' paper-direct evaluation uses per-label
macro-F1 and micro-F1 under multi-label binarization. The current grounded
scorer supports set-valued metrics (`set_precision`, `set_recall`, `set_f1`,
`jaccard`, `exact_match`) which express the same set-matching behavior at the
record level. The committed slice is small enough that label-averaged macro-F1
would be dominated by support differences, so this fixture reports the
set-valued metrics honestly and does not claim paper-exact macro-F1. See
`authority/metrics.yaml` for the current metric contract.

# SciFact Grounded Benchmark

This benchmark is a grounded micro-benchmark built on the SciFact scientific
claim verification task. It keeps the joint verdict-plus-evidence contract
from the paper while staying small enough to run repeatedly.

The current MoLabel labeling engine for live benchmark runs is `MiniMax 2.7`
through the Anthropic-compatible adapter path.

Evaluation modes:

- `paper_direct`: score against the canonical SciFact verdict + rationale sentences.
- `model`: score raw model outputs after MoLabel normalization.
- `workflow`: score workflow execution, review preservation, and adjudication behavior.
- `operator`: score the external agent operating MoLabel through the CLI and benchmark skill only.

License: CC BY-NC 2.0 from the upstream `allenai/scifact` repository. The
committed utterances are representative synthetic claim/evidence pairs matched
to the SciFact task structure (verdict + abstract-grounded rationale
sentences); see `authority/provenance.lock` for provenance.

## Scoring notes and paper fidelity

- Verdicts use SciFact's native vocabulary (`SUPPORT`, `CONTRADICT`,
  `NOT_ENOUGH_INFO`) in the paper-direct gold view. The shared verification
  scorer normalizes these to the FEVER-compatible supports/refutes/nei set
  via the extended `_normalize_feverous_verdict` aliases, so SciFact claims
  can be scored by the existing joint scorer without vocabulary distortion.
- Evidence atoms follow the `{doc_id}_sentence_{index}` naming convention so
  the shared FEVEROUS joint scorer treats them as sentence-level atoms.
- The shared scorer applies the FEVEROUS sentence-atom truncation (first 5
  sentence atoms). SciFact claims naturally have ≤5 evidence sentences, so
  this truncation is documented but does not change the committed slice.
- Evidence grouping: each gold rationale from the paper becomes one
  alternative evidence set. A claim can be supported by any one rationale
  group, matching the "at least one complete evidence set" rule from the
  shared scorer.
- This fixture does NOT implement SciFact's abstract-level selection F1
  directly. It reports verdict accuracy, atom-level set metrics, and the
  FEVEROUS-style joint score as a faithful proxy at the sentence level.

# FEVEROUS Grounded Benchmark Design Note

## Why FEVEROUS

FEVEROUS is the best first grounded verification benchmark for MoLabel because
it already spans the product surfaces we care about:

- claim verification,
- evidence retrieval,
- sentence and table evidence,
- and paper-faithful adjudication against gold labels.

The current MoLabel labeling engine used when this benchmark is run live is
`MiniMax 2.7 highspeed` through the Anthropic-compatible adapter path.

The official paper defines the primary score as a joint condition: the verdict
must be correct and at least one complete gold evidence set must be contained
in the predicted evidence. The shared-task paper also tracks label accuracy and
evidence precision/recall/F1 separately.

## Repo Contract

The benchmark now has a canonical authority pack plus a transitional reference
workspace.

Authority files:

- `authority/manifest.yaml`
- `authority/packaging.yaml`
- `authority/provenance.lock`
- `authority/scenario.yaml`
- `authority/paper.yaml`
- `authority/label-map.yaml`
- `authority/metrics.yaml`
- `authority/baselines.yaml`
- `authority/operator.yaml`

Reference workspace:

- `workbench.project.yaml`
- `workbench/benchmarks/...`
- `workbench/config/task-schemas/...`
- `workbench/workflows/...`

The authority pack is canonical. The existing workspace tree remains available
as a compatibility and baseline surface until the new harness lands.

The committed slice uses six public FEVEROUS dev records sampled to cover:

- entity disambiguation,
- multi-hop reasoning,
- table-plus-text verification,
- and NOT ENOUGH INFO cases.

## Paper-Direct vs MoLabel-Operated

`paper-direct` preserves the official nested evidence-set structure from FEVEROUS
and is the correct place to assess paper-faithful success.

`molabel-operated` flattens evidence into atoms, which matches the shape MoLabel
can score and manipulate more easily during workflow and operator runs.

That split matters because the benchmark is not just asking, "Did the model get
the label right?" It is asking whether the operator preserved the paper-required
evidence structure while working through MoLabel.

## Tax Definition

The benchmark expresses three signed deltas:

- `model_tax`: paper-direct model score minus MoLabel-normalized model score
- `workflow_tax`: MoLabel-normalized model score minus MoLabel workflow score
- `operator_tax`: MoLabel workflow score minus MoLabel operator score

The shared grounded benchmark model in `molabel-core` now includes a dedicated
`feverous_score` metric for the exact paper-direct success rule, while
`metrics.yaml` still keeps the MoLabel-friendly flattened evidence diagnostics
for operational scoring and tax accounting.

## Licensing

The FEVEROUS repository is Apache-2.0, and the data annotations are
redistributable under the Wikipedia-derived attribution/share-alike terms
described on the official FEVEROUS download page. The committed fixture only
includes a small curated subset, and the authority pack separates that policy
from the legacy workspace layout.

`FUNSD` remains deferred because its distribution terms are more restrictive and
need a separate legal review before bundling.

## Open Follow-Up

The next benchmark work should add:

- workflow and operator scoring on actual CLI runs,
- generated comparison reports for non-oracle model outputs,
- and a full CLI execution path that uses the exact FEVEROUS paper-direct score
  during runtime, not just in test and shared-scoring code.

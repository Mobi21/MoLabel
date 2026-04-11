# HateXplain Benchmark Operator Notes

Use this benchmark to validate explainable hate-speech labeling through the
public MoLabel interfaces.

Rules:

- operate through the public `molabel` CLI and this benchmark guidance only
- write run artifacts under `workbench/benchmarks/runs/live-operator/`
- preserve the raw text exactly as shown in the source records
- do not sanitize slurs or rewrite the content
- keep `rationale_token_mask` aligned to the token sequence length
- treat majority-vote labels as the paper-direct truth
- preserve disagreement in workflow mode instead of flattening it
- report when human labels or review decisions are intentionally wrong

Evaluation intent:

- `paper-direct` measures the label and rationale quality of the model output
- `molabel-operated` measures whether the operator used MoLabel safely and
  consistently
- `operator` mode measures command execution discipline, artifact integrity,
  and disagreement handling

# FEVEROUS Grounded Benchmark Operator Notes

Use this benchmark when validating claim verification over the public FEVEROUS
dev set slice.

Core rules:

- Operate through the public `molabel` CLI and this benchmark guidance only.
- Write run artifacts under `workbench/benchmarks/runs/live-operator/`.
- Treat `workbench/benchmarks/gold/paper-direct/` as the paper-faithful view.
- Treat `workbench/benchmarks/gold/molabel-operated/` as the MoLabel-normalized
  view used for workflow and operator scoring.
- Do not collapse `NOT ENOUGH INFO` into a guessed verdict.
- Do not invent evidence atoms that are not present in the source claim or the
  matched Wikipedia page/table.
- For a claim to count as paper-direct correct, the verdict must be correct and
  at least one complete gold evidence set must be contained in the predicted
  evidence atoms.
- For operator evaluation, preserve disagreement and review state instead of
  silently overwriting human artifacts.

What to watch for:

- multi-hop evidence chains,
- table-plus-text evidence,
- entity disambiguation traps,
- and NEI claims that look easy but should stay unsupported.

The benchmark is intentionally small, so a disciplined operator should be able
to inspect every row and explain every correction.

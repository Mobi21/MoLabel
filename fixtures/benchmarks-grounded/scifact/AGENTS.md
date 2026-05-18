# SciFact Grounded Benchmark

Use this benchmark when evaluating scientific claim verification with
sentence-level rationales on grounded SciFact data.

Rules:

- Operate through the public `molabel` CLI and this benchmark guidance only.
- Use only these benchmark inputs: `workbench/benchmarks/splits/dev.jsonl`, `workbench/config/task-schemas/scifact-grounded-v1.yaml`, and `workbench/workflows/scifact-grounded.yaml`.
- Register the proposer model as MiniMax 2.7 highspeed exactly: provider `anthropic`, provider name `MiniMax`, model identifier `MiniMax-M2.7-highspeed`, auth ref `ANTHROPIC_API_KEY`, structured output enabled.
- Write run artifacts under `workbench/benchmarks/runs/live-operator/`.
- Do not read, list, or edit authority, gold, review, or benchmark-config paths such as `authority/`, `workbench/benchmarks/gold/`, `workbench/benchmarks/human-labels/`, `workbench/benchmarks/reviews/`, `label-map.yaml`, `metrics.yaml`, `baselines.yaml`, `operator.yaml`, `paper.yaml`, or `scenario.yaml`.
- Emit verdicts only from the declared vocabulary (`supports`, `refutes`, `nei`) in the MoLabel-operated view.
- Emit `evidence_atoms` as a list of stable `{doc_id}_sentence_{index}` identifiers drawn only from the abstracts referenced by the claim. Do not invent new atoms or sentence indices.
- Keep paper-direct and MoLabel-operated scores separate.
- Preserve intentional human-review mistakes; they are part of the benchmark contract.
- Treat any larger packaging of upstream SciFact data as a licensing review item before redistribution (CC BY-NC 2.0, non-commercial).

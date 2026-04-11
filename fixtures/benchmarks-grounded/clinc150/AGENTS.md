# CLINC150 Grounded Benchmark

Use this benchmark when evaluating intent classification with out-of-scope detection on grounded CLINC/OOS data.

Rules:

- Operate through the public `molabel` CLI and this benchmark guidance only.
- Use only these benchmark inputs: `workbench/benchmarks/splits/test.jsonl`, `workbench/config/task-schemas/clinc150-grounded-v1.yaml`, and `workbench/workflows/clinc150-grounded.yaml`.
- Register the proposer model as MiniMax 2.7 exactly: provider `anthropic`, provider name `MiniMax`, model identifier `minimax-2.7`, auth ref `ANTHROPIC_API_KEY`, structured output enabled.
- Write run artifacts under `workbench/benchmarks/runs/live-operator/`.
- Do not read, list, or edit authority, gold, review, or benchmark-config paths such as `authority/`, `workbench/benchmarks/gold/`, `workbench/benchmarks/human-labels/`, `workbench/benchmarks/reviews/`, `label-map.yaml`, `metrics.yaml`, `baselines.yaml`, `operator.yaml`, `paper.yaml`, or `scenario.yaml`.
- Do not edit the benchmark split file unless you are regenerating the fixture from the upstream dataset.
- Keep paper-direct and MoLabel-operated scores separate.
- Preserve intentional human-review mistakes; they are part of the benchmark contract.
- Treat any larger packaging of upstream CLINC/OOS data as a licensing review item before redistribution.

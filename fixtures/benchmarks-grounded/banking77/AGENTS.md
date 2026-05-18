# BANKING77 Grounded Benchmark

Use this benchmark when evaluating fine-grained banking intent classification on grounded BANKING77 data.

Rules:

- Operate through the public `molabel` CLI and this benchmark guidance only.
- Use only these benchmark inputs: `workbench/benchmarks/splits/test.jsonl`, `workbench/config/task-schemas/banking77-grounded-v1.yaml`, and `workbench/workflows/banking77-grounded.yaml`.
- Register the proposer model as MiniMax 2.7 highspeed exactly: provider `anthropic`, provider name `MiniMax`, model identifier `MiniMax-M2.7-highspeed`, auth ref `ANTHROPIC_API_KEY`, structured output enabled.
- Write run artifacts under `workbench/benchmarks/runs/live-operator/`.
- Do not read, list, or edit authority, gold, review, or benchmark-config paths such as `authority/`, `workbench/benchmarks/gold/`, `workbench/benchmarks/human-labels/`, `workbench/benchmarks/reviews/`, `label-map.yaml`, `metrics.yaml`, `baselines.yaml`, `operator.yaml`, `paper.yaml`, or `scenario.yaml`.
- Do not edit the benchmark split file unless you are regenerating the fixture from the upstream dataset.
- Keep paper-direct and MoLabel-operated scores separate.
- Preserve intentional human-review mistakes; they are part of the benchmark contract.
- Only predict labels drawn from the declared BANKING77 label set. Do not invent new intents or use an invalid label as an implicit abstention.
- Treat any larger packaging of upstream BANKING77 data as a licensing review item before redistribution.

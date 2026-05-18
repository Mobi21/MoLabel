# Evidence Inference 2.0 Grounded Benchmark

Rules:

- Operate through the public molabel CLI and this benchmark guidance only.
- Use only the benchmark inputs under workbench/benchmarks/splits/dev.jsonl, workbench/config/task-schemas/evidence-inference-grounded-v1.yaml, and workbench/workflows/evidence-inference-grounded.yaml.
- Register the proposer model as MiniMax 2.7 highspeed exactly via the Anthropic-compatible adapter path.
- Write run artifacts under workbench/benchmarks/runs/live-operator/.
- Do not read, list, or edit authority, gold, review, or benchmark-config paths such as authority/, workbench/benchmarks/gold/, workbench/benchmarks/human-labels/, workbench/benchmarks/reviews/, label-map.yaml, metrics.yaml, baselines.yaml, operator.yaml, paper.yaml, or scenario.yaml.
- Emit decision only from increase, decrease, or no_difference.
- Emit grouped evidence atoms using stable article sentence ids drawn only from the supplied slice.
- Do not flatten alternative evidence groups into a single unordered set.

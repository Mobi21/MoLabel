# HotpotQA Grounded Benchmark

Rules:

- Operate through the public molabel CLI and this benchmark guidance only.
- Use only the benchmark inputs under workbench/benchmarks/splits/dev.jsonl, workbench/config/task-schemas/hotpotqa-grounded-v1.yaml, and workbench/workflows/hotpotqa-grounded.yaml.
- Register the proposer model as MiniMax 2.7 highspeed exactly via the Anthropic-compatible adapter path.
- Write run artifacts under workbench/benchmarks/runs/live-operator/.
- Do not read, list, or edit authority, gold, review, or benchmark-config paths such as authority/, workbench/benchmarks/gold/, workbench/benchmarks/human-labels/, workbench/benchmarks/reviews/, label-map.yaml, metrics.yaml, baselines.yaml, operator.yaml, paper.yaml, or scenario.yaml.
- Answer with concise text and include all required supporting facts; partial support is scored separately from the answer itself.
- Do not substitute free-form rationale text for supporting fact references.

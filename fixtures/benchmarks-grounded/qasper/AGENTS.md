# QASPER Grounded Benchmark

Rules:

- Operate through the public molabel CLI and this benchmark guidance only.
- Use only the benchmark inputs under workbench/benchmarks/splits/dev.jsonl, workbench/config/task-schemas/qasper-grounded-v1.yaml, and workbench/workflows/qasper-grounded.yaml.
- Register the proposer model as MiniMax 2.7 exactly via the Anthropic-compatible adapter path.
- Write run artifacts under workbench/benchmarks/runs/live-operator/.
- Do not read, list, or edit authority, gold, review, or benchmark-config paths such as authority/, workbench/benchmarks/gold/, workbench/benchmarks/human-labels/, workbench/benchmarks/reviews/, label-map.yaml, metrics.yaml, baselines.yaml, operator.yaml, paper.yaml, or scenario.yaml.
- Use unanswerable true only when the paper slice truly lacks the required answer evidence.
- Keep answer text, evidence references, and null handling distinct in reports and artifacts.

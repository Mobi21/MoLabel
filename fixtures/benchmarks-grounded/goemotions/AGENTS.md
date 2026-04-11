# GoEmotions Grounded Benchmark

Use this benchmark when evaluating multi-label emotion classification on grounded GoEmotions data.

Rules:

- Operate through the public `molabel` CLI and this benchmark guidance only.
- Use only these benchmark inputs: `workbench/benchmarks/splits/test.jsonl`, `workbench/config/task-schemas/goemotions-grounded-v1.yaml`, and `workbench/workflows/goemotions-grounded.yaml`.
- Register the proposer model as MiniMax 2.7 exactly: provider `anthropic`, provider name `MiniMax`, model identifier `minimax-2.7`, auth ref `ANTHROPIC_API_KEY`, structured output enabled.
- Write run artifacts under `workbench/benchmarks/runs/live-operator/`.
- Do not read, list, or edit authority, gold, review, or benchmark-config paths such as `authority/`, `workbench/benchmarks/gold/`, `workbench/benchmarks/human-labels/`, `workbench/benchmarks/reviews/`, `label-map.yaml`, `metrics.yaml`, `baselines.yaml`, `operator.yaml`, `paper.yaml`, or `scenario.yaml`.
- Emit `emotion_labels` as a set of unique labels drawn only from the declared GoEmotions vocabulary. Do not repeat labels in the set.
- Empty prediction sets are valid only for records where no listed emotion applies; do not use an empty set as a proxy for "I could not parse this utterance".
- Keep paper-direct and MoLabel-operated scores separate.
- Preserve intentional human-review mistakes; they are part of the benchmark contract.
- Preserve annotator disagreement where the slice carries it; do not flatten borderline cases into a single comfortable label.

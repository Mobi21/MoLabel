# MoLabel CLI Skill Notes

- MoLabel is agent-first and CLI-primary.
- Agents should operate through `molabel` and the installed MoLabel skill only.
- Assume raw backend APIs are unavailable and out of contract for operator work.
- Every command prints one JSON document and exits 0 or 1. On exit 1, read `error.code` from the error envelope described in the CLI README.
- Use `molabel manifest --json` before assuming command behavior.
- Use `molabel workspace detect` before mutating local canonical artifacts.
- Treat the GUI as the inspection and manual-review layer, not the primary automation surface.
- The primary command families are `session`, `dataset`, `task-schema`, `prompt`, `workflow`, `queue`, `review`, `adjudication`, `agent-run`, `quality`, `export`, `release`, and `artifact`.
- Benchmark operators must create or confirm a reviewer session before claiming review work.
- A grounded benchmark run is not complete until the review queue is empty and the required run artifacts are written.

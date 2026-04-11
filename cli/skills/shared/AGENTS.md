# MoLabel CLI Skill Notes

- MoLabel is agent-first and CLI-primary.
- Agents should operate through `molabel` and the installed MoLabel skill only.
- Assume raw backend APIs are unavailable and out of contract for operator work.
- Prefer `--json` for machine use and NDJSON-style streams for long-running operations.
- Use `molabel manifest --json` before assuming command behavior.
- Use `molabel workspace detect` before mutating local canonical artifacts.
- Treat the GUI as the inspection and manual-review layer, not the primary automation surface.
- The primary command families are `session`, `dataset`, `task-schema`, `prompt`, `workflow`, `queue`, `review`, `adjudication`, `agent-run`, `quality`, `export`, `release`, and `artifact`.

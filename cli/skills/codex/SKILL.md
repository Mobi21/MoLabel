---
name: "molabel-cli"
description: "Use when Codex should operate a MoLabel workspace through the public molabel CLI and installed MoLabel skill only."
---

# MoLabel Codex Skill

Use this skill when Codex is operating a MoLabel workspace through the public CLI.

## Operating Rules

1. Treat `molabel` as the primary public interface.
2. Assume raw backend APIs are unavailable for operator work.
3. Do not use `curl`, handwritten HTTP requests, or direct SDK calls as substitutes for `molabel`.
4. Detect the workspace before mutating anything.
5. Inspect the command manifest before assuming a command shape.
6. Prefer machine-readable output over prose or terminal scraping.
7. Read canonical artifacts before attempting to change them.
8. Use safe write flows with explicit expected hashes whenever possible.

## Recommended Workflow

1. Run `molabel workspace detect`.
2. Run `molabel doctor --json`.
3. Run `molabel manifest --json`.
4. Use `molabel session ...` to confirm or switch reviewer identity.
5. Use `molabel dataset ...`, `molabel task-schema ...`, and `molabel prompt ...` to prepare the project.
6. Use `molabel workflow ...` and `molabel agent-run ...` to execute agent work.
7. Use `molabel queue ...`, `molabel review ...`, and `molabel adjudication ...` for human-in-review and disagreement handling.
8. Use `molabel quality ...`, `molabel export ...`, and `molabel release ...` to finish the governed delivery flow.
9. Use `molabel artifact ...` only when working with canonical files directly.

## Review And Benchmark Work

When operating benchmark or evaluation workspaces:

- compare outputs against gold labels where available,
- inspect disagreement rather than flattening it,
- pay special attention to intentionally bad human labels or reviews,
- stay on the CLI-and-skill surface even if you suspect a backend shortcut exists,
- and summarize whether the agent, the human, or both appear wrong.

## Notes

- The CLI is local-first and file-aware.
- Benchmark operators should treat backend URLs and API routes as hidden implementation details.
- Stable JSON output is the default operating mode for Codex.
- The expected steady state is CLI-and-skill-only operation, not ad hoc `curl` or direct HTTP calls.

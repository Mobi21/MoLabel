# MoLabel CLI

Use this skill when operating MoLabel from Claude Code.

## Workflow

1. Run `molabel workspace detect`.
2. Run `molabel status --json` to see backend and workspace state.
3. Run `molabel workflow templates --json` before creating new flows.
4. Prefer `--json` output and explicit paths.

## Notes

- The CLI preserves MoLabel's local-first file ownership rules.
- Use `molabel skill install` to sync this skill bundle into the agent environment.

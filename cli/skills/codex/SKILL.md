# MoLabel CLI

Use this skill when operating MoLabel from Codex or another terminal agent.

## Workflow

1. Run `molabel workspace detect` to establish the workspace root.
2. Use `molabel doctor --json` for a quick environment check.
3. Use `molabel manifest --json` to inspect the supported command contract.
4. Prefer `--json` and `--expected-hash` for all mutating commands.

## Notes

- The CLI is local-first and file-aware.
- The CLI can talk to the MoLabel backend when `--base-url` or `MOLABEL_BASE_URL` is set.
- The command surface is designed for agents, so stable JSON output is the default.

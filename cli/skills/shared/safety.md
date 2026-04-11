# Safety

- Never overwrite human-authored files without an explicit selector and `--expected-hash`.
- Prefer JSON output in agent workflows.
- Use the workspace root discovered from the current directory unless a path is supplied.
- Stay inside the public CLI and installed skill surface for normal operations.
- Treat raw backend HTTP as a maintainer-only debugging tool, not an operator surface.
- Inspect canonical artifacts before mutating them.
- Use workflow commands and backend state transitions instead of ad hoc file edits where possible.
- Preserve evidence of disagreement when humans and agents conflict; do not silently flatten review history.

# MoLabel CLI Implementation Plan

> For agentic workers: use subagents with disjoint write scopes. Keep existing `/api/v1/*` behavior unchanged. Any backend additions for the CLI must live under `/api/v1/cli/*`.

**Goal:** Ship a long-term, npm-distributed MoLabel CLI and bundled skill package that agents can install and use from a terminal with strong local-first workspace support.

**North Star:** `npx @molabel/cli` should be enough for an agent to detect a workspace, bootstrap or connect to the backend, inspect state, operate canonical artifacts safely, run workflows, and sync the packaged skill instructions.

## Scope

### CLI package

- Create a standalone `cli/` npm package with Node-targeted TypeScript.
- Add a `molabel` executable with machine-readable JSON output by default.
- Implement path-first workspace discovery from the current directory.
- Implement persisted CLI config and cookie-backed session handling.
- Implement a bundled command manifest and bundled Codex/Claude skill content.

### Additive backend API

- Add a new FastAPI router at `/api/v1/cli`.
- Do not change or rename any existing routes.
- Add only the backend affordances the CLI needs and the current API does not expose well:
  - workspace path detection and bootstrap metadata,
  - aggregate status for agents,
  - selector resolution,
  - canonical artifact read/diff/write with revision checks,
  - built-in workflow template discovery,
  - snapshot restore.

### Validation

- Add Python integration tests for the new CLI router.
- Add Vitest coverage for CLI config, workspace discovery, and command execution paths.
- Verify `uv run pytest` for the new integration slice and `npm test` plus `npm run build` in `cli/`.

## Implementation Slices

### Slice 1: Backend CLI Router

**Ownership:** `packages/molabel-app/src/molabel/app/api/v1/cli.py`, `packages/molabel-app/src/molabel/app/api/v1/__init__.py`, `tests/integration/test_api_cli.py`

Deliver:

- `GET /api/v1/cli/status`
- `POST /api/v1/cli/workspaces/detect`
- `POST /api/v1/cli/selectors/resolve`
- `GET /api/v1/cli/workflow-templates`
- `GET /api/v1/cli/workflow-templates/{template_id}`
- `POST /api/v1/cli/artifacts/read`
- `POST /api/v1/cli/artifacts/diff`
- `POST /api/v1/cli/artifacts/write`
- `POST /api/v1/cli/snapshots/restore`

Rules:

- Prefer existing core utilities where available.
- Keep file writes guarded by path validation and expected-hash conflict checks.
- Return structured JSON models, not ad hoc dicts.

### Slice 2: CLI Runtime and Commands

**Ownership:** everything under `cli/`

Deliver:

- package scaffold: `package.json`, `tsconfig.json`, `eslint.config.js`, `.prettierrc`, `vitest.config.ts`
- executable entrypoint: `src/bin/molabel.ts`
- runtime pieces:
  - config loading,
  - workspace context detection,
  - HTTP client and cookie jar,
  - JSON/table/raw rendering,
  - local artifact input handling
- command groups:
  - `doctor`
  - `status`
  - `manifest`
  - `session whoami`
  - `workspace detect`
  - `workspace bootstrap`
  - `workflow list`
  - `workflow run`
  - `workflow templates`
  - `artifact read`
  - `artifact diff`
  - `artifact write`
  - `skill install`

Rules:

- Default to JSON output for agent use.
- Keep options stable and explicit.
- Support `--base-url`, `--workspace`, `--json`, `--raw`, `--file`, and stdin where relevant.

### Slice 3: Skill Bundle and Manifest

**Ownership:** `cli/skills/*`, `cli/src/manifest/*`

Deliver:

- bundled Codex skill
- bundled Claude Code skill
- shared operating guidance and safety notes
- machine-readable command manifest exposed by `molabel manifest --json`

## Execution Order

1. Land the backend router and tests.
2. Land the CLI package scaffold and core runtime.
3. Wire command groups to existing `/api/v1/*` routes plus new `/api/v1/cli/*` routes.
4. Add bundled skill install flow and manifest output.
5. Run backend and CLI tests and fix integration issues.

## Acceptance Criteria

- `cli/` builds cleanly with `npm run build`.
- `molabel manifest --json` prints the installed command contract.
- `molabel workspace detect` works from a path containing `workbench.project.yaml`.
- `molabel workflow templates --json` returns built-in template metadata.
- `molabel artifact read|diff|write` can safely operate canonical files with conflict detection.
- `uv run pytest tests/integration/test_api_cli.py` passes.
- Existing `/api/v1/*` routes continue to exist unchanged.

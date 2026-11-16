# AGENTS.md

Project-level guidance for AI agents working in this repository.

## Project Overview

MoLabel is a local-first, agent-first, CLI-primary data operations workbench. The canonical product specification lives in `docs/prd/agentic-data-operations-workbench-prd.md`.
The intended operating model is:

- external agents use the public `molabel` CLI as the primary interface,
- the backend API stays behind that CLI for normal project work,
- the GUI is the manual control room, inspection surface, and review interface.

## Repository Layout

This is a uv workspace monorepo with three Python packages, a TypeScript CLI, and a React frontend:

| Path | Namespace | Purpose |
|---|---|---|
| `packages/molabel-core/` | `molabel.core` | Core library: SQLModel tables and Alembic migrations, workflow engine, plugin protocols and discovery, provider adapters, review, quality, export, release |
| `packages/molabel-app/` | `molabel.app` | FastAPI backend: REST API under `/api/v1`, including the CLI routes under `/api/v1/cli`, and the `molabel-dev` launcher |
| `packages/molabel-plugins/` | `molabel.plugins` | Built-in data loaders and exporters, registered through the `molabel.plugins` entry-point group |
| `cli/` | `@molabel/cli` | The `molabel` CLI, its command manifest (`cli/manifest/`), and the bundled agent skills (`cli/skills/`) |
| `frontend/` | N/A | Work-in-progress React control-room UI. Its pages render mock data from `src/mocks/data.ts` and call no API yet |
| `tests/` | N/A | pytest suites: `unit/`, `integration/`, `e2e/` |
| `fixtures/` | N/A | Sample workspaces and grounded benchmark fixtures |

## The Agent Interface Is The CLI

- Agents operate MoLabel through `molabel`, not through raw HTTP calls to the backend.
- Every command prints exactly one JSON document to stdout and exits 0 or 1. On exit 1, branch on `error.code`. `cli/README.md` defines the contract and `cli/tests/json-contract.test.ts` enforces it.
- `molabel manifest --json` lists the commands. `molabel doctor` checks environment health and `molabel status` shows workspace and backend status.
- `molabel skill install --flavor codex` or `--flavor claude-code` installs the bundled skills from `cli/skills/`.
- The CLI reaches the backend through its own HTTP client in `cli/src/client/`, configured by `MOLABEL_BASE_URL` or `--base-url`.
- A backend capability that agents need gets a CLI command.

## State Boundary

- **Config is files.** Task schemas, prompts, and workflows are YAML files in the workspace folder, listed in `workbench.project.yaml`. Their database rows index the files, and the file wins when the two disagree. Creating or updating config through the API writes the file, the manifest, and the row as one unit.
- **Gold sets are files.** Released gold sets will be files too (planned, P8). Raw input data, exports, benchmark authority material, and release outputs are already files in the workspace tree.
- **Review state is SQLite.** Dataset records, queues, review events and drafts, agent runs, claims, sessions, and audit events live only in SQLite. For the review in progress, SQLite is the canonical record.
- **The server database lives in the per-user data directory**, never in the workspace or in the folder the server was launched from: `$XDG_DATA_HOME/molabel` or `~/.local/share/molabel` on Linux, `~/Library/Application Support/MoLabel` on macOS, `%LOCALAPPDATA%\MoLabel` on Windows. `MOLABEL_DATA_DIR` moves it and `MOLABEL_DB_URL` overrides the database.
- Never silently overwrite human-authored files.

`docs/guides/how-molabel-works-today.md` section 4 has the details.

## Module Boundary Rules

These boundaries are load-bearing. Do not violate them.

- `molabel-core` must NEVER import from `molabel-app` or `molabel-plugins`
- `molabel-app` depends on `molabel-core` only
- `molabel-plugins` depends on `molabel-core` only
- Cross-package imports must go through public APIs, not internal modules
- `cli/` and `frontend/` communicate with `molabel-app` ONLY via the REST API (no direct Python imports)
- API contracts are defined by FastAPI endpoints with Pydantic models
- Plugin custom UI components (React) must be self-contained and only use the documented plugin SDK props

## Namespace Package Convention

The `molabel` namespace is shared across `molabel-core`, `molabel-app`, and `molabel-plugins` using Python implicit namespace packages. There must be NO `__init__.py` at the `src/molabel/` level in any of these packages.

## Tech Stack

Backend:

- Python 3.12+
- FastAPI, Starlette, and Uvicorn
- Pydantic v2 (validation and serialization)
- SQLModel on SQLite, with Alembic migrations
- PyYAML (workspace files), httpx (provider adapters)
- uv, pytest, ruff

CLI:

- TypeScript (strict) on Node 20.18+
- commander, yaml
- vitest, eslint (`strict-type-checked`), prettier

Frontend:

- React 19 + TypeScript (strict), Vite, Tailwind CSS
- shadcn/ui-style components on Radix primitives
- React Router, TanStack Query (client set up, no queries yet), Zustand (UI state), React Flow (workflow page)
- vitest, eslint (`strict-type-checked`), prettier
- `npm run generate:api` runs `@hey-api/openapi-ts` against a running backend and writes the client to `src/api/generated/`. No generated client is committed yet.

## Conventions

- Use `ruff` for formatting and linting before committing
- Use `prettier` for TypeScript/React formatting
- Use `eslint` with strict TypeScript config
- Frontend components follow shadcn/ui patterns
- Write Python tests in `tests/`, CLI tests in `cli/tests/`, and frontend tests next to the component
- Use type hints on all public function signatures
- Prefer Pydantic models for data contracts
- API endpoints return Pydantic models (enables OpenAPI codegen)
- Use explicit imports (no wildcard imports)
- Keep plugin interfaces as Python protocols or abstract base classes
- Task schemas, prompts, and workflows are YAML files (file-backed, version-controllable)
- Prompts live under `workbench/prompts/`, and each update adds a version

## Testing

```bash
uv run pytest tests/             # all Python tests
uv run pytest tests/unit/        # unit tests only
uv run pytest tests/integration/ # integration tests
uv run pytest tests/e2e/         # end-to-end tests (in-process API, recorded LLM cassettes)
cd cli && npx vitest run         # CLI tests
cd frontend && npm run test      # frontend tests
```

Fixture workspaces in `fixtures/` provide sample project data for tests.

## What Not To Do

- Do not create `__init__.py` at the `src/molabel/` level in core, app, or plugins packages
- Do not store secrets or API keys in project files (use environment variable references)
- Do not bypass the plugin interface to add task-specific behavior to the core
- Do not use wildcard imports
- Do not import Python modules from the frontend or the CLI (use the REST API only)
- Do not add heavyweight frontend state management beyond Zustand
- Do not use WebSocket. A feature that needs server push uses SSE.
- Do not store task schemas, prompts, or workflows only in the database (they must be YAML files)
- Do not hand-write frontend API calls; use the client that `npm run generate:api` produces

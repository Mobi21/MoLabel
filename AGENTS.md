# AGENTS.md

Project-level guidance for AI agents working in this repository.

## Project Overview

MoLabel is a local-first, GUI-first, modular data operations workbench. The canonical product specification lives in `docs/prd/agentic-data-operations-workbench-prd.md`.

## Repository Layout

This is a uv workspace monorepo with four Python packages, a React frontend, and a Tauri desktop shell:

| Package | Path | Namespace | Purpose |
|---|---|---|---|
| molabel-core | `packages/molabel-core/` | `molabel.core`, `molabel.storage`, etc. | Core library: data model, workflow engine, plugin system, provider adapters |
| molabel-app | `packages/molabel-app/` | `molabel.app` | FastAPI web application: REST API, backend logic |
| molabel-plugins | `packages/molabel-plugins/` | `molabel.plugins` | Built-in task type plugins (text labeling, chat review, etc.) |
| molabel-depolarize | `packages/molabel-depolarize/` | `molabel_depolarize` | DePolarize reference implementation (separate namespace) |
| frontend | `frontend/` | N/A (standalone) | React frontend: workflow builder, data explorer, review UI, all screens |
| tauri-shell | `src-tauri/` | N/A (Rust) | Tauri desktop app shell: window management, sidecar, system tray |

## Module Boundary Rules

These boundaries are load-bearing. Do not violate them.

- `molabel-core` must NEVER import from `molabel-app`, `molabel-plugins`, or `molabel-depolarize`
- `molabel-app` depends on `molabel-core` only
- `molabel-plugins` depends on `molabel-core` only
- `molabel-depolarize` depends on `molabel-core` and `molabel-plugins`
- Cross-package imports must go through public APIs, not internal modules
- `frontend/` communicates with `molabel-app` ONLY via the REST API (no direct Python imports)
- `src-tauri/` manages the Python sidecar process and webview, does not contain business logic
- API contracts are defined by FastAPI endpoints with Pydantic models; the TypeScript client is auto-generated from the OpenAPI spec
- Plugin custom UI components (React) must be self-contained and only use the documented plugin SDK props

## Namespace Package Convention

The `molabel` namespace is shared across `molabel-core`, `molabel-app`, and `molabel-plugins` using Python implicit namespace packages. There must be NO `__init__.py` at the `src/molabel/` level in any of these packages.

`molabel-depolarize` uses a separate `molabel_depolarize` namespace and does have its own `__init__.py`.

## Tech Stack

- Python 3.12+
- FastAPI (backend API)
- React 19 + TypeScript (frontend)
- Tauri v2 (desktop app shell)
- React Flow (workflow builder)
- shadcn/ui + Tailwind CSS (UI components)
- TanStack Table (data explorer)
- TanStack Query (API client)
- Zustand (state management)
- Vite (frontend build)
- SQLite in WAL mode (operational database)
- DuckDB + Polars (analytics and large-file scans)
- Pydantic (validation and serialization)
- SQLModel (ORM)
- uv (Python package management)
- npm (frontend package management)
- pytest (Python testing)
- vitest (frontend testing)
- Playwright (E2E testing)
- ruff (Python linting and formatting)
- prettier + eslint (TypeScript linting and formatting)

## Conventions

- Use `ruff` for formatting and linting before committing
- Use `prettier` for TypeScript/React formatting
- Use `eslint` with strict TypeScript config
- Frontend components follow shadcn/ui patterns
- Write tests for new functionality in `tests/`
- Use type hints on all public function signatures
- Prefer Pydantic models for data contracts
- API endpoints return Pydantic models (enables OpenAPI codegen)
- Use explicit imports (no wildcard imports)
- Keep plugin interfaces as Python protocols or abstract base classes
- Real-time updates use SSE (Server-Sent Events), not WebSocket
- Workflow definitions are YAML files (file-backed, version-controllable)
- Agent prompts are YAML files under `workbench/prompts/` with auto-versioning

## File Ownership

- Canonical project data lives on disk (see PRD section 13)
- SQLite stores operational state, not canonical truth
- Machine-generated outputs go to stable paths under `workbench/` namespaces
- Never silently overwrite human-authored files

## Testing

```bash
uv run pytest                    # all Python tests
uv run pytest tests/unit/        # unit tests only
uv run pytest tests/integration/ # integration tests
cd frontend && npm run test      # frontend tests
npx playwright test              # E2E tests
```

Fixture workspaces in `fixtures/` provide sample project data for tests.

## What Not To Do

- Do not add DePolarize-specific logic to `molabel-core` or `molabel-app`
- Do not create `__init__.py` at the `src/molabel/` level in core, app, or plugins packages
- Do not store secrets or API keys in project files (use environment variable references)
- Do not bypass the plugin interface to add task-specific behavior to the core
- Do not use wildcard imports
- Do not import Python modules from the frontend (use REST API only)
- Do not add heavyweight frontend state management beyond Zustand
- Do not use WebSocket (use SSE for real-time updates)
- Do not store workflow definitions only in the database (they must be YAML files)
- Do not bypass the OpenAPI codegen pipeline for API calls

# CLAUDE.md

Instructions for Claude Code when working in this repository.

## Bootstrap

```bash
# Backend
uv sync                    # install all Python workspace packages
uv run pytest              # run Python tests
uv run ruff check .        # lint Python
uv run ruff format .       # format Python

# Frontend
cd frontend && npm install  # install frontend deps
npm run dev                # start frontend dev server
npm run test               # run frontend tests
npm run build              # production build

# Desktop App
cargo tauri dev            # run Tauri desktop app in dev mode
cargo tauri build          # build distributable desktop app

# Full Stack Dev
uv run molabel-dev         # starts FastAPI + frontend dev server together
```

## Package Structure

This is a uv workspace monorepo. Python packages live under `packages/`, with a React frontend and Tauri desktop shell alongside.

- `packages/molabel-core/` — core library (Python)
- `packages/molabel-app/` — FastAPI backend (Python)
- `packages/molabel-plugins/` — built-in plugins (Python)
- `packages/molabel-depolarize/` — DePolarize reference app (Python)
- `frontend/` — React frontend (TypeScript)
- `src-tauri/` — Tauri desktop shell (Rust)

## Key References

- PRD (source of truth): `docs/prd/agentic-data-operations-workbench-prd.md`
- UX/AI strategy: `docs/prd/ux-and-ai-strategy.md`
- Architecture decisions: `docs/architecture/ADR-*.md`

## Rules

- Respect module boundaries in AGENTS.md
- No `__init__.py` at `src/molabel/` level (namespace packages)
- Use ruff for Python formatting
- Use prettier for TypeScript/React formatting
- Use pytest for Python tests
- Use vitest for frontend tests
- Use Playwright for E2E tests
- Python 3.12+ only
- React 19 + TypeScript strict mode
- All REST API endpoints must have Pydantic response models (for OpenAPI codegen)
- Frontend components use shadcn/ui conventions
- State management via Zustand stores
- API calls via TanStack Query + generated OpenAPI client

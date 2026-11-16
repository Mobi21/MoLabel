# CLAUDE.md

Instructions for Claude Code when working in this repository.

## Bootstrap

```bash
# Backend
uv sync                    # install all Python workspace packages
uv run pytest tests/       # run Python tests
uv run ruff check .        # lint Python
uv run ruff format .       # format Python

# CLI
cd cli && npm ci           # install CLI deps
npm run build              # compile to dist/; the bin is dist/bin/molabel.js
npx vitest run             # run CLI tests
npm run lint               # eslint
npx prettier --check .     # formatting

# Frontend
cd frontend && npm ci      # install frontend deps
npm run dev                # start frontend dev server
npm run test               # run frontend tests
npm run build              # type-check and production build
npm run test:e2e           # Playwright review loop on the real backend (build cli/ first)
npm run generate:api       # regenerate the API client from the backend on :8000, or MOLABEL_OPENAPI_INPUT

# Full Stack Dev
uv run molabel-dev         # starts FastAPI on :8000 and Vite on :5173 together
```

## Package Structure

This is a uv workspace monorepo. Python packages live under `packages/`, with the CLI and the review GUI alongside.

- `packages/molabel-core/` — core library (Python)
- `packages/molabel-app/` — FastAPI backend (Python)
- `packages/molabel-plugins/` — built-in loaders and exporters (Python)
- `cli/` — the agent-first `molabel` CLI and its bundled skills (TypeScript)
- `frontend/` — the keyboard-first review GUI on the REST API (TypeScript)

## Key References

- PRD (source of truth): `docs/prd/agentic-data-operations-workbench-prd.md`
- How the system works today, including the state boundary: `docs/guides/how-molabel-works-today.md`
- CLI output contract: `cli/README.md`
- UX/AI strategy: `docs/prd/ux-and-ai-strategy.md`
- Architecture decisions: `docs/architecture/ADR-*.md`

## Rules

- Respect the module boundaries and the state boundary in AGENTS.md
- No `__init__.py` at `src/molabel/` level (namespace packages)
- Use ruff for Python formatting
- Use prettier for TypeScript/React formatting
- Use pytest for Python tests, including the end-to-end suites in `tests/e2e/`
- Use vitest for CLI and frontend tests
- Python 3.12+ only
- React 19 + TypeScript strict mode
- All REST API endpoints must have Pydantic response models (for OpenAPI codegen)
- Frontend components use shadcn/ui conventions
- Frontend server state uses TanStack Query over the generated client; screen state stays in components and the URL
- Do not hand-write API calls or edit `frontend/src/api/generated/`; change the backend and run `npm run generate:api`
- No mock data in shipped frontend code; fixtures belong in tests

# molabel-app — Agent Guidance

## Responsibility

FastAPI backend API for MoLabel. Owns REST endpoints under `/api/v1/`, Pydantic
response models, middleware, and server lifecycle. The `molabel` CLI is its
main client. The CLI-oriented routes live under `/api/v1/cli/`.

See ADR-001 for the decision to adopt React over the original
HTMX/Jinja2 approach.

## Stack

- FastAPI for HTTP routing and OpenAPI schema generation
- Pydantic v2 for request/response models
- Uvicorn as the ASGI server

## Structure

Code lives under `src/molabel/app/`:

- `api/v1/` — versioned API route modules
- `schemas.py` — shared Pydantic response/query models
- `main.py` — application factory and middleware setup
- `dev.py` — `molabel-dev`, which starts the API and the Vite dev server
- `middleware/`, `services/` — session handling and review claims
- `tasks/` — background claim expiry
- `server_state.py` — the per-user server data directory, its database, and the app secret
- `workspace_paths.py` — confines request paths to registered workspace roots
- `workspace_config.py` — writes config files, the manifest, and their rows as one unit

## Rules

- Depends on molabel-core only (never on molabel-plugins directly)
- Plugins are discovered through the core plugin interface
- All REST endpoints must have Pydantic response models (for OpenAPI codegen)
- No templates or static file serving — the React frontend is served separately
- All critical workflows must be operable via the API (PRD section 16.1)

# molabel-app — Agent Guidance

## Responsibility

FastAPI backend API for MoLabel. Owns REST endpoints under `/api/v1/`, Pydantic
response models, middleware, and server lifecycle. The frontend is a separate
React application that consumes this API via OpenAPI-generated clients.

See ADR-001 for the decision to adopt React + Tauri over the original
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
- `dev.py` — development server entry point

## Rules

- Depends on molabel-core only (never on molabel-plugins or molabel-depolarize directly)
- Plugin-contributed API surfaces are loaded through the core plugin interface
- All REST endpoints must have Pydantic response models (for OpenAPI codegen)
- No templates or static file serving — the React frontend is served separately
- All critical workflows must be operable via the API (PRD section 16.1)

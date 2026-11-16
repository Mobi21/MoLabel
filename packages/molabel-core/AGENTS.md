# molabel-core — Agent Guidance

## Responsibility

Core library for MoLabel. Owns the data model, workflow engine, plugin system, provider adapters, and all domain logic that is not GUI-specific.

## Modules

Code lives under `src/molabel/core/`:

- `models/` — SQLModel tables
- `migrations/`, `migration_runner.py` — Alembic migrations and the startup upgrade
- `database.py` — engine and session helpers
- `manifest.py` — reads and writes `workbench.project.yaml`
- `data/` — workspace bootstrap, artifact indexing, dataset operations, pre-label import, snapshots, label mappings
- `workflow/` — workflow parser, engine, lifecycle, step types, bundled templates
- `agents/` — agent run orchestration, output validation, confidence, comparison, feedback loop
- `providers/` — model provider adapters (Anthropic, OpenAI, OpenRouter, Ollama, custom), detection, cost tracking
- `prompts/` — prompt manager
- `review/` — calibration, overlap, queue ordering
- `adjudication/` — disagreement resolution
- `quality/` — agreement, drift, readiness, grounded benchmark scoring
- `export/` — export building and atomic file writes
- `release/` — release manager and frozen views
- `plugins/` — plugin protocols, entry-point discovery, registry
- `services/` — model and runtime profile services
- `types.py` — shared enums and types

## Rules

- This package must NEVER import from molabel-app or molabel-plugins
- All plugin interfaces must be defined here as protocols or abstract base classes
- Use Pydantic for all data contracts
- Review events must be append-only (PRD section 19.1)
- Canonical file I/O must use atomic writes (PRD section 14)

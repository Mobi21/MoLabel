# molabel-core — Agent Guidance

## Responsibility

Core library for MoLabel. Owns the data model, workflow engine, plugin system, provider adapters, and all domain logic that is not GUI-specific.

## Planned Modules

These modules will be created under `src/molabel/` as development progresses (see PRD section 18.3):

- `core` — app settings, workspace lifecycle, audit logging, service wiring
- `storage` — SQLite models, canonical file I/O, migrations, transactions
- `indexing` — file scanning, metadata extraction, record projection, drift detection
- `tasks` — queue creation, task configuration, assignment rules
- `workflow` — stage model, completion criteria, blockers, next-action computation
- `providers` — model provider adapters, runtime profiles, routing rules
- `agents` — agent adapter interface, run orchestration, output normalization
- `monitoring` — live run status, event timelines, log aggregation
- `assistant` — supportive AI summaries, explanations, recommendations
- `review` — review state machine, blind review, overlap, adjudication inputs
- `quality` — agreement metrics, delta analysis, readiness summaries
- `curation` — filtering, mining, clustering, derived subsets
- `exports` — labeled dataset packaging, export formats, release bundles
- `validation` — plugin-defined checks, release gates, report generation
- `plugins` — plugin loading, metadata, lifecycle management

## Rules

- This package must NEVER import from molabel-app, molabel-plugins, or molabel-depolarize
- All plugin interfaces must be defined here as protocols or abstract base classes
- Use Pydantic for all data contracts
- Review events must be append-only (PRD section 19.1)
- Canonical file I/O must use atomic writes (PRD section 14)

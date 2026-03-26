# MoLabel

Local-first agentic data operations workbench for agent-assisted labeling, human review, adjudication, dataset curation, and release control.

## What is MoLabel?

MoLabel is a GUI-first, local-first, modular workbench that handles the full data lifecycle:

- **Intake** and normalization of datasets (CSV, JSONL, Parquet, chat transcripts, and more)
- **Agent-assisted labeling** with provider-agnostic model support
- **Human review** with blind review, overlap, and calibration workflows
- **Adjudication** for disagreement resolution
- **Quality measurement** and readiness analysis
- **Dataset curation** with filtering, mining, and subset operations
- **Export packaging** and release validation

MoLabel is not another annotation tool. It is a dataset control plane that owns the full operational lifecycle from messy source data to reviewed, traceable, exportable dataset artifacts.

## Status

Early development. The product requirements are defined in [`docs/prd/`](docs/prd/).

## Quick Start

```bash
# Clone and install
git clone https://github.com/your-org/MoLabel.git
cd MoLabel
uv sync

# Run the workbench (coming soon)
uv run molabel
```

## Repository Structure

This is a Python monorepo using [uv workspaces](https://docs.astral.sh/uv/concepts/workspaces/):

```
packages/
  molabel-core/         Core library (storage, workflow, agents, review, etc.)
  molabel-app/          FastAPI web application (routes, templates, static)
  molabel-plugins/      Built-in task type plugins (text labeling, chat review)
  molabel-depolarize/   DePolarize reference implementation
docs/                   PRD, architecture decisions, guides
tests/                  Unit, integration, and e2e tests
fixtures/               Sample workspaces for testing
```

## Architecture

- **Backend**: FastAPI with server-rendered templates (HTMX)
- **Database**: SQLite (WAL mode) for operational state, DuckDB/Polars for analytics
- **Packaging**: uv workspaces, Python 3.12+
- **Extensibility**: Plugin architecture with typed interfaces for data loaders, model providers, task types, review forms, export packagers, and more

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions.

## License

Apache 2.0 — see [LICENSE](LICENSE).

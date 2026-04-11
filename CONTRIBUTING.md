# Contributing to MoLabel

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (package manager)

## Setup

```bash
git clone https://github.com/Mobi21/MoLabel.git
cd MoLabel
uv sync

cd frontend && npm install
cd ../cli && npm install && npm run build
cd ..
```

This installs all workspace packages in development mode.

## Development

### Run the workbench

```bash
uv run molabel-dev
```

Backend-only CLI development:

```bash
uv run python -m uvicorn molabel.app.main:app --reload --host 127.0.0.1 --port 8000
```

Current status:

- CLI and backend are the main development surfaces today.
- The frontend is in the repo but is not ready for general use yet.

### Run tests

```bash
uv run pytest                     # all tests
uv run pytest tests/unit/         # unit tests
uv run pytest tests/integration/  # integration tests

cd frontend && npm run test
cd cli && npm test
```

### Lint and format

```bash
uv run ruff check .    # lint
uv run ruff format .   # format
```

## Repository Structure

MoLabel is a uv workspace monorepo with four packages:

- **molabel-core** (`packages/molabel-core/`) — Core library: data model, workflow, plugins, providers
- **molabel-app** (`packages/molabel-app/`) — FastAPI web application
- **molabel-plugins** (`packages/molabel-plugins/`) — Built-in task type plugins
- **molabel-depolarize** (`packages/molabel-depolarize/`) — DePolarize reference implementation

Additional top-level apps:

- **cli** (`cli/`) — public `molabel` CLI and bundled agent skills
- **frontend** (`frontend/`) — work-in-progress control-room UI
- **src-tauri** (`src-tauri/`) — work-in-progress desktop shell

See [AGENTS.md](AGENTS.md) for module boundary rules and conventions.

## Fixture Workspaces

The `fixtures/` directory contains sample project workspaces used for testing. Each fixture includes a `workbench.project.yaml` manifest. Use these for verifying end-to-end flows.

## Pull Requests

- Keep PRs focused on a single change
- Include tests for new functionality
- Run `uv run ruff check .` and `uv run ruff format .` before submitting
- Follow the module boundary rules in AGENTS.md

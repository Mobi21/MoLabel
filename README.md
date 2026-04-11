# MoLabel

MoLabel is a local-first, agent-first data operations workbench for building,
reviewing, auditing, benchmarking, and releasing labeled datasets.

It is designed for a different operating model than a typical annotation tool:

- the public interface for agents is the `molabel` CLI,
- the backend API stays behind that CLI for normal project work,
- the GUI is the manual control room for inspection, review, and adjudication,
- and canonical project state lives on disk instead of being trapped in a
  hosted service.

If you want a human-governed system where external agents can do real data
operations work without bypassing review, auditability, or file ownership,
that is what MoLabel is for.

## Why MoLabel Exists

Most labeling tools are GUI-first. Most automation stacks are API-first. Most
agent integrations are thin wrappers around hidden internals.

MoLabel is trying to close a different gap:

- local-first operation,
- file-canonical project artifacts,
- external-agent operation through a public CLI,
- human review and adjudication as first-class workflows,
- and benchmarkable end-to-end evaluation on messy real-world data work.

MoLabel is not "an annotation app with a chat box."
It is an agent-operable data operations platform with a manual control room.

## What You Can Do With It

MoLabel is built to support the full lifecycle of labeled data work:

1. bootstrap or open a workspace,
2. import messy source data,
3. define task schemas and prompts,
4. run model or agent proposals,
5. route records into human review queues,
6. adjudicate disagreements,
7. compute quality and readiness metrics,
8. export stable dataset artifacts,
9. and package release outputs with traceability.

## Product Surfaces

- `cli/`: the public `molabel` CLI for agents and scripted operation
- `packages/molabel-app/`: the FastAPI backend API behind the CLI
- `frontend/`: a work-in-progress control-room UI that is not ready for public
  use yet
- `src-tauri/`: a work-in-progress desktop shell for the local app experience

The intended center of gravity is the CLI, not the GUI.

## Current Status

MoLabel is under active development and the repo is opening up before every
surface is equally polished.

What is real today:

- the backend API and core workflow/data model,
- the CLI command families used by the benchmark harness,
- the grounded benchmark framework and fixtures,
- and bundled agent skills for Codex and Claude Code.

What is not ready yet:

- the cleanest public install path is currently from source,
- the frontend is not ready for general public use,
- the desktop shell is still early,
- and the product direction is clearer than the packaging story.

That means you can use the project today, but you should expect an early
open-source developer experience rather than a finished end-user product.

## Install From Source

Today, the most reliable way to run MoLabel is from this repository.

### Prerequisites

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/)
- Node.js 20.18+
- `npm`

### Clone And Install

```bash
git clone https://github.com/Mobi21/MoLabel.git
cd MoLabel

uv sync

cd frontend
npm install
cd ..

cd cli
npm install
npm run build
npm link
cd ..
```

After `npm link`, the `molabel` command should be available on your machine.

If you do not want to link it globally, you can still run it directly:

```bash
node cli/dist/bin/molabel.js --help
```

## Run MoLabel

Today, the supported operating path is backend plus CLI.
The frontend code is in the repo, but it is not ready for general use yet.

### Full Dev Mode

This starts the FastAPI backend on `127.0.0.1:8000` and the Vite frontend on
`127.0.0.1:5173`.

```bash
uv run molabel-dev
```

### Backend Only

If you only want the API for CLI-driven work:

```bash
uv run python -m uvicorn molabel.app.main:app --reload --host 127.0.0.1 --port 8000
```

### Configure The CLI

```bash
export MOLABEL_BASE_URL=http://127.0.0.1:8000
molabel doctor --json
```

The CLI also supports:

- `MOLABEL_WORKSPACE` for a workspace root override
- `MOLABEL_SESSION` for a session token override

CLI config is stored by default at `~/.config/molabel/cli.json`.

## Install The Agent Skill

MoLabel ships bundled skills so an external coding agent can operate the system
through the public CLI instead of making up private shortcuts.

### Codex

```bash
molabel skill install --flavor codex
```

This installs the main skill at `~/.codex/skills/molabel-cli` and also installs
the standalone grounded benchmark operator skill.

### Claude Code

```bash
molabel skill install --flavor claude-code
```

You can install into a custom skill directory with `--target <path>`.

## Use MoLabel With An Agent

Once the backend is running and the skill is installed, point your agent at a
workspace and tell it to stay on the public CLI surface.

For Codex, a good starting instruction is:

```text
Use the installed `molabel-cli` skill. Operate this workspace through `molabel`
only. Start with:
- molabel workspace detect
- molabel doctor --json
- molabel manifest --json
Then inspect the dataset, task schema, prompt, workflow, review queue, and
quality state before making changes.
```

For benchmark work, use the bundled `molabel-grounded-benchmark-operator`
skill instead.

If you are evaluating MoLabel today, use the CLI and backend flows first.
Do not treat the frontend as the primary or most complete product surface yet.

The steady-state MoLabel workflow for agents is:

1. detect the workspace,
2. inspect CLI capabilities with `molabel manifest --json`,
3. bootstrap or open the workspace,
4. create/import datasets,
5. create task schemas and prompts,
6. create and run workflows,
7. work review queues with explicit human-review decisions,
8. inspect quality,
9. then export and release.

The important rule is simple: use `molabel`, not handwritten HTTP calls.

## First Commands To Run

Once the backend is up, these are the first commands most users should run:

```bash
molabel doctor --json
molabel manifest --json
molabel workspace detect
molabel session list-reviewers --json
molabel workflow templates --json
```

If you want to bootstrap a new workspace:

```bash
molabel workspace bootstrap ./my-workspace --workspace-name "My Workspace" --json
```

If you want to inspect an existing benchmark or example workspace:

```bash
molabel workspace detect fixtures/benchmarks-grounded/clinc150/reference-workspace --json
```

## End-To-End CLI Flow

A typical MoLabel flow looks like this:

### 1. Create Or Import A Dataset

```bash
molabel dataset create \
  --name "Support Tickets" \
  --source-type file \
  --loader-plugin jsonl \
  --record-kind text \
  --canonical-id-strategy source_record_id \
  --indexing-mode projection \
  --json
```

```bash
molabel dataset import <dataset-id> --source-uri data/tickets.jsonl --json
```

### 2. Create A Task Schema

```bash
molabel task-schema create --file workbench/config/task-schemas/intent.yaml --json
```

### 3. Create A Prompt

```bash
molabel prompt create \
  --name "Intent proposer" \
  --agent-role proposer \
  --task-schema-id <task-schema-id> \
  --system-instructions "Classify each ticket into the schema labels." \
  --task-rubric "Choose exactly one intent label and explain uncertainty." \
  --json
```

### 4. Register A Model Profile

```bash
molabel model-profile create --body-text '{
  "model_profile_slug": "main-proposer",
  "provider_type": "anthropic",
  "provider_name": "anthropic-compatible",
  "model_identifier": "minimax-2.7",
  "auth_ref": "ANTHROPIC_API_KEY",
  "supports_structured_output": true
}' --json
```

MoLabel is provider-configurable underneath, but the grounded benchmark harness
currently uses `MiniMax 2.7` through the Anthropic-compatible adapter path.

### 5. Create And Run A Workflow

```bash
molabel workflow create --file workbench/workflows/intent-labeling.yaml --json
molabel workflow run <workflow-slug-or-id> --json
```

### 6. Review Work

```bash
molabel queue claim <queue-id> --json
molabel review reveal-ai <task-id> --json
molabel review submit <task-id> \
  --labels-json '{"intent_label":"reset_password"}' \
  --decision accept \
  --rationale "Matches the user request." \
  --json
```

### 7. Inspect Quality, Export, And Release

```bash
molabel quality dashboard --json
molabel export create --file export.json --json
molabel release create --file release.json --json
```

## Grounded Benchmark Quick Start

If you want to see the agent-first design most clearly, start with the grounded
benchmark fixtures in [`fixtures/benchmarks-grounded/`](fixtures/benchmarks-grounded/README.md).

Recommended starting points:

- `fixtures/benchmarks-grounded/clinc150/`
- `fixtures/benchmarks-grounded/banking77/`
- `fixtures/benchmarks-grounded/goemotions/`

Useful commands:

```bash
molabel benchmark inspect fixtures/benchmarks-grounded/clinc150
molabel benchmark verify-pack fixtures/benchmarks-grounded/clinc150
molabel benchmark report fixtures/benchmarks-grounded/clinc150
```

For the full benchmark model and scoring semantics, see
[docs/guides/grounded-benchmark-framework.md](docs/guides/grounded-benchmark-framework.md).

## Repository Layout

```text
packages/
  molabel-core/         Core runtime, storage, workflow, providers, quality
  molabel-app/          FastAPI backend API
  molabel-plugins/      Built-in plugin implementations
  molabel-depolarize/   DePolarize reference implementation
cli/                    Public CLI and bundled MoLabel skills
frontend/               React control-room UI
src-tauri/              Tauri desktop shell
docs/                   Guides, architecture docs, PRDs, and research notes
fixtures/               Sample workspaces and benchmark fixtures
tests/                  Unit, integration, and e2e coverage
```

## Documentation

Start here:

- [docs/README.md](docs/README.md)
- [How MoLabel Works Today](docs/guides/how-molabel-works-today.md)
- [Grounded Benchmark Framework](docs/guides/grounded-benchmark-framework.md)
- [Product Requirements](docs/prd/agentic-data-operations-workbench-prd.md)

## Development

Useful commands:

```bash
uv run pytest
uv run pytest tests/unit/
uv run pytest tests/integration/

cd frontend && npm run test
cd frontend && npm run lint

cd cli && npm test
cd cli && npm run lint
```

## License

Apache 2.0. See [LICENSE](LICENSE).

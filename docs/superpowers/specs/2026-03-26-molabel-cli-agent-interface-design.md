# MoLabel CLI + Skill Package: Long-Term Agent Interface

**Date:** 2026-03-26
**Status:** Revised Draft
**Scope:** A long-term, npm-distributed CLI and bundled skill package that lets coding agents and terminal users operate MoLabel end to end without changing existing GUI/API behavior. Existing API routes stay valid and unchanged. Any missing behavior is added under CLI-specific endpoints only.

---

## Decision Summary

1. The CLI is an **npm package**, not a Python workspace package.
2. The package name is **`@molabel/cli`** and the executable is **`molabel`**.
3. The CLI is **path-first and local-first aware**. It must understand workspace folders, canonical files, and project context, not just HTTP resources.
4. The CLI is **JSON-first for structured reads** and **NDJSON-first for long-running streams**.
5. The CLI does **not** duplicate backend business logic, but it **does** handle local concerns:
   - workspace detection from the current directory,
   - canonical file loading from disk/stdin,
   - launcher management for local server startup,
   - skill installation and sync.
6. Existing `/api/v1/*` routes remain intact. Missing capabilities needed by the CLI are added under **`/api/v1/cli/*`** only.
7. The CLI ships with a **bundled skill package** for tools like Codex and Claude Code, plus a machine-readable manifest so the skill stays in sync with the command surface.

---

## Why This Revision

The original draft was directionally right but too thin in three places:

- It treated MoLabel as a generic HTTP app instead of a **local-first, file-canonical** system.
- It claimed a **standalone pure HTTP client** while also promising **server lifecycle** control.
- It exposed only the happy-path CRUD surface, not the **operator controls** required for real workflows: breakpoint continue/skip, gate approve/reject, retry after failure, partial-failure handling, lock visibility, and canonical file conflict management.

This revision fixes those gaps.

---

## Product Fit

MoLabel is not just a GUI over database rows. It is a local-first workbench whose core artifacts live on disk:

- `workbench.project.yaml`
- `workbench/workflows/*.yaml`
- `workbench/prompts/*.yaml`
- `workbench/prompts/corrections/*.yaml`
- `workbench/config/task-schemas/*.yaml`
- `workbench/snapshots/*.json`
- `workbench/exports/*`
- `workbench/reports/*`
- `workbench/runs/*`

The CLI therefore must support two equally important jobs:

1. **Operate the backend**
   - list resources,
   - run workflows,
   - manage review,
   - inspect quality,
   - create exports/releases.

2. **Operate canonical artifacts safely**
   - read raw YAML/JSON source,
   - compare local candidate files to canonical files,
   - write through backend-managed conflict checks,
   - preserve auditability and local-first ownership rules.

The GUI and the CLI are sibling control surfaces over the same system, not separate products.

---

## Goals

### Primary Goals

- Give agents like Codex and Claude Code a **stable long-term shell interface** for MoLabel.
- Make the CLI installable with `npm install -g @molabel/cli` or runnable with `npx @molabel/cli`.
- Keep **existing API behavior unchanged** for the GUI and generated clients.
- Add only the minimal **CLI-specific backend endpoints** needed for:
  - canonical file round-trips,
  - path-based workspace bootstrap,
  - long-running NDJSON streams,
  - operator-complete workflow control,
  - lock inspection,
  - selector resolution.
- Make the CLI easy for both **agents** and **humans**:
  - JSON/NDJSON by default,
  - raw file output when needed,
  - table rendering for humans,
  - deterministic exit codes,
  - structured errors,
  - explicit non-interactive mode.

### Non-Goals

- Re-implement backend domain logic in the CLI.
- Replace the GUI.
- Replace the internal MoLabel assistant.
- Introduce a second non-shell agent integration stack when a CLI is sufficient.
- Break or rename existing `/api/v1/*` routes for GUI convenience.

---

## Architecture

```text
             EXTERNAL AGENTS / HUMANS
       (Codex, Claude Code, Cursor, shell users)
                           |
                           | shell command
                           v
                @molabel/cli  (npm package)
         - JSON / NDJSON output
         - workspace auto-detect
         - raw artifact read/write helpers
         - optional launcher support
         - bundled skills + manifest
                           |
            -----------------------------------
            |                                 |
            | existing API routes             | additive CLI routes
            | /api/v1/*                       | /api/v1/cli/*
            v                                 v
                FastAPI backend (MoLabel app)
                           |
          ---------------------------------------------
          |                    |                      |
          v                    v                      v
   file-canonical        SQLite operational      GUI / desktop shell
   project artifacts     state + queues          (separate surface)
```

### Key Architectural Rule

The CLI is not “pure HTTP only” in the literal sense. It is:

- **domain-thin**: no business logic duplicated from backend/core,
- **artifact-aware**: it knows how to read files/stdin and pass raw content,
- **launcher-aware**: it can start a local server when configured,
- **skill-aware**: it installs documentation/manifests for external agents.

That is the right boundary for a long-term agent CLI.

---

## Distribution Strategy

### Package

- **Package name:** `@molabel/cli`
- **Executable:** `molabel`
- **Install modes:**
  - `npm install -g @molabel/cli`
  - `npx @molabel/cli <command>`

### Why npm / TypeScript

- Coding agents already commonly install tools via npm.
- A Node-based CLI runs well in the same environments as Codex/Claude Code.
- The repository already has a TypeScript toolchain.
- Streaming, JSON, file IO, and shell integration are all first-class in Node.
- This avoids forcing agent users to provision the Python workspace just to get the CLI.

### Repository Placement

The CLI should live as a standalone npm package outside the Python workspace contract. Recommended location:

```text
cli/
  package.json
  tsconfig.json
  src/
  tests/
  skills/
```

This avoids mixing a non-Python package into the `packages/*` uv workspace contract.

---

## Package Structure

```text
cli/
├── package.json
│   name: "@molabel/cli"
│   bin:
│     molabel: "./dist/bin/molabel.js"
│
├── src/
│   ├── bin/
│   │   └── molabel.ts                # process entrypoint
│   ├── cli.ts                        # command registration
│   ├── config.ts                     # XDG/project config loading
│   ├── workspace-context.ts          # cwd -> workspace detection
│   ├── launcher.ts                   # optional server lifecycle helpers
│   ├── client/
│   │   ├── http.ts                   # JSON HTTP client
│   │   ├── ndjson.ts                 # streaming decoder
│   │   ├── cookies.ts                # session jar persistence
│   │   └── resolve.ts                # selector resolution helpers
│   ├── render/
│   │   ├── json.ts
│   │   ├── table.ts
│   │   ├── raw.ts
│   │   └── errors.ts
│   ├── artifacts/
│   │   ├── input.ts                  # --file / stdin / raw text loading
│   │   ├── diff.ts                   # local candidate diff helpers
│   │   └── revision.ts               # expected-revision handling
│   ├── commands/
│   │   ├── doctor.ts
│   │   ├── status.ts
│   │   ├── server.ts
│   │   ├── workspace.ts
│   │   ├── dataset.ts
│   │   ├── workflow.ts
│   │   ├── agent.ts
│   │   ├── review.ts
│   │   ├── adjudication.ts
│   │   ├── schema.ts
│   │   ├── prompt.ts
│   │   ├── mapping.ts
│   │   ├── export.ts
│   │   ├── release.ts
│   │   ├── provider.ts
│   │   ├── model-profile.ts
│   │   ├── runtime-profile.ts
│   │   ├── plugin.ts
│   │   ├── reviewer.ts
│   │   ├── session.ts
│   │   ├── cost.ts
│   │   ├── audit.ts
│   │   ├── assistant.ts
│   │   ├── events.ts
│   │   ├── locks.ts
│   │   ├── manifest.ts
│   │   └── skill.ts
│   └── manifest/
│       ├── commands.schema.json      # machine-readable CLI contract
│       ├── recipes.json
│       └── stream-events.schema.json
│
├── skills/
│   ├── shared/
│   │   ├── AGENTS.md
│   │   ├── recipes.md
│   │   └── safety.md
│   ├── codex/
│   │   └── SKILL.md
│   └── claude-code/
│       └── SKILL.md
│
└── tests/
    ├── unit/
    ├── integration/
    ├── golden/
    └── contract/
```

### Recommended Dependencies

- `commander` for command definition
- `zod` for runtime input/output validation
- `yaml` for local artifact parsing when needed
- `eventsource-parser` only for passive SSE topic watching
- native `fetch` / `undici` for HTTP
- `picocolors` and a lightweight table renderer for `--human`

Avoid heavy UI frameworks. The CLI should stay shell-native.

---

## Operating Modes

### 1. Remote Client Mode

The CLI talks to an already-running MoLabel server.

Use cases:

- team-shared server
- CI jobs
- local dev with manually started backend

### 2. Local Workspace Mode

The CLI detects a workspace from the current directory or an explicit path.

Use cases:

- agents working inside a repository checkout
- local project automation
- one-command bootstrap and operation

### 3. Optional Launcher Mode

`molabel server up/down/status` are convenience commands, not the core contract.

They use a configured launcher preset:

- `repo-dev`: run `uv run molabel-dev` in a checked-out MoLabel repo
- `desktop`: launch the local app/sidecar if available
- `command`: use a user-provided command

If no launcher is configured, the CLI still works fully in remote-client mode.

---

## Backend Compatibility Rule

### Existing API

All existing `/api/v1/*` routes remain valid and unchanged.

The CLI uses them whenever they are already sufficient.

### Additive CLI Namespace

Any missing behavior needed by the CLI is added under:

```text
/api/v1/cli/*
```

This preserves GUI/client compatibility while allowing the CLI to expose a better shell contract.

### When a CLI Endpoint Is Allowed

Only when the existing API is missing one of these capabilities:

- path-first workspace bootstrap/detection,
- raw canonical artifact round-trip,
- conflict-aware artifact writes,
- NDJSON long-operation streaming,
- operator-complete workflow controls,
- selector resolution,
- lock inspection,
- machine-readable status summaries,
- snapshot restore.

---

## Required CLI-Specific Backend Additions

### 1. Workspace / Context Helpers

#### `POST /api/v1/cli/workspaces/detect`

Input:

```json
{
  "path": "/absolute/path/to/workspace"
}
```

Purpose:

- detect `workbench.project.yaml`,
- classify folder as `manifest`, `heuristic`, or `empty`,
- return suggested workspace name and discovered files.

#### `POST /api/v1/cli/workspaces/bootstrap`

Purpose:

- perform the real manifest-first bootstrap flow,
- create or rebuild indexed DB state from canonical files,
- optionally create the first reviewer/session,
- return workspace summary plus session info.

This is the path-first command MoLabel actually needs. It is the CLI equivalent of “open this workspace folder”.

### 2. Selector Resolution

#### `POST /api/v1/cli/resolve`

Purpose:

- resolve resource selectors by `id`, `slug`, `name`, `prefix`, or `path`,
- return exact match or structured ambiguity error.

Request:

```json
{
  "resource": "workflow",
  "selector": "quick-agentic-label",
  "workspace_id": "ws-123",
  "match_mode": "auto"
}
```

### 3. Aggregated Status

#### `GET /api/v1/cli/status`

Purpose:

- one-call overview for agents:
  - server health,
  - current workspace,
  - dataset/workflow/review/export counts,
  - active runs,
  - pending operator actions,
  - active locks,
  - session identity.

This should be the first command skills call.

### 4. Lock Inspection

#### `GET /api/v1/cli/locks`

Purpose:

- expose active locks and the owning action,
- cover workspace migration, dataset indexing, export namespace, and task schema edit locks.

### 5. Workflow Templates

#### `GET /api/v1/cli/workflow-templates`
#### `GET /api/v1/cli/workflow-templates/{template_id}`

Purpose:

- list built-in templates,
- return metadata and raw YAML.

### 6. Canonical Artifact API

Needed for:

- workflows,
- prompts,
- task schemas,
- label mappings,
- workspace manifest.

#### `GET /api/v1/cli/artifacts/{kind}/{selector}`

Returns:

- canonical raw content,
- parsed summary,
- `file_path`,
- `revision`,
- `content_hash`,
- `is_frozen`,
- `is_human_authored`,
- conflict metadata if any.

#### `POST /api/v1/cli/artifacts/{kind}`
#### `PUT /api/v1/cli/artifacts/{kind}/{selector}`

Request shape:

```json
{
  "workspace_id": "ws-123",
  "content": "raw yaml or json text",
  "content_format": "yaml",
  "source_path": "/local/file/that/user/edited.yaml",
  "expected_revision": "rev-abc",
  "write_mode": "safe",
  "allow_force_machine_overwrite": false,
  "dry_run": false
}
```

Response shape:

```json
{
  "status": "written",
  "resource_id": "wf-123",
  "file_path": "workbench/workflows/my-flow_v2.yaml",
  "revision": "rev-def",
  "parsed_summary": {},
  "conflict": null
}
```

Conflict response:

```json
{
  "status": "conflict",
  "conflict": {
    "reason": "disk_changed_since_read",
    "is_human_authored": true,
    "base_revision": "rev-abc",
    "current_revision": "rev-xyz",
    "diff": {
      "format": "unified",
      "text": "..."
    }
  }
}
```

#### `POST /api/v1/cli/artifacts/{kind}/{selector}/diff`

Purpose:

- compare a candidate local file or stdin payload to canonical content,
- return structured diff without writing.

This is the core CLI-safe write path. It preserves the product rule that human-authored files are never silently overwritten.

### 7. Long-Running Operation Streams

The GUI uses SSE topics. The CLI should not have to assemble completion state from keepalive-only streams.

Add NDJSON-first CLI endpoints:

- `POST /api/v1/cli/datasets/{dataset_id}/import-stream`
- `POST /api/v1/cli/workflows/{workflow_id}/execute-stream`
- `POST /api/v1/cli/agent-runs/execute-stream`
- `GET /api/v1/cli/workflows/executions/{execution_id}/watch`
- `GET /api/v1/cli/agent-runs/{agent_run_id}/watch`
- `GET /api/v1/cli/queues/{queue_id}/watch`
- `GET /api/v1/cli/providers/watch`

These endpoints may internally consume existing backend event infrastructure, but their external contract to the CLI is NDJSON.

### 8. Workflow Operator Control

#### `POST /api/v1/cli/workflows/executions/{execution_id}/control`

Purpose:

- provide a single operator-complete action endpoint for the CLI.

Request:

```json
{
  "action": "step_continue",
  "workflow_id": "wf-123",
  "step_id": "label",
  "override": null,
  "note": null
}
```

Supported actions:

- `pause`
- `cancel`
- `resume`
- `retry_failed_step`
- `step_continue`
- `step_skip`
- `step_retry`
- `step_accept_partial`
- `step_retry_remaining`
- `gate_approve`
- `gate_reject`
- `set_step_override`

This is the minimum needed for breakpoints, gates, manual loops, and partial failures.

### 9. Snapshot Restore

#### `POST /api/v1/cli/datasets/{dataset_id}/snapshots/{snapshot_id}/restore`

Purpose:

- create a safety snapshot of the current state,
- restore the chosen historical snapshot,
- return the new snapshot created by the restore flow.

---

## Command Design

### Top-Level Shape

```bash
molabel <group> <verb> [args] [flags]
```

### Global Flags

```text
--server <url>            MoLabel server URL
--workspace <selector>    Explicit workspace
--cwd <path>              Detect workspace from this directory
--json                    Structured JSON output (default for structured reads)
--jsonl                   NDJSON output (default for long streams)
--human                   Human-friendly tables/text
--raw                     Raw canonical file output
--quiet                   Minimal scalar output for scripts
--non-interactive         Never prompt
--yes                     Confirm destructive operations
--verbose                 Debug timing/HTTP/launcher info
```

### Workspace Context Resolution

Every command resolves workspace context in this order:

1. `--workspace`
2. `MOLABEL_WORKSPACE`
3. config default
4. detect from `--cwd`
5. detect from current working directory

If still unresolved, the CLI returns a structured error with the exact fix.

### Selector Rules

Resources accept:

- exact ID,
- exact slug,
- exact name where supported,
- unique prefix when unambiguous.

Agents should prefer exact IDs or slugs in scripts. Auto-resolution remains available for interactive use.

---

## Command Surface

This is the long-term command surface the skill package should teach.

### General

```bash
molabel doctor
molabel status
molabel version
molabel manifest --json
molabel resolve <resource> <selector>
molabel locks list
```

### Server

Optional convenience commands. These depend on a configured launcher.

```bash
molabel server up
molabel server down
molabel server status
molabel server logs
```

### Workspace

```bash
molabel workspace detect <path>
molabel workspace bootstrap <path>
molabel workspace list
molabel workspace show <selector>
molabel workspace use <selector>
molabel workspace current
molabel workspace reindex <selector>
```

### Dataset

```bash
molabel dataset list
molabel dataset show <selector>
molabel dataset create <name> --source-type <type>
molabel dataset import <selector> --source <uri> [--mapping <selector>] [--wait]
molabel dataset records <selector> [--limit N]
molabel dataset record <selector> <record-id>
molabel dataset analytics <selector>
molabel dataset compare <selector-a> <selector-b>
molabel dataset snapshot create <selector> --name <name>
molabel dataset snapshot list <selector>
molabel dataset snapshot diff <selector> <snapshot-id> [--vs <snapshot-id>]
molabel dataset snapshot restore <selector> <snapshot-id>
```

### Workflow

```bash
molabel workflow template list
molabel workflow template show <template-id>
molabel workflow list
molabel workflow show <selector>
molabel workflow cat <selector>
molabel workflow create --file <yaml> [--name <name>] [--workspace <ws>]
molabel workflow update <selector> --file <yaml>
molabel workflow diff <selector> --file <yaml>
molabel workflow validate --file <yaml>
molabel workflow run <selector> [--dataset <ds>] [--wait | --detach]
molabel workflow watch <execution-id>
molabel workflow executions <selector>
molabel workflow execution <execution-id>
molabel workflow pause <execution-id>
molabel workflow cancel <execution-id>
molabel workflow resume <execution-id>
molabel workflow step continue <execution-id> <step-id>
molabel workflow step skip <execution-id> <step-id>
molabel workflow step retry <execution-id> <step-id>
molabel workflow step override <execution-id> <step-id> --file <json>
molabel workflow gate approve <execution-id> <step-id>
molabel workflow gate reject <execution-id> <step-id>
molabel workflow partial accept <execution-id> <step-id>
molabel workflow partial retry-remaining <execution-id> <step-id>
```

### Agent Runs

```bash
molabel agent run --dataset <ds> --schema <schema> --model-profile <mp> --agent-role <role> [--prompt <prompt>] [--runtime-profile <rp>] [--wait | --detach]
molabel agent cancel <run-id>
molabel agent show <run-id>
molabel agent outputs <run-id> [--limit N]
molabel agent output <run-id> <record-id>
molabel agent compare --dataset <ds> --schema <schema> --agent-role <role> --models <a,b,c>
molabel agent comparison <comparison-id>
molabel agent analytics [--dataset <ds>]
molabel agent watch <run-id>
```

### Review and Adjudication

```bash
molabel review queue status <queue-id>
molabel review queue watch <queue-id>
molabel review reviewers
molabel review claim <queue-id>
molabel review submit <task-id> --file <labels.json>
molabel review skip <task-id>
molabel review release <task-id>
molabel review draft <task-id> --file <labels.json>
molabel review reveal-ai <task-id>
molabel review correct <task-id> --file <labels.json>
molabel review events [--record <record-id>]

molabel adjudication detect --file <events.json>
molabel adjudication build-queue --file <events.json>
molabel adjudication queue
molabel adjudication show <item-id>
molabel adjudication resolve <item-id> --resolution <type> [--file <labels.json>]
```

### Schemas, Prompts, and Mappings

```bash
molabel schema list
molabel schema show <selector>
molabel schema cat <selector>
molabel schema create --file <yaml>
molabel schema update <selector> --file <yaml>
molabel schema diff <selector> --file <yaml>
molabel schema validate --file <yaml>

molabel prompt list
molabel prompt show <selector>
molabel prompt cat <selector>
molabel prompt create --file <yaml>
molabel prompt update <selector> --file <yaml>
molabel prompt diff <selector> --v1 <version> --v2 <version>
molabel corrections list
molabel corrections analyze <batch-id>
molabel corrections refinement <batch-id>

molabel mapping preview --file <mapping.json> --sample <records.json>
molabel mapping save --file <mapping.json>
molabel mapping show <selector>
molabel mapping cat <selector>
```

### Export and Release

```bash
molabel export list
molabel export create --file <export.json> [--wait | --detach]
molabel export preview --file <export.json>
molabel export show <export-id>
molabel export validate <export-id>
molabel export download <export-id> --out <path>
molabel export push-hf <export-id> --repo <repo-id>

molabel release list
molabel release create --file <release.json>
molabel release show <release-id>
molabel release approve <release-id>
molabel release reject <release-id>
```

### System

```bash
molabel provider list
molabel provider scan
molabel provider health <provider-type>
molabel provider models <provider-type>
molabel provider hf-auth
molabel provider watch

molabel model-profile list
molabel model-profile show <id>
molabel model-profile create --file <json>
molabel model-profile update <id> --file <json>
molabel model-profile delete <id>
molabel model-profile test <id>

molabel runtime-profile list
molabel runtime-profile show <id>
molabel runtime-profile create --file <json>
molabel runtime-profile update <id> --file <json>
molabel runtime-profile delete <id>
molabel runtime-profile retry-config <id>

molabel plugin list
molabel plugin show <id>
molabel plugin enable <id>
molabel plugin disable <id>

molabel reviewer list
molabel reviewer create <name> --workspace <ws>
molabel reviewer show <id>
molabel reviewer update <id> --file <json>

molabel session login <reviewer-id>
molabel session switch <reviewer-id>
molabel session me
molabel session logout

molabel cost summary
molabel cost estimate --dataset <ds> --model-profile <mp> --agent-role <role>
molabel audit list
molabel audit show <id>
molabel assistant context
molabel assistant query --screen <screen> --text <query>
molabel events watch <topic> <id>
```

### Skill Package

```bash
molabel skill install --preset codex
molabel skill install --preset claude-code
molabel skill print --preset codex
molabel skill update --preset codex
```

---

## Canonical Artifact Rules

### Read Modes

- `show`: structured metadata and parsed summary
- `cat`: raw canonical file content
- `diff`: compare local candidate to canonical without writing

### Write Modes

All canonical artifact writes follow this contract:

1. CLI loads raw content from `--file`, stdin, or inline text.
2. CLI sends raw content plus `expected_revision`.
3. Backend validates and parses it.
4. Backend applies file-canonical conflict rules.
5. Backend updates indexed DB projections transactionally.
6. CLI receives:
   - success,
   - validation error,
   - conflict with diff,
   - lock/conflict block.

### Human vs Machine Authorship

- Human-authored canonical files may never be silently overwritten.
- Machine-authored files may support explicit force-overwrite only when the backend marks them as safe for that behavior.
- The CLI should expose:
  - `--write-mode safe`
  - `--write-mode force-machine`

No generic blind `--force` for canonical artifact writes.

---

## Streaming Contract

### Format

Long-running CLI operations use **NDJSON** directly from CLI-specific endpoints.

One JSON object per line:

```json
{"type":"started","op":"workflow.execute","execution_id":"exec-1","ts":"2026-03-26T10:00:00Z"}
{"type":"progress","step_id":"ingest","status":"running","completed":100,"total":5000,"ts":"2026-03-26T10:00:05Z"}
{"type":"paused","reason":"waiting_for_gate","step_id":"review_gate","ts":"2026-03-26T10:02:00Z"}
{"type":"terminal","status":"completed","execution_id":"exec-1","ts":"2026-03-26T10:03:00Z"}
```

### Required Event Envelope

Every event includes:

- `type`
- `ts`
- `op`
- resource IDs relevant to the operation
- enough payload for incremental progress

### Terminal States

The final event always has `type: "terminal"` and one of:

- `status: "completed"`
- `status: "failed"`
- `status: "paused"`
- `status: "cancelled"`

`paused` is not treated as a generic failure.

### Passive Watches

For watch-style commands, the CLI may translate existing SSE topics into NDJSON locally:

- workflow events
- queue events
- provider events
- agent run events

This keeps the shell contract consistent even if the backend topic source is SSE.

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Server unavailable |
| 3 | Resource not found |
| 4 | Validation error |
| 5 | Conflict / locked / wrong state |
| 6 | Authentication or session required |
| 7 | Ambiguous selector |
| 8 | Launcher unavailable or misconfigured |
| 10 | Long-running operation failed |
| 11 | Operation paused and requires human/operator input |
| 12 | Canonical write conflict |
| 130 | Interrupted |

This makes paused workflows, human steps, and gate waits machine-detectable.

---

## Error Contract

Errors are always JSON on stderr.

```json
{
  "error": {
    "code": "WORKSPACE_REQUIRED",
    "message": "No workspace context could be resolved",
    "detail": {
      "cwd": "/repo/project",
      "tried": ["flag", "env", "config", "cwd"]
    },
    "suggestions": [
      "Run: molabel workspace bootstrap .",
      "Or pass: --workspace <id>"
    ]
  }
}
```

Error payload fields:

- `code`
- `message`
- `detail`
- `suggestions`

For conflicts and ambiguity, the error payload must include candidate matches or diff summaries.

---

## Configuration

### Config Files

Use XDG-style config with optional project override:

- global: `~/.config/molabel/config.toml`
- project: `.molabel/config.toml`

### Session Storage

Store per-server cookie jars and identity metadata under:

- `~/.local/state/molabel/sessions.json`

Do not store a single raw cookie string in a flat file. The CLI should support multiple servers and multiple sessions safely.

### Recommended Config Keys

```toml
[default]
server = "http://127.0.0.1:8000"
workspace = ""
output = "json"

[launcher]
kind = "command"                # "command" | "repo-dev" | "desktop"
command = "uv run molabel-dev"
cwd = "/path/to/MoLabel"

[skills]
default_target_codex = "~/.codex/skills/molabel"
default_target_claude_code = "~/.claude/skills/molabel"
```

### Environment Variables

- `MOLABEL_SERVER`
- `MOLABEL_WORKSPACE`
- `MOLABEL_OUTPUT`
- `MOLABEL_LAUNCHER_KIND`
- `MOLABEL_LAUNCHER_COMMAND`
- `MOLABEL_LAUNCHER_CWD`

Flags override env. Env overrides config.

---

## Server Lifecycle Semantics

### Important Constraint

`molabel server up/down/status` are **optional local conveniences**, not a requirement for remote use.

### `molabel server up`

Flow:

1. If `/health` already responds, return success.
2. Resolve launcher preset.
3. Start the configured process.
4. Wait for `/health`.
5. Persist launcher PID/state locally.

### `molabel server down`

Flow:

1. Resolve launcher state.
2. Stop only the process started by the CLI.
3. Never kill an arbitrary process merely bound to port 8000.

### `molabel server status`

Returns:

- launcher status,
- server health,
- server URL,
- PID if launcher-managed,
- current workspace if known.

---

## Skill Package Design

### Purpose

The CLI package ships the skill package. Users should not need a separate repository or manual copy/paste.

### Install Model

`molabel skill install` writes a versioned skill bundle to a chosen target.

Presets:

- `codex`
- `claude-code`

### Skill Bundle Contents

- `SKILL.md`
- `AGENTS.md`
- `recipes.md`
- `safety.md`
- `commands.schema.json`
- `recipes.json`

### Required Skill Topics

- workspace bootstrap and detection
- canonical file safety rules
- preferred command order for situational awareness
- long-running stream handling
- exit code interpretation
- when to use `show` vs `cat` vs `diff`
- how to respond to `paused`, `conflict`, and `ambiguous selector`
- recommended end-to-end recipes:
  - bootstrap workspace
  - inspect current state
  - create or update workflow from YAML
  - run sample workflow
  - inspect quality
  - export and release

### Machine-Readable Manifest

`molabel manifest --json` must emit:

- command groups,
- verbs,
- flags,
- exit codes,
- stream event schemas,
- recipe names,
- CLI version.

This lets an external skill stay synchronized with the installed CLI version.

---

## Agent Ergonomics

### Readability Modes

- default structured reads: `--json`
- default long runs: `--jsonl`
- raw artifact source: `--raw`
- human tables: `--human`

### Scalar Capture

`--quiet` returns only the essential scalar:

- created resource ID
- execution ID
- current workspace ID

### Safe Defaults

- structured output by default
- no interactive prompt in `--non-interactive`
- paused operations return code `11`
- conflicts return code `12`
- ambiguous selectors return code `7`

### Explicit Artifact Operations

Agents should be taught this rule:

- use `show` to understand,
- use `cat` to inspect raw canonical source,
- use `diff` before `update` when editing canonical files.

---

## Testing Strategy

### Unit Tests

- config resolution
- workspace detection
- selector resolution
- cookie/session persistence
- artifact input loading
- output rendering
- exit code behavior

### Contract Tests

- compare CLI manifest to command registration
- validate NDJSON event envelopes against schema
- validate CLI-specific route request/response schemas

### Integration Tests

Against a real MoLabel backend:

- bootstrap workspace from path
- create/update workflow from YAML file
- prompt/schema artifact read/write conflict flow
- dataset import stream
- workflow execute stream
- workflow pause/resume/gate/breakpoint control
- review claim/submit/correct
- export validate/download
- release approve/reject

### Golden Tests

- `--json` output
- `--jsonl` stream output
- `--human` rendering
- `--raw` artifact output

### Skill Tests

- generated skill bundle contains expected files
- recipes reference only valid commands
- manifest version matches CLI version

---

## Phased Implementation Plan

### Phase 1: CLI Skeleton and Current API Coverage

- npm package scaffold
- config/session/workspace detection
- command groups over existing routes
- JSON/human/raw rendering
- skill install and manifest output

### Phase 2: CLI-Specific Backend Additions

- `/api/v1/cli/status`
- `/api/v1/cli/resolve`
- `/api/v1/cli/workspaces/detect`
- `/api/v1/cli/workspaces/bootstrap`
- `/api/v1/cli/locks`
- `/api/v1/cli/workflow-templates`
- canonical artifact endpoints
- NDJSON run/watch endpoints

### Phase 3: Operator-Complete Workflow Control

- execution control endpoint
- breakpoint/gate/partial-failure commands
- paused-state exit code semantics
- lock visibility in `status`

### Phase 4: Artifact Safety and Snapshot Restore

- revision-aware artifact writes
- conflict diffs
- safe machine overwrite mode
- snapshot restore flow

### Phase 5: Skill Polish

- recipe set
- manifest schemas
- install presets
- end-to-end golden tests for Codex/Claude Code usage

---

## Final Position

The long-term MoLabel CLI should be:

- **npm-distributed**
- **path-first**
- **canonical-file-aware**
- **JSON/NDJSON-first**
- **operator-complete**
- **skill-bundled**
- **backward-compatible with the existing API**
- and **supported by additive `/api/v1/cli/*` routes only where the current API is insufficient**

That is the right design for a CLI that agents can use adeptly, safely, and repeatedly across the full MoLabel lifecycle.

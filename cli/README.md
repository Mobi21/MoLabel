# MoLabel CLI

Agent-first CLI and bundled skill package for MoLabel.

The intended operating model is:

- agents use `molabel` as the primary public interface,
- the backend stays behind that CLI,
- the GUI is the inspection and manual-review surface.

## Command Groups

- `session`: reviewer identity and session control
- `workspace`: workspace detection and bootstrap
- `provider`: provider discovery, health, and model listing
- `model-profile`: model profile CRUD and connectivity checks
- `benchmark`: authority-pack inspection, validation, scoring, and reporting
- `dataset`: dataset and record inspection/import
- `task-schema`: task schema creation and inspection
- `prompt`: prompt creation and inspection
- `workflow`: workflow creation, execution, and execution control
- `queue`: review queue inspection, claiming, and closing unclaimed copies
- `review`: submit, draft, reveal, release, and correction flows
- `adjudication`: disagreement detection and resolution
- `agent-run`: agent-run lifecycle and comparison
- `quality`: quality dashboard, agreement, drift
- `export`: export creation and validation
- `release`: release creation and approval
- `artifact`: canonical file read/diff/write
- `skill`: install bundled MoLabel skills

## Output Contract

Every command prints exactly one JSON document to stdout and exits 0 or 1.
The exceptions are `--help` and `--version`, which print plain text to stdout
and exit 0. Commander's usage hints on a usage error go to stderr. Branch on
the exit code, then read `error.code`.

On exit 0, stdout is the command's result. Its shape belongs to the command,
and is usually the backend's response.

On exit 1, stdout is an error envelope. `details` is present when there is
more to say.

```json
{
  "error": {
    "code": "HTTP_400",
    "message": "This template needs a dataset, and the workspace has 2. Pass dataset_id (molabel workflow create --dataset) with one of: ...",
    "details": { "error": { "code": "BAD_REQUEST", "message": "..." } }
  }
}
```

| Code                     | Meaning                                                                                                    |
| ------------------------ | ---------------------------------------------------------------------------------------------------------- |
| `USAGE_ERROR`            | The command line is malformed, such as an unknown command or option or a missing argument.                 |
| `NO_BACKEND`             | The command needs a backend and neither `--base-url` nor `MOLABEL_BASE_URL` is set.                        |
| `BACKEND_UNREACHABLE`    | The CLI could not connect to the backend. `details` has the `url` and the `cause`.                         |
| `HTTP_<status>`          | The backend answered with an error. `message` is the backend's message and `details` is its response body. |
| `WORKFLOW_RUN_FAILED`    | `workflow run` or `workflow advance` stopped on a failed step. `details` is the execution.                 |
| `BENCHMARK_PACK_INVALID` | `benchmark verify-pack` found errors. `details` is the verification report.                                |
| `CLI_ERROR`              | Any other failure.                                                                                         |

Three things print something other than JSON. `--help` prints help text and
exits 0. `--version` prints the version and exits 0. `--raw` prints the raw
content for commands that have it, such as `artifact read` and
`benchmark report`. `--json` is accepted everywhere and changes nothing,
because JSON is the default.

`tests/json-contract.test.ts` runs every command against no backend, a backend
that answers `{}`, a backend that fails, and an unreachable backend, and checks
this contract for each.

## Labeling without an API key

The offline provider labels records with keyword heuristics instead of a
model. It needs no LLM key, no network, and no model download, so the whole
flow of import, pre-label, review, and export runs on any machine. Pick it
when you create a workflow from a template:

```bash
molabel workflow create --template quick_agentic_label --provider offline
```

This writes `model: offline-heuristic` and `provider_type: offline` into every
`agent_run` step. In a workflow file you write yourself, either key alone is
enough. `provider_type: offline` labels with `offline-heuristic` whatever
model name `model` gives. A model profile with `provider_type: offline` also
works. A step that pins a profile id in `model` or `model_profile_id` runs on
that profile, so next to `provider_type: offline` it must be an offline one.
`--model <id>` replaces the template's model with a different one instead.

A template can leave a model unset for you to choose. `agent_comparison`
compares `claude-sonnet-4-20250514` and `gpt-4o` with a model you name, so
creating it needs `--model <id>` or `--provider offline`. Without either,
`workflow create` fails with `HTTP_400` before it creates anything, and
`details.error.code` is `TEMPLATE_MODEL_REQUIRED`. `--provider offline` runs
every model the comparison names on the offline provider.

For a field with options, the provider picks the first option, in schema
order, that the record text contains as a whole word or phrase, ignoring case.
When no option matches, it picks the first option. A multi-select field gets
every matching option. A boolean field is true when the text contains the
field name. Any other field gets the simplest valid value of its type. The
same record and schema always give the same labels.

Offline proposals are marked so that reviewers and routing can tell them from
a model's. The agent run's adapter is `builtin.offline`, each output's
`raw_response.strategy` is `offline-heuristic`, its `composite_confidence` is
0, and the run costs nothing.

MoLabel does not switch to the offline provider on its own. Without a key, a
workflow that names a hosted model fails with `WORKFLOW_RUN_FAILED`, and the
message names the unset key variable and the `--provider offline` flag.

MoLabel does not guess a provider either. When an agent step's model matches
no model profile and no known model family, `workflow run` fails with
`HTTP_400` before any step runs. `details.error.code` is `MODEL_UNRESOLVED`,
and `details.error.details.usable_providers` lists the providers the backend
can use, with their models. Set `provider_type` on the step, or create a
profile for the model with `molabel model-profile create`.

`molabel doctor` lists the providers the backend can use under `providers`.
`scripts/smoke_no_key.py` runs the full flow with no key against a real
backend, and CI runs it in the `smoke-no-key` job.

## Development

```bash
npm install
npm run build
npm test
```

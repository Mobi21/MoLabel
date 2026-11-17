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
- `queue`: review queue inspection and claiming
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

## Development

```bash
npm install
npm run build
npm test
```

# MoLabel CLI

Agent-first CLI and bundled skill package for MoLabel.

The intended operating model is:

- agents use `molabel` as the primary public interface,
- the backend stays behind that CLI,
- the GUI is the inspection and manual-review surface.

## Command Groups

- `session`: reviewer identity and session control
- `reviewer`: create reviewer profiles
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
- `adjudication`: list, show, and resolve the disagreements of a review queue
- `gold`: create gold sets, promote reviewed records, append failures, dedupe, and export
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

## Adjudication

Adjudication works on one review queue at a time, through the same endpoints
as the GUI. A resolution is stored in the database, so it survives a backend
restart, sets the record's labels for export, and shows in the GUI.

A queue has disagreements only when two reviewers review the same record, so
a workflow's `human_review` step needs `overlap_count: 2` and the workspace
needs a second reviewer. `reviewer create` adds one to the current workspace
and prints the new profile. `session switch` makes the CLI act as it.

```bash
molabel reviewer create --display-name "Reviewer 2"
molabel session switch <reviewer-id>
```

```bash
molabel adjudication list <queue-id>
molabel adjudication show <queue-id> <record-id>
molabel adjudication resolve <queue-id> <record-id>   --review-event-ids <id>,<id> --resolved-labels-json '{"sentiment": "neutral"}'
```

`list` shows a record only once every review copy of it in the queue is
submitted, skipped, or closed, so no reviewer sees another's labels before
their own review is in. `molabel queue close-copies` closes the unclaimed
copies of a queue with more copies than reviewers.

`resolve` needs `--review-event-ids`, the `review_event_id` of each
`reviewer_labels` entry that `show` printed. When a review of the record came
in after the read, it fails with `HTTP_409`. Run `show` again and resolve on
what it prints. `--resolution` is `resolve` by default, which needs
`--resolved-labels-json` or `--resolved-labels-file`. The others are
`preserve_disagreement`, `downgrade`, and `exclude`. Another workspace's queue
fails with `HTTP_404`.

The earlier `adjudication detect`, `adjudication build`, and
`adjudication queue` commands are gone. They took review events from the
caller and kept their queue and resolutions in the backend's memory, so a
resolution vanished on restart and never reached export or the GUI. `list`
replaces `detect`, `build`, and `queue`, because the backend now finds a
queue's disagreements from its stored reviews. `resolve` takes a queue and a
record instead of a queue item ID.

## Gold sets

A gold set is `gold/<slug>/gold.yaml` and `gold/<slug>/gold.jsonl` in the
workspace, for you to commit. MoLabel writes the files and never runs git.
`docs/architecture/gold-sets.md` gives the item shape and the rules.

```bash
molabel gold create ticket-gold --task-schema ticket-triage
molabel gold promote ticket-gold --queue <queue-id>
molabel gold append ticket-gold --execution <execution-id>
molabel gold show ticket-gold
molabel gold dedupe ticket-gold
molabel gold export ticket-gold --raw > ticket-gold.jsonl
molabel gold export ticket-gold --out exports/ticket-gold.jsonl
```

`promote` takes the records an adjudication resolved with labels and the
records whose counted reviewers gave identical labels. With
`--allow-single-reviewer` it also takes a record one reviewer labelled, and
marks it `single_reviewer`. `--record <id>` limits it to records of
`--queue`. `append` takes only the records whose human label contradicts the
agent proposal. Both report `added`, `duplicates`, `conflicts` and `skipped`,
and say why each skipped record was left out. A second run adds nothing and
writes nothing. Other labels for an input the set holds are a conflict,
which is reported and never overwrites the item. `export` prints the JSONL
inside its JSON result, prints the lines alone with `--raw`, or writes them
to a workspace path with `--out`. A set of another workspace fails with
`HTTP_404`.

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

`molabel doctor` lists the providers the backend can use under `providers`,
and under `database.foreign_key_violations` the rows of the server database
whose foreign keys point at missing rows, per table and parent. The server
refuses new ones; rows written before it enforced foreign keys are kept and
listed here.
`scripts/smoke_no_key.py` runs the full flow with no key against a real
backend, and CI runs it in the `smoke-no-key` job. It ends with a
two-reviewer adjudication driven by the CLI alone: `reviewer create`,
`session switch`, and `adjudication list`, `show` and `resolve` on a queue
with two copies of each record.

## Development

```bash
npm install
npm run build
npm test
```

# Gold sets

A gold set is a released eval or training set: records with the labels people
settled on, kept as files in the workspace for the user to commit to git.
Review in progress stays in SQLite. MoLabel writes the files and never runs
git. This note fixes the file layout, the item shape, and the rules for
writes, duplicates and calibration.

## File layout

```
gold/<slug>/gold.yaml        the header
gold/<slug>/gold.jsonl       one item per line
gold/<slug>/conflicts.jsonl  one open conflict per line, once there is one
```

`workbench.project.yaml` lists each set under `gold_sets`, with its
`gold_set_id` (the slug) and `definition_path` (the header). The set's other
files are the ones beside the header, in the folder its path resolves to, and
a path written with `\` separators works on every platform. The header holds
the slug, `name`, `task_schema` (the task schema's slug, the file-canonical
id), `format_version`, `version`, `item_count`, `content_hash`,
`previous_hash`, `sources`, `created_at` and `updated_at`. `sources` lists each
queue the set took items from, with its workflow execution and workflow slug
when it has one.

One set holds one task schema, because labels are comparable only under one
schema. Promotion from a queue of another schema answers
`GOLD_TASK_SCHEMA_MISMATCH`.

Every write goes through `workspace_files`. It takes the workspace lock, checks
each path with the `workspace_paths` guard, refuses a name Windows cannot hold
(`422 PATH_NOT_PORTABLE`, so a slug such as `con` or `lpt1` is refused), and
restores both files if the write fails. It replaces `gold.jsonl` before
`gold.yaml`, so the header's `content_hash` and `item_count` always describe a
file already on disk. A process killed between the two leaves the previous
header beside the new items, and every read reports that, as below. The header
goes through `dump_yaml`, which keeps a person's comments and key order. Both
files are UTF-8 with LF line ends.

Items keep the order they were added in. Promote and append write new lines
after the file's bytes and leave every earlier line as it is, hand formatting
included, except a stale line (below), which they render afresh. Only dedupe,
which removes items, renders the whole file again.
Within an item the fields keep a fixed order and free-form objects (`input`,
`expected`) have sorted keys. U+0085, U+2028 and U+2029 are escaped inside
strings, so every editor sees one item per line. The same content renders to
the same bytes on any machine.

## Item shape

```json
{"item_id": "uuid", "input_ref": {"dataset": "support-tickets", "external_id": "ticket-4", "record_id": "uuid"},
 "input": {"text": "..."}, "input_hash": "sha256:...", "expected": {"intent": "refund", "urgent": false},
 "content_hash": "sha256:...", "provenance": {...}}
```

- `input` is the record's stable fields, the content a reviewer labels, with
  no id or source metadata. A record whose stable fields are all empty uses
  its payload. Fields that could leak a label, such as `gold_label`, are
  removed, as the review screen removes them.
- `expected` is the human label, with null fields dropped (null is missing).
- `input_hash` is the SHA-256 of `input` after normalization. Normalization
  applies Unicode NFC, turns CRLF into LF, strips each string's ends, and
  sorts keys. `content_hash` is the SHA-256 of `input_hash` and `expected`.
- `item_id` is a UUIDv5 of the task schema slug and `input_hash`, written
  hyphenated. The same input gives the same id on every machine.
- `provenance` holds `source` (`adjudication`, `reviewer_agreement` or
  `single_reviewer`), the `queue_id`, the `workflow_execution_id`, the
  `adjudication` when there is one, `reviews` (each counted review event with
  its reviewer, decision and whether an AI proposal was shown),
  `reviewer_ids`, `ai_revealed`, `accepted_ai_proposal`,
  `adjudicator_took_ai`, `model_failure`, `promoted_at` and `promoted_by`.

MoLabel recomputes `item_id`, `input_hash` and `content_hash` from the content
whenever it reads a file, and dedupes and finds conflicts on the recomputed
values. A line whose stored values differ from the recomputed ones, as a hand
edit to `input` or `expected` leaves it, is stale. `gold show` lists stale
lines under `stale_items` with `items_consistent: false`, and `gold export`
reports `items_consistent`. The next promotion or append that adds an item
replaces each stale line with the item rendered afresh and lists it under
`corrected`. A write never leaves a line whose stored id or hashes its content
contradicts.

## Version rule

A write that changes `gold.jsonl` increments `version`. It sets
`previous_hash` to the hash of the file it replaced and `content_hash` to the
hash of the new file. Create writes version 1 with no items. A promotion
that adds no item, or a dedupe that removes none, writes nothing and keeps the
version, so promoting the same records twice changes no file. A `content_hash` that does
not match the file means someone edited it outside MoLabel, or a write stopped
between the two files. Every summary of the set reports it as
`content_hash_matches: false`: `gold list`, `gold show`, `gold export`, and the
reports of promote, append and dedupe. The header's version and item count
then describe the previous file. The next write that changes the items
records the file as it is as the previous version.

Create never adopts or overwrites files it did not list. If `gold/<slug>/`
holds any file, such as a `gold.jsonl` left behind, and the manifest lists no
set there, create answers `409 GOLD_SET_FILES_EXIST` with the files it found.
Pick another slug, move the folder, or list its `gold.yaml` under `gold_sets`.
An empty folder is used as it is.

## Duplicates and conflicts

The dedupe key is the task schema plus `input_hash`, which is `item_id`. A
candidate whose key is new is added. A candidate whose key exists with the
same `content_hash` is a duplicate and is skipped. The same key with a
different `content_hash` means the same input has different expected labels.
That is a conflict. MoLabel reports both label sets and never overwrites the
item. `gold dedupe` removes repeated items with the same content, which a
git merge of two appends can leave, and keeps the first. It reports the
conflicts `gold.jsonl` holds and leaves them in place.

### conflicts.jsonl

A promotion or append writes each conflict it finds to `conflicts.jsonl`
beside `gold.jsonl`, so a conflict an agent's `gold append` met reaches the
lead who opens the set. The file appears with the first conflict. A line
looks like this:

```json
{"item_id": "uuid", "input_hash": "sha256:...", "input_ref": {"dataset": "support-tickets", "external_id": "ticket-4", "record_id": "uuid"},
 "fields": ["intent"], "existing": {"intent": "refund"}, "incoming": {"intent": "other"},
 "provenance": {...}, "detected_at": "2026-11-17T14:02:14+00:00"}
```

- `item_id` and `input_hash` name the gold item.
- `existing` is the labels `gold.jsonl` holds. `incoming` is the labels that
  were not added. `fields` names the fields where they differ.
- `input_ref` and `provenance` are the incoming item's: its record, `source`,
  queue, workflow execution, adjudication, review events and reviewers, and
  the model failure for an append. `provenance.promoted_at` is when the
  promotion ran, the same as `detected_at`.

The file is written like `gold.jsonl`: through `workspace_files`, one line
per conflict, LF line ends, fixed field order, sorted label keys, and the
same escapes for U+0085, U+2028 and U+2029. New conflicts go after the
file's lines. A line that is still open keeps its bytes.

A conflict is the same as one the file holds when its item, incoming labels
and `provenance.source` match, so running an append again adds no line.
Another label set or another source for the item adds a line.

Conflicts are not gold. Writing `conflicts.jsonl` never changes
`gold.jsonl`, `version`, `content_hash` or `item_count`. `gold.yaml` does not
name the file or count its lines. The header describes `gold.jsonl` alone, a
count there would go stale whenever someone edits `conflicts.jsonl`, and
rewriting the header for a conflict would show a gold change in git where
there is none. The file is found by its place beside `gold.jsonl`.

A person settles a conflict in one of two ways: edit the item in `gold.jsonl`
to the incoming labels, or delete the line from `conflicts.jsonl`. A conflict
whose item `gold.jsonl` no longer holds is settled too. Every read leaves
settled lines out. A hand edit that gives the item a third label set leaves
the conflict open, and reads show the item's current labels as `existing`.
The next promote, append or dedupe writes the file again. It drops settled
lines and renders afresh each line whose `existing` changed. When the last
conflict is settled the file stays, empty. There is no resolve command.

`gold show` and `GET /api/v1/gold-sets/{id}` list the open conflicts under
`open_conflicts`, and so does each promote, append and dedupe report. The
gold view in the GUI lists them in a table under Conflicts: the record, the
gold labels, the incoming labels with the differing fields marked, the
source and queue, and when the conflict was found. A `conflicts.jsonl` line
that does not parse answers `409 GOLD_SET_INVALID` with its line number, as
a bad `gold.jsonl` line does.

## What may be promoted

A record is eligible once every copy of it in the queue is submitted, skipped
or closed, in one of three ways:

1. An adjudication resolved it with labels. `preserve_disagreement`,
   `downgrade` and `exclude` give no expected label, so they are skipped.
2. Two or more counted reviewers gave identical labels, and none rejected it.
3. With `allow_single_reviewer`, one counted reviewer labelled it. Its
   `source` is `single_reviewer`.

Expected labels always come from a human review event or an adjudication. An
agent proposal that no human accepted is never promoted. `ai_revealed` says
whether a proposal was shown to any human whose review the label rests on.
`adjudicator_took_ai` says whether the adjudicator took a field's value from an
AI proposal, or resolved to labels equal to a proposal the adjudication screen
showed. The resolve request names each taken field and its proposal in
`agent_sources`, and the server refuses a field the proposal gave no value for,
or a value other than the resolved one, with 422.
`accepted_ai_proposal` says whether a counted reviewer accepted a shown
proposal or the adjudicator took one. P9's bias audits filter on these fields.

## Append failures

`gold append` promotes only the eligible records the model got wrong, those
whose expected label differs from a proposal bound to the record's review
tasks. An edit or a corrected reject changes the label, so it qualifies. A
reject with no corrected label gives no expected label and is skipped.
`provenance.model_failure` records the agent output, its labels, and the
fields it got wrong. Append dedupes like promotion and reports added,
duplicate, conflict and skipped counts.

## Calibration

A `human_calibration` step must name a set with `gold_set: <slug>`. It makes a
queue of the set's items. Each item finds its record by `record_id`, or by
dataset slug and `external_id` on a database that imported the data again.
Each item gets `min_reviewers` copies. The tasks are marked `is_calibration`.
A reviewer never sees the expected label. A reviewer sees an agent proposal
only when the step sets `show_ai_proposal: true`. A calibration answer never
becomes the record's latest label. Gold is the answer to each item, so a
calibration queue has nothing to adjudicate: its adjudication list, detail
and resolve answer `409 CALIBRATION_QUEUE_NOT_ADJUDICABLE`.

The calibration report scores each reviewer against gold, per field and
pooled. It gives `accuracy`, the share of compared values that match.
`exact_match` is the share of items where every expected field matches.
`cohen_kappa` treats gold as a second rater and comes from the P5b metrics
code. Kappa is used because accuracy rewards guessing the majority label. A
reviewer who always says `refund` on a set that is 80% refunds scores 0.80 on
accuracy and 0 on kappa. Cohen's kappa fits a two-rater comparison: it gives
each rater its own marginals, and a reviewer and the reference are not
interchangeable raters. Krippendorff's alpha and Fleiss' kappa pool the two
raters' marginals. Kappa is undefined when every value is one category, and
the report then gives the reason, as agreement does. A missing value is
counted as missing, not as wrong.

The queue records the version and the hash of the `gold.jsonl` it was made
from. The report scores against the set as it is now and warns when the
version moved, when the file's hash changed under the same version, as a
hand edit to `expected` does, and when the header does not describe the file.

## Later

Inspect's dataset shape (`input`, `target`, `id`, `metadata`) and its
`precomputed_scores` are the next export target. `gold export --format
jsonl` gives the file as it is today.

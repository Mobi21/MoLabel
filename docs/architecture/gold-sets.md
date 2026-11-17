# Gold sets

A gold set is a released eval or training set: records with the labels people
settled on, kept as files in the workspace for the user to commit to git.
Review in progress stays in SQLite. MoLabel writes the files and never runs
git. This note fixes the file layout, the item shape, and the rules for
writes, duplicates and calibration.

## File layout

```
gold/<slug>/gold.yaml    the header
gold/<slug>/gold.jsonl   one item per line
```

`workbench.project.yaml` lists each set under `gold_sets`, with its
`gold_set_id` (the slug) and `definition_path` (the header). The header holds
the slug, `name`, `task_schema` (the task schema's slug, the file-canonical
id), `format_version`, `version`, `item_count`, `content_hash`,
`previous_hash`, `sources`, `created_at` and `updated_at`. `sources` lists each
queue the set took items from, with its workflow execution and workflow slug
when it has one.

One set holds one task schema, because labels are comparable only under one
schema. Promotion from a queue of another schema answers
`GOLD_TASK_SCHEMA_MISMATCH`.

Every write goes through `workspace_files`. It takes the workspace lock, checks
each path with the `workspace_paths` guard, and restores both files if the
write fails. It replaces `gold.jsonl` before `gold.yaml`, so the header's
`content_hash` and `item_count` always describe a file already on disk. A
process killed between the two leaves the previous header beside the new
items, and every read reports that, as below. The header goes through `dump_yaml`, which keeps a person's
comments and key order. Both files are UTF-8 with LF line ends. Items keep the
order they were added in, so an append is lines added at the end. Within an
item the fields keep a fixed order and free-form objects (`input`, `expected`)
have sorted keys. The same content renders to the same bytes on any machine.

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
whenever it reads a file. A hand edit to `input` or `expected` therefore gets
correct hashes on the next write.

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
item. A person settles the conflict by editing `gold.jsonl` or the source
review. `gold dedupe` removes repeated items with the same content, which a
git merge of two appends can leave, and keeps the first. It reports conflicts
and leaves them in place.

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
`adjudicator_took_ai` says whether the adjudicator took an AI proposal's
column, which the resolve request names in `agent_output_ids`, or resolved to
labels equal to a proposal the adjudication screen showed.
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

# Database Migration Strategy

Date: 2026-03-23
Status: Draft
Related: data-model.md, PRD Section 18

## Overview

MoLabel uses SQLite as its operational database and SQLModel as its ORM. Schema migrations are managed by Alembic, the standard migration tool for SQLAlchemy-based projects (SQLModel is built on SQLAlchemy).

## Why Migrations Matter for a Local App

Unlike server-deployed applications where operators control upgrades, MoLabel is a local application that users update independently. This means:
- Users may skip versions (update from v0.1 to v0.5)
- Migrations must be forward-only (no interactive downgrade support needed)
- Migrations must be safe to run on user data (no data loss)
- The app must detect schema version on startup and auto-migrate

## Migration Infrastructure

### File Location
Migration files live at `packages/molabel-core/src/molabel/core/migrations/`

### Alembic Configuration
- There is no `alembic.ini`. `molabel.core.migration_runner` builds the Alembic config in code
- The migration env (`env.py`) reads the SQLModel metadata from the data model definitions
- Migrations are auto-generated from model changes, then reviewed and frozen as explicit DDL. A migration never calls `SQLModel.metadata.create_all`, so it does not drift when the models change
- Each migration has a descriptive name: `001_initial_schema.py`, `002_audit_events.py`, etc.
- Alembic is the only code that creates tables. Routes and bootstrap never run `CREATE TABLE`

### Version Tracking
- Alembic stores the current schema version in the `alembic_version` table of the server database. There is one server database for all workspaces (see `docs/guides/how-molabel-works-today.md` section 4.2)
- On startup, the server runs `upgrade_database`, which is `alembic upgrade head`
- Servers that share a SQLite file migrate it one at a time. Each takes an OS-level lock on `<database>.migrate.lock` beside the file, then re-reads the revision before running anything. The lock file may stay after startup on Linux; it holds no data
- A database created by `create_all` before Alembic owned the schema has tables but no `alembic_version`. It is stamped at `001`, whose DDL is frozen at exactly that schema, and then upgraded
- Before stamping, the server checks that such a database has every table and column that `001` creates. If any are missing, startup stops with an error that lists them, and the database is not changed

## Migration Lifecycle

### Development
1. Developer modifies SQLModel models in `molabel-core`
2. Run `uv run alembic revision --autogenerate -m "description"` to generate migration
3. Review and edit the generated migration (autogenerate is a starting point, not final)
4. Run `uv run alembic upgrade head` to test locally
5. Commit the migration file alongside the model changes

### User Experience
1. User updates MoLabel
2. On next app launch, startup detects schema version mismatch
3. App shows "Updating database..." progress indicator
4. Alembic runs all pending migrations in order
5. If migration succeeds: app starts normally
6. If migration fails: app shows error, preserves the database file, offers to create a backup and retry

### Migration Safety Rules
- Never drop columns that contain user data without a data migration step
- Always add new columns as nullable or with defaults so existing rows are valid
- Never rename tables — create new table, migrate data, drop old table in separate migrations
- Test every migration against a fixture database with realistic data
- Each migration must be idempotent (safe to run twice)

## Backup Strategy
- Before running migrations on a database that has tables, the app creates a backup: `{db_name}.backup.{timestamp}.sqlite`. It is written with SQLite's backup API, so rows still in the WAL file are included
- Backups are kept for 30 days, then cleaned up
- If a migration fails, the user can restore from the backup via the Settings screen

### One-way revisions
Revisions 005 and 006 rewrite ids in place and keep no copy of the old spelling, so they are one-way. Their `downgrade()` changes nothing and logs a warning that says so. To return to the data from before the upgrade, stop the server and restore the backup that `upgrade_database` wrote beside the database before it ran. The backup takes the database file's own name: `<database name>.backup.<timestamp>.sqlite`, so `molabel.backup.<timestamp>.sqlite` for the default `molabel.db`, and `custom-name.backup.<timestamp>.sqlite` for a database set through `MOLABEL_DB_URL` as `custom-name.db`.

## Multi-Skip Upgrades
- Alembic handles multi-version jumps natively (runs all pending migrations in sequence)
- Each migration declares its dependency chain via Alembic's revision graph
- No migration may assume the previous migration was the one immediately before it — always check state, don't assume

## Schema Version in Workspace Manifest
- The workspace manifest (`workbench.project.yaml`) includes `core_version` which indicates the expected schema version
- If a workspace manifest declares a newer `core_version` than the installed app, the app warns: "This workspace was created with a newer version of MoLabel"

## Ids inside JSON and text columns

Revision 005 rewrote every UUID column to the hyphenated form. A row's id is also copied into JSON and text columns, in the spelling the writer read. Revision 006 rewrites those copies. It rewrites a value only at a position that `ID_POSITIONS` or `TEXT_ID_COLUMNS` in `006_hyphenated_json_ids.py` lists, and only when the value is 32 hex characters, so a hash beside an id is never read. A reader that looks up an id it read from JSON passes the id through `molabel.core.database.hyphenated_id` first, so a hex id that 006 does not reach still matches.

These columns hold ids of rows whose primary key is a UUID:

| Column | Ids it holds | Rewritten by 006 | Looked up by | Reader |
|---|---|---|---|---|
| `workflow_executions.context` | Workspace, execution, dataset, record, agent run, export bundle and snapshot ids, and the ids in each step summary | Yes | The exporter, agent runner, review queue and agreement source of a resumed workflow | `hyphenated_id` |
| `workflow_step_executions.result` | The ids in the step summary | Yes | Nothing | None |
| `review_tasks.agent_output_ids` | Agent output ids | Yes | Adjudication detail, the queue agreement report, CLI queue operations | Parses each id as a UUID |
| `adjudications.conflicting_event_ids` | Review event ids | Yes | The check that a disagreement is resolved | `hyphenated_id` |
| `adjudications.metadata` | `review_event_id` | Yes | Nothing | None |
| `dataset_snapshots.dataset_membership` | Record ids, as the keys of `record_states` | Yes | Both snapshot restores | `hyphenated_id` |
| `saved_views.filters` | `dataset_id`, `parent_subset_id`, and the include and exclude record ids | Yes | `DerivedSubsetService` | Parses each id as a UUID |
| `datasets.source_config` | `source_dataset_id`, `source_subset_id` | Yes | Nothing | None |
| `agent_events.payload` | Workspace, dataset, task schema, model profile and record ids | Yes | Nothing | None |
| `audit_events.workspace_id`, `actor`, `object_id` | Workspace, reviewer, and release or artifact proposal ids, as text columns | Yes | The audit lists, by workspace and by object | None |
| `workflow_definitions.steps`, `workflow_step_executions.step_config`, `agent_runs.config` | Dataset, task schema and model profile ids in step config | No. They copy the workflow file, and the file wins over the row | Ingest, the task schema selector, the model lookup | `hyphenated_id` in the loader and the task schema selector. The agent step and the model lookup already parse ids as UUIDs |
| `task_schemas.record_selector` | `dataset_ids` | No. It copies the task schema file | Nothing | None |
| `releases.export_bundle_ids`, `releases.release_metadata` | The export ids a release names, and the ids in its proof manifest | No. They repeat the release's `proof-manifest.json` | Nothing | None |
| `audit_events.details` | Ids as each request named them | No. It records the request | Nothing | None |

These columns look like id containers but are not:

- `releases.validation_run_ids` holds validation gate names.
- `review_tasks.queue_id` and the context's `review_queue_ids` and `adjudication_queue_ids` hold queue ids, which name no row.
- No code writes `agent_runs.record_filter`, `audit_entries`, `correction_batches`, `export_bundles` or `validation_runs.gates`.
- `records.content_hash`, `artifacts.file_hash`, `export_bundles.file_hash` and `audit_entries.file_hash_before` and `file_hash_after` hold hashes.

### A hash in a UUID column is rewritten too

Revision 005 rewrites every 32-hex value in a UUID column. A 32-hex hash stored in a UUID column would come out hyphenated. Its 128 bits stay the same and `uuid.UUID` reads both forms, but a reader that compares the text with the original hash would no longer match it. No model stores a hash in a UUID column.

## Testing
- Fixture schemas at known versions are stored in `fixtures/migrations/`. `pre-alembic-create-all.sql` is the schema `create_all` produced before Alembic owned it
- `tests/integration/test_schema_migrations.py` starts the server on a fresh database and on each fixture, and checks that the result is at head and that autogenerate finds no difference from the models. A model change without a matching migration fails it
- `tests/integration/test_schema_migrations.py` also downgrades a database at head to `004` and checks that 006 and 005 each log the one-way warning
- `tests/integration/test_json_id_migration.py` runs revision 006 on each container above and resumes a paused workflow on a database written before 005

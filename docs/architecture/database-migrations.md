# Database Migration Strategy

Date: 2026-03-23
Status: Draft
Related: data-model.md, PRD Section 18

## Overview

MoLabel uses SQLite as its operational database and SQLModel as its ORM. Schema migrations are managed by Alembic, the standard migration tool for SQLAlchemy-based projects (SQLModel is built on SQLAlchemy).

## Why Migrations Matter for a Desktop App

Unlike server-deployed applications where operators control upgrades, MoLabel is a desktop application where users update independently. This means:
- Users may skip versions (update from v0.1 to v0.5)
- Migrations must be forward-only (no interactive downgrade support needed)
- Migrations must be safe to run on user data (no data loss)
- The app must detect schema version on startup and auto-migrate

## Migration Infrastructure

### File Location
Migration files live at `packages/molabel-core/src/molabel/core/migrations/`

### Alembic Configuration
- `alembic.ini` is generated at workspace bootstrap time (not shipped in the repo)
- The migration env (`env.py`) reads the SQLModel metadata from the data model definitions
- Migrations are auto-generated from model changes using `alembic revision --autogenerate`
- Each migration has a descriptive name: `001_initial_schema.py`, `002_add_workflow_tables.py`, etc.

### Version Tracking
- Alembic stores the current schema version in the `alembic_version` table within each workspace's SQLite database
- On app startup, the system checks whether the database schema is current
- If behind, the app runs pending migrations before proceeding

## Migration Lifecycle

### Development
1. Developer modifies SQLModel models in `molabel-core`
2. Run `uv run alembic revision --autogenerate -m "description"` to generate migration
3. Review and edit the generated migration (autogenerate is a starting point, not final)
4. Run `uv run alembic upgrade head` to test locally
5. Commit the migration file alongside the model changes

### User Experience
1. User updates MoLabel (Tauri auto-update or manual)
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
- Before running migrations, the app creates a backup: `{db_name}.backup.{timestamp}.sqlite`
- Backups are kept for 30 days, then cleaned up
- If a migration fails, the user can restore from the backup via the Settings screen

## Multi-Skip Upgrades
- Alembic handles multi-version jumps natively (runs all pending migrations in sequence)
- Each migration declares its dependency chain via Alembic's revision graph
- No migration may assume the previous migration was the one immediately before it — always check state, don't assume

## Schema Version in Workspace Manifest
- The workspace manifest (`workbench.project.yaml`) includes `core_version` which indicates the expected schema version
- If a workspace manifest declares a newer `core_version` than the installed app, the app warns: "This workspace was created with a newer version of MoLabel"

## Testing
- Fixture databases at known schema versions are stored in `fixtures/migrations/`
- CI runs upgrade tests: start from each fixture version, migrate to head, verify data integrity
- The migration test suite is part of `tests/integration/migrations/`

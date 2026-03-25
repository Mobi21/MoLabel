"""Alembic migration environment for MoLabel.

This module is configured programmatically — no alembic.ini is needed.
The migration runner (``molabel.core.migration_runner``) sets the engine
URL before invoking Alembic commands.
"""

from __future__ import annotations

from alembic import context
from sqlmodel import SQLModel

# Import all models so their tables are registered on SQLModel.metadata.
import molabel.core.models  # noqa: F401

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with just a URL and not an Engine.
    Calls to ``context.execute()`` emit the given SQL string to the
    script output.
    """
    url = context.config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # required for SQLite ALTER TABLE support
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    The connectable is provided by the migration runner via
    ``context.configure(connection=...)``.  If not present, fall back
    to creating one from the config URL.
    """
    connectable = context.config.attributes.get("connection", None)

    if connectable is not None:
        # Connection was passed in by the migration runner.
        context.configure(
            connection=connectable,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    else:
        # Standalone Alembic CLI usage — create engine from URL.
        from sqlalchemy import engine_from_config, pool

        config = context.config
        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                render_as_batch=True,
            )
            with context.begin_transaction():
                context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

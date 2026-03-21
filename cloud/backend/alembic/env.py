"""Alembic environment configuration for Plutus cloud backend.

Uses async engine (asyncpg) and imports all models so autogenerate
can detect schema changes.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.models.agent_state import AgentState, Memory, ScheduledTask, Skill  # noqa: F401

# ── Import all models so Base.metadata contains every table ──────────
from app.models.base import Base
from app.models.conversation import Conversation, Message  # noqa: F401
from app.models.plan import Plan  # noqa: F401
from app.models.sync_log import SyncLog  # noqa: F401
from app.models.user import User  # noqa: F401

# ── Alembic Config object ───────────────────────────────────────────
config = context.config

# Override the sqlalchemy.url from app settings so the single source of
# truth is always app/config.py (and .env), not alembic.ini.
try:
    from app.config import settings

    config.set_main_option("sqlalchemy.url", settings.database_url)
except Exception:
    pass  # Fall back to alembic.ini value if app config is unavailable

# Set up Python logging from the alembic.ini [loggers] section.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# MetaData target for 'autogenerate' support.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emits SQL to stdout."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    """Synchronous callback executed inside the async connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode — connects to the database."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

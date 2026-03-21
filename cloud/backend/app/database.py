import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.base import Base  # noqa: F401 — imported so metadata is populated

logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_size=20,
    max_overflow=10,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncSession:
    """Dependency for FastAPI routes."""
    async with async_session_factory() as session:
        yield session


async def init_db():
    """Run Alembic migrations to bring the database schema up to date.

    Using ``alembic upgrade head`` ensures that every migration is applied
    in order, including migrations added after the initial deployment (e.g.
    the ``plans`` table added in revision 002).  The old ``create_all``
    approach was skipped silently for tables that already existed and did not
    apply incremental migrations at all.
    """
    import asyncio
    from pathlib import Path

    try:
        # Run alembic upgrade head in a subprocess so we don't have to deal
        # with the synchronous Alembic API inside an async context.
        alembic_ini = Path(__file__).parent.parent / "alembic.ini"
        proc = await asyncio.create_subprocess_exec(
            "alembic",
            "-c",
            str(alembic_ini),
            "upgrade",
            "head",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(alembic_ini.parent),
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            logger.info("Database migrations applied successfully:\n%s", stdout.decode())
        else:
            logger.error(
                "Alembic migration failed (rc=%d):\n%s\n%s",
                proc.returncode,
                stdout.decode(),
                stderr.decode(),
            )
    except Exception as exc:
        logger.error("Failed to run database migrations: %s", exc, exc_info=True)


async def close_db():
    """Close the engine."""
    await engine.dispose()

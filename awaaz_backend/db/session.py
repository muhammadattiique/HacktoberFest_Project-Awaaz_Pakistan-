from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from config import settings
from db.models import Base

# Create async engine for SQLite (using aiosqlite)
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
)

# Async session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


async def _ensure_submission_id_column(conn) -> None:
    """Idempotently add the additive ``submission_id`` column + index on SQLite.

    ``create_all`` creates missing tables but never alters an existing one, so a
    pre-existing ``awaaz.db`` would keep the old schema. This is the project's
    only migration (no Alembic). It is safe to run on a fresh DB, an already
    migrated DB, and across restarts.
    """
    result = await conn.exec_driver_sql('PRAGMA table_info("complaints")')
    cols = {row[1] for row in result.fetchall()}
    if "submission_id" not in cols:
        await conn.exec_driver_sql(
            'ALTER TABLE complaints ADD COLUMN submission_id VARCHAR(36)'
        )
        await conn.exec_driver_sql(
            'CREATE INDEX IF NOT EXISTS ix_complaints_submission_id ON complaints (submission_id)'
        )


async def init_db() -> None:
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Additive, idempotent migration for SQLite (no Alembic in this project).
        if "sqlite" in settings.DATABASE_URL:
            await _ensure_submission_id_column(conn)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for providing database sessions to FastAPI routes."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


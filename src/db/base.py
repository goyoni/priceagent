"""SQLAlchemy base configuration for async operations with PostgreSQL/SQLite support."""

from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

# Global instances
_engine: Optional[AsyncEngine] = None
_async_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


def get_database_url(db_path: Optional[Path] = None) -> str:
    """Get the database URL from settings or construct SQLite URL.

    Args:
        db_path: Optional path for SQLite database (ignored if DATABASE_URL is set)

    Returns:
        Database URL string
    """
    from src.config.settings import settings

    # Use PostgreSQL if DATABASE_URL is configured
    if settings.database_url:
        url = settings.database_url
        # Convert postgres:// to postgresql+asyncpg:// for async support
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    # Fall back to SQLite
    if db_path is None:
        db_path = settings.database_path

    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+aiosqlite:///{db_path}"


def get_engine(db_path: Optional[Path] = None) -> AsyncEngine:
    """Get or create the async engine.

    Args:
        db_path: Path to SQLite database file (ignored if DATABASE_URL is set)

    Returns:
        AsyncEngine instance
    """
    global _engine

    if _engine is None:
        database_url = get_database_url(db_path)

        # Use NullPool for PostgreSQL in production to avoid connection issues
        # SQLite doesn't support connection pooling the same way
        is_postgres = "postgresql" in database_url

        engine_kwargs = {
            "echo": False,
            "future": True,
        }

        if is_postgres:
            # For PostgreSQL: use NullPool to avoid connection pool exhaustion
            # in serverless/container environments
            engine_kwargs["poolclass"] = NullPool

        _engine = create_async_engine(database_url, **engine_kwargs)

    return _engine


def get_async_session_factory(
    engine: Optional[AsyncEngine] = None,
) -> async_sessionmaker[AsyncSession]:
    """Get or create the async session factory.

    Args:
        engine: Optional engine to use. If None, uses default.

    Returns:
        Async session factory
    """
    global _async_session_factory

    if _async_session_factory is None:
        if engine is None:
            engine = get_engine()

        _async_session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    return _async_session_factory


async def init_db(db_path: Optional[Path] = None) -> None:
    """Initialize the database, creating all tables.

    Args:
        db_path: Path to SQLite database file (ignored if DATABASE_URL is set)
    """
    engine = get_engine(db_path)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def reset_engine() -> None:
    """Reset the global engine and session factory.

    Useful for testing or when database configuration changes.
    """
    global _engine, _async_session_factory
    _engine = None
    _async_session_factory = None

"""SQLAlchemy base configuration for async operations."""

from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

# Global instances
_engine: Optional[AsyncEngine] = None
_async_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


def get_engine(db_path: Optional[Path] = None) -> AsyncEngine:
    """Get or create the async engine.

    Args:
        db_path: Path to SQLite database file. If None, uses default.

    Returns:
        AsyncEngine instance
    """
    global _engine

    if _engine is None:
        if db_path is None:
            db_path = Path("data/negotiations.db")

        db_path.parent.mkdir(parents=True, exist_ok=True)

        database_url = f"sqlite+aiosqlite:///{db_path}"

        _engine = create_async_engine(
            database_url,
            echo=False,
            future=True,
        )

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
        db_path: Path to SQLite database file
    """
    engine = get_engine(db_path)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

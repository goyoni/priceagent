"""Async session management for SQLAlchemy."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from .base import get_async_session_factory


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get an async database session.

    Usage:
        async with get_db_session() as session:
            result = await session.execute(...)

    Yields:
        AsyncSession instance
    """
    session_factory = get_async_session_factory()
    session = session_factory()

    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()

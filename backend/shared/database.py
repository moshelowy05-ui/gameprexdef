from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from sqlalchemy.orm import DeclarativeBase

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker as AsyncSessionMaker


class Base(DeclarativeBase):
    pass


_engine: "AsyncEngine | None" = None
_session_factory: "AsyncSessionMaker | None" = None


def _get_engine() -> "AsyncEngine":
    global _engine
    if _engine is None:
        from sqlalchemy.ext.asyncio import create_async_engine
        from .config import settings
        _engine = create_async_engine(
            settings.database_url,
            echo=False,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
        )
    return _engine


def _get_session_factory() -> "AsyncSessionMaker":
    global _session_factory
    if _session_factory is None:
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        _session_factory = async_sessionmaker(
            _get_engine(), class_=AsyncSession, expire_on_commit=False
        )
    return _session_factory


def async_session_factory() -> "AsyncSession":
    """Return a new async session context manager."""
    return _get_session_factory()()


async def get_db() -> AsyncGenerator["AsyncSession", None]:
    async with _get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

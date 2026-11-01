"""Database engine, declarative base, and async session management."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy ORM models."""


settings = get_settings()

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    future=True,
)

async_session_maker: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

_worker_session_factory: async_sessionmaker[AsyncSession] | None = None


def set_worker_session_factory(
    factory: async_sessionmaker[AsyncSession] | None,
) -> None:
    """Configure a custom session factory for background worker tasks and tests."""
    global _worker_session_factory
    _worker_session_factory = factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional async database session for FastAPI endpoints."""
    async with async_session_maker() as session:
        yield session


@asynccontextmanager
async def get_worker_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated async session for Celery worker tasks."""
    if _worker_session_factory is not None:
        async with _worker_session_factory() as session:
            yield session
        return

    worker_engine = create_async_engine(
        get_settings().database_url,
        poolclass=pool.NullPool,
        future=True,
    )
    session_factory = async_sessionmaker(
        bind=worker_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    try:
        async with session_factory() as session:
            yield session
    finally:
        await worker_engine.dispose()

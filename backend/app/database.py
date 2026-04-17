"""
Database connection and session management
"""

import asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool
from contextlib import asynccontextmanager

from app.config import settings


# Convert postgresql:// to postgresql+asyncpg:// for async driver
def get_async_database_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://")
    return url


# Async engine for PostgreSQL
async_engine = create_async_engine(
    get_async_database_url(settings.database_url),
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    echo=settings.debug,
    pool_pre_ping=True,
)

# Async session factory
async_session_factory = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Base class for models
Base = declarative_base()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting async database session"""
    session = async_session_factory()
    try:
        yield session
    finally:
        await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncSession:
    """Context manager for database session"""
    session = async_session_factory()
    try:
        yield session
    finally:
        await session.close()


async def init_database():
    """Initialize database tables"""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_database():
    """Close database connections"""
    await async_engine.dispose()
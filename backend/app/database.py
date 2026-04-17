"""
Database connection and session management - 等保三增强版
"""

import asyncio
from typing import AsyncGenerator, Generator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base, Session, sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from contextlib import asynccontextmanager, contextmanager

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

# Sync engine for security services (等保三)
sync_engine = create_engine(
    settings.database_url,
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

# Sync session factory (等保三)
sync_session_factory = sessionmaker(
    bind=sync_engine,
    class_=Session,
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


def get_db_sync() -> Generator[Session, None, None]:
    """Dependency for getting sync database session (等保三安全服务)"""
    session = sync_session_factory()
    try:
        yield session
    finally:
        session.close()


@asynccontextmanager
async def get_db_context() -> AsyncSession:
    """Context manager for database session"""
    session = async_session_factory()
    try:
        yield session
    finally:
        await session.close()


@contextmanager
def get_db_sync_context() -> Session:
    """Context manager for sync database session"""
    session = sync_session_factory()
    try:
        yield session
    finally:
        session.close()


async def init_database():
    """Initialize database tables"""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_database():
    """Close database connections"""
    await async_engine.dispose()
    sync_engine.dispose()
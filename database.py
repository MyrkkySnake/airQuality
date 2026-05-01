"""
Database engine, session factory, and Base for SQLAlchemy models.
Supports both SQLite (dev) and PostgreSQL (production).
"""

import logging
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Engine & Session
# ---------------------------------------------------------------------------

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DB_ECHO,           # Set True for SQL query logging in dev
    pool_pre_ping=True,              # Reconnect dropped connections
    pool_size=10,                    # Max persistent connections
    max_overflow=20,                 # Extra connections under load
)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,          # Avoid lazy-load errors after commit
    autocommit=False,
    autoflush=False,
)

Base = declarative_base()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def init_db() -> None:
    """Create all tables on startup (idempotent)."""
    async with engine.begin() as conn:
        # Import models so Base.metadata knows about them
        from db import models  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created / verified.")


async def get_db() -> AsyncSession:
    """FastAPI dependency: yield a DB session, close it after request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def db_session():
    """Context manager for use outside FastAPI (e.g., bot handlers)."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

"""
Synchronous database session for Celery workers.
Celery workers are NOT async — using asyncpg/AsyncSession inside them
via "new event loop per task" is unreliable and causes silent failures.
This module gives Celery tasks a plain sync SQLAlchemy session instead.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings

# Convert async DSN (postgresql+asyncpg://) to sync DSN (postgresql+psycopg2://)
_sync_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg2")

sync_engine = create_engine(_sync_url, pool_pre_ping=True, pool_size=5, max_overflow=10)
SyncSessionLocal = sessionmaker(bind=sync_engine, autoflush=False, autocommit=False)


def get_sync_db():
    """Context-manager style session for use inside Celery tasks."""
    return SyncSessionLocal()

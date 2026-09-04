"""Engine / session setup.

Reads DATABASE_URL from app.core.config.settings, not a hardcoded string --
Alembic's env.py (backend/alembic/env.py) imports the same settings object
so migrations and the running app can never point at different databases by
accident.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency -- yields a session, closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

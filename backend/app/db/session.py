"""Engine / session setup.

Reads settings.runtime_database_url (local Docker Postgres by default,
Supabase's pooled connection when SUPABASE_DATABASE_URL is set) from
app.core.config.settings, never a hardcoded string. Alembic's env.py
(backend/alembic/env.py) reads the *migration* URL from the same settings
object instead -- see its module docstring for why that's a different URL
than this one.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings

_engine_kwargs: dict = {"connect_args": {"connect_timeout": 5}}

if settings.is_pooled_connection:
    # Supabase's Transaction pooler (pgbouncer, transaction mode) can hand a
    # different backend Postgres connection to every transaction, so nothing
    # that assumes a stable server-side session across statements is safe
    # here. Two concrete tweaks for that, both scoped to this pooled engine
    # only (the local Docker / Supabase-direct engine keeps SQLAlchemy's
    # normal defaults, since neither sits behind a transaction-mode pooler):
    #
    # - query_cache_size=0: disables SQLAlchemy's own compiled-statement
    #   cache. That cache's assumptions (e.g. reusing a prepared plan across
    #   calls) can silently misbehave when the "server" behind a given
    #   connection checkout isn't actually the same backend process each
    #   time, which is exactly pgbouncer transaction mode's behavior.
    # - poolclass=NullPool: pgbouncer is already doing connection pooling in
    #   front of this app. Layering SQLAlchemy's own QueuePool on top would
    #   just hold pgbouncer connection slots open and idle between requests
    #   instead of returning them to the pool, defeating the point of using
    #   a pooler in the first place (this is Supabase's own documented
    #   recommendation for SQLAlchemy + the Transaction pooler).
    _engine_kwargs["query_cache_size"] = 0
    _engine_kwargs["poolclass"] = NullPool

engine = create_engine(settings.runtime_database_url, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency -- yields a session, closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

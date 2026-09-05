"""Env-driven backend configuration.

Also resolves the repo root (by walking up for the CLAUDE.md marker, the same
pattern every ml/notebooks/*.ipynb and ml/tests/*.py use) and puts ml/src/ on
sys.path so app/ml/*.py can `import preprocessing` / `import split` directly
instead of duplicating that logic in the backend. This cross-directory import
is a bit awkward (see the forward-note in CLAUDE.md) but avoids a real
duplication risk between training and serving feature code.
"""

from __future__ import annotations

import sys
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_repo_root(start: Path) -> Path:
    for parent in [start, *start.parents]:
        if (parent / "CLAUDE.md").exists():
            return parent
    raise FileNotFoundError("Could not locate repo root (looked for CLAUDE.md)")


REPO_ROOT = _find_repo_root(Path(__file__).resolve())
ML_SRC_DIR = REPO_ROOT / "ml" / "src"

if str(ML_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(ML_SRC_DIR))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FRAUD_", env_file=".env", extra="ignore")

    log_level: str = "INFO"

    model_path: Path = REPO_ROOT / "ml" / "models" / "xgboost_model.pkl"
    model_metadata_path: Path = REPO_ROOT / "ml" / "models" / "model_metadata.json"
    # No separate "explainer path" setting: the SHAP explainer is reconstructed fresh from
    # the loaded model at startup (see app/ml/explainer.py), never unpickled from disk.
    isolation_forest_path: Path = REPO_ROOT / "ml" / "models" / "isolation_forest.pkl"

    # Default points at the local Docker Compose Postgres service (see
    # docker-compose.yml / SETUP.md for the connection-string convention).
    # This is the fallback used whenever the Supabase variables below are
    # unset -- local dev must never silently depend on Supabase being
    # reachable, so this default has to work with zero .env configuration.
    database_url: str = "postgresql://fraud:fraud@localhost:5432/fraud_detection"

    # Supabase (public demo deploy target) connection strings -- deliberately
    # read via a raw validation_alias rather than the FRAUD_ prefix every
    # other setting uses, since these names also need to be recognizable as
    # plain SUPABASE_* env vars when set directly on a hosting platform
    # (Render/Railway), not just inside this app's own .env convention.
    # `None` by default: local dev (see database_url above) never depends on
    # either of these existing.
    #
    # - supabase_database_url: the **pooled** (pgbouncer, transaction mode,
    #   port 6543) connection string -- used for the app's normal runtime
    #   queries (see runtime_database_url below).
    # - supabase_direct_url: the **direct**, non-pooled (port 5432) connection
    #   string -- used only for running Alembic migrations (see
    #   migration_database_url below), since DDL/migrations don't play well
    #   through a transaction-mode pooler (schema-change statements can span
    #   more session state than a single pooled transaction guarantees).
    supabase_database_url: str | None = Field(default=None, validation_alias="SUPABASE_DATABASE_URL")
    supabase_direct_url: str | None = Field(default=None, validation_alias="SUPABASE_DIRECT_URL")

    @property
    def runtime_database_url(self) -> str:
        """What app/db/session.py's engine actually connects to."""
        return self.supabase_database_url or self.database_url

    @property
    def migration_database_url(self) -> str:
        """What alembic/env.py actually connects to."""
        return self.supabase_direct_url or self.database_url

    @property
    def is_pooled_connection(self) -> bool:
        """True only for the Supabase transaction-pooler runtime connection --
        never true for the local Docker default or the Supabase direct URL,
        both of which are ordinary un-pooled Postgres connections."""
        return self.supabase_database_url is not None


settings = Settings()

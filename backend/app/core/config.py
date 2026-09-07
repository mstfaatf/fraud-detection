"""Env-driven backend configuration.

Also resolves the repo root (by walking up for a .git directory or the
.repo-root marker file, the same pattern ml/src/serialize_isolation_forest.py
and every ml/notebooks/*.ipynb use) and puts ml/src/ on sys.path so
app/ml/*.py can `import preprocessing` / `import split` directly instead of
duplicating that logic in the backend. This cross-directory import is a bit
awkward but avoids a real duplication risk between training and serving
feature code.

Previously this walked up looking for CLAUDE.md specifically, which broke
production once when CLAUDE.md was briefly untracked from git. CLAUDE.md is
an internal decision log with no guarantee of staying tracked or present in
every build environment, so it's a bad proxy for "this is the repo root."
.git and .repo-root are both checked: .git exists in a real git clone, which
covers local dev and most likely Render's build environment too (Render's
own docs don't explicitly confirm this either way, and this project has no
way to inspect Render's build filesystem directly to verify it), but .git is
deliberately excluded from the local Docker Compose build context (see
backend/Dockerfile.dockerignore's `.git/` entry) for build-context size and
hygiene reasons, so it can't be the only marker this relies on. .repo-root
(an empty file, always git-tracked, never gitignored, explicitly COPY'd into
the Docker image) is the one marker guaranteed present in every environment
this app actually runs in, and is what backend/Dockerfile relies on.
"""

from __future__ import annotations

import sys
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_repo_root(start: Path) -> Path:
    for parent in [start, *start.parents]:
        if (parent / ".git").exists() or (parent / ".repo-root").exists():
            return parent
    raise FileNotFoundError("Could not locate repo root (looked for .git or .repo-root)")


REPO_ROOT = _find_repo_root(Path(__file__).resolve())
ML_SRC_DIR = REPO_ROOT / "ml" / "src"

if str(ML_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(ML_SRC_DIR))


class Settings(BaseSettings):
    # env_file is REPO_ROOT / ".env", not the literal relative string ".env"
    # -- a real bug found and fixed in Phase 9 part 2's live Stripe webhook
    # verification: pydantic-settings resolves a relative env_file against the
    # process's cwd at Settings() instantiation time, not against this file's
    # own directory. SETUP.md's/CLAUDE.md's documented dev workflow runs the
    # backend as `uvicorn app.main:app --reload` from backend/ as cwd, so the
    # relative ".env" was silently resolving to backend/.env (which has never
    # existed) instead of the real repo-root .env -- meaning every setting
    # that depends on .env and has no safe hardcoded default (Supabase's
    # variables, frontend_origin, and now the Stripe keys) silently read as
    # unset whenever the backend was started exactly the way the docs say to.
    # Anchoring to REPO_ROOT (already resolved above for ml/src/) makes this
    # correct regardless of cwd.
    model_config = SettingsConfigDict(
        env_prefix="FRAUD_", env_file=str(REPO_ROOT / ".env"), extra="ignore"
    )

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

    # CORS (see main.py) -- the exact production Vercel origin, e.g.
    # "https://fraud-detection.vercel.app". `None` locally, where main.py's
    # hardcoded localhost origins already cover dev. Read via a raw
    # validation_alias for the same reason as the two Supabase URLs above:
    # recognizable as a plain FRONTEND_ORIGIN platform env var on Render, not
    # just inside this app's FRAUD_-prefixed convention.
    frontend_origin: str | None = Field(default=None, validation_alias="FRONTEND_ORIGIN")

    # Per-IP request cap for POST /predict (see main.py's slowapi limiter),
    # in slowapi's "N/period" string format. Overridable so the demo-scale
    # default can be loosened/tightened without a code change.
    predict_rate_limit: str = Field(default="20/minute", validation_alias="PREDICT_RATE_LIMIT")

    # Stripe test-mode integration (see app/services/stripe_adapter.py). Read via
    # raw validation_alias, same convention as the Supabase/frontend_origin
    # settings above, so these read identically whether set in this project's
    # .env or as a literal platform env var on a host. All `None` by default --
    # local dev without Stripe configured never breaks, since nothing outside
    # stripe_adapter.py touches these, and stripe_adapter.py's own pure mapping
    # function (map_payment_intent_to_transaction_input) doesn't need them
    # either -- only the real-API helpers (get_or_create_demo_customer) do.
    # stripe_webhook_secret is unused for now -- no webhook endpoint exists yet
    # (out of scope for this pass, see CLAUDE.md), included here so it's ready
    # for that phase without a second config change.
    stripe_secret_key: str | None = Field(default=None, validation_alias="STRIPE_SECRET_KEY")
    stripe_publishable_key: str | None = Field(default=None, validation_alias="STRIPE_PUBLISHABLE_KEY")
    stripe_webhook_secret: str | None = Field(default=None, validation_alias="STRIPE_WEBHOOK_SECRET")

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

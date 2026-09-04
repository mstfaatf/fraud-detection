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
    # Override with FRAUD_DATABASE_URL for Supabase or any other target --
    # not hardcoded anywhere else in the app (app/db/session.py and
    # alembic/env.py both read it from here).
    database_url: str = "postgresql://fraud:fraud@localhost:5432/fraud_detection"


settings = Settings()

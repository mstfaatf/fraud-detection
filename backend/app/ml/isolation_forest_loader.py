"""Loads the Isolation Forest anomaly-detection model at app startup.

ml/notebooks/07_isolation_forest.ipynb (Phase 4 part 2) was exploratory/
evaluative only, per its documented scope, and never pickled its trained
model. ml/models/isolation_forest.pkl is produced separately by
ml/src/serialize_isolation_forest.py, which retrains it with the exact same
hyperparameters, split, and feature pipeline the notebook used (see that
script's docstring), so this loader has an artifact to read.

Same fail-loudly contract as model_loader.py: called once at startup, never
per-request, and raises rather than letting the app start with no anomaly
model behind it.
"""

from __future__ import annotations

import pickle
from typing import Any

from app.core.config import Settings


class IsolationForestLoadError(RuntimeError):
    """Raised when the Isolation Forest model can't be loaded."""


def load_isolation_forest(settings: Settings) -> Any:
    if not settings.isolation_forest_path.exists():
        raise IsolationForestLoadError(
            f"Isolation Forest model not found at {settings.isolation_forest_path} -- run "
            "ml/src/serialize_isolation_forest.py to generate it."
        )

    try:
        with open(settings.isolation_forest_path, "rb") as f:
            return pickle.load(f)
    except Exception as exc:
        raise IsolationForestLoadError(
            f"Failed to unpickle Isolation Forest model at {settings.isolation_forest_path}: {exc}"
        ) from exc

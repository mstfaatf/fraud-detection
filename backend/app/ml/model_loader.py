"""Loads the trained XGBoost model + its metadata at app startup.

Called once from main.py's lifespan handler, never per-request. Fails loudly
(raises ModelLoadError) if either file is missing or fails to load -- the app
must not start up and silently serve traffic with no model behind it.
"""

from __future__ import annotations

import json
import pickle
from typing import Any

from app.core.config import Settings


class ModelLoadError(RuntimeError):
    """Raised when the XGBoost model or its metadata can't be loaded."""


def load_model(settings: Settings) -> tuple[Any, dict]:
    if not settings.model_path.exists():
        raise ModelLoadError(
            f"XGBoost model not found at {settings.model_path} -- run the Phase 3/4 "
            "training notebooks (ml/notebooks/) to generate it."
        )
    if not settings.model_metadata_path.exists():
        raise ModelLoadError(f"Model metadata not found at {settings.model_metadata_path}")

    try:
        with open(settings.model_path, "rb") as f:
            model = pickle.load(f)
    except Exception as exc:
        raise ModelLoadError(f"Failed to unpickle XGBoost model at {settings.model_path}: {exc}") from exc

    try:
        with open(settings.model_metadata_path) as f:
            metadata = json.load(f)
    except Exception as exc:
        raise ModelLoadError(f"Failed to read model metadata at {settings.model_metadata_path}: {exc}") from exc

    # app/core/config.py puts ml/src/ on sys.path for exactly this kind of import.
    from preprocessing import FEATURE_COLUMNS

    if metadata.get("feature_columns") != FEATURE_COLUMNS:
        raise ModelLoadError(
            "model_metadata.json's feature_columns no longer matches ml/src/preprocessing.py's "
            "FEATURE_COLUMNS -- the serialized model and the current preprocessing pipeline have "
            "drifted apart. Retrain/reserialize the model or update preprocessing.py."
        )

    return model, metadata

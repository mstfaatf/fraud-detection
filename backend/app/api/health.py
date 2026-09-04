"""GET /health -- reflects real ML-layer load status, not just a static 200."""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()

_ML_STATE_ATTRS = ("xgb_model", "shap_explainer", "isolation_forest")


@router.get("/health")
def health(request: Request) -> dict:
    model_loaded = all(getattr(request.app.state, attr, None) is not None for attr in _ML_STATE_ATTRS)
    return {"status": "ok", "model_loaded": model_loaded}

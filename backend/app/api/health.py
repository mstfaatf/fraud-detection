"""GET /health -- reflects real ML-layer load status and real DB
reachability, not just a static 200. The two are reported separately: the ML
layer and the database are independent dependencies (a scoring request only
needs the DB for persistence, per prediction_service._persist_prediction's
"still return the prediction even if the DB write fails" behavior), so
folding them into one boolean would hide which one is actually down.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import text

from app.db.session import SessionLocal

router = APIRouter()

_ML_STATE_ATTRS = ("xgb_model", "shap_explainer", "isolation_forest")


def _check_db_connected() -> bool:
    """A cheap, real round-trip -- not just "did the engine object get
    constructed". Uses the same connect_timeout configured on the engine
    (see app/db/session.py) so an unreachable DB fails fast instead of
    hanging the health check."""
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
        return True
    except Exception:
        return False


@router.get("/health")
def health(request: Request) -> dict:
    model_loaded = all(getattr(request.app.state, attr, None) is not None for attr in _ML_STATE_ATTRS)
    return {"status": "ok", "model_loaded": model_loaded, "db_connected": _check_db_connected()}

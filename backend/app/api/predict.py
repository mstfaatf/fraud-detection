"""POST /predict -- real-time single-transaction fraud scoring.

Runs the incoming transaction through the same preprocessing used at
training time, scores it with the XGBoost model loaded once at startup,
attaches a secondary (never blended) Isolation Forest anomaly signal,
explains the score with SHAP, and persists the transaction + prediction
(see prediction_service._persist_prediction for the sync-write / DB-failure
handling reasoning -- this route just supplies the request-scoped db
session via the get_db dependency).

Explainer reuse note: `app.state.shap_explainer` is the TreeExplainer built
once in main.py's lifespan handler, not reconstructed per-request. There's
nothing request-specific about the explainer itself (only the row being
explained), so rebuilding it from the booster on every call would be pure
added latency for zero benefit -- explaining a single row is fast, but
repeatedly reconstructing the explainer around it would not be.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.limiter import limiter
from app.db.session import get_db
from app.schemas.prediction import PredictionResponse, TransactionInput
from app.services.prediction_service import predict_transaction

router = APIRouter()

_REQUIRED_STATE_ATTRS = ("xgb_model", "model_metadata", "shap_explainer", "isolation_forest")


@router.post("/predict", response_model=PredictionResponse)
@limiter.limit(settings.predict_rate_limit)
def predict(
    payload: TransactionInput,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> PredictionResponse:
    # `response: Response` isn't used directly here -- it's required so
    # slowapi's limiter decorator (headers_enabled=True, app/core/limiter.py)
    # has somewhere to write the X-RateLimit-*/Retry-After headers on a
    # successful (non-429) response; without it slowapi has nothing to inject
    # into and raises internally.
    state = request.app.state
    missing = [attr for attr in _REQUIRED_STATE_ATTRS if getattr(state, attr, None) is None]
    if missing:
        raise HTTPException(
            status_code=503,
            detail=f"ML layer not ready -- missing: {', '.join(missing)}. Check /health.",
        )

    return predict_transaction(
        payload,
        xgb_model=state.xgb_model,
        model_metadata=state.model_metadata,
        explainer=state.shap_explainer,
        isolation_forest=state.isolation_forest,
        db=db,
    )

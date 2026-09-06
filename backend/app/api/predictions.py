"""GET /predictions and GET /predictions/{id} -- read endpoints for scored
predictions, deferred from the persistence phase (see CLAUDE.md, "Known
Limitations" -- "No GET/read endpoint exists yet") until real query
requirements were known: a dashboard feed (paginated list, filterable by
fraud/anomaly outcome) and a single-transaction detail view (full SHAP
explanation, not the top-5 capped list POST /predict returns).

Both endpoints read straight through app.db.session.get_db -- no ML state is
touched here, unlike POST /predict, so there's no 503-if-model-unloaded case
to check for.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.prediction import PredictionDetail, PredictionListResponse
from app.services.prediction_read_service import DEFAULT_LIMIT, MAX_LIMIT, get_prediction_detail, list_predictions

router = APIRouter()


@router.get("/predictions", response_model=PredictionListResponse)
def get_predictions(
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    is_fraud: bool | None = Query(None),
    anomaly_flag: bool | None = Query(None),
    source: str | None = Query(None, description="Filter by transaction source, e.g. 'stripe_test'."),
    db: Session = Depends(get_db),
) -> PredictionListResponse:
    return list_predictions(
        db, limit=limit, offset=offset, is_fraud=is_fraud, anomaly_flag=anomaly_flag, source=source
    )


@router.get("/predictions/{prediction_id}", response_model=PredictionDetail)
def get_prediction(prediction_id: uuid.UUID, db: Session = Depends(get_db)) -> PredictionDetail:
    detail = get_prediction_detail(db, prediction_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"No prediction found with id {prediction_id}")
    return detail

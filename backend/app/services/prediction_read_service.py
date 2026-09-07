"""Query logic behind GET /predictions and GET /predictions/{id}.

Kept out of app/api/predictions.py per this project's services/ convention
("business logic orchestrating db/ml/features" -- see CLAUDE.md
"Architecture"), even though these queries don't touch ml/features -- the
route handlers stay thin either way, mirroring app/api/predict.py's split
against app/services/prediction_service.py.

Pagination: offset/limit, not cursor-based. Chosen because this project's
demo-scale dataset (single-digit requests/sec, no production traffic --
see CLAUDE.md's persistence-phase latency notes) has no need for
cursor-pagination's consistency-under-concurrent-writes benefit, and
offset/limit is simpler to consume from a first dashboard page (jump to a
specific page number, show total count) than an opaque cursor would be.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Prediction, Transaction
from app.schemas.prediction import PredictionDetail, PredictionListItem, PredictionListResponse, ShapContribution

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def _list_item_from_row(transaction: Transaction, prediction: Prediction) -> PredictionListItem:
    return PredictionListItem(
        id=prediction.id,
        created_at=prediction.created_at,
        amount=transaction.amount,
        type=transaction.type.value,
        oldbalanceOrg=transaction.oldbalanceOrg,
        oldbalanceDest=transaction.oldbalanceDest,
        is_merchant_dest=transaction.is_merchant_dest,
        source=transaction.source,
        fraud_probability=prediction.fraud_probability,
        is_fraud=prediction.is_fraud,
        anomaly_flag=prediction.anomaly_flag,
        anomaly_score=prediction.anomaly_score,
        threshold_used=prediction.threshold_used,
        model_version=prediction.model_version,
    )


def list_predictions(
    db: Session,
    *,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    is_fraud: bool | None = None,
    anomaly_flag: bool | None = None,
    source: str | None = None,
) -> PredictionListResponse:
    limit = min(limit, MAX_LIMIT)

    base_query = select(Prediction, Transaction).join(Transaction, Prediction.transaction_id == Transaction.id)
    if is_fraud is not None:
        base_query = base_query.where(Prediction.is_fraud == is_fraud)
    if anomaly_flag is not None:
        base_query = base_query.where(Prediction.anomaly_flag == anomaly_flag)
    if source is not None:
        base_query = base_query.where(Transaction.source == source)

    total = db.scalar(select(func.count()).select_from(base_query.subquery())) or 0

    rows = db.execute(
        base_query.order_by(Prediction.created_at.desc()).limit(limit).offset(offset)
    ).all()

    items = [_list_item_from_row(transaction, prediction) for prediction, transaction in rows]
    return PredictionListResponse(items=items, limit=limit, offset=offset, total=total)


def get_prediction_detail(db: Session, prediction_id: uuid.UUID) -> PredictionDetail | None:
    row = db.execute(
        select(Prediction, Transaction)
        .join(Transaction, Prediction.transaction_id == Transaction.id)
        .where(Prediction.id == prediction_id)
    ).first()
    if row is None:
        return None

    prediction, transaction = row
    list_item = _list_item_from_row(transaction, prediction)
    return PredictionDetail(
        **list_item.model_dump(),
        shap_explanation=[ShapContribution(**c) for c in prediction.shap_explanation],
    )

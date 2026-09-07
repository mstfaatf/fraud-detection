"""Runs a single real-time prediction: preprocessing -> XGBoost score ->
Isolation Forest anomaly score -> SHAP explanation -> response schema ->
persistence.

Reuses ml/src/preprocessing.py's build_features() -- the same function used at
training time -- rather than reimplementing feature engineering here.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

import app.core.config  # noqa: F401 -- side effect: puts ml/src/ on sys.path

from preprocessing import build_features

from app.db.models import Prediction, Transaction, TransactionType as DBTransactionType
from app.schemas.prediction import PredictionResponse, ShapContribution, TransactionInput

TOP_K_SHAP_FEATURES = 5

logger = logging.getLogger(__name__)


def predict_transaction(
    payload: TransactionInput,
    *,
    xgb_model: Any,
    model_metadata: dict,
    explainer: Any,
    isolation_forest: Any,
    db: Session,
    source: str = "paysim_sim",
) -> PredictionResponse:
    raw_df = pd.DataFrame(
        [
            {
                "step": payload.step,
                "type": payload.type.value,
                "amount": payload.amount,
                "oldbalanceOrg": payload.oldbalanceOrg,
                "oldbalanceDest": payload.oldbalanceDest,
                "nameDest": payload.nameDest,
            }
        ]
    )

    X, _y, feature_columns = build_features(raw_df)
    X = X.astype(float)

    fraud_probability = float(xgb_model.predict_proba(X)[:, 1][0])
    threshold = float(model_metadata["threshold"])
    is_fraud = fraud_probability >= threshold

    # ml/models/isolation_forest.pkl was serialized with contamination=0.01
    # baked in (see ml/src/serialize_isolation_forest.py). Previously this
    # called both .predict() and .score_samples() separately, but sklearn's
    # IsolationForest.predict() computes decision_function(X), which is
    # itself just score_samples(X) - offset_ -- so calling both meant paying
    # for score_samples() twice per request (~24ms of the ~33ms measured
    # total /predict latency, per CLAUDE.md's Phase 5 wrap-up breakdown).
    # Calling score_samples() once and replicating predict()'s own
    # `decision_function(X) < 0 => -1` rule directly against offset_ gets the
    # identical flag with the computation done only once.
    raw_score = isolation_forest.score_samples(X)[0]
    anomaly_flag = bool(raw_score - isolation_forest.offset_ < 0)
    # score_samples: lower = more abnormal (sklearn convention) -- flipped
    # here to match "higher = more anomalous", the convention used
    # throughout this project's notebooks.
    anomaly_score = float(-raw_score)

    # shap_values() on a 1-row X returns a (1, n_features) array in the
    # model's log-odds output space (TreeExplainer's default for XGBClassifier).
    # Ranked once, in full: the POST /predict response only surfaces the top 5
    # (see PredictionResponse.shap_explanation), but the full ranked list is
    # persisted below so GET /predictions/{id} can show more than 5 later
    # (per CLAUDE.md's read-endpoint spec) without re-running SHAP.
    shap_row = explainer.shap_values(X)[0]
    ranked_idx = sorted(range(len(shap_row)), key=lambda i: -abs(shap_row[i]))
    full_shap_explanation = [
        ShapContribution(feature=feature_columns[i], shap_value=float(shap_row[i])) for i in ranked_idx
    ]
    shap_explanation = full_shap_explanation[:TOP_K_SHAP_FEATURES]

    response = PredictionResponse(
        fraud_probability=fraud_probability,
        is_fraud=is_fraud,
        threshold_used=threshold,
        anomaly_flag=anomaly_flag,
        anomaly_score=anomaly_score,
        shap_explanation=shap_explanation,
        model_version=str(model_metadata.get("model_version", "unknown")),
    )

    _persist_prediction(db, payload, response, full_shap_explanation, source)

    return response


def _persist_prediction(
    db: Session,
    payload: TransactionInput,
    response: PredictionResponse,
    full_shap_explanation: list[ShapContribution],
    source: str,
) -> None:
    """Writes one `transactions` row + one linked `predictions` row.

    Synchronous, in the request path -- a deliberate choice, not deferred to
    a background task. At this project's demo scale (single-digit
    requests/sec, not production traffic) a local Postgres insert adds a few
    ms next to the ~33ms /predict already takes end-to-end (see CLAUDE.md's
    Phase 5 wrap-up latency table), and a synchronous write means a
    caller's `is_fraud` result and its persisted row are never out of sync
    with each other -- a background task would only start paying for itself
    at a request volume this portfolio project isn't built to demonstrate.

    A DB failure here does not fail the request: the ML result is valid
    regardless of whether it could be persisted, so this logs the failure
    loudly and lets the caller still get their prediction, rather than
    turning a working scorer into a 500 over an unrelated storage problem.
    """
    try:
        transaction = Transaction(
            step=payload.step,
            type=DBTransactionType(payload.type.value),
            amount=payload.amount,
            oldbalanceOrg=payload.oldbalanceOrg,
            oldbalanceDest=payload.oldbalanceDest,
            nameDest=payload.nameDest,
            # Mirrors preprocessing.add_is_merchant_dest's exact rule
            # (nameDest starts with "M") rather than reading it back out of
            # X, which has already been cast to float by this point.
            is_merchant_dest=payload.nameDest.startswith("M"),
            source=source,
        )
        db.add(transaction)
        db.flush()  # assigns transaction.id without committing yet

        prediction = Prediction(
            transaction_id=transaction.id,
            fraud_probability=response.fraud_probability,
            is_fraud=response.is_fraud,
            threshold_used=response.threshold_used,
            anomaly_flag=response.anomaly_flag,
            anomaly_score=response.anomaly_score,
            # Full ranked list, not response.shap_explanation's top-5 -- see
            # the comment at the call site above.
            shap_explanation=[c.model_dump() for c in full_shap_explanation],
            model_version=response.model_version,
        )
        db.add(prediction)
        db.commit()
    except Exception:
        logger.exception("Failed to persist transaction/prediction for /predict request")
        db.rollback()

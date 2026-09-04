"""Runs a single real-time prediction: preprocessing -> XGBoost score ->
Isolation Forest anomaly score -> SHAP explanation -> response schema.

Reuses ml/src/preprocessing.py's build_features() -- the same function used at
training time -- rather than reimplementing feature engineering here.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

import app.core.config  # noqa: F401 -- side effect: puts ml/src/ on sys.path

from preprocessing import build_features

from app.schemas.prediction import PredictionResponse, ShapContribution, TransactionInput

TOP_K_SHAP_FEATURES = 5


def predict_transaction(
    payload: TransactionInput,
    *,
    xgb_model: Any,
    model_metadata: dict,
    explainer: Any,
    isolation_forest: Any,
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
    # baked in (see ml/src/serialize_isolation_forest.py), so .predict()
    # directly reflects that chosen operating threshold: -1 = flagged
    # anomaly, 1 = not. This is a separate signal from fraud_probability --
    # never blended into it (see ISOLATION_FOREST_FINDINGS.md).
    anomaly_flag = bool(isolation_forest.predict(X)[0] == -1)
    # score_samples: lower = more abnormal (sklearn convention) -- flipped
    # here to match "higher = more anomalous", the convention used
    # throughout this project's notebooks.
    anomaly_score = float(-isolation_forest.score_samples(X)[0])

    # shap_values() on a 1-row X returns a (1, n_features) array in the
    # model's log-odds output space (TreeExplainer's default for XGBClassifier).
    shap_row = explainer.shap_values(X)[0]
    top_idx = sorted(range(len(shap_row)), key=lambda i: -abs(shap_row[i]))[:TOP_K_SHAP_FEATURES]
    shap_explanation = [
        ShapContribution(feature=feature_columns[i], shap_value=float(shap_row[i])) for i in top_idx
    ]

    return PredictionResponse(
        fraud_probability=fraud_probability,
        is_fraud=is_fraud,
        threshold_used=threshold,
        anomaly_flag=anomaly_flag,
        anomaly_score=anomaly_score,
        shap_explanation=shap_explanation,
        model_version=str(model_metadata.get("model_version", "unknown")),
    )

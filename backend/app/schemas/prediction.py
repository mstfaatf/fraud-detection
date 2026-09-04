"""Request/response schemas for POST /predict."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class TransactionType(str, Enum):
    CASH_IN = "CASH_IN"
    CASH_OUT = "CASH_OUT"
    DEBIT = "DEBIT"
    PAYMENT = "PAYMENT"
    TRANSFER = "TRANSFER"


class TransactionInput(BaseModel):
    """Raw pre-transaction fields only -- everything a client actually has
    *before* a payment executes.

    Deliberately excludes newbalanceOrig / newbalanceDest: those are
    post-transaction state that doesn't exist yet at real-time decision time
    (see CLAUDE.md, "Feature Schema" -- Excluded, leakage). Accepting them
    here would invite the exact leakage that section rules out.
    """

    step: int = Field(ge=0, description="Hours since simulation start (PaySim's time unit).")
    type: TransactionType
    amount: float = Field(ge=0)
    oldbalanceOrg: float = Field(ge=0, description="Originating account balance before this transaction.")
    oldbalanceDest: float = Field(ge=0, description="Destination account balance before this transaction.")
    nameDest: str = Field(
        min_length=1,
        description="Destination account id. PaySim merchant accounts start with 'M' -- used to derive is_merchant_dest.",
    )


class ShapContribution(BaseModel):
    feature: str
    # SHAP value in the model's log-odds output space (TreeExplainer's default
    # for XGBClassifier) -- positive pushes toward fraud, negative toward
    # legitimate. Not a probability by itself.
    shap_value: float


class PredictionResponse(BaseModel):
    fraud_probability: float
    is_fraud: bool
    threshold_used: float
    # Isolation Forest's anomaly signal -- a separate, secondary flag, never
    # blended into fraud_probability/is_fraud. Per ISOLATION_FOREST_FINDINGS.md,
    # it added zero unique true positives on the evaluation test set, so it must
    # never override or auto-block based on an XGBoost decision.
    anomaly_flag: bool
    anomaly_score: float
    # Top 5 by |shap_value|, not the full feature vector. Interpretation note
    # (see CLAUDE.md, Known Limitations): is_merchant_dest carries 100% of the
    # merchant/type_PAYMENT collinear signal in this model -- type_PAYMENT will
    # essentially always show ~0 and that is not "type doesn't matter here".
    shap_explanation: list[ShapContribution]
    model_version: str

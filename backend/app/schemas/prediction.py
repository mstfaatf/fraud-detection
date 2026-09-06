"""Request/response schemas for POST /predict."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


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

    # Deliberate choice: silently ignore unrecognized fields (pydantic v2's
    # default) rather than reject them (extra="forbid"). A client forwarding
    # a full upstream transaction object may reasonably include
    # newbalanceOrig/newbalanceDest or other fields this API doesn't use --
    # a 422 for that would be needlessly brittle. This is safe specifically
    # because prediction_service.py builds its DataFrame from an explicit,
    # fixed set of named fields (see predict_transaction()), so an ignored
    # extra field can never silently reach preprocessing.build_features().
    model_config = ConfigDict(extra="ignore")

    step: int = Field(ge=0, description="Hours since simulation start (PaySim's time unit).")
    type: TransactionType
    amount: float = Field(ge=0)
    oldbalanceOrg: float = Field(ge=0, description="Originating account balance before this transaction.")
    oldbalanceDest: float = Field(ge=0, description="Destination account balance before this transaction.")
    nameDest: str = Field(
        min_length=1,
        max_length=255,
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


class PredictionListItem(BaseModel):
    """One row of GET /predictions -- a Prediction joined with its
    Transaction, flattened into the fields a dashboard feed actually needs.

    shap_explanation is deliberately omitted here (unlike PredictionDetail):
    a list view renders many rows at once and doesn't need per-row
    explanations, so leaving it out keeps the list payload small. Extends
    the existing PredictionResponse's vocabulary (TransactionType,
    ShapContribution) rather than redefining it.
    """

    id: uuid.UUID
    created_at: datetime

    # Transaction input fields (joined in).
    amount: float
    type: TransactionType
    oldbalanceOrg: float
    oldbalanceDest: float
    is_merchant_dest: bool
    # "paysim_sim" (simulator / POST /predict / Test a Transaction) or
    # "stripe_test" (POST /webhooks/stripe) -- see CLAUDE.md's Phase 9 part 2.
    source: str

    # Prediction output fields.
    fraud_probability: float
    is_fraud: bool
    anomaly_flag: bool
    anomaly_score: float
    threshold_used: float
    model_version: str


class PredictionDetail(PredictionListItem):
    """GET /predictions/{id} -- same joined shape as PredictionListItem, plus
    the full SHAP explanation (not capped at 5 like POST /predict's response
    -- a single-item detail view can afford to show the whole feature vector)."""

    shap_explanation: list[ShapContribution]


class PredictionListResponse(BaseModel):
    items: list[PredictionListItem]
    limit: int
    offset: int
    total: int

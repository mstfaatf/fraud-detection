"""SQLAlchemy ORM models: transactions + predictions.

Two tables, not one, on purpose: `Transaction` is "what was submitted" (the
raw pre-transaction fields a client sent to POST /predict) and `Prediction`
is "what the model said" about it. Keeping them separate keeps the schema
honest about those being genuinely different concerns -- a transaction is a
fact about the world, a prediction is one model's opinion about that fact at
a point in time. It also leaves room for re-scoring (a transaction re-run
through a newer model version, or through XGBoost and some future challenger
model side by side) as an additional `Prediction` row against the same
`Transaction`, without restructuring either table -- the FK is on
`Prediction`, so a transaction can accumulate many predictions but each
prediction points at exactly one transaction.

Wired into POST /predict in app/services/prediction_service.py.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TransactionType(str, enum.Enum):
    """Mirrors app.schemas.prediction.TransactionType's 5 PaySim categories.

    Deliberately redeclared here rather than imported: the db layer
    shouldn't depend on the API schema layer (see CLAUDE.md "Architecture"
    -- schemas/ and db/ are separate modules with separate concerns), even
    though the underlying values are the same fixed PaySim vocabulary.
    """

    CASH_IN = "CASH_IN"
    CASH_OUT = "CASH_OUT"
    DEBIT = "DEBIT"
    PAYMENT = "PAYMENT"
    TRANSFER = "TRANSFER"


class Transaction(Base):
    """Raw submitted input, as received by POST /predict -- nothing derived
    by the model lives here.
    """

    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    step: Mapped[int] = mapped_column(nullable=False)
    type: Mapped[TransactionType] = mapped_column(Enum(TransactionType, name="transaction_type"), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    oldbalanceOrg: Mapped[float] = mapped_column(Float, nullable=False)
    oldbalanceDest: Mapped[float] = mapped_column(Float, nullable=False)
    nameDest: Mapped[str] = mapped_column(String, nullable=False)
    # Derived from nameDest (starts with "M") at write time, per the Phase 1
    # feature schema -- stored rather than recomputed on read so the stored
    # row reflects exactly what preprocessing.build_features() saw.
    is_merchant_dest: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # Where this transaction actually came from -- "paysim_sim" (the
    # simulator, POST /predict / Test a Transaction, anything scored through
    # the PaySim-shaped TransactionInput schema directly) or "stripe_test"
    # (a real Stripe test-mode PaymentIntent, scored via
    # app/api/stripe_webhooks.py + app/services/stripe_adapter.py). A plain
    # string, not a Postgres enum, so a future third source doesn't need a
    # migration to add an enum value. server_default backfills every
    # pre-existing row to "paysim_sim" (see the migration that added this
    # column) -- new rows always pass `source` explicitly at the ORM layer
    # instead of relying on the server default.
    source: Mapped[str] = mapped_column(String, nullable=False, server_default="paysim_sim")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    predictions: Mapped[list["Prediction"]] = relationship(back_populates="transaction")


class Prediction(Base):
    """One model's scoring output for one transaction.

    A transaction can have more than one prediction over time (re-scoring
    against a newer model_version) -- transaction_id is a plain FK, not a
    one-to-one/unique constraint, specifically to allow that.
    """

    __tablename__ = "predictions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=False, index=True
    )

    fraud_probability: Mapped[float] = mapped_column(Float, nullable=False)
    is_fraud: Mapped[bool] = mapped_column(Boolean, nullable=False)
    threshold_used: Mapped[float] = mapped_column(Float, nullable=False)
    # Isolation Forest's anomaly signal -- stored as a separate pair of
    # columns, never folded into fraud_probability/is_fraud. Per
    # ISOLATION_FOREST_FINDINGS.md / CLAUDE.md, it must stay a distinct,
    # clearly-labeled secondary signal, including at rest in the db.
    anomaly_flag: Mapped[bool] = mapped_column(Boolean, nullable=False)
    anomaly_score: Mapped[float] = mapped_column(Float, nullable=False)
    # Top-5-by-|shap_value| list of {feature, shap_value} objects, matching
    # PredictionResponse.shap_explanation -- stored as JSONB (not a normalized
    # per-feature table) since it's read back as a unit, never queried/filtered
    # by individual feature server-side.
    shap_explanation: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    model_version: Mapped[str] = mapped_column(String, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    transaction: Mapped["Transaction"] = relationship(back_populates="predictions")

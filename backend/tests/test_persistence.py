"""Verifies POST /predict actually persists a transactions row + a linked
predictions row, against the real local Docker Postgres database (see
SETUP.md -- `docker compose up -d postgres` must be running for this test).

No GET/read endpoint exists yet (deliberately deferred until the frontend
dashboard phase defines what it actually needs to query), so this test reads
the database directly via a plain SQLAlchemy session instead of going through
the API.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db.models import Prediction, Transaction  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402

# Distinct from every payload used in test_predict.py so this test's DB
# lookup can't accidentally match a row some other test inserted.
PERSISTENCE_TEST_PAYLOAD = {
    "step": 42,
    "type": "TRANSFER",
    "amount": 73301.5,
    "oldbalanceOrg": 73301.5,
    "oldbalanceDest": 0.0,
    "nameDest": "C_PERSISTENCE_TEST_9182736",
}


def test_predict_persists_transaction_and_linked_prediction():
    with TestClient(app) as client:
        response = client.post("/predict", json=PERSISTENCE_TEST_PAYLOAD)
    assert response.status_code == 200
    data = response.json()

    db = SessionLocal()
    transaction = None
    prediction = None
    try:
        transaction = (
            db.query(Transaction)
            .filter(Transaction.nameDest == PERSISTENCE_TEST_PAYLOAD["nameDest"])
            .order_by(Transaction.created_at.desc())
            .first()
        )
        assert transaction is not None, "no transactions row was written for this request"
        assert transaction.step == PERSISTENCE_TEST_PAYLOAD["step"]
        assert transaction.type.value == PERSISTENCE_TEST_PAYLOAD["type"]
        assert transaction.amount == PERSISTENCE_TEST_PAYLOAD["amount"]
        assert transaction.oldbalanceOrg == PERSISTENCE_TEST_PAYLOAD["oldbalanceOrg"]
        assert transaction.oldbalanceDest == PERSISTENCE_TEST_PAYLOAD["oldbalanceDest"]
        assert transaction.nameDest == PERSISTENCE_TEST_PAYLOAD["nameDest"]
        # "C..." prefix -- not a merchant account.
        assert transaction.is_merchant_dest is False

        prediction = db.query(Prediction).filter(Prediction.transaction_id == transaction.id).one_or_none()
        assert prediction is not None, "no predictions row was written/linked for this transaction"
        assert prediction.fraud_probability == pytest.approx(data["fraud_probability"], abs=1e-9)
        assert prediction.is_fraud == data["is_fraud"]
        assert prediction.threshold_used == pytest.approx(data["threshold_used"], abs=1e-9)
        assert prediction.anomaly_flag == data["anomaly_flag"]
        assert prediction.anomaly_score == pytest.approx(data["anomaly_score"], abs=1e-9)
        assert prediction.model_version == data["model_version"]
        # The persisted row stores the *full* ranked SHAP list (so
        # GET /predictions/{id} can show more than 5 -- see
        # prediction_service.py), while the API response caps at 5. The
        # stored list's first 5 entries must still match the response
        # exactly, since both are the same ranking just truncated differently.
        stored_features = [c["feature"] for c in prediction.shap_explanation]
        response_features = [c["feature"] for c in data["shap_explanation"]]
        assert len(stored_features) >= len(response_features)
        assert stored_features[: len(response_features)] == response_features
    finally:
        # Keep the local dev DB from accumulating test rows across runs.
        if prediction is not None:
            db.delete(prediction)
        if transaction is not None:
            db.delete(transaction)
        db.commit()
        db.close()

"""Tests for POST /predict -- starts the real app (via TestClient) so the
lifespan handler actually loads the XGBoost model, SHAP explainer, and
Isolation Forest model, then exercises the endpoint against real payloads."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

# A small PAYMENT to a merchant, with a healthy origin balance -- nothing
# about this resembles PaySim's account-draining fraud pattern.
LEGIT_PAYLOAD = {
    "step": 10,
    "type": "PAYMENT",
    "amount": 150.75,
    "oldbalanceOrg": 25000.0,
    "oldbalanceDest": 0.0,
    "nameDest": "M998877665",
}

# Account-draining CASH_OUT (amount == oldbalanceOrg) to an empty-balance
# destination -- PaySim's core fraud signature per EDA_FINDINGS.md.
FRAUD_PAYLOAD = {
    "step": 12,
    "type": "CASH_OUT",
    "amount": 181000.0,
    "oldbalanceOrg": 181000.0,
    "oldbalanceDest": 0.0,
    "nameDest": "C1900366749",
}

# The exact false-negative example from ml/notebooks/06_shap_explainability.ipynb /
# SHAP_FINDINGS.md (test_df row 61953, step=611): real fraud (isFraud=1) with the
# same draining signature as a true positive, but the destination account already
# holds a large balance (~905K) rather than PaySim's typical empty drop account --
# enough to pull the model's confidence (documented proba=0.522544) just under the
# chosen threshold (~0.6145). Reproduced here bit-for-bit (verified against the
# notebook's raw row) as a regression check that preprocessing/scoring hasn't
# drifted between the notebook and the backend.
FALSE_NEGATIVE_PAYLOAD = {
    "step": 611,
    "type": "CASH_OUT",
    "amount": 40873.25,
    "oldbalanceOrg": 40873.25,
    "oldbalanceDest": 905220.62,
    "nameDest": "C2011653330",
}
FALSE_NEGATIVE_DOCUMENTED_PROBA = 0.522544


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def assert_valid_prediction_response(data: dict) -> None:
    """Shared schema assertions -- shape/types every /predict response must satisfy,
    independent of the actual fraud outcome."""
    assert isinstance(data["fraud_probability"], float)
    assert 0.0 <= data["fraud_probability"] <= 1.0
    assert isinstance(data["is_fraud"], bool)
    assert isinstance(data["threshold_used"], float)
    assert isinstance(data["anomaly_flag"], bool)
    assert isinstance(data["anomaly_score"], float)
    assert isinstance(data["model_version"], str) and data["model_version"]

    shap_explanation = data["shap_explanation"]
    assert isinstance(shap_explanation, list)
    assert 1 <= len(shap_explanation) <= 5
    for contribution in shap_explanation:
        assert isinstance(contribution["feature"], str) and contribution["feature"]
        assert isinstance(contribution["shap_value"], float)


def test_legit_payload_predicts_not_fraud(client):
    response = client.post("/predict", json=LEGIT_PAYLOAD)

    assert response.status_code == 200
    data = response.json()
    assert_valid_prediction_response(data)
    assert data["is_fraud"] is False
    assert data["fraud_probability"] < data["threshold_used"]


def test_fraud_shaped_payload_predicts_fraud(client):
    response = client.post("/predict", json=FRAUD_PAYLOAD)

    assert response.status_code == 200
    data = response.json()
    assert_valid_prediction_response(data)
    assert data["is_fraud"] is True
    assert data["fraud_probability"] > data["threshold_used"]


@pytest.mark.parametrize(
    "bad_payload",
    [
        pytest.param(
            {k: v for k, v in LEGIT_PAYLOAD.items() if k != "nameDest"},
            id="missing_required_field",
        ),
        pytest.param({**LEGIT_PAYLOAD, "type": "NOT_A_PAYSIM_TYPE"}, id="invalid_type_value"),
        pytest.param({**LEGIT_PAYLOAD, "amount": -100.0}, id="negative_amount"),
    ],
)
def test_malformed_payload_returns_422(client, bad_payload):
    response = client.post("/predict", json=bad_payload)

    assert response.status_code == 422


def test_post_transaction_leakage_fields_are_silently_ignored(client):
    """newbalanceOrig/newbalanceDest don't exist at real-time decision time
    (see CLAUDE.md, "Feature Schema" -- Excluded, leakage) and aren't part of
    TransactionInput at all. Confirms the deliberately-chosen extra="ignore"
    behavior (see schemas/prediction.py): a client that includes them anyway
    doesn't get a 422, and -- more importantly -- the values have zero effect
    on the prediction, confirming they never reach preprocessing."""
    payload_with_leakage_fields = {
        **FRAUD_PAYLOAD,
        "newbalanceOrig": 0.0,
        "newbalanceDest": 999999999.0,
    }

    baseline_response = client.post("/predict", json=FRAUD_PAYLOAD)
    response = client.post("/predict", json=payload_with_leakage_fields)

    assert response.status_code == 200
    assert response.json() == baseline_response.json()


def test_anomaly_fields_present_for_legit_and_fraud_payloads(client):
    for payload in (LEGIT_PAYLOAD, FRAUD_PAYLOAD):
        data = client.post("/predict", json=payload).json()
        assert isinstance(data["anomaly_flag"], bool)
        assert isinstance(data["anomaly_score"], float)


def test_shap_explanation_capped_at_five_features(client):
    # This model has 12 feature columns, so the top-5 cap is actually exercised.
    for payload in (LEGIT_PAYLOAD, FRAUD_PAYLOAD):
        data = client.post("/predict", json=payload).json()
        assert len(data["shap_explanation"]) == 5


def test_known_false_negative_example_reproduced(client):
    response = client.post("/predict", json=FALSE_NEGATIVE_PAYLOAD)

    assert response.status_code == 200
    data = response.json()
    assert_valid_prediction_response(data)

    # Below threshold -- the model misses this one, exactly as documented.
    assert data["is_fraud"] is False
    assert data["fraud_probability"] == pytest.approx(FALSE_NEGATIVE_DOCUMENTED_PROBA, abs=1e-4)
    # But still clearly fraud-shaped, not a low/ambiguous score -- confirms this
    # is the documented "pulled just under threshold" case, not a different one.
    assert data["fraud_probability"] > 0.4


def test_ml_layer_not_ready_returns_503(client):
    # `app` is a module-level singleton, so app.state survives across
    # TestClient instances within the same process -- a second, never-started
    # TestClient would still see the first one's already-loaded state. To
    # actually simulate a broken ML layer, temporarily remove the state
    # attributes predict.py checks for, then restore them.
    state_attrs = ("xgb_model", "model_metadata", "shap_explainer", "isolation_forest")
    saved = {attr: getattr(app.state, attr) for attr in state_attrs}
    try:
        for attr in state_attrs:
            delattr(app.state, attr)

        response = client.post("/predict", json=LEGIT_PAYLOAD)

        assert response.status_code == 503
    finally:
        for attr, value in saved.items():
            setattr(app.state, attr, value)

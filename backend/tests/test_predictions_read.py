"""Tests for GET /predictions and GET /predictions/{id} -- the read
endpoints deferred from the persistence phase (see CLAUDE.md, "Known
Limitations" -- "No GET/read endpoint exists yet") until real query
requirements (a dashboard feed + a detail view) were known.

Seeds its own rows through the real POST /predict path (so they're realistic,
not hand-inserted) rather than assuming the shared local dev Postgres
database starts empty -- other test modules (test_predict.py,
test_persistence.py) also write to it. Looks the seeded rows up directly via
SessionLocal, same pattern as test_persistence.py, and cleans them up in a
finally block so repeated local runs don't accumulate data.
"""

import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db.models import Prediction, Transaction  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402

# Distinct amounts/nameDest from every payload used elsewhere in the suite,
# so seeded rows can be picked out of a shared list response unambiguously.
READ_TEST_LEGIT_PAYLOAD = {
    "step": 20,
    "type": "PAYMENT",
    "amount": 42.5,
    "oldbalanceOrg": 5000.0,
    "oldbalanceDest": 0.0,
    "nameDest": "M_READ_TEST_LEGIT_1122",
}

READ_TEST_FRAUD_PAYLOAD = {
    "step": 21,
    "type": "CASH_OUT",
    "amount": 250000.0,
    "oldbalanceOrg": 250000.0,
    "oldbalanceDest": 0.0,
    "nameDest": "C_READ_TEST_FRAUD_3344",
}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def seeded(client):
    legit_resp = client.post("/predict", json=READ_TEST_LEGIT_PAYLOAD)
    fraud_resp = client.post("/predict", json=READ_TEST_FRAUD_PAYLOAD)
    assert legit_resp.status_code == 200
    assert fraud_resp.status_code == 200

    db = SessionLocal()
    legit_txn = fraud_txn = legit_pred = fraud_pred = None
    try:
        legit_txn = (
            db.query(Transaction)
            .filter(Transaction.nameDest == READ_TEST_LEGIT_PAYLOAD["nameDest"])
            .order_by(Transaction.created_at.desc())
            .first()
        )
        fraud_txn = (
            db.query(Transaction)
            .filter(Transaction.nameDest == READ_TEST_FRAUD_PAYLOAD["nameDest"])
            .order_by(Transaction.created_at.desc())
            .first()
        )
        assert legit_txn is not None and fraud_txn is not None
        legit_pred = db.query(Prediction).filter(Prediction.transaction_id == legit_txn.id).one()
        fraud_pred = db.query(Prediction).filter(Prediction.transaction_id == fraud_txn.id).one()

        yield {
            "legit": {"id": str(legit_pred.id), "response": legit_resp.json()},
            "fraud": {"id": str(fraud_pred.id), "response": fraud_resp.json()},
        }
    finally:
        for pred in (legit_pred, fraud_pred):
            if pred is not None:
                db.delete(pred)
        for txn in (legit_txn, fraud_txn):
            if txn is not None:
                db.delete(txn)
        db.commit()
        db.close()


def test_list_includes_seeded_rows_with_joined_shape(client, seeded):
    response = client.get("/predictions", params={"limit": 200})

    assert response.status_code == 200
    data = response.json()
    assert set(data.keys()) == {"items", "limit", "offset", "total"}
    assert data["limit"] == 200
    assert data["offset"] == 0
    assert data["total"] >= 2

    by_id = {item["id"]: item for item in data["items"]}
    legit_item = by_id[seeded["legit"]["id"]]
    fraud_item = by_id[seeded["fraud"]["id"]]

    # Joined transaction fields.
    assert legit_item["amount"] == READ_TEST_LEGIT_PAYLOAD["amount"]
    assert legit_item["type"] == READ_TEST_LEGIT_PAYLOAD["type"]
    assert legit_item["oldbalanceOrg"] == READ_TEST_LEGIT_PAYLOAD["oldbalanceOrg"]
    assert legit_item["oldbalanceDest"] == READ_TEST_LEGIT_PAYLOAD["oldbalanceDest"]
    assert legit_item["is_merchant_dest"] is True  # nameDest starts with "M"
    # Everything scored through POST /predict is "paysim_sim" -- see
    # CLAUDE.md's Phase 9 part 2 ("source" column / stripe_test).
    assert legit_item["source"] == "paysim_sim"

    # Prediction fields, matching the POST /predict response for the same row.
    assert fraud_item["fraud_probability"] == pytest.approx(
        seeded["fraud"]["response"]["fraud_probability"], abs=1e-9
    )
    assert fraud_item["is_fraud"] == seeded["fraud"]["response"]["is_fraud"]
    assert fraud_item["anomaly_flag"] == seeded["fraud"]["response"]["anomaly_flag"]
    assert fraud_item["threshold_used"] == pytest.approx(seeded["fraud"]["response"]["threshold_used"], abs=1e-9)
    assert fraud_item["model_version"] == seeded["fraud"]["response"]["model_version"]
    assert "created_at" in fraud_item

    # List items never carry shap_explanation -- that's detail-only.
    assert "shap_explanation" not in legit_item


def test_list_is_sorted_by_created_at_desc(client, seeded):
    response = client.get("/predictions", params={"limit": 200})
    items = response.json()["items"]

    created_ats = [item["created_at"] for item in items]
    assert created_ats == sorted(created_ats, reverse=True)


def test_list_respects_is_fraud_filter(client, seeded):
    response = client.get("/predictions", params={"is_fraud": True, "limit": 200})

    assert response.status_code == 200
    data = response.json()
    ids = {item["id"] for item in data["items"]}
    assert seeded["fraud"]["id"] in ids
    assert seeded["legit"]["id"] not in ids
    assert all(item["is_fraud"] is True for item in data["items"])


def test_list_respects_anomaly_flag_filter(client, seeded):
    target_flag = seeded["fraud"]["response"]["anomaly_flag"]

    response = client.get("/predictions", params={"anomaly_flag": target_flag, "limit": 200})

    assert response.status_code == 200
    data = response.json()
    assert seeded["fraud"]["id"] in {item["id"] for item in data["items"]}
    assert all(item["anomaly_flag"] == target_flag for item in data["items"])


def test_list_respects_source_filter(client, seeded):
    response = client.get("/predictions", params={"source": "paysim_sim", "limit": 200})

    assert response.status_code == 200
    data = response.json()
    ids = {item["id"] for item in data["items"]}
    assert seeded["legit"]["id"] in ids
    assert seeded["fraud"]["id"] in ids
    assert all(item["source"] == "paysim_sim" for item in data["items"])

    no_match = client.get("/predictions", params={"source": "stripe_test", "limit": 200}).json()
    assert seeded["legit"]["id"] not in {item["id"] for item in no_match["items"]}


def test_list_pagination_limit_and_offset(client, seeded):
    page_1 = client.get("/predictions", params={"limit": 1, "offset": 0}).json()
    page_2 = client.get("/predictions", params={"limit": 1, "offset": 1}).json()

    assert len(page_1["items"]) == 1
    assert len(page_2["items"]) == 1
    assert page_1["items"][0]["id"] != page_2["items"][0]["id"]
    assert page_1["total"] == page_2["total"]


def test_list_is_empty_safe_past_the_last_page(client, seeded):
    # An offset guaranteed to be past the end of the table, regardless of how
    # many rows other tests/runs have left behind -- exercises the
    # zero-matching-rows path without requiring a truly empty table.
    response = client.get("/predictions", params={"offset": 10_000_000})

    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert isinstance(data["total"], int)


def test_get_prediction_detail_includes_full_shap_explanation(client, seeded):
    response = client.get(f"/predictions/{seeded['legit']['id']}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == seeded["legit"]["id"]
    assert data["amount"] == READ_TEST_LEGIT_PAYLOAD["amount"]

    predict_shap = seeded["legit"]["response"]["shap_explanation"]
    detail_shap = data["shap_explanation"]
    # Detail is not capped at 5 like POST /predict's response -- this model
    # has more than 5 feature columns, so the full list must be longer.
    assert len(detail_shap) > len(predict_shap) == 5
    # Same ranking underneath both -- the detail's top 5 must match
    # POST /predict's response exactly, just not truncated after that.
    assert [c["feature"] for c in detail_shap[:5]] == [c["feature"] for c in predict_shap]


def test_get_prediction_detail_404_for_nonexistent_id(client):
    response = client.get(f"/predictions/{uuid.uuid4()}")

    assert response.status_code == 404
